from __future__ import annotations

from dataclasses import dataclass

import pytest
from youtube_transcript_api._errors import NoTranscriptFound, RequestBlocked

from on_record_ingest.transcripts import youtube_captions


class MissingApi:
    def fetch(self, _video_id: str, *, languages: list[str]) -> list[object]:
        raise NoTranscriptFound("abcDEF_1234", languages, None)


class BlockedApi:
    def fetch(self, video_id: str, *, languages: list[str]) -> list[object]:
        del languages
        raise RequestBlocked(video_id)


@dataclass
class Cue:
    text: str
    start: float
    duration: float


class WorkingApi:
    def fetch(self, _video_id: str, *, languages: list[str]) -> list[object]:
        del languages
        return [Cue(" hello\nworld ", 12.5, 3.0)]


def test_genuine_caption_absence_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(youtube_captions, "YouTubeTranscriptApi", MissingApi)
    assert youtube_captions.fetch_cues("abcDEF_1234") == []


def test_temporary_caption_failure_stays_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(youtube_captions, "YouTubeTranscriptApi", BlockedApi)
    with pytest.raises(youtube_captions.CaptionSourceUnavailable):
        youtube_captions.fetch_cues("abcDEF_1234")


def test_caption_items_are_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(youtube_captions, "YouTubeTranscriptApi", WorkingApi)
    assert youtube_captions.fetch_cues("abcDEF_1234") == [
        {"start": 12.5, "duration": 3.0, "text": "hello world"}
    ]
