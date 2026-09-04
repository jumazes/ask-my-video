"""Groups timestamped transcript segments into overlapping, timestamped chunks.

Why group segments instead of splitting raw concatenated text: YouTube already
gives us the transcript as small timestamped pieces (TranscriptSegment). If we
joined them into one big string and then split that string by character count,
we'd lose the exact timestamp for anything past the first segment in a chunk.
Instead we walk the segment list and decide chunk boundaries in terms of whole
segments, so every chunk keeps an exact start_time.
"""

from dataclasses import dataclass

from .youtube_ingest import TranscriptSegment


@dataclass
class Chunk:
    chunk_id: str
    video_id: str
    text: str
    start_time: float
    end_time: float
    start_label: str


def format_timestamp(seconds: float) -> str:
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def chunk_transcript(
    segments: list[TranscriptSegment],
    video_id: str,
    max_words: int = 180,
    overlap_words: int = 40,
) -> list[Chunk]:
    """Sliding window over segments: accumulate segments into a chunk until
    adding the next one would exceed max_words, then close the chunk and start
    the next one with ~overlap_words carried over from the tail of the last."""
    if not segments:
        return []

    chunks: list[Chunk] = []
    current: list[TranscriptSegment] = []
    current_word_count = 0

    for seg in segments:
        seg_word_count = len(seg.text.split())

        if current and current_word_count + seg_word_count > max_words:
            chunks.append(_build_chunk(current, video_id, len(chunks)))
            current, current_word_count = _carry_overlap(current, overlap_words)

        current.append(seg)
        current_word_count += seg_word_count

    if current:
        chunks.append(_build_chunk(current, video_id, len(chunks)))

    return chunks


def _carry_overlap(
    prev_segments: list[TranscriptSegment], overlap_words: int
) -> tuple[list[TranscriptSegment], int]:
    """Take trailing segments from the chunk we just closed, worth roughly
    overlap_words, so the next chunk opens with some shared context instead
    of a hard cut."""
    overlap: list[TranscriptSegment] = []
    word_count = 0
    for seg in reversed(prev_segments):
        seg_words = len(seg.text.split())
        if overlap and word_count + seg_words > overlap_words:
            break
        overlap.insert(0, seg)
        word_count += seg_words
    return overlap, word_count


def _build_chunk(segments: list[TranscriptSegment], video_id: str, index: int) -> Chunk:
    text = " ".join(seg.text.replace("\n", " ") for seg in segments)
    start_time = segments[0].start
    last = segments[-1]
    end_time = last.start + last.duration
    return Chunk(
        chunk_id=f"{video_id}_{index}",
        video_id=video_id,
        text=text,
        start_time=start_time,
        end_time=end_time,
        start_label=format_timestamp(start_time),
    )


if __name__ == "__main__":
    # Smoke test: python -m backend.chunking
    from .youtube_ingest import extract_video_id, fetch_transcript

    vid = extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    segments, lang, _title = fetch_transcript(vid)
    chunks = chunk_transcript(segments, vid)
    print(f"{len(segments)} segments -> {len(chunks)} chunks")
    for c in chunks[:3]:
        word_count = len(c.text.split())
        print(f"[{c.start_label}] ({word_count} words) {c.text[:80]}...")
