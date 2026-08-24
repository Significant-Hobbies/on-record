from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx

USER_AGENT = "on-record/0.1 youtube-rss"


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


def fetch_channel(channel_id: str, since: datetime, client: httpx.Client) -> list[dict[str, Any]]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    response = client.get(url, headers={"User-Agent": USER_AGENT}, timeout=20.0)
    response.raise_for_status()
    return entries_from_xml(response.text, since)
