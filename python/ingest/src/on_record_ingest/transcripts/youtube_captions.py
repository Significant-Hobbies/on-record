from __future__ import annotations

import logging

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApiException,
)

LOGGER = logging.getLogger(__name__)


class CaptionSourceUnavailable(RuntimeError):
    """The caption source failed without proving that captions are absent."""


def _field(item: object, name: str) -> object:
    value = getattr(item, name, None)
    if value is None and isinstance(item, dict):
        return item.get(name)
    return value


def fetch_cues(video_id: str) -> list[dict[str, float | str]]:
    try:
        items = YouTubeTranscriptApi().fetch(video_id, languages=["en"])
    except (NoTranscriptFound, TranscriptsDisabled):
        return []
    except YouTubeTranscriptApiException as exc:
        error = type(exc).__name__
        LOGGER.warning("youtube captions unavailable video=%s error=%s", video_id, error)
        raise CaptionSourceUnavailable(f"youtube captions unavailable: {error}") from exc
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
