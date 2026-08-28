import json
from dataclasses import replace

import httpx
import pytest

from on_record_ingest import pipeline
from on_record_ingest.config import settings as load_settings


def _publisher_cues():
    return [
        {
            "duration": 7.0,
            "sourceUrl": "https://www.youtube.com/watch?v=abcDEF_1234&t=0",
            "speaker": "lex-fridman",
            "speakerName": "Lex Fridman",
            "start": 0.0,
            "text": "A publisher-authored opening turn.",
        },
        {
            "duration": 0.0,
            "sourceUrl": "https://www.youtube.com/watch?v=abcDEF_1234&t=7",
            "speaker": "andrej-karpathy",
            "speakerName": "Andrej Karpathy",
            "start": 7.0,
            "text": "A publisher-authored answer.",
        },
    ]


def _cwt_cues():
    return [
        {
            "duration": 0.0,
            "speaker": "tyler-cowen",
            "speakerName": "COWEN",
            "speakerNameSource": "publisher",
            "start": 0.0,
            "text": "A publisher-authored question.",
        },
        {
            "duration": 0.0,
            "speaker": "guest",
            "speakerName": "GUEST",
            "speakerNameSource": "publisher",
            "start": 1.0,
            "text": "A publisher-authored answer.",
        },
    ]


def _acquired_cues():
    return [
        {
            "duration": 0.0,
            "speaker": "ben-gilbert",
            "speakerName": "Ben",
            "speakerNameSource": "publisher",
            "start": 0.0,
            "text": "A publisher-authored Acquired turn.",
        }
    ]


def _lennys_cues():
    return [
        {
            "duration": 4.0,
            "speaker": "lenny-rachitsky",
            "speakerName": "Lenny Rachitsky",
            "speakerNameSource": "publisher",
            "start": 0.0,
            "text": "A publisher-approved timed Substack transcript turn.",
        }
    ]


