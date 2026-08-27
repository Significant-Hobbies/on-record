from __future__ import annotations

import httpx
import pytest

from on_record_ingest.transcripts.acquired import (
    PublisherSourceUnavailable,
    fetch_cues,
    is_acquired_site_url,
    is_acquired_url,
    match_episode_url,
    parse_transcript_html,
)


def _page(*paragraphs: str, title: str = "Formula 1 | Acquired") -> str:
    transcript = "".join(f"<p>{paragraph}</p>" for paragraph in paragraphs)
    return f"""
    <html><head><meta property="og:title" content="{title}"></head><body>
      <div id="transcript" class="popup-section episode-transcript">
        <div><div class="episode-rich-text mb-2xl w-richtext">
          <h3>Start</h3>{transcript}
        </div></div>
      </div>
      <div class="episode-rich-text w-richtext"><p>Overview text.</p></div>
    </body></html>
    """


def test_is_acquired_url_requires_an_episode_page():
    assert is_acquired_url("https://www.acquired.fm/episodes/formula-1")
    assert is_acquired_site_url("http://acquired.fm/")
    assert not is_acquired_url("https://www.acquired.fm/")
    assert not is_acquired_url("https://example.com/episodes/formula-1")


def test_match_episode_url_requires_one_clear_sitemap_match():
    urls = [
        "https://www.acquired.fm/episodes/formula-1",
        "https://www.acquired.fm/episodes/ferrari",
        "https://www.acquired.fm/episodes/episode-1-pixar",
        "https://www.acquired.fm/episodes/season-2-episode-3nest",
        "https://www.acquired.fm/episodes/netflix-part-1",
        "https://www.acquired.fm/episodes/netflix-part-2",
        "https://www.acquired.fm/episodes/2017-holiday-special",
        "https://www.acquired.fm/episodes/holiday-special-2022",
        "https://www.acquired.fm/episodes/episode-2-instagram",
        "https://www.acquired.fm/episodes/instagram-revisited-with-emily-white",
        "https://www.acquired.fm/episodes/episode-4-bungie",
        "https://www.acquired.fm/episodes/episode-41-bookingcom-with-jetsetter-room-77-ceo-drew-patterson",
        "https://www.acquired.fm/episodes/solana-with-ceo-anatoly-yakovenko",
    ]
    assert match_episode_url("Formula 1", urls) == urls[0]
    assert match_episode_url("Season 1, Episode 1: Pixar", urls) == urls[2]
    assert match_episode_url("Nest", urls) == urls[3]
    assert match_episode_url("Netflix (Part I)", urls) == urls[4]
    assert match_episode_url("Netflix (Part II)", urls) == urls[5]
    assert match_episode_url("2017 Holiday Special", urls) == urls[6]
    assert match_episode_url("Instagram", urls) == urls[8]
    assert match_episode_url("Bungie (with Xbox Co-Founder Ed Fries)", urls) == urls[10]
    assert match_episode_url("Booking.com with Jetsetter CEO Drew Patterson", urls) == urls[11]
    assert match_episode_url("Special: Solana (with CEO Anatoly Yakovenko)", urls) == urls[12]
    assert match_episode_url("Unknown Company", urls) is None


def test_parse_transcript_keeps_labels_and_continuations_inside_transcript_only():
    title, cues = parse_transcript_html(
        _page(
            "Ben: Welcome to Acquired.",
            "This continuation belongs to Ben.",
            "David: I am David Rosenthal.",
            "Opening Song:",
            "Ben: Let us begin.",
        ),
        "https://www.acquired.fm/episodes/formula-1",
        {"ben": "ben-gilbert", "david": "david-rosenthal"},
    )
    assert title == "Formula 1 | Acquired"
    assert cues == [
        {
            "duration": 0.0,
            "speaker": "ben-gilbert",
            "speakerName": "Ben",
            "speakerNameSource": "publisher",
            "start": 0.0,
            "text": "Welcome to Acquired. This continuation belongs to Ben.",
        },
        {
            "duration": 0.0,
            "speaker": "david-rosenthal",
            "speakerName": "David",
            "speakerNameSource": "publisher",
            "start": 1.0,
            "text": "I am David Rosenthal.",
        },
        {
            "duration": 0.0,
            "speaker": "ben-gilbert",
            "speakerName": "Ben",
            "speakerNameSource": "publisher",
            "start": 2.0,
            "text": "Let us begin.",
        },
    ]


def test_parse_transcript_rejects_wrong_host_and_missing_transcript():
    html = _page("Ben: Welcome.")
    assert parse_transcript_html(html, "https://example.com/episodes/formula-1") == ("", [])
    assert parse_transcript_html(
        '<meta property="og:title" content="Formula 1 | Acquired"><p>Ben: Welcome.</p>',
        "https://www.acquired.fm/episodes/formula-1",
    ) == ("Formula 1 | Acquired", [])


def test_fetch_rejects_title_mismatch():
    paragraphs = [
        f"Ben: Turn {index} has enough transcript text to be useful." for index in range(20)
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text=_page(*paragraphs, title="Rolex | Acquired"), request=request
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert (
            fetch_cues(
                "https://www.acquired.fm/episodes/formula-1",
                client,
                "Formula 1",
                {"ben": "ben-gilbert"},
            )
            == []
        )


@pytest.mark.parametrize(
    ("episode_title", "publisher_title"),
    [
        ("Google Part I: Origins of Search", "Google: The Origin of Search | Acquired"),
        ("Google Part II: Alphabet", "Alphabet Inc. | Acquired"),
    ],
)
def test_fetch_accepts_verified_publisher_title_variants(episode_title, publisher_title):
    paragraphs = [
        f"{'Ben' if index % 2 == 0 else 'David'}: "
        f"Turn {index} has enough transcript text to be useful for title verification."
        for index in range(20)
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=_page(*paragraphs, title=publisher_title),
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert (
            len(
                fetch_cues(
                    "https://www.acquired.fm/episodes/google",
                    client,
                    episode_title,
                )
            )
            == 20
        )


def test_fetch_returns_empty_for_an_empty_transcript_section():
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_page(title="Formula 1 | Acquired"), request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert (
            fetch_cues(
                "https://www.acquired.fm/episodes/formula-1",
                client,
                "Formula 1",
            )
            == []
        )


def test_fetch_server_failure_stays_retryable():
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        pytest.raises(PublisherSourceUnavailable),
    ):
        fetch_cues(
            "https://www.acquired.fm/episodes/formula-1",
            client,
            "Formula 1",
        )
