from __future__ import annotations

import re
from typing import Any

from .seed.people import PEOPLE

TWO_DAYS_MS = 2 * 24 * 60 * 60 * 1000


def norm_title(title: str) -> set[str]:
    return {part for part in re.sub(r"[^a-z0-9]+", " ", title.lower()).split() if len(part) > 2}


def titles_close(left: str, right: str) -> bool:
    a, b = norm_title(left), norm_title(right)
    if not a or not b:
        return False
    return len(a & b) / max(len(a), len(b)) >= 0.45


def merge_video(episode: dict[str, Any], videos: list[dict[str, Any]]) -> dict[str, Any]:
    published = int(episode.get("publishedAt") or 0)
    for video in videos:
        if not titles_close(str(episode.get("title") or ""), str(video.get("title") or "")):
            continue
        if abs(int(video.get("publishedAt") or 0) - published) > TWO_DAYS_MS:
            continue
        merged = dict(episode)
        merged["youtubeVideoId"] = video.get("youtubeVideoId")
        merged["sourceUrl"] = merged.get("sourceUrl") or video.get("sourceUrl")
        return merged
    return episode


def names_text(text: str, names: list[str]) -> bool:
    """Whole-word match, so "Sam" does not match "same" and "Gil" not "Gilbert"."""
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(str(name).lower())}\b", lowered) for name in names if name)


def guests_from_text(text: str) -> list[dict[str, Any]]:
    """Credit an episode to someone only when its metadata names them.

    Matching uses the full name plus the person's explicit `matchAliases` —
    distinctive surnames and handles. Bare first names stay out of it: the
    roster decides who a claim is attributed to, and a wrong roster entry is
    how a quote ends up on the wrong person.
    """
    guests: list[dict[str, Any]] = []
    for person in PEOPLE:
        names = [str(person["name"]), *[str(a) for a in person.get("matchAliases") or []]]
        if names_text(text, names):
            guests.append(
                {
                    "personId": person["slug"],
                    "role": "guest",
                    "attributionSource": "metadata_match",
                    "confidence": 0.7,
                }
            )
    return guests
