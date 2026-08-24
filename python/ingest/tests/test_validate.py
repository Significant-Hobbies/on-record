from on_record_ingest.extract.validate import (
    find_verbatim_anchor,
    parse_claims_json,
    resolve_speaker,
    validate_claim,
    validate_references,
)

SEGMENT = (
    "I think software development is shifting toward supervising coding agents, "
    "not writing every line by hand anymore."
)
ROSTER = {"andrej-karpathy"}
TOPICS = {"coding-agents", "software-development"}


def test_verbatim_anchor_allows_collapsed_whitespace():
    quote = "software   development is shifting toward supervising coding agents"
    anchor = find_verbatim_anchor(SEGMENT, quote)
    assert anchor is not None
    assert "software development" in SEGMENT[anchor[0] : anchor[1]]


def test_paraphrase_is_rejected():
    row = {
        "speaker": "andrej-karpathy",
        "claim_type": "belief",
        "assertion": "Karpathy thinks agents write all software now.",
        "quote": "engineers will mostly babysit AI tools going forward forever",
        "topics": ["coding-agents"],
        "extraction_confidence": 0.9,
        "speaker_confidence": 0.9,
    }
    claim, reason = validate_claim(row, SEGMENT, ROSTER, TOPICS)
    assert claim is None
    assert reason == "quote_not_verbatim"


def test_alias_and_full_name_resolve_to_roster_slug():
    assert resolve_speaker("Karpathy", ROSTER) == "andrej-karpathy"
    assert resolve_speaker("Andrej Karpathy", ROSTER) == "andrej-karpathy"
    row = {
        "speaker": "Karpathy",
        "claim_type": "belief",
        "assertion": "Karpathy thinks software work is shifting toward agents.",
        "quote": "software development is shifting toward supervising coding agents",
        "topics": ["coding-agents"],
        "extraction_confidence": 0.9,
        "speaker_confidence": 0.9,
    }
    claim, reason = validate_claim(row, SEGMENT, ROSTER, TOPICS)
    assert reason is None
    assert claim is not None
    assert claim["speakerRaw"] == "andrej-karpathy"


def test_unknown_speaker_allowed_but_roster_mismatch_rejected():
    row = {
        "speaker": "not-a-person",
        "claim_type": "belief",
        "assertion": "Someone said something long enough to pass.",
        "quote": "software development is shifting toward supervising coding agents",
        "topics": ["coding-agents"],
        "extraction_confidence": 0.9,
        "speaker_confidence": 0.4,
    }
    claim, reason = validate_claim(row, SEGMENT, ROSTER, TOPICS)
    assert claim is None
    assert reason == "speaker_not_in_roster"


def test_parse_claims_json_unwraps_fences():
    raw = '```json\n{"claims": [{"speaker": "unknown"}]}\n```'
    parsed = parse_claims_json(raw)
    assert parsed == [{"speaker": "unknown"}]


def test_short_quote_rejected():
    assert find_verbatim_anchor(SEGMENT, "I think software development") is None


STACK = (
    "I still recommend The Sovereign Individual, and personally I use Cursor "
    "every day instead of writing every line by hand anymore."
)


def test_keeps_book_and_app_named_in_segment():
    refs = validate_references(
        {
            "references": [
                {"kind": "book", "name": "The Sovereign Individual", "role": "recommends"},
                {"kind": "app", "name": "Cursor", "role": "uses"},
                {"kind": "book", "name": "Invented Title", "role": "recommends"},
            ]
        },
        STACK,
    )
    assert {(r["kind"], r["name"], r["role"]) for r in refs} == {
        ("book", "The Sovereign Individual", "recommends"),
        ("app", "Cursor", "uses"),
    }


def test_claim_includes_validated_references():
    row = {
        "speaker": "andrej-karpathy",
        "claim_type": "recommendation",
        "assertion": "Karpathy recommends The Sovereign Individual.",
        "quote": "I still recommend The Sovereign Individual, and personally I use Cursor",
        "topics": ["books"],
        "extraction_confidence": 0.9,
        "speaker_confidence": 0.9,
        "references": [{"kind": "book", "name": "The Sovereign Individual", "role": "recommends"}],
    }
    claim, reason = validate_claim(row, STACK, ROSTER, {"books"})
    assert reason is None
    assert claim is not None
    assert claim["references"][0]["name"] == "The Sovereign Individual"
