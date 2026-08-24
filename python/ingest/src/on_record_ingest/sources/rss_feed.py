from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx

USER_AGENT = "on-record/0.1 rss-ingest"


def parse_rss_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError, IndexError):
        return None


def transcript_url(entry: dict[str, Any]) -> str:
    for key in ("podcast_transcript", "transcript"):
        value = entry.get(key)
        if isinstance(value, dict) and value.get("url"):
            return str(value["url"])
        if isinstance(value, str) and value.startswith("http"):
            return value
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict) and first.get("url"):
                return str(first["url"])
            if isinstance(first, str):
                return first
    links = entry.get("links") or []
    for link in links:
        if not isinstance(link, dict):
            continue
        rel = str(link.get("rel") or "")
        type_ = str(link.get("type") or "")
        if "transcript" in rel or "transcript" in type_ or type_ in {"text/vtt", "application/srt"}:
            return str(link.get("href") or "")
    return ""


def _enclosure(entry: dict[str, Any]) -> str:
    for link in entry.get("links") or []:
        if isinstance(link, dict) and str(link.get("rel") or "") == "enclosure":
            return str(link.get("href") or "")
    return ""


def _rss_item(entry: dict[str, Any], since: datetime) -> dict[str, Any] | None:
    title = str(entry.get("title") or "").strip()
    published = parse_rss_date(str(entry.get("published") or entry.get("updated") or ""))
    guid = str(entry.get("id") or entry.get("guid") or entry.get("link") or "").strip()
    if not title or not guid or published is None or published < since:
        return None
    return {
        "guid": guid,
        "title": title,
        "description": str(entry.get("summary") or entry.get("description") or ""),
        "publishedAt": int(published.timestamp() * 1000),
        "sourceUrl": str(entry.get("link") or ""),
        "audioUrl": _enclosure(entry),
        "transcriptUrl": transcript_url(entry),
    }


def entries_from_xml(xml: str, since: datetime) -> list[dict[str, Any]]:
    parsed = feedparser.parse(xml)
    out: list[dict[str, Any]] = []
    for entry in parsed.entries:
        item = _rss_item(entry, since)
        if item:
            out.append(item)
    return out


def fetch_feed(feed_url: str, since: datetime, client: httpx.Client) -> list[dict[str, Any]]:
    response = client.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=20.0)
    response.raise_for_status()
    return entries_from_xml(response.text, since)
