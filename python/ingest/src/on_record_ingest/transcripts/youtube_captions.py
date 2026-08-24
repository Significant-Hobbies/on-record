from __future__ import annotations

import logging

LOGGER = logging.getLogger(__name__)


def _field(item: object, name: str) -> object:
    value = getattr(item, name, None)
    if value is None and isinstance(item, dict):
        return item.get(name)
    return value


def fetch_cues(video_id: str) -> list[dict[str, float | str]]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError("youtube-transcript-api is required") from exc
    try:
        items = YouTubeTranscriptApi().fetch(video_id, languages=["en"])
    except Exception as exc:
        LOGGER.info("youtube captions failed video=%s error=%s", video_id, exc)
        return []
    cues: list[dict[str, float | str]] = []
    for item in items:
        text = str(_field(item, "text") or "").replace("\xa0", " ").replace("\n", " ").strip()
        if not text:
            continue
        cues.append(
            {
                "start": float(_field(item, "start") or 0),
                "duration": float(_field(item, "duration") or 0),
                "text": text,
            }
        )
    return cues
