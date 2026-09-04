"""Turns a YouTube URL into a timestamped transcript.

Uses yt-dlp rather than youtube-transcript-api. Both scrape the same
YouTube endpoints and both can get IP-blocked when running from a cloud
host's datacenter IP - but yt-dlp is far more actively maintained
specifically to keep up with YouTube's anti-scraping changes, so it's the
more resilient choice for a publicly deployed instance.

Two jobs:
1. extract_video_id() - pull the 11-character video ID out of whatever URL
   format the user pastes in.
2. fetch_transcript() - ask yt-dlp for the video's caption tracks (without
   downloading the video itself) and parse the timed caption data into a
   list of TranscriptSegment (text + start time + duration), so downstream
   code (chunking.py) can keep timestamps attached to the text. Also
   returns the video title, read from the same yt-dlp response - no
   separate network call needed.
"""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, parse_qs

import requests
import yt_dlp

try:
    from yt_dlp.utils import DownloadError
except ImportError:  # pragma: no cover - defensive, matches installed yt-dlp
    DownloadError = Exception


class InvalidVideoUrlError(Exception):
    """Raised when we can't find a video ID in what the user gave us."""


class TranscriptUnavailableError(Exception):
    """Raised when YouTube has no usable transcript for this video.

    `reason` is one of: "no_captions", "unavailable_video", "unknown".
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


def _pick_track(
    manual: dict, auto: dict, languages: list[str]
) -> tuple[Optional[str], Optional[list[dict]]]:
    """Prefer human-written captions over auto-generated ones, and the
    requested languages over whatever else is available."""
    for lang in languages:
        if lang in manual:
            return lang, manual[lang]
    for lang in languages:
        if lang in auto:
            return lang, auto[lang]
    if manual:
        lang = next(iter(manual))
        return lang, manual[lang]
    if auto:
        lang = next(iter(auto))
        return lang, auto[lang]
    return None, None


def _parse_json3(data: dict) -> list[TranscriptSegment]:
    """Parses YouTube's json3 caption format into TranscriptSegments.

    Each "event" is a caption cue: {tStartMs, dDurationMs, segs: [{utf8: text}, ...]}.
    Some events carry no text at all (pure styling/positioning) or are
    newline-only continuation markers - both are skipped.
    """
    segments = []
    for event in data.get("events", []):
        segs = event.get("segs")
        if not segs:
            continue
        text = "".join(seg.get("utf8", "") for seg in segs).replace("\n", " ").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                text=text,
                start=event.get("tStartMs", 0) / 1000,
                duration=event.get("dDurationMs", 0) / 1000,
            )
        )
    return segments


def fetch_transcript(
    video_id: str, languages: Optional[list[str]] = None
) -> tuple[list[TranscriptSegment], str, Optional[str]]:
    """Returns (segments, language_code_actually_used, video_title).

    Tries the preferred languages first (default English), preferring
    manually-written captions over auto-generated ones. Falls back to
    whatever transcript YouTube does have if none of the preferred
    languages are available, rather than failing outright.
    """
    languages = languages or ["en"]
    url = f"https://www.youtube.com/watch?v={video_id}"

    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        raise TranscriptUnavailableError(video_id, "unavailable_video", str(e))

    title = info.get("title")
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}

    lang_code, formats = _pick_track(manual, auto, languages)
    if not formats:
        raise TranscriptUnavailableError(
            video_id, "no_captions", "No captions are available for this video."
        )

    json3 = next((f for f in formats if f.get("ext") == "json3"), None)
    if json3 is None:
        raise TranscriptUnavailableError(
            video_id, "no_captions", "Captions exist but not in a usable format."
        )

    try:
        resp = requests.get(json3["url"], timeout=15)
        resp.raise_for_status()
        segments = _parse_json3(resp.json())
    except requests.RequestException as e:
        raise TranscriptUnavailableError(video_id, "unknown", str(e))

    if not segments:
        raise TranscriptUnavailableError(
            video_id, "no_captions", "The transcript for this video was empty."
        )

    return segments, lang_code, title


if __name__ == "__main__":
    # Smoke test: python -m backend.youtube_ingest
    for test_url in [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # has captions
        "https://youtu.be/dQw4w9WgXcQ?t=30",
    ]:
        vid = extract_video_id(test_url)
        print(f"{test_url} -> video_id={vid}")

    vid = extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    segments, lang, title = fetch_transcript(vid)
    print(f"title={title!r}, language={lang}, segments={len(segments)}")
    for s in segments[:3]:
        print(" ", s)
