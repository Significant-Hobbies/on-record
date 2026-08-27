from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any

from ..seed.people import PEOPLE

Cue = dict[str, float | str]

TIMESTAMP = re.compile(
    r"(?:(\d{2,}):)?(\d{2}):(\d{2})[.,](\d{1,3})",
)
BRACKETED_HEADER = re.compile(r"^\[((?:\d{2,}:)?\d{2}:\d{2}[.,]\d{1,3})\]\s*(.+?)\s*$")
PARENTHESIZED_HEADER = re.compile(
    r"^([^()\n]{1,100}?)\s+\(((?:\d{1,3}:)?\d{2}:\d{2}(?:[.,]\d{1,3})?)\):?\s*$"
)
CLOCK = re.compile(r"^(?:(\d{1,3}):)?(\d{2}):(\d{2})(?:[.,](\d{1,3}))?$")
SPEAKER_LINE = re.compile(r"^([^:\n]{1,80}):\s*(.*)$")
_SPEAKER_SLUGS = {
    " ".join(str(person["name"]).split()).casefold(): str(person["slug"]) for person in PEOPLE
}


def ts_to_seconds(raw: str) -> float:
    match = TIMESTAMP.fullmatch(raw.strip())
    if not match:
        raise ValueError(f"bad timestamp: {raw}")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    fraction = match.group(4).ljust(3, "0")
    return hours * 3600 + minutes * 60 + seconds + int(fraction) / 1000


def clock_to_seconds(raw: str) -> float:
    match = CLOCK.fullmatch(raw.strip())
    if not match:
        raise ValueError(f"bad clock: {raw}")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    fraction = (match.group(4) or "0").ljust(3, "0")
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


def parse_timestamped_text(text: str) -> list[Cue]:
    """Parse publisher text shaped ``[HH:MM:SS.xx] Speaker`` plus a body."""
    cues: list[Cue] = []
    blocks = re.split(r"\n\s*\n+", text.replace("\r\n", "\n").strip())
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        header = BRACKETED_HEADER.fullmatch(lines[0].strip())
        body = " ".join(line.strip() for line in lines[1:] if line.strip())
        if not (header and body):
            continue
        speaker_name = " ".join(header.group(2).split())
        cue: Cue = {
            "duration": 0.0,
            "speakerName": speaker_name,
            "speakerNameSource": "publisher",
            "start": ts_to_seconds(header.group(1)),
            "text": body,
        }
        speaker = _SPEAKER_SLUGS.get(speaker_name.casefold())
        if speaker:
            cue["speaker"] = speaker
        cues.append(cue)
    for current, following in zip(cues, cues[1:], strict=False):
        current["duration"] = max(0.0, float(following["start"]) - float(current["start"]))
    return cues


def parse_parenthesized_speaker_text(text: str) -> list[Cue]:
    """Parse publisher blocks shaped ``Name (HH:MM:SS):`` plus a body."""
    cues: list[Cue] = []
    blocks = re.split(r"\n\s*\n+", text.replace("\r\n", "\n").strip())
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        header = PARENTHESIZED_HEADER.fullmatch(lines[0].strip())
        body = " ".join(line.strip() for line in lines[1:] if line.strip())
        if not (header and body):
            continue
        speaker_name = " ".join(header.group(1).split())
        cue: Cue = {
            "duration": 0.0,
            "speakerName": speaker_name,
            "speakerNameSource": "publisher",
            "start": clock_to_seconds(header.group(2)),
            "text": body,
        }
        speaker = _SPEAKER_SLUGS.get(speaker_name.casefold())
        if speaker:
            cue["speaker"] = speaker
        cues.append(cue)
    return _finish_durations(cues)


def _finish_durations(cues: list[Cue]) -> list[Cue]:
    for current, following in zip(cues, cues[1:], strict=False):
        current["duration"] = max(0.0, float(following["start"]) - float(current["start"]))
    return cues


