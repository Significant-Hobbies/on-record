from __future__ import annotations

from typing import Any

Cue = dict[str, float | str]

TARGET_CHARS = 3000
OVERLAP_CHARS = 200


def cues_to_segments(cues: list[Cue], target_chars: int = TARGET_CHARS) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    buf: list[Cue] = []
    buf_len = 0

    def flush(overlap_from: str = "") -> None:
        nonlocal buf, buf_len
        if not buf:
            return
        text = " ".join(str(cue["text"]) for cue in buf).strip()
        if overlap_from:
            text = (overlap_from[-OVERLAP_CHARS:] + " " + text).strip()
        start = float(buf[0]["start"])
        last = buf[-1]
        end = float(last["start"]) + float(last["duration"])
        segments.append(
            {
                "idx": len(segments),
                "startS": start,
                "endS": end,
                "text": text,
                "speakerHint": None,
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
        if buf and next_len > target_chars:
            flush(previous_text)
            previous_text = segments[-1]["text"] if segments else ""
        buf.append(cue)
        buf_len += len(piece) + 1
    flush(previous_text)
    return segments
