"""Approved timed transcripts from official Lenny's Podcast Substack pages."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from ..match import norm_title
from ._publisher_html import Cue, PublisherSourceUnavailable, title_overlap

USER_AGENT = "on-record/0.1 publisher-transcript-ingest"
TRANSCRIPT_KIND = "publisher_json"
LENNYS_HOSTS = {"lennysnewsletter.com", "www.lennysnewsletter.com"}
MIN_CUES = 10
MIN_CHARS = 1000
MIN_INVALID_CUE_LIMIT = 10
MAX_INVALID_CUE_FRACTION = 0.02
MIN_TITLE_SCORE = 0.65
PRELOAD_RE = re.compile(r'window\._preloads\s*=\s*JSON\.parse\(("(?:\\.|[^"\\])*")\)')


def _speaker_key(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _speaker_label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"SPEAKER_0*(\d+)", value.strip())
    return f"SPEAKER_{int(match.group(1))}" if match else None


def is_lennys_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and (parsed.hostname or "").casefold() in LENNYS_HOSTS
        and parsed.path.startswith("/p/")
        and len(parsed.path.rstrip("/").split("/")) == 3
    )


def _preload(html: str) -> dict[str, Any]:
    match = PRELOAD_RE.search(html)
    if match is None:
        raise PublisherSourceUnavailable("publisher page omitted preload data")
    try:
        decoded = json.loads(match.group(1))
        payload = json.loads(decoded)
    except (json.JSONDecodeError, TypeError) as exc:
        raise PublisherSourceUnavailable("publisher preload data was malformed") from exc
    if not isinstance(payload, dict):
        raise PublisherSourceUnavailable("publisher preload data was malformed")
    return payload


def _post_id_from_guid(episode_guid: str) -> int | None:
    prefix = "substack:post:"
    if not episode_guid.startswith(prefix):
        return None
    value = episode_guid.removeprefix(prefix)
    return int(value) if value.isdigit() else None


def _title_tokens(value: str) -> set[str]:
    title = re.split(r"\s*[|]\s*", value, maxsplit=1)[0]
    return norm_title(title)


def _validated_transcription(
    preload: dict[str, Any], episode_title: str, episode_guid: str
) -> tuple[dict[str, str], str] | None:
    post = preload.get("post")
    if not isinstance(post, dict):
        raise PublisherSourceUnavailable("publisher page omitted post data")
    expected_id = _post_id_from_guid(episode_guid)
    if expected_id is not None and post.get("id") != expected_id:
        logging.getLogger("on_record_ingest").warning(
            "Lenny publisher post id mismatch for %s", episode_title
        )
        return None
    if (
        expected_id is None
        and title_overlap(_title_tokens(str(post.get("title") or "")), _title_tokens(episode_title))
        < MIN_TITLE_SCORE
    ):
        logging.getLogger("on_record_ingest").warning(
            "Lenny publisher title mismatch for %s", episode_title
        )
        return None
    upload = post.get("podcastUpload")
    transcription = upload.get("transcription") if isinstance(upload, dict) else None
    if not isinstance(transcription, dict):
        return None
    if transcription.get("status") != "transcribed" or not transcription.get("approved_at"):
        return None
    speaker_map = transcription.get("speaker_map")
    cdn_url = transcription.get("cdn_url")
    if not isinstance(speaker_map, dict) or not speaker_map or not isinstance(cdn_url, str):
        return None
    normalized_speakers: dict[str, str] = {}
    for label, name in speaker_map.items():
        normalized_label = label.strip() if isinstance(label, str) else ""
        normalized_name = name.strip() if isinstance(name, str) else ""
        if _speaker_label(normalized_label) is None or not normalized_name:
            return None
        normalized_speakers[normalized_label] = normalized_name
    return normalized_speakers, cdn_url


def _fetch_json(client: httpx.Client, cdn_url: str) -> Any:
    try:
        response = client.get(cdn_url, headers={"User-Agent": USER_AGENT}, timeout=45.0)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        # Signed CDN URLs are intentionally excluded from error messages.
        raise PublisherSourceUnavailable("publisher transcript download failed") from exc


def _publisher_speaker_lookups(
    publisher_speakers: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    exact_speakers: dict[str, str] = {}
    canonical_names: dict[str, set[str]] = {}
    for label, name in publisher_speakers.items():
        normalized_label = _speaker_label(label)
        if normalized_label is None:
            raise PublisherSourceUnavailable("publisher speaker map was malformed")
        exact_speakers[label.strip()] = name
        canonical_names.setdefault(normalized_label, set()).add(name)
    fallback_speakers = {
        label: next(iter(names)) for label, names in canonical_names.items() if len(names) == 1
    }
    return exact_speakers, fallback_speakers


def _parse_raw_cue(
    raw: Any,
    exact_speakers: dict[str, str],
    fallback_speakers: dict[str, str],
    normalized_identities: dict[str, str],
    previous_start: float,
) -> tuple[Cue | None, bool]:
    if not isinstance(raw, dict):
        return None, True
    text = " ".join(str(raw.get("text") or "").split())
    raw_speaker_label = raw.get("speaker").strip() if isinstance(raw.get("speaker"), str) else ""
    speaker_label = _speaker_label(raw_speaker_label)
    speaker_name = exact_speakers.get(raw_speaker_label) or fallback_speakers.get(
        speaker_label or ""
    )
    try:
        start = float(raw["start"])
        end = float(raw["end"])
    except (KeyError, TypeError, ValueError):
        return None, True
    if not text:
        return None, False
    if start < 0 or end < start or start < previous_start:
        return None, True
    cue: Cue = {
        "duration": end - start,
        "speakerName": speaker_name or "Unknown",
        "speakerNameSource": (
            "publisher"
            if speaker_name
            else "publisher_missing"
            if speaker_label is None
            else "publisher_unmapped_label"
        ),
        "start": start,
        "text": text,
    }
    speaker = normalized_identities.get(_speaker_key(speaker_name or ""))
    if speaker:
        cue["speaker"] = speaker
    return cue, False


def parse_transcript_json(
    payload: Any,
    publisher_speakers: dict[str, str],
    identity_map: dict[str, str] | None = None,
) -> list[Cue]:
    """Validate exact publisher timing and map only approved roster identities."""
    if not isinstance(payload, list):
        raise PublisherSourceUnavailable("publisher transcript JSON was malformed")
    normalized_identities = {
        _speaker_key(name): slug for name, slug in (identity_map or {}).items()
    }
    exact_speakers, fallback_speakers = _publisher_speaker_lookups(publisher_speakers)
    cues: list[Cue] = []
    invalid_cues = 0
    previous_start = -1.0
    for raw in payload:
        cue, invalid = _parse_raw_cue(
            raw,
            exact_speakers,
            fallback_speakers,
            normalized_identities,
            previous_start,
        )
        if invalid:
            invalid_cues += 1
            continue
        if cue is not None:
            cues.append(cue)
            previous_start = float(cue["start"])
    invalid_limit = max(MIN_INVALID_CUE_LIMIT, int(len(payload) * MAX_INVALID_CUE_FRACTION))
    if invalid_cues > invalid_limit:
        raise PublisherSourceUnavailable("publisher transcript contained too many malformed cues")
    if len(cues) < MIN_CUES or sum(len(str(cue["text"])) for cue in cues) < MIN_CHARS:
        raise PublisherSourceUnavailable("publisher transcript contained too few usable cues")
    return cues


def fetch_cues(
    source_url: str,
    client: httpx.Client,
    episode_title: str,
    episode_guid: str = "",
    identity_map: dict[str, str] | None = None,
) -> list[Cue]:
    """Fetch one canonical page and its approved, signed transcript payload."""
    if not is_lennys_url(source_url):
        return []
    try:
        response = client.get(source_url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {404, 410}:
            return []
        raise PublisherSourceUnavailable(f"publisher page HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise PublisherSourceUnavailable("publisher page request failed") from exc
    if not is_lennys_url(str(response.url)):
        return []
    transcription = _validated_transcription(_preload(response.text), episode_title, episode_guid)
    if transcription is None:
        return []
    publisher_speakers, cdn_url = transcription
    return parse_transcript_json(_fetch_json(client, cdn_url), publisher_speakers, identity_map)
