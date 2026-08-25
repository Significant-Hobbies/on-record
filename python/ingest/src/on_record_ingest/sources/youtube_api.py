"""Full video listings from the YouTube Data API.

The channel RSS feed returns its latest 15 videos and does not paginate, which
capped us at 205 ids across 4,052 episodes however often we swept. The uploads
playlist returns everything: 1,029 videos for one channel that RSS showed 15 of.

Cost is 1 quota unit per page of 50 against a free 10,000/day allowance, so the
whole back catalogue of ten shows is around 100 units. Search would be 100
units *per query* and, worse, returns other people's videos — a title match
alone once scored a Georgia Cancer Center upload as a perfect hit for an a16z
episode.

This finds ids so a claim can deep-link into the moment it quotes. It cannot
fetch captions: `captions.download` needs OAuth as the video's owner.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

LOGGER = logging.getLogger("on_record_ingest")

API = "https://www.googleapis.com/youtube/v3/playlistItems"
PAGE = 50


def uploads_playlist(channel_id: str) -> str:
    """Every channel's uploads playlist is its id with the prefix swapped."""
    return "UU" + channel_id[2:] if channel_id.startswith("UC") else channel_id


def fetch_uploads(
    channel_id: str, api_key: str, client: httpx.Client, max_videos: int = 2000
) -> list[dict[str, Any]]:
    """Every video on a channel, newest first."""
    playlist = uploads_playlist(channel_id)
    videos: list[dict[str, Any]] = []
    token: str | None = None
    while len(videos) < max_videos:
        params = {
            "part": "snippet",
            "maxResults": str(PAGE),
            "playlistId": playlist,
            "key": api_key,
        }
        if token:
            params["pageToken"] = token
        try:
            response = client.get(API, params=params, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            LOGGER.warning("youtube api %s: %s", channel_id, exc)
            break
        payload = response.json()
        for item in payload.get("items") or []:
            snippet = item.get("snippet") or {}
            video_id = (snippet.get("resourceId") or {}).get("videoId")
            if not video_id:
                continue
            videos.append(
                {
                    "youtubeVideoId": video_id,
                    "title": str(snippet.get("title") or ""),
                    "publishedAt": str(snippet.get("publishedAt") or ""),
                }
            )
        token = payload.get("nextPageToken")
        if not token:
            break
    return videos


VIDEOS_API = "https://www.googleapis.com/youtube/v3/videos"
LOOKUP_PAGE = 50


def channels_for(video_ids: list[str], api_key: str, client: httpx.Client) -> dict[str, str | None]:
    """Which channel each video is on. Missing means the video is gone.

    Transport and API failures propagate so a transient lookup failure can
    never be mistaken for a deleted video by the mutating verification stage.
    """
    found: dict[str, str | None] = {}
    for start in range(0, len(video_ids), LOOKUP_PAGE):
        chunk = video_ids[start : start + LOOKUP_PAGE]
        response = client.get(
            VIDEOS_API,
            params={"part": "snippet", "id": ",".join(chunk), "key": api_key},
            timeout=40.0,
        )
        response.raise_for_status()
        for item in response.json().get("items") or []:
            found[item["id"]] = (item.get("snippet") or {}).get("channelId")
    return {video_id: found.get(video_id) for video_id in video_ids}
