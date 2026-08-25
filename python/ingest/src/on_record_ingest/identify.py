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
    """The most substantial things each voice said.

    Taking the first turns instead picks up the cold-open montage, which is
    chopped clips with no context — the model saw fragments and, correctly,
    refused to name anyone.
    """
    by_label: dict[str, list[dict[str, Any]]] = {}
    for segment in segments:
        label = segment.get("diarLabel") or segment.get("speakerHint")
        if label:
            by_label.setdefault(str(label), []).append(segment)
    samples: dict[str, list[str]] = {}
    for label, rows in by_label.items():
        longest = sorted(rows, key=lambda r: -len(str(r.get("text") or "")))[:SAMPLE_TURNS]
        longest.sort(key=lambda r: float(r.get("startS") or 0))
        samples[label] = [str(r.get("text") or "")[:SAMPLE_CHARS] for r in longest]
    return samples


def build_prompt(
    samples: dict[str, list[str]],
    roster: list[dict[str, str]],
    episode_title: str,
    description: str = "",
) -> str:
    people = "\n".join(f"- {p['slug']} ({p['name']}, {p['role']})" for p in roster)
    voices = "\n\n".join(
        f"Speaker {label}:\n" + "\n".join(f'  "{turn}"' for turn in turns)
        for label, turns in sorted(samples.items())
    )
    blurb = f"Episode notes: {description[:600]}\n\n" if description else ""
    return (
        f"Episode: {episode_title}\n\n{blurb}"
        f"People expected on this episode:\n{people}\n\n"
        f"Here is how each voice talks:\n\n{voices}\n\n"
        'Map every speaker label to one roster slug, or to "unknown".\n'
        "The host introduces the episode and asks the questions; guests answer.\n"
        'Someone who says "I sit down with X and Y" is the host, not X or Y.\n'
        'Never give the same slug to two labels. Use "unknown" whenever the '
        "evidence does not actually single someone out — an unnamed voice is far "
        "better than the wrong name."
    )


def match_label(key: str, labels: set[str]) -> str | None:
    """Line the model's key up with a diarization label.

    It answers with the wording it was shown — "Speaker B" for label "B" — and
    an exact-match lookup silently discarded every correct identification.
    """
    candidate = str(key).strip()
    if candidate in labels:
        return candidate
    trimmed = candidate.removeprefix("Speaker").removeprefix("speaker").strip(" :#\t")
    for label in labels:
        if trimmed.casefold() == label.casefold():
            return label
    return None


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
    for key, slug in mapping.items():
        label = match_label(key, labels)
        if label is None:
            continue
        value = str(slug)
        # One person cannot be two voices; a duplicate means the model guessed.
        if value not in slugs or value in taken:
            out[label] = UNKNOWN
            continue
        taken.add(value)
        out[label] = value
    return out


def identify_speakers(
    settings: Any,
    segments: list[dict[str, Any]],
    roster: list[dict[str, str]],
    episode_title: str,
    description: str = "",
    attempts: int = 2,
) -> dict[str, str]:
    """Map diarized labels to roster slugs. Unmapped voices come back unknown."""
    from .extract.claims import _chat

    samples = sample_by_speaker(segments)
    if not (samples and roster):
        return {}
    labels = set(samples)
    slugs = {str(p["slug"]) for p in roster}
    prompt = build_prompt(samples, roster, episode_title, description)
    mapping: dict[str, str] = {}
    for attempt in range(attempts):
        try:
            raw, _, _ = _chat(settings, prompt, IDENTIFY_SYSTEM)
        except Exception as exc:
            LOGGER.warning("speaker identification failed: %s", exc)
            continue
        mapping = parse_mapping(raw, labels, slugs)
        if any(v != UNKNOWN for v in mapping.values()):
            break
        # Naming nobody is the safe answer but a useless one; the call is
        # cheap and the models behind the gateway vary.
        LOGGER.info("identification named nobody (attempt %s)", attempt + 1)
    for label in labels:
        mapping.setdefault(label, UNKNOWN)
    LOGGER.info("identified speakers: %s", mapping)
    return mapping