def test_lennys_publisher_json_precedes_youtube(monkeypatch):
    requested: list[tuple[str, str, dict[str, str]]] = []
    monkeypatch.setattr(
        pipeline,
        "fetch_lennys_cues",
        lambda source_url, client, episode_title, episode_guid, identity_map: (
            requested.append((source_url, episode_guid, identity_map)) or _lennys_cues()
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "fetch_cues",
        lambda video_id: (_ for _ in ()).throw(AssertionError("captions should not be fetched")),
    )
    with httpx.Client() as client:
        kind, cues = pipeline.resolve_cues(
            {
                "guid": "substack:post:123",
                "lennysSpeakerMap": {"lenny rachitsky": "lenny-rachitsky"},
                "sourceUrl": "https://www.lennysnewsletter.com/p/a-useful-episode",
                "title": "A Useful Episode",
                "youtubeVideoId": "abcDEF_1234",
            },
            client,
        )
    assert kind == pipeline.LENNYS_PUBLISHER_JSON
    assert cues == _lennys_cues()
    assert requested == [
        (
            "https://www.lennysnewsletter.com/p/a-useful-episode",
            "substack:post:123",
            {"lenny rachitsky": "lenny-rachitsky"},
        )
    ]


def test_lennys_roster_map_uses_unique_full_and_first_names():
    detail = {
        "people": [
            {"personId": "host-id", "confidence": 1.0},
            {"personId": "guest-id", "confidence": 1.0},
            {"personId": "other-id", "confidence": 1.0},
        ]
    }
    people = {
        "host-id": {"slug": "lenny-rachitsky", "name": "Lenny Rachitsky"},
        "guest-id": {"slug": "jen-abel", "name": "Jen Abel"},
        "other-id": {"slug": "jen-smith", "name": "Jen Smith"},
    }
    mapping = pipeline.lennys_speaker_map(detail, people)
    assert mapping["lenn"] == "lenny-rachitsky"
    assert mapping["lenny"] == "lenny-rachitsky"
    assert mapping["lenny rachitsky"] == "lenny-rachitsky"
    assert mapping["jen abel"] == "jen-abel"
    assert "jen" not in mapping


def test_acquired_publisher_page_precedes_youtube(monkeypatch):
    requested: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        pipeline,
        "fetch_acquired_cues",
        lambda source_url, client, episode_title, speaker_map: (
            requested.append((source_url, speaker_map)) or _acquired_cues()
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "fetch_cues",
        lambda video_id: (_ for _ in ()).throw(AssertionError("captions should not be fetched")),
    )
    with httpx.Client() as client:
        kind, cues = pipeline.resolve_cues(
            {
                "acquiredSpeakerMap": {"ben": "ben-gilbert"},
                "sourceUrl": "https://www.acquired.fm/episodes/formula-1",
                "title": "Formula 1",
                "youtubeVideoId": "abcDEF_1234",
            },
            client,
        )
    assert kind == pipeline.ACQUIRED_PUBLISHER_HTML
    assert cues == _acquired_cues()
    assert requested == [("https://www.acquired.fm/episodes/formula-1", {"ben": "ben-gilbert"})]


def test_acquired_root_source_resolves_through_official_sitemap(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "acquired_episode_url_from_source",
        lambda source_url, title, client: "https://www.acquired.fm/episodes/formula-1",
    )
    monkeypatch.setattr(
        pipeline,
        "fetch_acquired_cues",
        lambda source_url, client, episode_title, speaker_map: _acquired_cues(),
    )
    with httpx.Client() as client:
        kind, cues = pipeline.resolve_cues(
            {
                "acquiredSpeakerMap": {"ben": "ben-gilbert"},
                "sourceUrl": "http://acquired.fm/",
                "title": "Formula 1",
            },
            client,
        )
    assert kind == pipeline.ACQUIRED_PUBLISHER_HTML
    assert cues == _acquired_cues()


def test_acquired_roster_map_keeps_only_unique_first_and_last_names():
    detail = {
        "people": [
            {"personId": "ben-id", "confidence": 1.0},
            {"personId": "guest-id", "confidence": 0.9},
            {"personId": "other-id", "confidence": 0.9},
        ]
    }
    people = {
        "ben-id": {"slug": "ben-gilbert", "name": "Ben Gilbert"},
        "guest-id": {"slug": "first-smith", "name": "Alex Smith"},
        "other-id": {"slug": "second-smith", "name": "Jordan Smith"},
    }
    mapping = pipeline.acquired_speaker_map(detail, people)
    assert mapping["ben"] == "ben-gilbert"
    assert mapping["gilbert"] == "ben-gilbert"
    assert mapping["alex"] == "first-smith"
    assert mapping["jordan"] == "second-smith"
    assert "smith" not in mapping


def test_acquired_roster_map_uses_initials_and_publisher_host_labels():
    detail = {
        "people": [
            {"personId": "host-id", "confidence": 1.0},
            {"personId": "guest-id", "confidence": 0.9},
        ]
    }
    people = {
        "host-id": {"slug": "ben-gilbert", "name": "Ben Gilbert"},
        "guest-id": {"slug": "ben-thompson", "name": "Ben Thompson"},
    }
    mapping = pipeline.acquired_speaker_map(detail, people)
    assert mapping["ben"] == "ben-gilbert"
    assert mapping["bg"] == "ben-gilbert"
    assert mapping["bt"] == "ben-thompson"
    assert mapping["ben thompson"] == "ben-thompson"


def test_cwt_publisher_page_precedes_generic_structured_transcript(monkeypatch):
    requested: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        pipeline,
        "fetch_cwt_cues",
        lambda source_url, client, episode_title, speaker_map: (
            requested.append((source_url, speaker_map)) or _cwt_cues()
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "structured_transcript_cues",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("publisher page should win before generic transcript parsing")
        ),
    )
    with httpx.Client() as client:
        kind, cues = pipeline.resolve_cues(
            {
                "cwtSpeakerMap": {"cowen": "tyler-cowen", "guest": "guest"},
                "sourceUrl": "https://conversationswithtyler.com/episodes/a-real-episode/",
                "title": "A Real Episode",
                "transcriptUrl": "https://example.test/transcript.vtt",
            },
            client,
        )
    assert kind == pipeline.CWT_PUBLISHER_HTML
    assert cues == _cwt_cues()
    assert requested == [
        (
            "https://conversationswithtyler.com/episodes/a-real-episode/",
            {"cowen": "tyler-cowen", "guest": "guest"},
        )
    ]


def test_cwt_roster_map_keeps_only_unique_labels():
    detail = {
        "people": [
            {"personId": "host-id", "confidence": 1.0},
            {"personId": "guest-id", "confidence": 0.9},
            {"personId": "other-id", "confidence": 0.9},
            {"personId": "mention-id", "confidence": 0.1},
        ]
    }
    people = {
        "host-id": {"slug": "tyler-cowen", "name": "Tyler Cowen"},
        "guest-id": {"slug": "first-smith", "name": "First Smith"},
        "other-id": {"slug": "second-smith", "name": "Second Smith"},
        "mention-id": {"slug": "wrong", "name": "Wrong Person"},
    }
    mapping = pipeline.cwt_speaker_map(detail, people)
    assert mapping["cowen"] == "tyler-cowen"
    assert mapping["t cowen"] == "tyler-cowen"
    assert mapping["first smith"] == "first-smith"
    assert mapping["second smith"] == "second-smith"
    assert "smith" not in mapping
    assert "wrong person" not in mapping


