from pathlib import Path

import httpx

from on_record_ingest.transcripts.lex_fridman import (
    fetch_cues,
    parse_transcript_html,
    transcript_url_from_episode_html,
    transcript_url_from_metadata,
    youtube_video_id,
)

FIXTURES = Path(__file__).parent / "fixtures"
EPISODE_HTML = (FIXTURES / "lex_episode.html").read_text()
TRANSCRIPT_HTML = (FIXTURES / "lex_transcript.html").read_text()
EPISODE_URL = "https://lexfridman.com/?p=999"
TRANSCRIPT_URL = "https://lexfridman.com/actual-guests-and-topic-transcript/"


def test_resolves_the_episode_pages_actual_transcript_link():
    assert transcript_url_from_episode_html(EPISODE_HTML, EPISODE_URL) == TRANSCRIPT_URL
    assert "999" not in TRANSCRIPT_URL


def test_resolves_the_title_matching_link_when_adjacent_transcripts_are_listed():
    html = """
    <a href="/previous-transcript/">
      ← Transcript for Jordan Peterson | Lex Fridman Podcast #448
    </a>
    <a href="/current-transcript/">
      Transcript for Graham Hancock: Lost Civilization | Lex Fridman Podcast #449 →
    </a>
    """
    episode_title = "#449 – Graham Hancock: Lost Civilization of the Ice Age"
    assert transcript_url_from_episode_html(html, EPISODE_URL, episode_title) == (
        "https://lexfridman.com/current-transcript/"
    )


def test_rejects_ambiguous_adjacent_transcript_links():
    html = """
    <a href="/first-transcript/">Transcript</a>
    <a href="/second-transcript/">Transcript</a>
    """
    assert transcript_url_from_episode_html(html, EPISODE_URL, "Unmatched episode") is None


def test_rejects_an_only_link_that_belongs_to_the_adjacent_episode():
    html = """
    <a href="/dave-hone-transcript/">
      Transcript for Dave Hone: T-Rex and Dinosaurs | Lex Fridman Podcast #480
    </a>
    """
    episode_title = "#479 – Dave Plummer: Programming and Old-School Microsoft Stories"
    assert transcript_url_from_episode_html(html, EPISODE_URL, episode_title) is None


def test_episode_number_prevents_same_guest_from_matching_an_older_episode():
    html = """
    <a href="/michael-malice-transcript/">
      Transcript for Michael Malice: Totalitarianism and Anarchy | Podcast #200
    </a>
    """
    episode_title = "#150 – Michael Malice: The White Pill, Freedom, Hope, and Happiness"
    assert transcript_url_from_episode_html(html, EPISODE_URL, episode_title) is None


def test_does_not_follow_a_transcript_link_off_the_publishers_domain():
    html = '<a href="https://example.com/episode-transcript">Transcript</a>'
    assert transcript_url_from_episode_html(html, EPISODE_URL) is None


def test_resolves_an_exact_transcript_url_from_plain_or_html_metadata():
    plain = "Transcript:\nhttps://lexfridman.com/exact-guest-transcript\n"
    linked = '<a href="https://lexfridman.com/exact-guest-transcript/">Transcript</a>'
    assert transcript_url_from_metadata(plain) == ("https://lexfridman.com/exact-guest-transcript")
    assert transcript_url_from_metadata(linked) == (
        "https://lexfridman.com/exact-guest-transcript/"
    )


def test_metadata_resolver_uses_title_to_avoid_a_previous_episode_link():
    metadata = """
    <a href="https://lexfridman.com/jordan-peterson-transcript/">
      Transcript for Jordan Peterson #448
    </a>
    <a href="https://lexfridman.com/graham-hancock-transcript/">
      Transcript for Graham Hancock #449
    </a>
    """
    assert (
        transcript_url_from_metadata(
            metadata,
            episode_title="#449 – Graham Hancock: Lost Civilization",
        )
        == "https://lexfridman.com/graham-hancock-transcript/"
    )


