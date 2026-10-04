from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

from on_record_ingest import pipeline
from on_record_ingest.transcripts.youtube_captions import CaptionSourceUnavailable

NOW = datetime(2026, 10, 4, 6, 0, tzinfo=UTC)


def _ep(eid, published, attempts=0, ago_days=0.0):
    row = {"id": eid, "publishedAt": published, "status": "discovered"}
    if attempts:
        row["statusDetail"] = pipeline.attempt_detail(attempts, NOW - timedelta(days=ago_days))
    return row


def test_backoff_schedule_is_1_3_7_then_14_days():
    days = [pipeline.backoff_for(n).days for n in (1, 2, 3, 4, 9)]
    assert days == [1, 3, 7, 14, 14]


def test_episode_is_skipped_until_backoff_elapses():
    assert pipeline.in_backoff(_ep("a", 1, attempts=1, ago_days=0.5), NOW)
    assert not pipeline.in_backoff(_ep("a", 1, attempts=1, ago_days=1.01), NOW)
    assert pipeline.in_backoff(_ep("a", 1, attempts=2, ago_days=2.9), NOW)
    assert pipeline.in_backoff(_ep("a", 1, attempts=5, ago_days=13), NOW)
    assert not pipeline.in_backoff(_ep("a", 1, attempts=5, ago_days=14.1), NOW)


def test_unrelated_or_malformed_status_detail_is_not_backoff():
    assert pipeline.transcript_attempts({"statusDetail": "something else"}) == (0, None)
    assert pipeline.transcript_attempts({"statusDetail": pipeline.ATTEMPT_PREFIX + "{"}) == (
        0,
        None,
    )
    assert not pipeline.in_backoff({"id": "x"}, NOW)


def test_plan_orders_never_attempted_first_then_newest_and_caps():
    episodes = [
        _ep("old-fresh", 100),
        _ep("new-retry", 900, attempts=1, ago_days=2),
        _ep("new-fresh", 800),
        _ep("mid-fresh", 500),
        _ep("blocked", 950, attempts=1, ago_days=0.1),
    ]
    batch, skipped, remaining = pipeline.plan_transcript_batch(episodes, NOW, 3)
    assert [e["id"] for e in batch] == ["new-fresh", "mid-fresh", "old-fresh"]
    assert (skipped, remaining) == (1, 1)
    batch, _, remaining = pipeline.plan_transcript_batch(episodes, NOW, 0)
    assert [e["id"] for e in batch][-1] == "new-retry"
    assert remaining == 0


def test_force_ignores_backoff():
    episodes = [_ep("a", 1, attempts=1, ago_days=0.1)]
    batch, skipped, _ = pipeline.plan_transcript_batch(episodes, NOW, 10, honor_backoff=False)
    assert len(batch) == 1 and skipped == 0


def test_default_cap_reads_env(monkeypatch):
    monkeypatch.delenv("INGEST_MAX_EPISODES", raising=False)
    assert pipeline.default_max_episodes() == 100
    monkeypatch.setenv("INGEST_MAX_EPISODES", "7")
    assert pipeline.default_max_episodes() == 7
    monkeypatch.setenv("INGEST_MAX_EPISODES", "junk")
    assert pipeline.default_max_episodes() == 100


class _Api:
    def __init__(self, episodes):
        self.episodes = episodes
        self.statuses = []

    def list_episodes(self, status=None, **kwargs):
        return list(self.episodes)

    def set_episode_status(self, episode_id, **fields):
        self.statuses.append((episode_id, fields))


def test_run_transcripts_caps_records_failures_and_logs(monkeypatch, caplog):
    episodes = [_ep(f"e{i}", i) for i in range(5)] + [_ep("held", 99, attempts=1, ago_days=0.2)]
    api = _Api(episodes)
    tried = []

    def fake(api_, cfg, episode, client, opts, people):
        tried.append(episode["id"])
        if episode["id"] == "e4":
            raise_failure = CaptionSourceUnavailable("RequestBlocked")
            pipeline.LOGGER.warning("left: %s", raise_failure)
            pipeline.record_transcript_failure(api_, episode, NOW)
            return False
        return True

    monkeypatch.setattr(pipeline, "run_transcript_episode", fake)
    with caplog.at_level(logging.INFO, logger="on_record_ingest"):
        count = pipeline.run_transcripts(api, None, False, False, max_episodes=3, now=NOW)
    assert tried == ["e4", "e3", "e2"]
    assert count == 2
    episode_id, fields = api.statuses[0]
    assert episode_id == "e4" and fields["status"] == "discovered"
    detail = json.loads(fields["statusDetail"][len(pipeline.ATTEMPT_PREFIX) :])
    assert detail["attempts"] == 1
    summary = [r.message for r in caplog.records if "transcripts summary" in r.message]
    assert summary == [
        "transcripts summary processed=3 resolved=2 skipped_backoff=1 remaining_backlog=2"
    ]


def test_failed_fetch_increments_attempts(monkeypatch):
    api = _Api([])
    ep = _ep("a", 1, attempts=2, ago_days=4)
    pipeline.record_transcript_failure(api, ep, NOW)
    assert (
        json.loads(api.statuses[0][1]["statusDetail"][len(pipeline.ATTEMPT_PREFIX) :])["attempts"]
        == 3
    )
