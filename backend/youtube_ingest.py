"""Turns a YouTube URL into a timestamped transcript.

Two jobs:
1. extract_video_id() - pull the 11-character video ID out of whatever URL
   format the user pastes in.
2. fetch_transcript() - download the transcript via youtube-transcript-api
   and return it as a list of TranscriptSegment (text + start time + duration),
   so downstream code (chunking.py) can keep timestamps attached to the text.
"""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, parse_qs

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)


class InvalidVideoUrlError(Exception):
    """Raised when we can't find a video ID in what the user gave us."""


class TranscriptUnavailableError(Exception):
    """Raised when YouTube has no usable transcript for this video.

    `reason` is one of: "disabled", "no_captions", "unavailable_video", "unknown".
    The API layer (main.py) maps this to a friendly HTTP error for the user.
    """

    def __init__(self, video_id: str, reason: str, message: str):
        self.video_id = video_id
        self.reason = reason
        super().__init__(message)


@dataclass
class TranscriptSegment:
    text: str
    start: float
    duration: float


_VIDEO_ID_RE = re.compile(r"^[0-9A-Za-z_-]{11}$")


def extract_video_id(url_or_id: str) -> str:
    """Accepts a full YouTube URL (any common format) or a bare video ID."""
    candidate = url_or_id.strip()

    if _VIDEO_ID_RE.match(candidate):
        return candidate

    parsed = urlparse(candidate)
    host = parsed.hostname or ""

    if host in ("youtu.be", "www.youtu.be"):
        video_id = parsed.path.lstrip("/")
        if _VIDEO_ID_RE.match(video_id):
            return video_id

    if "youtube.com" in host:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
            if video_id and _VIDEO_ID_RE.match(video_id):
                return video_id
        for prefix in ("/embed/", "/shorts/", "/live/"):
            if parsed.path.startswith(prefix):
                video_id = parsed.path[len(prefix):].split("/")[0]
                if _VIDEO_ID_RE.match(video_id):
                    return video_id

    raise InvalidVideoUrlError(f"Could not find a YouTube video ID in: {url_or_id!r}")


def fetch_transcript(
    video_id: str, languages: Optional[list[str]] = None
) -> tuple[list[TranscriptSegment], str]:
    """Returns (segments, language_code_actually_used).

    Tries the preferred languages first (default English). If none of those
    are available, falls back to whatever transcript YouTube does have
    (e.g. auto-generated captions in another language) rather than failing
    outright.
    """
    languages = languages or ["en"]
    ytt_api = YouTubeTranscriptApi()

    try:
        fetched = ytt_api.fetch(video_id, languages=languages)
    except NoTranscriptFound:
        try:
            transcript_list = ytt_api.list(video_id)
            first_available = next(iter(transcript_list))
            fetched = first_available.fetch()
        except StopIteration:
            raise TranscriptUnavailableError(
                video_id, "no_captions", "No captions are available for this video."
            )
        except TranscriptsDisabled:
            raise TranscriptUnavailableError(
                video_id, "disabled", "Captions are disabled for this video."
            )
        except CouldNotRetrieveTranscript as e:
            raise TranscriptUnavailableError(video_id, "unknown", str(e))
    except TranscriptsDisabled:
        raise TranscriptUnavailableError(
            video_id, "disabled", "Captions are disabled for this video."
        )
    except VideoUnavailable:
        raise TranscriptUnavailableError(
            video_id, "unavailable_video", "This video is unavailable."
        )
    except CouldNotRetrieveTranscript as e:
        raise TranscriptUnavailableError(video_id, "unknown", str(e))

    segments = [
        TranscriptSegment(text=s.text, start=s.start, duration=s.duration)
        for s in fetched
    ]
    return segments, fetched.language_code


def fetch_video_title(video_id: str) -> Optional[str]:
    """Best-effort video title via YouTube's public oEmbed endpoint (no API key).
    Returns None on any failure - ingestion should still work without a title.
    """
    try:
        resp = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json().get("title")
    except Exception:
        return None


if __name__ == "__main__":
    # Smoke test: python -m backend.youtube_ingest
    for test_url in [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # has captions
        "https://youtu.be/dQw4w9WgXcQ?t=30",
    ]:
        vid = extract_video_id(test_url)
        print(f"{test_url} -> video_id={vid}")

    vid = extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    segments, lang = fetch_transcript(vid)
    print(f"language={lang}, segments={len(segments)}")
    for s in segments[:3]:
        print(" ", s)
    print("title:", fetch_video_title(vid))
