from __future__ import annotations

from typing import Any

Cue = dict[str, float | str]
CueMap = list[list[float]]

TARGET_CHARS = 3000
OVERLAP_CHARS = 200
# One cue anchor roughly every this many characters. Full per-cue maps run to
# hundreds of entries per segment; sampling keeps the stored row small and is
# still accurate to a second or two of speech.
CUE_MAP_STRIDE = 40


def _split_oversized_text(text: str, limit: int) -> list[str]:
    """Bound one publisher cue without inventing timestamps inside it."""
    remaining = text.strip()
    out: list[str] = []
    while len(remaining) > limit:
        floor = limit // 2
        sentence_breaks = [
            remaining.rfind(marker, floor, limit + 1) + 1 for marker in (". ", "? ", "! ")
        ]
        split_at = max(sentence_breaks)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, limit + 1)
        if split_at <= 0:
            split_at = limit
        out.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        out.append(remaining)
    return out


def _bounded_cues(cues: list[Cue], target_chars: int) -> list[Cue]:
    out: list[Cue] = []
    for cue in cues:
        text = str(cue.get("text") or "").strip()
        for part in _split_oversized_text(text, target_chars):
            bounded = dict(cue)
            bounded["text"] = part
            out.append(bounded)
    return out


def cue_time_at(cue_map: CueMap, offset: int) -> float | None:
    """Start time of the last cue anchored at or before ``offset``."""
    found: float | None = None
    for at, start in cue_map:
        if at > offset:
            break
        found = float(start)
    return found


def _cue_map(pieces: list[str], starts: list[float], lead: int, shift: int) -> CueMap:
    """Map character offsets in the emitted segment text to cue start times.

    ``lead`` is the whitespace stripped from the front of the joined cue text
    and ``shift`` is where that joined text begins inside the emitted segment
    (non-zero when an overlap prefix was prepended).
    """
    out: CueMap = []
    pos = 0
    for piece, start in zip(pieces, starts, strict=True):
        offset = max(0, shift + pos - lead)
        if not out or offset - out[-1][0] >= CUE_MAP_STRIDE:
            out.append([offset, round(float(start), 2)])
        pos += len(piece) + 1
    return out


def _prefix_anchor(previous: dict[str, Any] | None, overlap_from: str, prefix: str) -> CueMap:
    """Anchor offset 0 to when the copied overlap prefix was actually spoken."""
    if not (previous and prefix):
        return []
    start = cue_time_at(previous.get("cueMap") or [], len(overlap_from) - len(prefix))
    return [] if start is None else [[0, start]]


def cues_to_segments(
    cues: list[Cue], target_chars: int = TARGET_CHARS, speakers_resolved: bool = False
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    buf: list[Cue] = []
    buf_len = 0

    def flush(overlap_from: str = "") -> None:
        nonlocal buf, buf_len
        if not buf:
            return
        pieces = [str(cue["text"]) for cue in buf]
        joined = " ".join(pieces)
        lead = len(joined) - len(joined.lstrip())
        body = joined.strip()
        prefix = overlap_from[-OVERLAP_CHARS:] if overlap_from else ""
        if prefix:
            combined = prefix + " " + body
            text = combined.strip()
            shift = len(prefix) + 1 - (len(combined) - len(combined.lstrip()))
        else:
            text = body
            shift = 0
        last = buf[-1]
        speaker_hint = buf[0].get("speaker")
        if speakers_resolved and not speaker_hint:
            # The publisher supplied a name but it did not map uniquely onto
            # our roster. Keep the segment explicitly unpublishable instead of
            # letting extraction guess from the episode roster.
            speaker_hint = "unknown"
        segments.append(
            {
                "idx": len(segments),
                "startS": float(buf[0]["start"]),
                "endS": float(last["start"]) + float(last["duration"]),
                "text": text,
                "speakerHint": speaker_hint,
                # A publisher name is already resolved. Only an anonymous
                # diarization label should be offered to the identification
                # model again later.
                "diarLabel": None if speakers_resolved else buf[0].get("speaker"),
                "cueMap": _prefix_anchor(segments[-1] if segments else None, overlap_from, prefix)
                + _cue_map(pieces, [float(cue["start"]) for cue in buf], lead, shift),
            }
        )
        buf = []
        buf_len = 0

    # The prefix belongs to whatever is currently buffered, so it has to be
    # decided at the break and survive until that buffer is flushed — including
    # the final flush after the loop.
    pending_prefix = ""
    for cue in _bounded_cues(cues, target_chars):
        piece = str(cue.get("text") or "").strip()
        if not piece:
            continue
        next_len = buf_len + len(piece) + 1
        # Break where the voice changes as well as on length. A segment that
        # spans two people cannot be attributed to either, which is the whole
        # failure diarization exists to remove.
        changed = bool(buf) and cue.get("speaker") != buf[0].get("speaker")
        if buf and (next_len > target_chars or changed):
            flush(pending_prefix)
            # Overlap carries context across an arbitrary split in one person's
            # speech. Carried across a change of voice it does the opposite:
            # the previous speaker's words would open the next speaker's
            # segment, and a quote anchored there is credited to the wrong
            # person.
            pending_prefix = "" if changed else (segments[-1]["text"] if segments else "")
        buf.append(cue)
        buf_len += len(piece) + 1
    flush(pending_prefix)
    return segments
