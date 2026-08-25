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


def cues_to_segments(cues: list[Cue], target_chars: int = TARGET_CHARS) -> list[dict[str, Any]]:
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
        segments.append(
            {
                "idx": len(segments),
                "startS": float(buf[0]["start"]),
                "endS": float(last["start"]) + float(last["duration"]),
                "text": text,
                "speakerHint": buf[0].get("speaker"),
                "cueMap": _prefix_anchor(segments[-1] if segments else None, overlap_from, prefix)
                + _cue_map(pieces, [float(cue["start"]) for cue in buf], lead, shift),
            }
        )
        buf = []
        buf_len = 0

    previous_text = ""
    for cue in cues:
        piece = str(cue.get("text") or "").strip()
        if not piece:
            continue
        next_len = buf_len + len(piece) + 1
        # Break where the voice changes as well as on length. A segment that
        # spans two people cannot be attributed to either, which is the whole
        # failure diarization exists to remove.
        changed = bool(buf) and cue.get("speaker") != buf[0].get("speaker")
        if buf and (next_len > target_chars or changed):
            flush(previous_text)
            previous_text = segments[-1]["text"] if segments else ""
        buf.append(cue)
        buf_len += len(piece) + 1
    flush(previous_text)
    return segments