def test_publisher_transcript_precedes_youtube_captions(monkeypatch):
    requested: list[str] = []
    monkeypatch.setattr(
        pipeline,
        "fetch_lex_cues",
        lambda source_url, client, episode_title="": (
            requested.append(source_url) or _publisher_cues()
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "fetch_cues",
        lambda video_id: (_ for _ in ()).throw(AssertionError("captions should not be fetched")),
    )
    with httpx.Client() as client:
        kind, cues = pipeline.resolve_cues(
            {
                "sourceUrl": "https://lexfridman.com/a-real-episode/",
                "youtubeVideoId": "abcDEF_1234",
            },
            client,
        )
    assert kind == pipeline.PUBLISHER_HTML
    assert cues == _publisher_cues()
    assert requested == ["https://lexfridman.com/a-real-episode/"]


def test_canonical_lex_page_precedes_unrelated_transcript_link_in_description(monkeypatch):
    requested: list[str] = []
    monkeypatch.setattr(
        pipeline,
        "fetch_lex_cues",
        lambda source_url, client, episode_title="": (
            requested.append(source_url) or _publisher_cues()
        ),
    )
    with httpx.Client() as client:
        kind, cues = pipeline.resolve_cues(
            {
                "description": "Previous episode: https://lexfridman.com/other-guest-transcript",
                "sourceUrl": "https://lexfridman.com/current-episode/",
            },
            client,
        )
    assert kind == pipeline.PUBLISHER_HTML
    assert cues == _publisher_cues()
    assert requested == ["https://lexfridman.com/current-episode/"]


def test_empty_publisher_result_falls_through_to_youtube(monkeypatch):
    monkeypatch.setattr(pipeline, "fetch_lex_cues", lambda source_url, client, episode_title="": [])
    monkeypatch.setattr(
        pipeline,
        "fetch_cues",
        lambda video_id: [{"duration": 1.0, "start": 0.0, "text": "caption"}],
    )
    with httpx.Client() as client:
        kind, cues = pipeline.resolve_cues(
            {
                "sourceUrl": "https://lexfridman.com/an-episode/",
                "youtubeVideoId": "abcDEF_1234",
            },
            client,
        )
    assert kind == "youtube_captions"
    assert cues[0]["text"] == "caption"


def test_structured_transcript_server_failure_stays_retryable():
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(pipeline.PublisherSourceUnavailable):
            pipeline.structured_transcript_cues("https://example.com/transcript.vtt", client)


def test_youtube_canonical_episode_uses_exact_metadata_transcript_link(monkeypatch):
    requested: list[str] = []
    monkeypatch.setattr(
        pipeline,
        "fetch_lex_cues",
        lambda source_url, client, episode_title="": (
            requested.append(source_url) or _publisher_cues()
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "fetch_cues",
        lambda video_id: (_ for _ in ()).throw(AssertionError("captions should not be fetched")),
    )
    with httpx.Client() as client:
        kind, cues = pipeline.resolve_cues(
            {
                "description": (
                    "Transcript:\nhttps://lexfridman.com/exact-guest-and-topic-transcript\n"
                ),
                "sourceUrl": "https://www.youtube.com/watch?v=abcDEF_1234",
                "youtubeVideoId": "abcDEF_1234",
            },
            client,
        )
    assert kind == pipeline.PUBLISHER_HTML
    assert cues == _publisher_cues()
    assert requested == ["https://lexfridman.com/exact-guest-and-topic-transcript"]


class _TranscriptApi:
    def __init__(self, youtube_video_id=None) -> None:
        self.segments = []
        self.status = None
        self.youtube_video_id = youtube_video_id

    def list_episodes(self, status=None):
        return [
            {
                "id": "episode-1",
                "sourceUrl": "https://lexfridman.com/an-episode/",
                "status": "discovered",
            }
        ]

    def get_raw(self, episode_id, key=None):
        return {"content": json.dumps({"sourceUrl": "https://lexfridman.com/an-episode/"})}

    def get_episode(self, episode_id):
        return {
            "episode": {
                "id": episode_id,
                "sourceUrl": "https://lexfridman.com/an-episode/",
                "status": "discovered",
                "title": "#123 - A Real Episode",
                "youtubeVideoId": self.youtube_video_id,
            },
            "people": [],
        }

    def put_raw(self, episode_id, key, content, content_type):
        return None

    def put_segments(self, episode_id, segments, transcript_kind):
        self.segments = segments
        return ["segment-1"]

    def set_episode_status(self, episode_id, **fields):
        self.status = fields


def test_source_only_lex_episode_is_not_skipped(monkeypatch):
    api = _TranscriptApi()
    monkeypatch.setattr(
        pipeline,
        "fetch_lex_cues",
        lambda source_url, client, episode_title="": _publisher_cues(),
    )
    count = pipeline.run_transcripts(
        api,
        episode_id=None,
        force=False,
        dry_run=False,
    )
    assert count == 1
    assert [segment["speakerHint"] for segment in api.segments] == [
        "lex-fridman",
        "andrej-karpathy",
    ]
    assert all(segment["diarLabel"] is None for segment in api.segments)
    assert api.status["transcriptKind"] == pipeline.PUBLISHER_HTML
    assert api.status["youtubeVideoId"] == "abcDEF_1234"


def test_targeted_transcript_fetches_the_episode_directly(monkeypatch):
    api = _TranscriptApi()
    monkeypatch.setattr(
        api,
        "list_episodes",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not paginate the corpus")),
    )
    monkeypatch.setattr(
        pipeline,
        "fetch_lex_cues",
        lambda source_url, client, episode_title="": _publisher_cues(),
    )
    count = pipeline.run_transcripts(api, episode_id="episode-1", force=False, dry_run=False)
    assert count == 1


def test_transcript_listing_applies_the_show_filter():
    class Api:
        def list_episodes(self, status=None, show_id=None):
            assert status == "discovered"
            assert show_id == "show-1"
            return []

    assert (
        pipeline.run_transcripts(
            Api(),
            episode_id=None,
            force=False,
            dry_run=True,
            show_id="show-1",
        )
        == 0
    )


def test_publisher_timestamp_video_overrides_a_stale_episode_video(monkeypatch):
    api = _TranscriptApi(youtube_video_id="wrongID_123")
    monkeypatch.setattr(
        pipeline,
        "fetch_lex_cues",
        lambda source_url, client, episode_title="": _publisher_cues(),
    )
    count = pipeline.run_transcripts(
        api,
        episode_id="episode-1",
        force=True,
        dry_run=False,
    )
    assert count == 1
    assert api.status["youtubeVideoId"] == "abcDEF_1234"


def test_missing_video_id_stays_null():
    assert pipeline.transcript_video_id("rss_vtt", [], None) is None


def test_temporary_caption_failure_does_not_retire_episode(monkeypatch):
    api = _TranscriptApi(youtube_video_id="abcDEF_1234")
    monkeypatch.setattr(pipeline, "fetch_lex_cues", lambda *args: [])
    monkeypatch.setattr(
        pipeline,
        "fetch_cues",
        lambda _video_id: (_ for _ in ()).throw(
            pipeline.CaptionSourceUnavailable("temporarily blocked")
        ),
    )
    count = pipeline.run_transcripts(api, episode_id="episode-1", force=True, dry_run=False)
    assert count == 0
    assert api.status is None


def test_temporary_publisher_failure_does_not_retire_episode(monkeypatch):
    api = _TranscriptApi()
    monkeypatch.setattr(
        pipeline,
        "fetch_lex_cues",
        lambda *args: (_ for _ in ()).throw(
            pipeline.PublisherSourceUnavailable("temporarily unavailable")
        ),
    )
    count = pipeline.run_transcripts(api, episode_id="episode-1", force=True, dry_run=False)
    assert count == 0
    assert api.status is None


def test_resolved_publisher_speakers_never_reenter_identification(monkeypatch):
    api = _TranscriptApi()
    monkeypatch.setattr(
        pipeline,
        "resolve_segment_speakers",
        lambda *args: (_ for _ in ()).throw(AssertionError("speaker identification must not run")),
    )
    pipeline.store_transcript(
        api,
        object(),
        {"id": "episode-1"},
        _publisher_cues(),
        pipeline.PUBLISHER_HTML,
        "abcDEF_1234",
    )
    assert all(segment["diarLabel"] is None for segment in api.segments)


def test_unknown_publisher_name_cannot_fall_back_to_roster_guessing():
    api = _TranscriptApi()
    unknown_cue = {
        "duration": 0.0,
        "speakerName": "Unlisted Researcher",
        "speakerNameSource": "publisher",
        "start": 0.0,
        "text": "A publisher turn whose name is not in the roster.",
    }
    pipeline.store_transcript(
        api,
        None,
        {"id": "episode-1"},
        [unknown_cue],
        pipeline.PUBLISHER_HTML,
        None,
    )
    segment = api.segments[0]
    assert segment["speakerHint"] == pipeline.UNKNOWN
    assert pipeline.segment_action(segment, set(), set(), False, "all", "extract-v4") == "skip"


def test_generic_transcript_without_identification_is_explicitly_unknown():
    api = _TranscriptApi()
    pipeline.store_transcript(
        api,
        None,
        {"id": "episode-1"},
        [{"duration": 4.0, "start": 0.0, "text": "An anonymous caption turn."}],
        "rss_vtt",
        None,
    )
    segment = api.segments[0]
    assert segment["speakerHint"] == pipeline.UNKNOWN
    assert pipeline.segment_action(segment, set(), set(), False, "all", "extract-v4") == "skip"


def test_matching_zero_result_attempt_is_a_checkpoint_unless_forced():
    segment = {"id": "segment-1", "speakerHint": "known", "text": "I love Cursor."}
    attempted = {("segment-1", "extract-v4", "recs")}
    assert (
        pipeline.segment_action(segment, set(), attempted, False, "recs", "extract-v4")
        == "attempted"
    )
    assert pipeline.segment_action(segment, set(), attempted, True, "recs", "extract-v4") == "rec"


def test_recommendation_focus_revisits_general_claim_but_respects_any_rec_checkpoint():
    segment = {"id": "segment-1", "speakerHint": "known", "text": "I love Cursor."}
    assert (
        pipeline.segment_action(segment, {"segment-1"}, set(), False, "recs", "extract-recs-v5")
        == "rec"
    )
    previous_rec_attempt = {("segment-1", "extract-recs-v4", "recs")}
    assert (
        pipeline.segment_action(
            segment,
            {"segment-1"},
            previous_rec_attempt,
            False,
            "recs",
            "extract-recs-v5",
        )
        == "attempted"
    )


def test_unlabelled_generic_transcript_with_identification_config_stays_unknown():
    segments = [{"diarLabel": None, "speakerHint": None, "text": "No voice label."}]
    resolved = pipeline.resolve_segment_speakers(
        _TranscriptApi(),
        object(),
        {"id": "episode-1", "transcriptKind": "rss_vtt"},
        segments,
    )
    assert resolved[0]["speakerHint"] == pipeline.UNKNOWN


def test_identification_roster_excludes_people_judged_to_be_mentions():
    class Api:
        def get_episode(self, episode_id):
            return {
                "people": [
                    {"personId": "host-id", "role": "host", "confidence": 1.0},
                    {"personId": "guest-id", "role": "guest", "confidence": 0.95},
                    {"personId": "mention-id", "role": "guest", "confidence": 0.1},
                ]
            }

        def list_people(self):
            return [
                {"id": "host-id", "name": "Host", "slug": "host"},
                {"id": "guest-id", "name": "Guest", "slug": "guest"},
                {"id": "mention-id", "name": "Mention", "slug": "mention"},
            ]

    roster = pipeline.episode_roster(Api(), "episode-1")
    assert [person["slug"] for person in roster] == ["host", "guest"]


def test_local_extraction_does_not_require_a_fake_api_key(monkeypatch):
    local = replace(
        load_settings(),
        ai_api_key="",
        ai_base_url="http://127.0.0.1:1234/v1",
    )
    remote = replace(local, ai_base_url="https://ai.example.test/v1")
    monkeypatch.setattr(pipeline, "_extract_targets", lambda api, episode_id, show_id: [])
    opts = pipeline.ExtractOpts(episode_id=None, dry_run=False)
    assert pipeline.run_extract(object(), local, {}, opts) == 0
    with pytest.raises(SystemExit, match="AI_API_KEY is required"):
        pipeline.run_extract(object(), remote, {}, opts)


def test_recommendation_focus_keeps_only_claims_with_surviving_references():
    claims = [
        {"assertion": "A bold observation.", "references": []},
        {
            "assertion": "A book recommendation.",
            "references": [{"kind": "book", "name": "The Beginning of Infinity"}],
        },
    ]
    assert pipeline.claims_for_focus(claims, "recs") == [claims[1]]
    assert pipeline.claims_for_focus(claims, "all") == claims


def test_book_focus_revisits_recommendation_checkpoint_and_keeps_only_books():
    segment = {
        "id": "segment-1",
        "speakerHint": "known",
        "text": "I've read The Beginning of Infinity three times now.",
    }
    attempted = {("segment-1", "extract-recs-v5", "recs")}
    assert (
        pipeline.segment_action(
            segment, {"segment-1"}, attempted, False, "books", "extract-books-v1"
        )
        == "book"
    )
    claims = [
        {
            "references": [
                {"kind": "book", "name": "The Beginning of Infinity", "role": "uses"},
                {"kind": "app", "name": "Kindle", "role": "uses"},
            ]
        }
    ]
    assert pipeline.claims_for_focus(claims, "books") == [
        {"references": [{"kind": "book", "name": "The Beginning of Infinity", "role": "uses"}]}
    ]


def test_book_answer_focus_keeps_only_direct_answers_with_its_own_checkpoint():
    context = pipeline.EpisodeExtractContext(
        api=object(),
        cfg=object(),
        people_map={},
        episode={"id": "episode-1"},
        opts=pipeline.ExtractOpts(
            episode_id="episode-1", dry_run=True, focus="book_answers", batch_size=8
        ),
        prompt_version="extract-book-answers-v4",
        already={"answer"},
        attempted=set(),
        guests=[],
        published_claims=0,
    )
    question = {
        "id": "question",
        "idx": 0,
        "speakerHint": "host",
        "text": "What are two or three books that you recommend most often?",
    }
    answer = {
        "id": "answer",
        "idx": 1,
        "speakerHint": "guest",
        "text": "The first is The Power Broker by Robert Caro, which changed how I think.",
    }
    candidates, skipped = pipeline._batch_candidates(context, [question, answer])
    assert skipped == 1
    assert candidates == [{**answer, "bookQuestion": question["text"]}]


def test_book_focus_never_routes_candidates_through_reference_free_rules(monkeypatch):
    context = pipeline.EpisodeExtractContext(
        api=object(),
        cfg=object(),
        people_map={},
        episode={"id": "episode-1"},
        opts=pipeline.ExtractOpts(
            episode_id="episode-1", dry_run=True, focus="books", batch_size=8
        ),
        prompt_version="extract-books-v1",
        already=set(),
        attempted=set(),
        guests=[],
        published_claims=0,
    )
    segment = {
        "id": "segment-1",
        "idx": 0,
        "speakerHint": "guest-one",
        "text": (
            "I've read The Beginning of Infinity three times because it changed how I think, "
            "and I recommend the book to every founder."
        ),
    }
    monkeypatch.setattr(
        pipeline, "deterministic_claim_for_segment", lambda _segment: {"quote": "x"}
    )

    assert pipeline._extract_episode_batches(context, [segment]) == (0, 1, 0)


def test_exact_segment_speaker_allows_extraction_without_episode_roster():
    class Api:
        def get_episode(self, episode_id):
            return {
                "episode": {"id": episode_id},
                "people": [],
                "segments": [
                    {
                        "id": "segment-1",
                        "idx": 0,
                        "speakerHint": "publisher-guest",
                        "text": (
                            "I recommend Anki because I use it every day to remember "
                            "technical material."
                        ),
                    }
                ],
                "extractedSegmentIds": [],
            }

    opts = pipeline.ExtractOpts(episode_id="episode-1", dry_run=True, focus="recs")
    assert pipeline._extract_episode(Api(), object(), {}, {"id": "episode-1"}, opts) == (0, 1, 0)


def test_batch_extraction_posts_one_checkpoint_per_candidate(monkeypatch):
    class Api:
        def __init__(self):
            self.posts = []

        def get_episode(self, episode_id):
            return {
                "episode": {"id": episode_id},
                "people": [],
                "segments": [
                    {
                        "id": "segment-1",
                        "idx": 0,
                        "speakerHint": "guest-one",
                        "text": (
                            "I recommend direct customer contact because it keeps product "
                            "priorities tied to real problems."
                        ),
                    },
                    {
                        "id": "segment-2",
                        "idx": 1,
                        "speakerHint": "guest-one",
                        "text": (
                            "I use short weekly feedback loops because they reduce the distance "
                            "between a customer problem and the decision maker."
                        ),
                    },
                ],
                "extractedSegmentIds": [],
                "extractionAttempts": [],
            }

        def post_claims(self, episode_id, claims, llm_runs):
            self.posts.append((episode_id, claims, llm_runs))
            return {
                "results": [
                    {"id": f"claim-{index}", "reviewStatus": "published"}
                    for index, _claim in enumerate(claims)
                ]
            }

    monkeypatch.setattr(
        pipeline,
        "extract_one_batch",
        lambda cfg, people_map, segments, focus="all": (
            [
                {
                    "segmentId": "segment-1",
                    "personId": "person-1",
                    "assertion": "The speaker values direct customer contact.",
                }
            ],
            {
                "latencyMs": 20,
                "model": "local-test",
                "promptVersion": "extract-v4",
                "reason": "ok",
                "requestJson": {"segmentIds": ["segment-1", "segment-2"]},
                "responseJson": {"model": "local-test"},
            },
        ),
    )
    api = Api()
    cfg = replace(load_settings(), ai_base_url="http://127.0.0.1:1234/v1")
    opts = pipeline.ExtractOpts(episode_id="episode-1", dry_run=False, batch_size=2)
    result = pipeline._extract_episode(
        api,
        cfg,
        {"guest-one": "person-1"},
        {"id": "episode-1"},
        opts,
    )
    assert result == (1, 1, 0)
    assert len(api.posts) == 1
    _, claims, runs = api.posts[0]
    assert claims[0]["segmentId"] == "segment-1"
    assert [run["segmentId"] for run in runs] == ["segment-1", "segment-2"]
    assert [run["accepted"] for run in runs] == [True, False]
    assert runs[1]["reason"] == "batch_no_quality_claim"


def test_batch_target_counts_existing_published_claims(monkeypatch):
    class Api:
        def get_episode(self, episode_id):
            return {
                "episode": {"id": episode_id},
                "people": [],
                "segments": [
                    {
                        "id": "segment-1",
                        "idx": 0,
                        "speakerHint": "guest-one",
                        "text": "I think durable products solve a recurring customer problem.",
                    }
                ],
                "extractedSegmentIds": [],
                "extractionAttempts": [],
                "publishedClaimCount": 10,
            }

    monkeypatch.setattr(
        pipeline,
        "extract_one_batch",
        lambda *args: (_ for _ in ()).throw(AssertionError("target already met")),
    )
    cfg = replace(load_settings(), ai_base_url="http://127.0.0.1:1234/v1")
    opts = pipeline.ExtractOpts(
        episode_id="episode-1", dry_run=False, batch_size=8, target_claims=10
    )
    assert pipeline._extract_episode(Api(), cfg, {}, {"id": "episode-1"}, opts) == (0, 0, 0)


def test_duplicate_api_outcome_does_not_inflate_newly_published_count():
    class Api:
        def post_claims(self, episode_id, claims, llm_runs):
            return {
                "results": [
                    {
                        "id": "existing-claim",
                        "reason": "duplicate",
                        "reviewStatus": "published",
                    }
                ]
            }

    cfg = replace(load_settings(), ai_base_url="http://127.0.0.1:1234/v1")
    opts = pipeline.ExtractOpts(episode_id="episode-1", dry_run=False)
    context = pipeline.EpisodeExtractContext(
        api=Api(),
        cfg=cfg,
        people_map={},
        episode={"id": "episode-1"},
        opts=opts,
        prompt_version="extract-v4",
        already=set(),
        attempted=set(),
        guests=[],
        published_claims=0,
    )
    claim = {
        "segmentId": "segment-1",
        "personId": "person-1",
        "assertion": "The speaker recommends a durable feedback loop.",
    }
    saved, newly_published = pipeline._post_candidate_claims(
        context,
        [{"id": "segment-1"}],
        [claim],
        {"reason": "ok"},
        [],
        0,
    )
    assert saved == [claim]
    assert newly_published == 0


def test_extraction_defaults_to_full_episode_in_maximum_batches():
    args = pipeline._argument_parser().parse_args(["--stage", "extract"])
    assert args.batch_size == 20
    assert args.target_claims == 0
    assert args.skip_episodes == 0
    assert args.rules_only is False


def test_unverified_speaker_claims_use_a_non_person_attribution_tier():
    claims = pipeline.attach_person_ids(
        [{"speakerRaw": pipeline.UNVERIFIED_SPEAKER_SLUG, "quote": "Use the tool."}],
        {pipeline.UNVERIFIED_SPEAKER_SLUG: "person-sentinel"},
    )
    assert claims == [
        {
            "attributionStatus": "speaker_unverified",
            "personId": "person-sentinel",
            "quote": "Use the tool.",
            "speakerRaw": pipeline.UNVERIFIED_SPEAKER_SLUG,
        }
    ]


def test_near_duplicate_claims_require_substantial_word_overlap():
    original = {
        "quote": "Founders should define their ambition through the eyes of their customers."
    }
    repeated = {
        "quote": "Founders should define their ambition through the eyes of their customers!"
    }
    distinct = {"quote": "Teams learn faster when they speak to customers every week."}
    assert pipeline.claims_are_near_duplicates(original, repeated)
    assert not pipeline.claims_are_near_duplicates(original, distinct)


def test_deterministic_fast_path_keeps_only_complete_strong_non_reference_claims():
    segment = {
        "id": "segment-1",
        "speakerHint": pipeline.UNVERIFIED_SPEAKER_SLUG,
        "text": (
            "I think the biggest risk for hardware companies is failing to make enough "
            "technical progress to justify the next investment round."
        ),
    }
    claim = pipeline.deterministic_claim_for_segment(segment)
    assert claim is not None
    assert claim["assertion"] == claim["quote"]
    assert claim["attributionStatus"] == "speaker_unverified"
    assert claim["speakerConfidence"] == 0.0
    assert claim["extractionConfidence"] == 0.9

    recommendation = {
        **segment,
        "text": "I recommend Linear because it keeps product work organized across teams.",
    }
    assert pipeline.deterministic_claim_for_segment(recommendation) is None

    fragment = {
        **segment,
        "text": (
            "Because if the instructions are precise, then you do not have an issue, "
            "because the process is already scripted for you."
        ),
    }
    assert pipeline.deterministic_claim_for_segment(fragment) is None

    signal_outside_excerpt = {
        **segment,
        "text": (
            "I believe direct customer contact creates a durable operating advantage. "
            "The final implementation shipped on Tuesday after a routine review."
        ),
    }
    claim = pipeline.deterministic_claim_for_segment(signal_outside_excerpt)
    assert claim is not None
    assert pipeline.deterministic_claim_type(claim["quote"]) == claim["claimType"]


def test_rules_only_publishes_strong_claim_without_calling_the_model(monkeypatch):
    class Api:
        def get_episode(self, episode_id):
            return {
                "episode": {"id": episode_id},
                "people": [],
                "segments": [
                    {
                        "id": "segment-1",
                        "idx": 0,
                        "speakerHint": "guest-one",
                        "text": (
                            "I think direct customer contact is the durable advantage because "
                            "it shortens the learning loop for every product decision."
                        ),
                    }
                ],
                "extractedSegmentIds": [],
                "extractionAttempts": [],
            }

        def post_claims(self, episode_id, claims, llm_runs):
            assert claims[0]["model"] == "deterministic-v1"
            return {"results": [{"id": "claim-1", "reviewStatus": "published"}]}

    monkeypatch.setattr(
        pipeline,
        "extract_one_batch",
        lambda *args: (_ for _ in ()).throw(AssertionError("model must not run")),
    )
    cfg = replace(load_settings(), ai_base_url="http://127.0.0.1:1234/v1")
    opts = pipeline.ExtractOpts(
        episode_id="episode-1",
        dry_run=False,
        batch_size=20,
        rules_only=True,
    )
    assert pipeline._extract_episode(
        Api(), cfg, {"guest-one": "person-1"}, {"id": "episode-1"}, opts
    ) == (1, 0, 0)


def test_extract_only_loads_the_existing_roster_without_reseeding(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "load_roster",
        lambda api: {
            "person": "uuid",
            pipeline.UNVERIFIED_SPEAKER_SLUG: "sentinel-uuid",
        },
    )
    monkeypatch.setattr(
        pipeline,
        "seed_roster",
        lambda api: (_ for _ in ()).throw(AssertionError("must not reseed for extraction")),
    )
    assert pipeline.seed_maps_for_stage(object(), "extract", dry_run=False) == (
        {"person": "uuid", pipeline.UNVERIFIED_SPEAKER_SLUG: "sentinel-uuid"},
        {},
    )


def test_extract_seeds_only_the_unverified_speaker_sentinel_when_missing(monkeypatch):
    class Api:
        def __init__(self):
            self.people = []

        def upsert_people(self, people):
            self.people.extend(people)
            return ["sentinel-uuid"]

    monkeypatch.setattr(pipeline, "load_roster", lambda api: {"person": "uuid"})
    api = Api()
    people_map, _ = pipeline.seed_maps_for_stage(api, "extract", dry_run=False)
    assert people_map == {
        "person": "uuid",
        pipeline.UNVERIFIED_SPEAKER_SLUG: "sentinel-uuid",
    }
    assert [person["slug"] for person in api.people] == [pipeline.UNVERIFIED_SPEAKER_SLUG]


def test_extract_targets_apply_the_show_filter():
    class Api:
        def list_episodes(self, status=None, show_id=None):
            assert show_id == "show-1"
            return [{"id": f"{status}-episode"}]

    rows = pipeline._extract_targets(Api(), episode_id=None, show_id="show-1")
    assert len(rows) == len(pipeline.EXTRACTABLE_STATUSES)


def test_extract_targets_skip_publicly_withheld_shows_by_default():
    class Api:
        def list_episodes(self, status=None, show_id=None):
            return [
                {"id": f"{status}-trusted", "showId": "trusted"},
                {"id": f"{status}-withheld", "showId": "odd-lots"},
            ]

        def list_shows(self):
            return [
                {"id": "trusted", "slug": "lennys-podcast"},
                {"id": "odd-lots", "slug": "odd-lots"},
            ]

    rows = pipeline._extract_targets(Api(), episode_id=None)
    assert {row["showId"] for row in rows} == {"trusted"}


def test_extract_limit_caps_episode_work(monkeypatch):
    cfg = replace(load_settings(), ai_base_url="http://127.0.0.1:1234/v1")
    monkeypatch.setattr(
        pipeline,
        "_extract_targets",
        lambda api, episode_id, show_id: [{"id": "one"}, {"id": "two"}],
    )
    visited = []

    def extract(api, settings, people, episode, opts):
        visited.append(episode["id"])
        return 0, 0, 0

    monkeypatch.setattr(pipeline, "_extract_episode", extract)
    opts = pipeline.ExtractOpts(episode_id=None, dry_run=False, limit=1)
    assert pipeline.run_extract(object(), cfg, {}, opts) == 0
    assert visited == ["one"]


def test_extract_episode_skip_partitions_before_limit(monkeypatch):
    cfg = replace(load_settings(), ai_base_url="http://127.0.0.1:1234/v1")
    monkeypatch.setattr(
        pipeline,
        "_extract_targets",
        lambda api, episode_id, show_id: [
            {"id": "one"},
            {"id": "two"},
            {"id": "three"},
        ],
    )
    visited = []

    def extract(api, settings, people, episode, opts):
        visited.append(episode["id"])
        return 0, 0, 0

    monkeypatch.setattr(pipeline, "_extract_episode", extract)
    opts = pipeline.ExtractOpts(
        episode_id=None,
        dry_run=False,
        limit=1,
        skip_episodes=1,
    )
    assert pipeline.run_extract(object(), cfg, {}, opts) == 0
    assert visited == ["two"]
