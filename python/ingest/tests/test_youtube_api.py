from types import SimpleNamespace

import httpx
import pytest

from on_record_ingest.pipeline import run_youtube_verify
from on_record_ingest.sources.youtube_api import channels_for


def test_channel_lookup_failure_propagates_before_verification_can_mutate():
    def fail(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            channels_for(["video-id"], "key", client)


def test_youtube_verify_leaves_unconfigured_shows_untouched(monkeypatch):
    class Api:
        changes: list[tuple[object, ...]] = []

        def list_shows(self):
            return [{"id": "unknown-show", "slug": "not-in-the-seed"}]

        def list_episodes(self):
            return [
                {
                    "id": "episode-1",
                    "showId": "unknown-show",
                    "youtubeVideoId": "video-id",
                    "status": "published",
                }
            ]

        def set_episode_status(self, *args, **kwargs):
            self.changes.append((args, kwargs))

    monkeypatch.setattr(
        "on_record_ingest.pipeline.youtube_api.channels_for",
        lambda *_args, **_kwargs: {"video-id": "some-channel"},
    )
    api = Api()
    tally = run_youtube_verify(api, SimpleNamespace(youtube_api_key="key"))

    assert tally == {"kept": 0, "wrong_channel": 0, "gone": 0, "unverified": 1}
    assert api.changes == []
