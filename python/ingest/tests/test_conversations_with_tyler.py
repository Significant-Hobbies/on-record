import httpx

from on_record_ingest.transcripts.conversations_with_tyler import (
    PublisherSourceUnavailable,
    fetch_cues,
    is_cwt_url,
    parse_transcript_html,
    transcript_url_from_metadata,
)

PAGE_URL = "https://conversationswithtyler.com/episodes/example-guest/"
PAGE_HTML = """
<html>
  <head><meta property="og:title" content="Example Guest on Useful Things (Ep. 42)"></head>
  <body>
    <main id="main">
      <p><strong>Introduction</strong></p>
      <p><strong>Read the full transcript</strong></p>
      <p><strong>TYLER COWEN:</strong> Welcome to the conversation.</p>
      <p>This paragraph continues Tyler's publisher-labelled turn.</p>
      <blockquote><p>This pull quote duplicates transcript text.</p></blockquote>
      <p><strong>EXAMPLE GUEST:</strong> First answer with enough text.</p>
      <p><strong>COWEN:</strong> Second question.</p>
      <p><strong>GUEST:</strong> Second answer.</p>
      <p><strong>COWEN:</strong> Third question.</p>
      <p><strong>GUEST:</strong> Third answer.</p>
      <p><strong>COWEN:</strong> Fourth question.</p>
      <p><strong>GUEST:</strong> Fourth answer.</p>
      <p><strong>COWEN:</strong> Fifth question.</p>
      <p><strong>GUEST:</strong> Fifth answer.</p>
    </main>
    <footer><p><strong>NOT A SPEAKER:</strong> Newsletter text.</p></footer>
  </body>
</html>
"""


def test_resolves_only_one_publisher_supplied_transcript_link():
    metadata = f'<p>Read a <a href="{PAGE_URL}">full transcript</a>.</p>'
    assert transcript_url_from_metadata(metadata) == PAGE_URL
    assert (
        transcript_url_from_metadata(
            metadata,
            '<a href="https://conversationswithtyler.com/episodes/other/">transcript</a>',
        )
        is None
    )
    assert (
        transcript_url_from_metadata(
            '<a href="https://example.com/episodes/example-guest/">full transcript</a>'
        )
        is None
    )
    assert transcript_url_from_metadata(
        '<a href="https://conversationswithtyler.com/episodes/broken…20-retrospective/">transcript</a>',
        episode_title="Conversations with Tyler 2020 Retrospective",
        allow_title_override=True,
    ) == (
        "https://conversationswithtyler.com/episodes/conversations-with-tyler-2020-retrospective/"
    )


def test_title_override_requires_explicit_cwt_scope():
    assert (
        transcript_url_from_metadata(episode_title="Conversations with Tyler 2020 Retrospective")
        is None
    )


def test_accepts_recorded_marker_and_colon_outside_strong_label():
    html = """
    <meta property="og:title" content="Example Guest on Useful Things (Ep. 42)">
    <main id="main">
      <p><em>Recorded May 2nd, 2026.</em></p>
      <p><strong>TYLER COWEN</strong>: Welcome.</p>
      <p><strong>EXAMPLE GUEST</strong>: Thank you.</p>
    </main>
    """
    _, cues = parse_transcript_html(html, PAGE_URL)
    assert [cue["speakerName"] for cue in cues] == ["TYLER COWEN", "EXAMPLE GUEST"]
    assert [cue["text"] for cue in cues] == ["Welcome.", "Thank you."]


def test_accepts_full_conversation_marker():
    html = PAGE_HTML.replace("Read the full transcript", "Read the full conversation")
    assert len(parse_transcript_html(html, PAGE_URL)[1]) == 10


def test_repairs_a_publisher_label_split_across_adjacent_strong_tags():
    html = """
    <meta property="og:title" content="Ada Palmer on History (Ep. 1)">
    <main id="main">
      <p><strong>Read the full transcript</strong></p>
      <p><strong>PA</strong><strong>LMER:</strong> One answer.</p>
    </main>
    """
    _, cues = parse_transcript_html(html, PAGE_URL, {"PALMER": "ada-palmer"})
    assert cues == [
        {
            "duration": 0.0,
            "speaker": "ada-palmer",
            "speakerName": "PALMER",
            "speakerNameSource": "publisher",
            "start": 0.0,
            "text": "One answer.",
        }
    ]


def test_accepts_unicode_uppercase_publisher_labels():
    html = """
    <meta property="og:title" content="Leopoldo López on Venezuela (Ep. 1)">
    <main id="main">
      <p><strong>Read the full transcript</strong></p>
      <p><strong>COWEN:</strong> Which books did you read?</p>
      <p><strong>LÓPEZ:</strong> I read the Bible in prison.</p>
      <p>This paragraph continues López's answer.</p>
    </main>
    """
    _, cues = parse_transcript_html(
        html,
        PAGE_URL,
        {"COWEN": "tyler-cowen", "LÓPEZ": "leopoldo-lopez"},
    )
    assert cues == [
        {
            "duration": 0.0,
            "speaker": "tyler-cowen",
            "speakerName": "COWEN",
            "speakerNameSource": "publisher",
            "start": 0.0,
            "text": "Which books did you read?",
        },
        {
            "duration": 0.0,
            "speaker": "leopoldo-lopez",
            "speakerName": "LÓPEZ",
            "speakerNameSource": "publisher",
            "start": 1.0,
            "text": "I read the Bible in prison. This paragraph continues López's answer.",
        },
    ]


