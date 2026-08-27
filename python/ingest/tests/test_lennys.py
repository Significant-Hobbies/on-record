from __future__ import annotations

import json

import httpx
import pytest

from on_record_ingest.transcripts.lennys import (
    PublisherSourceUnavailable,
    fetch_cues,
    is_lennys_url,
    parse_transcript_json,
)

PAGE_URL = "https://www.lennysnewsletter.com/p/a-useful-episode"
CDN_URL = "https://substackcdn.com/transcription.json?Signature=not-logged"


def _payload() -> list[dict]:
    return [
        {
            "start": float(index * 2),
            "end": float(index * 2 + 1.5),
            "speaker": f"SPEAKER_{index % 2}",
            "text": (
                f"Turn {index} contains enough exact publisher transcript text "
                "to validate timing, identity, and the minimum useful corpus size."
            ),
        }
        for index in range(12)
    ]


def _page(
    *,
    post_id: int = 123,
    title: str = "A Useful Episode | Guest Name",
    approved: bool = True,
    speaker_map: dict[str, str] | None = None,
) -> str:
    transcription = {
        "status": "transcribed",
        "approved_at": "2026-08-20T16:46:21Z" if approved else None,
        "cdn_url": CDN_URL,
        "speaker_map": speaker_map
        if speaker_map is not None
        else {"SPEAKER_0": "Lenny Rachitsky", "SPEAKER_1": "Guest Name"},
    }
    preload = {
        "post": {
            "id": post_id,
            "title": title,
            "podcastUpload": {"transcription": transcription},
        }
    }
    return f"<script>window._preloads = JSON.parse({json.dumps(json.dumps(preload))})</script>"


def test_is_lennys_url_requires_an_official_post():
    assert is_lennys_url(PAGE_URL)
    assert not is_lennys_url("https://www.lennysnewsletter.com/p/")
    assert not is_lennys_url("https://www.lennysnewsletter.com/archive")
    assert not is_lennys_url("https://example.com/p/a-useful-episode")


def test_parse_transcript_json_preserves_timing_and_maps_only_known_people():
    cues = parse_transcript_json(
        _payload(),
        {"SPEAKER_0": "Lenny Rachitsky", "SPEAKER_1": "Guest Name"},
        {"lenny rachitsky": "lenny-rachitsky"},
    )
    assert cues[0] == {
        "duration": 1.5,
        "speaker": "lenny-rachitsky",
        "speakerName": "Lenny Rachitsky",
        "speakerNameSource": "publisher",
        "start": 0.0,
        "text": (
            "Turn 0 contains enough exact publisher transcript text to validate "
            "timing, identity, and the minimum useful corpus size."
        ),
    }
    assert cues[1]["speakerName"] == "Guest Name"
    assert "speaker" not in cues[1]


def test_parse_transcript_normalizes_zero_padded_speaker_labels():
    payload = _payload()
    for cue in payload:
        cue["speaker"] = f"SPEAKER_0{str(cue['speaker']).removeprefix('SPEAKER_')}"
    cues = parse_transcript_json(
        payload,
        {"SPEAKER_0": "Lenny Rachitsky", "SPEAKER_1": "Guest Name"},
        {"lenny rachitsky": "lenny-rachitsky"},
    )
    assert cues[0]["speaker"] == "lenny-rachitsky"
    assert cues[1]["speakerName"] == "Guest Name"


def test_parse_transcript_prefers_exact_labels_when_padded_maps_conflict():
    payload = _payload()
    payload[0]["speaker"] = "SPEAKER_00"
    cues = parse_transcript_json(
        payload,
        {
            "SPEAKER_0": "Guest Name",
            "SPEAKER_1": "Lenny Rachitsky",
            "SPEAKER_00": "Lenny Rachitsky",
            "SPEAKER_01": "Guest Name",
        },
        {"lenny rachitsky": "lenny-rachitsky"},
    )
    assert cues[0]["speaker"] == "lenny-rachitsky"
    assert cues[1]["speakerName"] == "Lenny Rachitsky"


def test_parse_transcript_preserves_unlabelled_words_as_unknown():
    payload = _payload()
    payload[0]["speaker"] = None
    cues = parse_transcript_json(
        payload,
        {"SPEAKER_0": "Lenny Rachitsky", "SPEAKER_1": "Guest Name"},
        {"lenny rachitsky": "lenny-rachitsky"},
    )
    assert cues[0]["speakerName"] == "Unknown"
    assert cues[0]["speakerNameSource"] == "publisher_missing"
    assert "speaker" not in cues[0]


def test_fetch_uses_matching_post_and_never_exposes_signed_url():
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "substackcdn.com":
            return httpx.Response(200, json=_payload(), request=request)
        return httpx.Response(200, text=_page(), request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        cues = fetch_cues(
            PAGE_URL,
            client,
            "A Useful Episode | Guest Name",
            "substack:post:123",
            {"guest name": "guest-name", "lenny rachitsky": "lenny-rachitsky"},
        )
    assert len(cues) == 12
    assert cues[1]["speaker"] == "guest-name"


@pytest.mark.parametrize(
    "page",
    [
        _page(approved=False),
        _page(speaker_map={}),
        _page(post_id=456),
    ],
)
def test_fetch_fails_closed_when_publisher_identity_is_not_approved(page: str):
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=page, request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert (
            fetch_cues(
                PAGE_URL,
                client,
                "A Useful Episode | Guest Name",
                "substack:post:123",
            )
            == []
        )


def test_fetch_uses_title_guard_when_exact_post_id_is_unavailable():
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "substackcdn.com":
            return httpx.Response(200, json=_payload(), request=request)
        return httpx.Response(
            200,
            text=_page(title="An Unrelated Episode"),
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert fetch_cues(PAGE_URL, client, "A Useful Episode | Guest Name") == []


def test_fetch_download_failure_stays_retryable_without_signed_url_in_error():
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "substackcdn.com":
            return httpx.Response(503, request=request)
        return httpx.Response(200, text=_page(), request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        pytest.raises(PublisherSourceUnavailable) as exc,
    ):
        fetch_cues(
            PAGE_URL,
            client,
            "A Useful Episode | Guest Name",
            "substack:post:123",
        )
    assert "Signature=" not in str(exc.value)


def test_parse_transcript_drops_one_regressing_cue_without_inventing_timing():
    payload = _payload()
    payload[2]["start"] = 0.5
    cues = parse_transcript_json(
        payload,
        {"SPEAKER_0": "Lenny Rachitsky", "SPEAKER_1": "Guest Name"},
    )
    assert len(cues) == 11
    assert all("Turn 2 " not in cue["text"] for cue in cues)


def test_parse_transcript_rejects_too_many_malformed_cues():
    payload = _payload()
    for cue in payload[:11]:
        cue["end"] = -1
    with pytest.raises(PublisherSourceUnavailable, match="too many malformed cues"):
        parse_transcript_json(
            payload,
            {"SPEAKER_0": "Lenny Rachitsky", "SPEAKER_1": "Guest Name"},
        )
