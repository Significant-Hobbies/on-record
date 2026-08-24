from __future__ import annotations

import json
import re
from typing import Any

Cue = dict[str, float | str]

TIMESTAMP = re.compile(
    r"(?:(\d{2,}):)?(\d{2}):(\d{2})[.,](\d{1,3})",
)


def ts_to_seconds(raw: str) -> float:
    match = TIMESTAMP.fullmatch(raw.strip())
    if not match:
        raise ValueError(f"bad timestamp: {raw}")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    fraction = match.group(4).ljust(3, "0")
    return hours * 3600 + minutes * 60 + seconds + int(fraction) / 1000


def parse_vtt(text: str) -> list[Cue]:
    cues: list[Cue] = []
    blocks = re.split(r"\n\n+", text.replace("\r\n", "\n").strip())
    for block in blocks:
        lines = [
            line for line in block.split("\n") if line.strip() and not line.startswith("WEBVTT")
        ]
        if not lines:
            continue
        timing = next((line for line in lines if "-->" in line), "")
        if not timing:
            continue
        start_raw, end_raw = [part.strip().split(" ")[0] for part in timing.split("-->")]
        body = " ".join(line for line in lines if "-->" not in line and not line.strip().isdigit())
        body = re.sub(r"<[^>]+>", "", body).strip()
        if not body:
            continue
        start = ts_to_seconds(start_raw)
        end = ts_to_seconds(end_raw)
        cues.append({"start": start, "duration": max(0.0, end - start), "text": body})
    return cues


def parse_srt(text: str) -> list[Cue]:
    normalized = text.replace(",", ".").replace("\r\n", "\n")
    return parse_vtt("WEBVTT\n\n" + normalized)


def _json_cues(rows: list[Any]) -> list[Cue]:
    cues: list[Cue] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or row.get("body") or row.get("content") or "").strip()
        if not text:
            continue
        start = float(row.get("start") or row.get("startTime") or 0)
        duration = row.get("duration") or row.get("dur")
        if duration is None:
            end = float(row.get("end") or row.get("endTime") or start)
            duration = max(0.0, end - start)
        cues.append({"start": start, "duration": float(duration), "text": text})
    return cues


def parse_json_transcript(text: str) -> list[Cue]:
    payload = json.loads(text)
    if isinstance(payload, list):
        return _json_cues(payload)
    if not isinstance(payload, dict):
        return []
    for key in ("transcripts", "segments", "cues", "results"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return _json_cues(rows)
    return []


def parse_transcript(text: str, content_type: str = "") -> tuple[str, list[Cue]]:
    lowered = content_type.lower()
    stripped = text.lstrip()
    if "json" in lowered or stripped.startswith("{") or stripped.startswith("["):
        return "rss_json", parse_json_transcript(text)
    if "srt" in lowered or TIMESTAMP.search(
        stripped.split("-->", 1)[0] if "-->" in stripped else ""
    ):
        if stripped.startswith("WEBVTT") or "webvtt" in lowered or "vtt" in lowered:
            return "rss_vtt", parse_vtt(text)
        return "rss_srt", parse_srt(text)
    if stripped.startswith("WEBVTT") or "vtt" in lowered:
        return "rss_vtt", parse_vtt(text)
    return "rss_srt", parse_srt(text)