def test_splits_label_when_bold_markup_includes_response_prefix():
    html = """
    <meta property="og:title" content="Example Guest on Useful Things (Ep. 42)">
    <main id="main">
      <p><strong>Read the full transcript</strong></p>
      <p><strong>COWEN: “H</strong>ow should this split?”</p>
    </main>
    """
    _, cues = parse_transcript_html(html, PAGE_URL, {"COWEN": "tyler-cowen"})
    assert cues == [
        {
            "duration": 0.0,
            "speaker": "tyler-cowen",
            "speakerName": "COWEN",
            "speakerNameSource": "publisher",
            "start": 0.0,
            "text": "“How should this split?”",
        }
    ]


def test_repairs_a_label_split_between_plain_text_and_bold_markup():
    html = """
    <meta property="og:title" content="Example Guest on Useful Things (Ep. 42)">
    <main id="main">
      <p><strong>Read the full transcript</strong></p>
      <p>S<strong>ASSE:</strong> That is right.</p>
    </main>
    """
    _, cues = parse_transcript_html(html, PAGE_URL, {"SASSE": "ben-sasse"})
    assert cues == [
        {
            "duration": 0.0,
            "speaker": "ben-sasse",
            "speakerName": "SASSE",
            "speakerNameSource": "publisher",
            "start": 0.0,
            "text": "That is right.",
        }
    ]


def test_repairs_leading_punctuation_and_plain_text_labels():
    html = """
    <meta property="og:title" content="Example Guest on Useful Things (Ep. 42)">
    <main id="main">
      <p><strong>Read the full transcript</strong></p>
      <p><strong>GUEST:</strong> First answer.</p>
      <p>.<strong>COWEN:</strong> A question after malformed punctuation.</p>
      <p>BROOKS: A plain-text uppercase response.</p>
      <p>Cowen: A plain-text host question.</p>
      <p>For example: this remains a continuation, not a speaker.</p>
      <p>PBS: this short organization prefix also remains a continuation.</p>
    </main>
    """
    _, cues = parse_transcript_html(
        html,
        PAGE_URL,
        {"COWEN": "tyler-cowen", "BROOKS": "david-brooks"},
    )
    assert [cue["speakerName"] for cue in cues] == [
        "GUEST",
        "COWEN",
        "BROOKS",
        "Cowen",
    ]
    assert cues[-1]["text"].endswith(
        "For example: this remains a continuation, not a speaker. "
        "PBS: this short organization prefix also remains a continuation."
    )


def test_separates_unreviewed_mixed_case_publisher_labels_as_unknown():
    html = """
    <meta property="og:title" content="Example Guest on Useful Things (Ep. 42)">
    <main id="main">
      <p><strong>Read the full transcript</strong></p>
      <p><strong>COWEN:</strong> First question.</p>
      <p><strong>Audience member:</strong> A separate unreviewed comment.</p>
      <p><strong>GUEST:</strong> An attributed answer.</p>
    </main>
    """
    _, cues = parse_transcript_html(html, PAGE_URL, {"COWEN": "tyler-cowen"})
    assert [cue["speakerName"] for cue in cues] == [
        "COWEN",
        "Audience member",
        "GUEST",
    ]
    assert "speaker" not in cues[1]


def test_parses_labelled_turns_and_groups_unlabelled_continuations():
    title, cues = parse_transcript_html(
        PAGE_HTML,
        PAGE_URL,
        {"TYLER COWEN": "tyler-cowen", "COWEN": "tyler-cowen"},
    )
    assert title == "Example Guest on Useful Things (Ep. 42)"
    assert len(cues) == 10
    assert cues[0]["speaker"] == "tyler-cowen"
    assert cues[0]["speakerName"] == "TYLER COWEN"
    assert "continues Tyler's" in cues[0]["text"]
    assert "duplicates transcript" not in cues[0]["text"]
    assert "speaker" not in cues[1]
    assert [cue["start"] for cue in cues] == [float(index) for index in range(10)]
    assert all(cue["duration"] == 0.0 for cue in cues)


def test_missing_transcript_marker_fails_closed():
    title, cues = parse_transcript_html(
        PAGE_HTML.replace("Read the full transcript", "Episode notes"), PAGE_URL
    )
    assert title
    assert cues == []


def test_fetch_checks_page_identity_and_minimum_structure():
    long_html = PAGE_HTML.replace("Welcome to the conversation.", "x" * 1100)

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=long_html, request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        cues = fetch_cues(PAGE_URL, client, "Example Guest on Useful Things")
        assert len(cues) == 10
        assert fetch_cues(PAGE_URL, client, "Different Person and Topic") == []

    short_html = PAGE_HTML.replace("Welcome to the conversation.", "x" * 100)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=short_html, request=request)
        )
    ) as client:
        try:
            fetch_cues(PAGE_URL, client, "Example Guest on Useful Things")
        except PublisherSourceUnavailable:
            pass
        else:
            raise AssertionError("undersized transcript should stay retryable")


def test_rejects_off_domain_pages_and_redirects():
    assert not is_cwt_url("https://example.com/episodes/example-guest/")
    assert parse_transcript_html(PAGE_HTML, "https://example.com/episodes/example-guest/") == (
        "",
        [],
    )

    def redirect(request: httpx.Request) -> httpx.Response:
        if request.url.host == "conversationswithtyler.com":
            return httpx.Response(
                302, headers={"location": "https://example.com/page"}, request=request
            )
        return httpx.Response(200, text=PAGE_HTML, request=request)

    with httpx.Client(transport=httpx.MockTransport(redirect), follow_redirects=True) as client:
        assert fetch_cues(PAGE_URL, client, "Example Guest on Useful Things") == []
