"""Stores and searches transcript chunk embeddings for each ingested video.

In-memory only - nothing is written to disk. Ingested videos live for as
long as the server process keeps running; restart it and you start over.
This is a deliberate privacy/simplicity choice for a personal weekend
project: no transcripts or questions linger on disk between runs.

No vector database either: at a few hundred chunks per video, a plain
linear scan (compare the question's vector against every chunk vector)
takes single-digit milliseconds, and writing it by hand keeps the "vector
search" step visible instead of hidden inside a library.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from .chunking import Chunk


@dataclass
class _VideoEntry:
    title: Optional[str]
    chunks: list[Chunk]
    embeddings: np.ndarray
    ingested_at: str


_videos: dict[str, _VideoEntry] = {}

# Caps how many videos accumulate in RAM at once. There's no disk backing
# (see module docstring), so without a cap this would grow for as long as
# the process stays up - a real risk on a small, memory-limited host if a
# few people each ingest a different video in the same running instance.
_MAX_VIDEOS = 5


def video_exists(video_id: str) -> bool:
    return video_id in _videos


def save_video(
    video_id: str, title: Optional[str], chunks: list[Chunk], embeddings: np.ndarray
) -> None:
    if video_id not in _videos and len(_videos) >= _MAX_VIDEOS:
        oldest_id = next(iter(_videos))
        del _videos[oldest_id]

    _videos[video_id] = _VideoEntry(
        title=title,
        chunks=chunks,
        embeddings=embeddings,
        ingested_at=datetime.now(timezone.utc).isoformat(),
    )


def load_video(video_id: str) -> Optional[tuple[list[Chunk], np.ndarray]]:
    entry = _videos.get(video_id)
    if entry is None:
        return None
    return entry.chunks, entry.embeddings


def list_videos() -> list[dict]:
    return [
        {
            "video_id": video_id,
            "title": entry.title,
            "num_chunks": len(entry.chunks),
            "ingested_at": entry.ingested_at,
        }
        for video_id, entry in _videos.items()
    ]


def top_k_search(
    embeddings: np.ndarray, chunks: list[Chunk], query_vec: np.ndarray, k: int = 5
) -> list[tuple[Chunk, float]]:
    """The actual vector search. Every embedding is a unit vector (see
    embeddings.py), so cosine similarity between the question and each chunk
    is just their dot product - one matrix multiply scores every chunk at
    once, then we take the top k."""
    scores = embeddings @ query_vec
    top_idx = np.argsort(scores)[::-1][:k]
    return [(chunks[i], float(scores[i])) for i in top_idx]


if __name__ == "__main__":
    # Smoke test: python -m backend.vectorstore
    from .chunking import chunk_transcript
    from .embeddings import embed_query, embed_texts
    from .youtube_ingest import extract_video_id, fetch_transcript

    vid = extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    segments, _lang, title = fetch_transcript(vid)
    chunks = chunk_transcript(segments, vid)
    vectors = embed_texts([c.text for c in chunks])

    save_video(vid, title, chunks, vectors)
    print(f"saved {len(chunks)} chunks for {vid} (in-memory)")

    loaded_chunks, loaded_vectors = load_video(vid)
    print(f"loaded {len(loaded_chunks)} chunks, embeddings shape {loaded_vectors.shape}")

    query_vec = embed_query("never gonna give you up")
    results = top_k_search(loaded_vectors, loaded_chunks, query_vec, k=2)
    for chunk, score in results:
        print(f"score={score:.3f} [{chunk.start_label}] {chunk.text[:60]}...")

    print("videos:", list_videos())
