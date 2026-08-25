from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx

LOGGER = logging.getLogger("on_record_ingest")
USER_AGENT = "on-record/0.1 youtube-rss"
# YouTube answers bursts of channel-feed requests with 404s and 500s that clear
# on their own. Treat them as throttling, not as a missing channel.
RETRY_STATUSES = (404, 429, 500, 502, 503)


def parse_published(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def video_id_from_entry(entry: dict[str, Any]) -> str:
    video_id = str(entry.get("yt_videoid") or "").strip()
    if video_id:
        return video_id
    link = str(entry.get("link") or "")
    if "v=" in link:
        return link.split("v=", 1)[1].split("&", 1)[0]
    if "/shorts/" in link:
        return link.split("/shorts/", 1)[1].split("?", 1)[0]
    return link.rsplit("/", 1)[-1]


def entries_from_xml(xml: str, since: datetime) -> list[dict[str, Any]]:
    parsed = feedparser.parse(xml)
    out: list[dict[str, Any]] = []
    for entry in parsed.entries:
        title = str(entry.get("title") or "").strip()
        published = parse_published(str(entry.get("published") or entry.get("updated") or ""))
        if not title or published is None or published < since:
            continue
        video_id = video_id_from_entry(entry)
        if not video_id:
            continue
        out.append(
            {
                "guid": f"yt:{video_id}",
                "title": title,
                "description": str(entry.get("summary") or entry.get("description") or ""),
                "publishedAt": int(published.timestamp() * 1000),
                "sourceUrl": str(
                    entry.get("link") or f"https://www.youtube.com/watch?v={video_id}"
                ),
                "youtubeVideoId": video_id,
            }
        )
    return out


def fetch_channel(
    channel_id: str, since: datetime, client: httpx.Client, attempts: int = 3
) -> list[dict[str, Any]]:
    """Recent videos for a channel, or an empty list if YouTube will not answer.

    A dead channel feed must not take the run down with it: the rest of the
    show still discovers from RSS, and the next run tries again.
    """
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    for attempt in range(attempts):
        try:
            response = client.get(url, headers={"User-Agent": USER_AGENT}, timeout=20.0)
            if response.status_code in RETRY_STATUSES and attempt < attempts - 1:
                time.sleep(2**attempt)
                continue
            response.raise_for_status()
            return entries_from_xml(response.text, since)
        except httpx.HTTPError as exc:
            if attempt == attempts - 1:
                LOGGER.warning("youtube channel %s unavailable: %s", channel_id, exc)
                return []
            time.sleep(2**attempt)
    return []
