from __future__ import annotations

import logging

LOGGER = logging.getLogger(__name__)


def fetch_cues(video_id: str) -> list[dict[str, float | str]]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError("youtube-transcript-api is required") from exc
    try:
        items = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
    except Exception as exc:
        LOGGER.info("youtube captions failed video=%s error=%s", video_id, exc)
        return []
    cues: list[dict[str, float | str]] = []
    for item in items:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        cues.append(
            {
                "start": float(item.get("start") or 0),
                "duration": float(item.get("duration") or 0),
                "text": text,
            }
        )
    return cues
