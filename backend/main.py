"""FastAPI app: wires the ingestion pipeline and the RAG pipeline to HTTP
endpoints, and serves the frontend.
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from . import config, vectorstore
from .chunking import chunk_transcript
from .embeddings import embed_texts, get_embedder
from .models import (
    AskRequest,
    AskResponse,
    IngestRequest,
    IngestResponse,
    SourceResponse,
    VideoSummary,
)
from .rag import VideoNotIngestedError, answer_question
from .youtube_ingest import (
    InvalidVideoUrlError,
    TranscriptUnavailableError,
    extract_video_id,
    fetch_transcript,
)


def _resource_path(relative: str) -> str:
    """Resolves a path relative to the project root - or, when running
    inside a PyInstaller-bundled exe, relative to the bundle's data
    directory (sys._MEIPASS), since bundled data isn't at the same
    relative path as it is when running from source."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return str(base / relative)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Preload the embedding model once at startup instead of on the first
    # request - loading it takes a few seconds.
    get_embedder()
    yield


app = FastAPI(title="YouTube RAG Chatbot", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/videos", response_model=list[VideoSummary])
def list_videos():
    return vectorstore.list_videos()


@app.post("/api/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest):
    try:
        video_id = extract_video_id(req.youtube_url)
    except InvalidVideoUrlError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if vectorstore.video_exists(video_id):
        existing = next(
            (v for v in vectorstore.list_videos() if v["video_id"] == video_id), None
        )
        if existing:
            return IngestResponse(
                video_id=video_id,
                title=existing["title"],
                num_chunks=existing["num_chunks"],
            )

    try:
        segments, _language, title = fetch_transcript(video_id)
    except TranscriptUnavailableError as e:
        raise HTTPException(status_code=422, detail=str(e))

    chunks = chunk_transcript(
        segments,
        video_id,
        max_words=config.CHUNK_MAX_WORDS,
        overlap_words=config.CHUNK_OVERLAP_WORDS,
    )
    embeddings = embed_texts([c.text for c in chunks])
    vectorstore.save_video(video_id, title, chunks, embeddings)

    return IngestResponse(video_id=video_id, title=title, num_chunks=len(chunks))


@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest):
    try:
        result = answer_question(req.video_id, req.question, top_k=config.TOP_K)
    except VideoNotIngestedError:
        raise HTTPException(status_code=404, detail="This video hasn't been ingested yet.")
    except Exception as e:
        # Covers Gemini API errors (bad key, rate limit, etc.)
        raise HTTPException(status_code=502, detail=f"Failed to generate an answer: {e}")

    return AskResponse(
        answer=result.answer,
        sources=[
            SourceResponse(start_label=s.start_label, text_snippet=s.text_snippet, score=s.score)
            for s in result.sources
        ],
    )


# Must be registered after the /api/* routes above - a root static mount
# would otherwise intercept every path, including API routes.
app.mount("/", StaticFiles(directory=_resource_path("frontend"), html=True), name="frontend")
