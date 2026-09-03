"""Retrieval-augmented generation: find relevant transcript chunks for a
question, then ask Gemini to answer using only those chunks.
"""

from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import types

from . import config, vectorstore
from .chunking import Chunk
from .embeddings import embed_query

SYSTEM_PROMPT = """You are a helpful assistant that answers questions about a specific YouTube video or podcast, using only the transcript excerpts provided to you.

Rules:
- Answer only using the information in the provided excerpts.
- When you reference something specific, cite its approximate timestamp in [mm:ss] format, copied from the excerpt it came from.
- If the excerpts don't contain the answer, say so plainly instead of guessing or using outside knowledge.
- Be concise and conversational."""

_client: Optional[genai.Client] = None


class VideoNotIngestedError(Exception):
    pass


@dataclass
class Source:
    start_label: str
    text_snippet: str
    score: float


@dataclass
class AnswerResult:
    answer: str
    sources: list[Source]


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _get_video_data(video_id: str):
    data = vectorstore.load_video(video_id)
    if data is None:
        raise VideoNotIngestedError(video_id)
    return data


def _build_context_block(chunks: list[Chunk]) -> str:
    # Chronological order, not similarity-rank order, so Gemini reads a
    # coherent narrative instead of shuffled fragments.
    ordered = sorted(chunks, key=lambda c: c.start_time)
    return "\n\n".join(f"[{c.start_label}] {c.text}" for c in ordered)


def answer_question(video_id: str, question: str, top_k: Optional[int] = None) -> AnswerResult:
    top_k = top_k or config.TOP_K
    chunks, embeddings = _get_video_data(video_id)

    query_vec = embed_query(question)
    matches = vectorstore.top_k_search(embeddings, chunks, query_vec, k=top_k)

    context_block = _build_context_block([chunk for chunk, _ in matches])
    user_content = f"Transcript excerpts:\n\n{context_block}\n\nQuestion: {question}"

    client = _get_client()
    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=1024,
        ),
    )
    answer_text = response.text

    sources = [
        Source(start_label=chunk.start_label, text_snippet=chunk.text[:120], score=score)
        for chunk, score in matches
    ]
    return AnswerResult(answer=answer_text, sources=sources)


if __name__ == "__main__":
    # Smoke test: python -m backend.rag
    # Requires GEMINI_API_KEY in .env, and the video already ingested
    # (run `python -m backend.vectorstore` first if you haven't).
    result = answer_question("dQw4w9WgXcQ", "What is the singer promising in this song?")
    print("ANSWER:", result.answer)
    print("\nSOURCES:")
    for s in result.sources:
        print(f"  [{s.start_label}] score={s.score:.3f} {s.text_snippet}")
