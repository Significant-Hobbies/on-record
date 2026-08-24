from __future__ import annotations

import json
import re
from typing import Any

CLAIM_TYPES = {
    "belief",
    "prediction",
    "recommendation",
    "evaluation",
    "observation",
    "preference",
    "commitment",
    "disagreement",
    "uncertainty",
}
MIN_QUOTE_CHARS = 40
REFERENCE_KINDS = {
    "book",
    "app",
    "tool",
    "service",
    "paper",
    "course",
    "hardware",
    "person",
    "other",
}
REFERENCE_ROLES = {"recommends", "uses", "built", "avoids", "mentions"}


def normalize_ws(text: str) -> str:
    return " ".join(text.split())


def find_verbatim_anchor(
    segment: str, quote: str, min_chars: int = MIN_QUOTE_CHARS
) -> tuple[int, int] | None:
    needle = normalize_ws(quote)
    if len(needle) < min_chars:
        return None
    norm_chars: list[str] = []
    mapping: list[int] = []
    i = 0
    length = len(segment)
    while i < length and segment[i].isspace():
        i += 1
    while i < length:
        ch = segment[i]
        if ch.isspace():
            while i < length and segment[i].isspace():
                i += 1
            if i < length:
                mapping.append(i)
                norm_chars.append(" ")
            continue
        mapping.append(i)
        norm_chars.append(ch)
        i += 1
    haystack = "".join(norm_chars)
    at = haystack.find(needle)
    if at < 0:
        return None
    start = mapping[at]
    end = mapping[at + len(needle) - 1] + 1
    return start, end


def timestamp_for_offset(
    cues: list[dict[str, Any]], offset: int, segment_text: str
) -> float | None:
    if offset < 0 or offset > len(segment_text):
        return None
    running = 0
    for cue in cues:
        text = str(cue.get("text") or "")
        nxt = running + len(text) + 1
        if offset < nxt:
            return float(cue.get("start") or 0)
        running = nxt
    if cues:
        return float(cues[0].get("start") or 0)
    return None


def parse_claims_json(raw: str) -> list[dict[str, Any]] | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict) and isinstance(payload.get("claims"), list):
        payload = payload["claims"]
    if not isinstance(payload, list):
        return None
    return [row for row in payload if isinstance(row, dict)]


def validate_references(row: dict[str, Any], segment_text: str) -> list[dict[str, str]]:
    raw = row.get("references") or []
    if not isinstance(raw, list):
        return []
    haystack = normalize_ws(segment_text).lower()
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().lower()
        role = str(item.get("role") or "").strip().lower()
        name = str(item.get("name") or "").strip()
        if kind not in REFERENCE_KINDS or role not in REFERENCE_ROLES or len(name) < 2:
            continue
        if normalize_ws(name).lower() not in haystack:
            continue
        key = (kind, role, name.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": kind, "name": name, "role": role})
    return out


def _confidence(row: dict[str, Any], *keys: str) -> float | None:
    try:
        return float(next((row[key] for key in keys if row.get(key) is not None), 0))
    except (TypeError, ValueError):
        return None


def validate_claim(
    row: dict[str, Any],
    segment_text: str,
    roster: set[str],
    topics: set[str],
) -> tuple[dict[str, Any] | None, str | None]:
    speaker = str(row.get("speaker") or row.get("speakerRaw") or "").strip()
    if speaker not in roster and speaker != "unknown":
        return None, "speaker_not_in_roster"
    claim_type = str(row.get("claim_type") or row.get("claimType") or "").strip()
    if claim_type not in CLAIM_TYPES:
        return None, "bad_claim_type"
    quote = str(row.get("quote") or "").strip()
    assertion = str(row.get("assertion") or row.get("normalized_claim") or "").strip()
    if not assertion:
        return None, "missing_assertion"
    return _validated_body(row, speaker, claim_type, quote, assertion, segment_text, topics)


def _validated_body(
    row: dict[str, Any],
    speaker: str,
    claim_type: str,
    quote: str,
    assertion: str,
    segment_text: str,
    topics: set[str],
) -> tuple[dict[str, Any] | None, str | None]:
    anchor = find_verbatim_anchor(segment_text, quote)
    if anchor is None:
        return None, "quote_not_verbatim"
    topic_list = row.get("topics") or []
    if not isinstance(topic_list, list):
        return None, "bad_topics"
    extraction = _confidence(row, "extraction_confidence", "extractionConfidence")
    speaker_conf = _confidence(row, "speaker_confidence", "speakerConfidence")
    if extraction is None or speaker_conf is None:
        return None, "bad_confidence"
    return {
        "speakerRaw": speaker,
        "claimType": claim_type,
        "assertion": assertion,
        "stance": str(row.get("stance") or "") or None,
        "quote": quote,
        "quoteStartChar": anchor[0],
        "quoteEndChar": anchor[1],
        "extractionConfidence": extraction,
        "speakerConfidence": speaker_conf,
        "topics": [str(slug) for slug in topic_list if str(slug) in topics],
        "references": validate_references(row, segment_text),
    }, None
