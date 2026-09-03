"""Pydantic schemas for request/response bodies.

FastAPI uses these to validate incoming JSON and to auto-generate the
OpenAPI docs at /docs.
"""

from typing import Optional

from pydantic import BaseModel


class IngestRequest(BaseModel):
    youtube_url: str


class IngestResponse(BaseModel):
    video_id: str
    title: Optional[str]
    num_chunks: int


class AskRequest(BaseModel):
    video_id: str
    question: str


class SourceResponse(BaseModel):
    start_label: str
    text_snippet: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceResponse]


class VideoSummary(BaseModel):
    video_id: str
    title: Optional[str]
    num_chunks: int
    ingested_at: str
