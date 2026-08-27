from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

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


def merge_discovery_items(
    rss_items: list[dict[str, Any]],
    videos: list[dict[str, Any]],
    *,
    include_unmatched_videos: bool,
) -> list[dict[str, Any]]:
    """Attach matching uploads and optionally admit channel-only episodes."""
    merged_items: list[dict[str, Any]] = []
    matched_video_ids: set[str] = set()
    for item in rss_items:
        merged = merge_video(item, videos)
        merged_items.append(merged)
        video_id = str(merged.get("youtubeVideoId") or "")
        if video_id:
            matched_video_ids.add(video_id)
    if include_unmatched_videos:
        merged_items.extend(
            video
            for video in videos
            if str(video.get("youtubeVideoId") or "") not in matched_video_ids
        )
    return merged_items


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


YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "www.youtu.be"}
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def video_id_from_source_url(source_url: str | None) -> str | None:
    """A video id only when the episode's canonical URL is itself YouTube.

    Descriptions routinely contain links to prior interviews, sponsors, and
    recurring promotional videos. Mining an arbitrary link from that prose
    assigned one TWiST promo to 200 unrelated episodes. Channel uploads are
    matched separately by title and date; this helper therefore fails closed
    unless the source URL itself identifies the video.
    """
    parsed = urlparse(str(source_url or "").strip())
    host = (parsed.hostname or "").casefold()
    if parsed.scheme not in {"http", "https"} or host not in YOUTUBE_HOSTS:
        return None
    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.strip("/").split("/", 1)[0]
    elif parsed.path.rstrip("/") == "/watch":
        candidate = (parse_qs(parsed.query).get("v") or [""])[0]
    else:
        parts = parsed.path.strip("/").split("/")
        candidate = parts[1] if len(parts) > 1 and parts[0] in {"embed", "live", "shorts"} else ""
    return candidate if YOUTUBE_ID.fullmatch(candidate) else None
