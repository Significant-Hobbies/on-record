"""Decide whether a person named in an episode's metadata is actually on it.

Matching a roster name against the title and description finds the guest about
half the time. The other half are people the blurb happens to name: a paper's
author list, a story about a past meeting, a reference to an earlier episode,
a VC's track record. Measured over 4,089 attributions, 25% matched only beyond
the 800th character of the description, and every sampled one of those was
wrong.

Position alone is too blunt — the middle of a description holds both real
guests and passing mentions. Reading the sentence settles it, and a 4B model
does that in about half a second, which is cheap enough to ask for every
attribution we hold.

The question is deliberately narrow: does this person appear, yes or no. It is
judgement over a short passage, which small models are good at — unlike
verbatim reproduction, which they are not.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

LOGGER = logging.getLogger("on_record_ingest")

SYSTEM = (
    "You decide whether a named person actually appears on a podcast episode as a host "
    "or guest, as opposed to merely being mentioned or discussed. "
    'Reply JSON only: {"appears": true|false, "why": "<six words>"}'
)
VERDICT_SCHEMA = {
    "type": "object",
    "properties": {"appears": {"type": "boolean"}, "why": {"type": "string"}},
    "required": ["appears", "why"],
}
# Enough of the blurb to hold the introduction and the chapter list that follows.
DESCRIPTION_CHARS = 900
APPEARS_CONFIDENCE = 0.95
MENTIONED_CONFIDENCE = 0.1


def strip_html(value: str | None) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", value or "").split())


def build_prompt(name: str, title: str, description: str) -> str:
    return (
        f"Episode title: {title}\n\n"
        f"Episode description:\n{strip_html(description)[:DESCRIPTION_CHARS]}\n\n"
        f"Question: does {name} appear on this episode as a host or guest?"
    )


def judge(
    client: httpx.Client, base_url: str, model: str, name: str, title: str, description: str
) -> dict[str, Any] | None:
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": 120,
        # Thinking returns an empty message on Qwen3.5 and this is not a puzzle.
        "reasoning_effort": "none",
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "verdict", "strict": True, "schema": VERDICT_SCHEMA},
        },
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_prompt(name, title, description)},
        ],
    }
    try:
        response = client.post(f"{base_url}/chat/completions", json=body, timeout=120.0)
        response.raise_for_status()
        return json.loads(response.json()["choices"][0]["message"]["content"])
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.warning("attribution check failed for %s: %s", name, exc)
        return None


# A title naming someone is strong evidence on its own. The model reads the
# common formats well but misread Lex's "#500 - Guest: topics" twice, burying a
# guest who was named right there. It may decline to promote a title match; it
# may not bury one.
TITLE_FLOOR = 0.6


def confidence_for(verdict: dict[str, Any] | None, name: str = "", title: str = "") -> float | None:
    """None means undecided — leave the attribution exactly as it was."""
    if verdict is None:
        return None
    if verdict.get("appears") is True:
        return APPEARS_CONFIDENCE
    in_title = bool(name) and name.lower() in (title or "").lower()
    return TITLE_FLOOR if in_title else MENTIONED_CONFIDENCE