def test_metadata_resolver_rejects_guesses_and_external_lookalikes():
    assert transcript_url_from_metadata("Transcript: https://example.com/guest-transcript") is None
    assert transcript_url_from_metadata("Episode: https://lexfridman.com/guest") is None


def test_parses_timestamped_turns_and_fails_unknown_speakers_closed():
    cues = parse_transcript_html(TRANSCRIPT_HTML, TRANSCRIPT_URL)
    assert len(cues) == 4
    assert [cue["start"] for cue in cues] == [0.0, 7.0, 20.0, 70.0]
    assert [cue["duration"] for cue in cues] == [7.0, 13.0, 50.0, 0.0]
    assert cues[0]["speaker"] == "lex-fridman"
    assert cues[1]["speaker"] == "andrej-karpathy"
    assert cues[2]["speaker"] == "andrej-karpathy"
    assert cues[2]["speakerNameSource"] == "publisher_continuation"
    assert cues[3]["speakerName"] == "Unlisted Researcher"
    assert "speaker" not in cues[3]
    assert cues[1]["text"] == "Nested markup must keep its words and whitespace."
    assert youtube_video_id(str(cues[0]["sourceUrl"])) == "abcDEF_1234"


def test_rejects_non_monotonic_transcript_timestamps():
    broken = TRANSCRIPT_HTML.replace("(00:01:10)", "(00:00:03)")
    assert parse_transcript_html(broken, TRANSCRIPT_URL) == []


def test_preserves_small_publisher_clock_jitter_without_reordering_text():
    jittered = TRANSCRIPT_HTML.replace("(00:00:20)", "(00:00:05)")
    cues = parse_transcript_html(jittered, TRANSCRIPT_URL)
    assert [cue["start"] for cue in cues[:3]] == [0.0, 7.0, 5.0]
    assert cues[1]["duration"] == 0.0
    assert cues[2]["text"] == "A blank name continues the prior publisher turn."


def test_fetches_the_linked_page_instead_of_guessing_a_slug():
    requested: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if str(request.url) == EPISODE_URL:
            return httpx.Response(200, text=EPISODE_HTML, request=request)
        if str(request.url) == TRANSCRIPT_URL:
            return httpx.Response(200, text=TRANSCRIPT_HTML, request=request)
        return httpx.Response(404, request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        cues = fetch_cues(EPISODE_URL, client)

    assert len(cues) == 4
    assert requested == [EPISODE_URL, TRANSCRIPT_URL]


def test_rejects_a_publisher_redirect_off_domain():
    def respond(request: httpx.Request) -> httpx.Response:
        if str(request.url) == EPISODE_URL:
            return httpx.Response(
                302,
                headers={"location": "https://example.com/transcript"},
                request=request,
            )
        return httpx.Response(200, text=TRANSCRIPT_HTML, request=request)

    with httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=True) as client:
        assert fetch_cues(EPISODE_URL, client) == []


def test_youtube_id_parser_accepts_known_forms_and_rejects_lookalikes():
    assert youtube_video_id("https://youtu.be/abcDEF_1234?t=7") == "abcDEF_1234"
    assert youtube_video_id("https://www.youtube.com/embed/abcDEF_1234") == "abcDEF_1234"
    assert youtube_video_id("https://youtube.example/watch?v=abcDEF_1234") is None
    assert youtube_video_id("https://youtube.com/watch?v=too-short") is None


def test_malformed_metadata_url_fails_closed():
    assert transcript_url_from_metadata("see https://[broken/transcript") is None


def test_leading_blank_speaker_is_not_invented():
    html = """
    <div class="ts-segment">
      <span class="ts-name"></span>
      <span class="ts-timestamp"><a href="https://youtu.be/abcDEF_1234">(00:00)</a></span>
      <span class="ts-text">No prior publisher name exists.</span>
    </div>
    """
    cue = parse_transcript_html(html, TRANSCRIPT_URL)[0]
    assert "speaker" not in cue
    assert "speakerName" not in cue
