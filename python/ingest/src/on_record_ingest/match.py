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


def guests_from_text(text: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    guests: list[dict[str, Any]] = []
    for person in PEOPLE:
        names = [person["name"], *list(person.get("aliases") or [])]
        if any(str(name).lower() in lowered for name in names if len(str(name)) > 3):
            guests.append(
                {
                    "personId": person["slug"],
                    "role": "guest",
                    "attributionSource": "metadata_match",
                    "confidence": 0.7,
                }
            )
    return guests