def parse_labelled_text(text: str) -> list[Cue]:
    """Parse blocks shaped ``HH:MM:SS`` then ``Speaker 1: words``."""
    cues: list[Cue] = []
    blocks = re.split(r"\n\s*\n+", text.replace("\r\n", "\n").strip())
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2 or not CLOCK.fullmatch(lines[0]):
            continue
        spoken = SPEAKER_LINE.match(lines[1])
        if not spoken:
            continue
        body = " ".join([spoken.group(2), *lines[2:]]).strip()
        if not body:
            continue
        cues.append(
            {
                "duration": 0.0,
                "speaker": " ".join(spoken.group(1).split()),
                "start": clock_to_seconds(lines[0]),
                "text": body,
            }
        )
    return _finish_durations(cues)


class _TimedHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, str]] = []
        self._capture = ""
        self._parts: list[str] = []
        self._speaker = ""
        self._timestamp = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"cite", "time", "p"}:
            self._capture = tag
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != self._capture:
            return
        value = " ".join("".join(self._parts).split())
        if tag == "cite":
            self._speaker = value.rstrip(":")
        elif tag == "time":
            self._timestamp = value
        elif tag == "p" and self._speaker and self._timestamp and value:
            self.rows.append(
                {"speaker": self._speaker, "timestamp": self._timestamp, "text": value}
            )
        self._capture = ""
        self._parts = []


def parse_timed_html(text: str) -> list[Cue]:
    parser = _TimedHtmlParser()
    parser.feed(text)
    cues: list[Cue] = []
    for row in parser.rows:
        try:
            start = clock_to_seconds(row["timestamp"])
        except ValueError:
            continue
        cues.append(
            {
                "duration": 0.0,
                "speaker": row["speaker"],
                "start": start,
                "text": row["text"],
            }
        )
    return _finish_durations(cues)


def _first_line(stripped: str) -> str:
    lines = stripped.splitlines()
    return lines[0].strip() if lines else ""


def _looks_like_timed_html(html: str) -> bool:
    return "<cite" in html and "<time" in html and "<p" in html


def _looks_like_json(lowered: str, stripped: str) -> bool:
    return "json" in lowered or stripped.startswith(("{", "["))


def _looks_like_srt(lowered: str, stripped: str) -> bool:
    before_arrow = stripped.split("-->", 1)[0] if "-->" in stripped else ""
    return "srt" in lowered or bool(TIMESTAMP.search(before_arrow))


def _looks_like_vtt(lowered: str, stripped: str) -> bool:
    return stripped.startswith("WEBVTT") or "webvtt" in lowered or "vtt" in lowered


def parse_transcript(text: str, content_type: str = "") -> tuple[str, list[Cue]]:
    lowered = content_type.lower()
    stripped = text.lstrip()
    html = stripped.lower()
    first_line = _first_line(stripped)
    if BRACKETED_HEADER.fullmatch(first_line):
        return "rss_named_text", parse_timestamped_text(text)
    if PARENTHESIZED_HEADER.fullmatch(first_line):
        return "rss_named_text", parse_parenthesized_speaker_text(text)
    if CLOCK.fullmatch(first_line):
        cues = parse_labelled_text(text)
        return ("rss_text_coarse" if len(cues) == 1 else "rss_text"), cues
    if _looks_like_timed_html(html):
        return "rss_text", parse_timed_html(text)
    if _looks_like_json(lowered, stripped):
        try:
            return "rss_json", parse_json_transcript(text)
        except json.JSONDecodeError:
            return "rss_json", []
    if _looks_like_srt(lowered, stripped):
        if _looks_like_vtt(lowered, stripped):
            return "rss_vtt", parse_vtt(text)
        return "rss_srt", parse_srt(text)
    if _looks_like_vtt(lowered, stripped):
        return "rss_vtt", parse_vtt(text)
    return "rss_srt", parse_srt(text)
