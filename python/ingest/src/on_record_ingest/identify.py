"""Decide who each diarized voice belongs to, once per episode.

Diarization says "this is speaker B" consistently for a whole episode but has
no idea who B is. Naming them is a single decision per voice rather than a
guess per sentence, which is the difference between one judgement call an
episode and several hundred.

That distinction is why the old approach failed silently: asked afresh on every
segment, the model picked whichever roster name looked plausible and reported
0.9 confidence, so 69 of 72 claims on a two-guest episode went to one man.

A voice we cannot place stays unknown. Its claims are still extracted, but an
unknown speaker never publishes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

LOGGER = logging.getLogger("on_record_ingest")

UNKNOWN = "unknown"
# Enough of a voice to recognise it, not so much that the prompt balloons.
SAMPLE_TURNS = 6
SAMPLE_CHARS = 400

IDENTIFY_SYSTEM = (
    'You identify speakers in an interview. Reply with JSON only, shaped {"speakers": '
    '{"<label>": "<roster-slug or unknown>"}}. No prose, no other keys.'
)


def sample_by_speaker(segments: list[dict[str, Any]]) -> dict[str, list[str]]:
    samples: dict[str, list[str]] = {}
    for segment in segments:
        label = segment.get("speakerHint")
        if not label:
            continue
        bucket = samples.setdefault(str(label), [])
        if len(bucket) < SAMPLE_TURNS:
            bucket.append(str(segment.get("text") or "")[:SAMPLE_CHARS])
    return samples


def build_prompt(
    samples: dict[str, list[str]],
    roster: list[dict[str, str]],
    episode_title: str,
) -> str:
    people = "\n".join(f"- {p['slug']} ({p['name']}, {p['role']})" for p in roster)
    voices = "\n\n".join(
        f"Speaker {label}:\n" + "\n".join(f'  "{turn}"' for turn in turns)
        for label, turns in sorted(samples.items())
    )
    return (
        f"Episode: {episode_title}\n\n"
        f"People expected on this episode:\n{people}\n\n"
        f"Here is how each voice talks:\n\n{voices}\n\n"
        'Map every speaker label to one roster slug, or to "unknown".\n'
        "The host introduces the episode and asks the questions; guests answer.\n"
        'Someone who says "I sit down with X and Y" is the host, not X or Y.\n'
        'Never give the same slug to two labels. Use "unknown" whenever the '
        "evidence does not actually single someone out — an unnamed voice is far "
        "better than the wrong name."
    )


def parse_mapping(raw: str, labels: set[str], slugs: set[str]) -> dict[str, str]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :] if "{" in text else text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    mapping = payload.get("speakers") if isinstance(payload, dict) else None
    if not isinstance(mapping, dict):
        return {}
    out: dict[str, str] = {}
    taken: set[str] = set()
    for label, slug in mapping.items():
        if str(label) not in labels:
            continue
        value = str(slug)
        # One person cannot be two voices; a duplicate means the model guessed.
        if value not in slugs or value in taken:
            out[str(label)] = UNKNOWN
            continue
        taken.add(value)
        out[str(label)] = value
    return out


def identify_speakers(
    settings: Any,
    segments: list[dict[str, Any]],
    roster: list[dict[str, str]],
    episode_title: str,
) -> dict[str, str]:
    """Map diarized labels to roster slugs. Unmapped voices come back unknown."""
    from .extract.claims import _chat

    samples = sample_by_speaker(segments)
    if not (samples and roster):
        return {}
    labels = set(samples)
    slugs = {str(p["slug"]) for p in roster}
    try:
        raw, _, _ = _chat(settings, build_prompt(samples, roster, episode_title), IDENTIFY_SYSTEM)
    except Exception as exc:
        LOGGER.warning("speaker identification failed: %s", exc)
        return dict.fromkeys(labels, UNKNOWN)
    mapping = parse_mapping(raw, labels, slugs)
    for label in labels:
        mapping.setdefault(label, UNKNOWN)
    LOGGER.info("identified speakers: %s", mapping)
    return mapping
