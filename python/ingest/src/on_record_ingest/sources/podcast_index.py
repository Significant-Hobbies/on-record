from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any

import httpx

EPISODES_URL = "https://api.podcastindex.org/api/1.0/episodes/byfeedid"
USER_AGENT = "on-record/0.1 podcast-index-ingest"


def auth_headers(key: str, secret: str) -> dict[str, str]:
    auth_date = str(int(time.time()))
    auth = hashlib.sha1(f"{key}{secret}{auth_date}".encode()).hexdigest()
    return {
        "User-Agent": USER_AGENT,
        "X-Auth-Key": key,
        "X-Auth-Date": auth_date,
        "Authorization": auth,
        "Accept": "application/json",
    }


def parse_epoch(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def items_from_response(payload: dict[str, Any], since: datetime) -> list[dict[str, Any]]:
    rows = payload.get("items") if isinstance(payload.get("items"), list) else []
    out: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        published = parse_epoch(item.get("datePublished"))
        title = str(item.get("title") or "").strip()
        guid = str(item.get("guid") or item.get("id") or "").strip()
        if not guid or published is None or published < since or not title:
            continue
        out.append(
            {
                "guid": guid,
                "title": title,
                "description": str(item.get("description") or ""),
                "publishedAt": int(published.timestamp() * 1000),
                "sourceUrl": str(item.get("link") or item.get("enclosureUrl") or ""),
                "audioUrl": str(item.get("enclosureUrl") or ""),
                "durationS": int(item.get("duration") or 0) or None,
                "transcriptUrl": str(item.get("transcriptUrl") or ""),
                "raw": item,
            }
        )
    return out


def fetch_feed(
    feed_id: int,
    since: datetime,
    key: str,
    secret: str,
    client: httpx.Client,
) -> list[dict[str, Any]]:
    response = client.get(
        EPISODES_URL,
        params={"id": feed_id, "max": 40},
        headers=auth_headers(key, secret),
        timeout=20.0,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return []
    return items_from_response(payload, since)
