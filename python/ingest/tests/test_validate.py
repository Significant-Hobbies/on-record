import json

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


def test_keeps_book_and_app_named_in_claim_quote():
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


def test_drops_reference_named_elsewhere_in_segment_but_not_claim_quote():
    row = {
        "speaker": "andrej-karpathy",
        "claim_type": "recommendation",
        "assertion": "Karpathy recommends The Sovereign Individual.",
        "quote": "I still recommend The Sovereign Individual",
        "topics": ["books"],
        "extraction_confidence": 0.9,
        "speaker_confidence": 0.9,
        "references": [
            {"kind": "book", "name": "The Sovereign Individual", "role": "recommends"},
            {"kind": "app", "name": "Cursor", "role": "uses"},
        ],
    }
    claim, reason = validate_claim(row, STACK, ROSTER, {"books"})
    assert reason is None
    assert claim is not None
    assert claim["references"] == [
        {"kind": "book", "name": "The Sovereign Individual", "role": "recommends"}
    ]


def test_drops_mentions_and_roles_supported_only_by_a_different_clause():
    refs = validate_references(
        {
            "references": [
                {"kind": "book", "name": "The Sovereign Individual", "role": "mentions"},
                {"kind": "book", "name": "The Sovereign Individual", "role": "uses"},
                {"kind": "app", "name": "Cursor", "role": "recommends"},
            ]
        },
        STACK,
    )
    assert refs == []


def test_keeps_built_avoids_and_reading_speech_acts():
    quote = (
        "I built comma.ai from scratch. I do not use Facebook anymore. "
        "I am reading The Beginning of Infinity this week."
    )
    refs = validate_references(
        {
            "references": [
                {"kind": "tool", "name": "comma.ai", "role": "built"},
                {"kind": "service", "name": "Facebook", "role": "avoids"},
                {"kind": "book", "name": "The Beginning of Infinity", "role": "uses"},
            ]
        },
        quote,
    )
    assert {(ref["name"], ref["role"]) for ref in refs} == {
        ("comma.ai", "built"),
        ("Facebook", "avoids"),
        ("The Beginning of Infinity", "uses"),
    }


def test_keeps_preferences_and_ownership_distinct_from_recommendations():
    quote = (
        "I love Linear for planning, and I bought The Staff Engineer's Path last week. "
        "These are personal choices, not blanket recommendations."
    )
    refs = validate_references(
        {
            "references": [
                {"kind": "app", "name": "Linear", "role": "likes"},
                {"kind": "book", "name": "The Staff Engineer's Path", "role": "owns"},
                {"kind": "app", "name": "Linear", "role": "recommends"},
            ]
        },
        quote,
    )
    assert refs == [
        {"kind": "app", "name": "Linear", "role": "likes"},
        {"kind": "book", "name": "The Staff Engineer's Path", "role": "owns"},
    ]


def test_normalizes_a_kind_that_conflicts_with_the_quoted_context():
    quote = "Zork was a fantastic game, and I highly recommend Zork to everyone."
    refs = validate_references(
        {
            "references": [
                {"kind": "book", "name": "Zork", "role": "recommends"},
                {"kind": "other", "name": "Zork", "role": "recommends"},
            ]
        },
        quote,
    )
    assert refs == [{"kind": "other", "name": "Zork", "role": "recommends"}]


def test_normalizes_an_account_mislabeled_as_an_app():
    quote = "I recommend the FFmpeg account on Twitter/X to everybody who likes open source."
    refs = validate_references(
        {
            "references": [
                {
                    "kind": "app",
                    "name": "FFmpeg account on Twitter/X",
                    "role": "recommends",
                }
            ]
        },
        quote,
    )
    assert refs == [
        {
            "kind": "other",
            "name": "FFmpeg account on Twitter/X",
            "role": "recommends",
        }
    ]


def test_rejects_generic_objects_passive_hearsay_and_non_object_people():
    cases = [
        (
            "Anybody listening should know I highly recommend this game.",
            {"kind": "app", "name": "this game", "role": "recommends"},
        ),
        (
            "I saw WSL2 recommended for certain operations.",
            {"kind": "tool", "name": "WSL2", "role": "recommends"},
        ),
        (
            "You had conversations with Nurlan, with Adam, which I highly recommend.",
            {"kind": "person", "name": "Adam", "role": "recommends"},
        ),
        (
            "I read a paper recently about modern working scientists.",
            {"kind": "paper", "name": "a paper", "role": "uses"},
        ),
    ]
    for quote, reference in cases:
        assert validate_references({"references": [reference]}, quote) == []


def test_rejects_pronoun_object_followed_by_an_unrelated_name():
    quote = "I read it when they first did Crime and Punishment, and that was amazing."
    refs = validate_references(
        {"references": [{"kind": "book", "name": "Crime and Punishment", "role": "uses"}]},
        quote,
    )
    assert refs == []


def test_rejects_descriptive_phrases_that_are_not_named_references():
    quote = (
        "I used leading and suggestive questions in my research. "
        "I recommend many sources who disagree with each other."
    )
    refs = validate_references(
        {
            "references": [
                {
                    "kind": "other",
                    "name": "leading and suggestive questions",
                    "role": "uses",
                },
                {
                    "kind": "other",
                    "name": "many sources who disagree with each other",
                    "role": "recommends",
                },
            ]
        },
        quote,
    )
    assert refs == []


def test_rejects_generic_plural_categories():
    quote = "As you can tell, I read a lot of books."
    refs = validate_references(
        {"references": [{"kind": "book", "name": "books", "role": "uses"}]},
        quote,
    )
    assert refs == []


def test_rejects_descriptive_book_labels_and_book_subjects():
    cases = [
        ("I read Bill Walsh's book.", "Bill Walsh's book", "uses"),
        ("I love John Klassen books.", "John Klassen books", "likes"),
        ("I use Gwern's book reviews.", "Gwern's book reviews", "uses"),
        (
            "The front inside cover of this book is something I read every year.",
            "The front inside cover of this book",
            "uses",
        ),
        ("I read a book about Roy Cohn.", "Roy Cohn", "uses"),
    ]
    for quote, name, role in cases:
        assert (
            validate_references(
                {"references": [{"kind": "book", "name": name, "role": role}]}, quote
            )
            == []
        )


def test_rejects_audited_non_title_book_answer_labels():
    cases = [
        "Andrew Roberts latest book on Winston Churchill",
        "Elon Musk book",
        "Kim Scott's writing",
        "The How to Book",
    ]
    for name in cases:
        quote = f"I recommend {name}."
        assert (
            validate_references(
                {
                    "bookAnswer": True,
                    "references": [{"kind": "book", "name": name, "role": "recommends"}],
                },
                quote,
            )
            == []
        )


def test_reclassifies_audited_non_book_names():
    cases = [
        ("I love Hey Jude.", "Hey Jude", "likes", "other"),
        ("I read Wikipedia every day.", "Wikipedia", "uses", "other"),
        ("I love Michael Lewis.", "Michael Lewis", "likes", "person"),
        ("I read ULM Fit.", "ULM Fit", "uses", "paper"),
    ]
    for quote, name, role, expected_kind in cases:
        refs = validate_references(
            {"references": [{"kind": "book", "name": name, "role": role}]}, quote
        )
        assert refs == [{"kind": expected_kind, "name": name, "role": role}]


def test_converges_audited_cross_kind_duplicates():
    quote = "I use Coda every day."
    expected = [{"kind": "app", "name": "Coda", "role": "uses"}]
    for kind in ("app", "tool"):
        assert (
            validate_references(
                {"references": [{"kind": kind, "name": "Coda", "role": "uses"}]}, quote
            )
            == expected
        )


def test_rejects_lowercase_generic_objects_and_descriptive_series_names():
    cases = [
        (
            "I bought the luggage first, long before they sent more luggage.",
            {"kind": "hardware", "name": "luggage", "role": "owns"},
        ),
        (
            "I highly recommend people watch your series with 3Blue1Brown on distance.",
            {
                "kind": "other",
                "name": "your series with 3Blue1Brown on distance",
                "role": "recommends",
            },
        ),
        (
            "I don't use AI note taking.",
            {"kind": "tool", "name": "AI note taking", "role": "avoids"},
        ),
        (
            "I love how everything connects to how tech works and how AI came to be.",
            {
                "kind": "other",
                "name": "how everything connects to how tech works and how AI came to be",
                "role": "likes",
            },
        ),
        (
            "One of my favorite books is one that was sent to me by Nijolė Skripskaitė.",
            {
                "kind": "book",
                "name": "one that was sent to me by Nijolė Skripskaitė",
                "role": "likes",
            },
        ),
    ]
    for quote, reference in cases:
        assert validate_references({"references": [reference]}, quote) == []


def test_normalizes_an_explicitly_named_channel_or_podcast_to_other():
    cases = [
        (
            "I highly recommend the channel, Animagraffs.",
            {"kind": "app", "name": "Animagraffs", "role": "recommends"},
        ),
        (
            "I listened to an episode of Invest Like the Best last year.",
            {"kind": "app", "name": "Invest Like the Best", "role": "uses"},
        ),
    ]
    for quote, reference in cases:
        assert validate_references({"references": [reference]}, quote) == [
            {**reference, "kind": "other"}
        ]


def test_rejects_a_topic_mistaken_for_the_recommended_book_title():
    quote = "That ties in with another book I recommended to you about the origins of Trump."
    refs = validate_references(
        {"references": [{"kind": "book", "name": "the origins of Trump", "role": "recommends"}]},
        quote,
    )
    assert refs == []


def test_normalizes_an_author_shorthand_mislabeled_as_a_book():
    quote = "I read in Solzhenitsyn that the authorities made hundreds of decisions a day."
    refs = validate_references(
        {"references": [{"kind": "book", "name": "Solzhenitsyn", "role": "uses"}]},
        quote,
    )
    assert refs == [{"kind": "other", "name": "Solzhenitsyn", "role": "uses"}]


def test_rejects_a_descriptive_book_phrase_promoted_into_a_title():
    quote = "I highly recommend people read his new book on Elon."
    refs = validate_references(
        {"references": [{"kind": "book", "name": "his new book on Elon", "role": "recommends"}]},
        quote,
    )
    assert refs == []


def test_rejects_a_person_incidental_to_the_recommended_action():
    quote = "I recommend being a POW with the Americans. That would be my choice."
    refs = validate_references(
        {"references": [{"kind": "person", "name": "Americans", "role": "recommends"}]},
        quote,
    )
    assert refs == []


def test_normalizes_a_documentary_mislabeled_as_a_book():
    quote = "He created the documentary I highly recommend called This Place Rules."
    refs = validate_references(
        {"references": [{"kind": "book", "name": "This Place Rules", "role": "recommends"}]},
        quote,
    )
    assert refs == [{"kind": "other", "name": "This Place Rules", "role": "recommends"}]


def test_rejects_recommended_media_wrapped_around_a_person_name():
    quote = "I recommend my conversation with Serhii Plokhy about the history of the region."
    refs = validate_references(
        {"references": [{"kind": "person", "name": "Serhii Plokhy", "role": "recommends"}]},
        quote,
    )
    assert refs == []


def test_rejects_a_reference_spoken_inside_someone_elses_reported_quote():
    cases = [
        (
            "A woman said this to me, ‘It never occurred to me that I could be a doctor "
            "until I read Ayn Rand.’",
            {"kind": "book", "name": "Ayn Rand", "role": "uses"},
        ),
        (
            "Then I read another book, by Frederick Buechner, who said, “In those moments "
            "of pain, you can either be broken or broken open.”",
            {
                "kind": "book",
                "name": "In those moments of pain, you can either be broken or broken open",
                "role": "uses",
            },
        ),
    ]
    for quote, reference in cases:
        assert validate_references({"references": [reference]}, quote) == []


def test_deduplicates_the_same_named_item_and_role_across_model_supplied_kinds():
    refs = validate_references(
        {
            "references": [
                {"kind": "app", "name": "v0", "role": "uses"},
                {"kind": "tool", "name": "v0", "role": "uses"},
            ]
        },
        "We use v0 every day.",
    )
    assert refs == [{"kind": "app", "name": "v0", "role": "uses"}]


def test_kind_conflict_can_come_from_source_context_outside_the_quote():
    refs = validate_references(
        {"references": [{"kind": "app", "name": "Zork", "role": "recommends"}]},
        "I highly recommend Zork.",
        "Zork changed how I think about games. I highly recommend Zork.",
    )
    assert refs == [{"kind": "other", "name": "Zork", "role": "recommends"}]


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


def test_salvages_claims_from_a_truncated_response():
    from on_record_ingest.extract.validate import parse_claims_json

    truncated = (
        '{"claims":[{"speaker":"andrej-karpathy","quote":"first quote here","claim_type":"belief"},'
        '{"speaker":"dario-amodei","quote":"second quote here","claim_type":"prediction"},'
        '{"speaker":"sam-altman","quote":"third one that got cut'
    )
    rows = parse_claims_json(truncated)
    assert rows is not None
    assert [row["speaker"] for row in rows] == ["andrej-karpathy", "dario-amodei"]


def test_braces_inside_quoted_text_do_not_confuse_the_salvage():
    from on_record_ingest.extract.validate import parse_claims_json

    truncated = (
        '{"claims":[{"speaker":"x","quote":"he said {weird} things","claim_type":"belief"},{'
    )
    rows = parse_claims_json(truncated)
    assert rows is not None
    assert rows[0]["quote"] == "he said {weird} things"


def test_well_formed_json_is_untouched():
    from on_record_ingest.extract.validate import parse_claims_json

    assert parse_claims_json('{"claims":[]}') == []
    assert parse_claims_json('```json\n{"claims":[{"quote":"a"}]}\n```') == [{"quote": "a"}]


def test_served_model_prefers_what_the_gateway_actually_used():
    from on_record_ingest.extract.claims import served_model

    assert served_model({"x_gateway": {"model": "ministral-3b-latest"}}, "gemini-2.5-flash") == (
        "ministral-3b-latest"
    )
    assert served_model({"model": "gemini-2.5-flash"}, "auto") == "gemini-2.5-flash"
    assert served_model({}, "auto") == "auto"


def test_extraction_prompt_carries_only_this_episode_roster():
    from on_record_ingest.extract.claims import build_user_prompt

    prompt = build_user_prompt(
        ["dwarkesh-patel", "dario-amodei"],
        "",
        "segment text",
        ["ai-agents"],
        ["dwarkesh-patel", "dario-amodei"],
    )
    assert "dario-amodei" in prompt
    # Someone on the global roster but not on this episode must not appear.
    assert "jensen-huang" not in prompt


def test_local_and_gateway_requests_differ_where_they_must():
    from dataclasses import replace

    from on_record_ingest.config import settings as load
    from on_record_ingest.extract.claims import build_body, is_local

    base = load()
    local = replace(base, ai_base_url="http://localhost:1234/v1", force_model="qwen/qwen3.5-27b")
    gateway = replace(base, ai_base_url="https://ai-gateway.sassmaker.com/v1", force_model="")

    assert is_local(local) and not is_local(gateway)

    lb = build_body(local, "sys", "user")
    assert lb["response_format"]["type"] == "json_schema"
    # Thinking left on returns an empty message; extraction is a reading task.
    assert lb["reasoning_effort"] == "none"
    assert "min_reasoning_level" not in lb and "project_id" not in lb

    gb = build_body(gateway, "sys", "user")
    assert gb["response_format"]["type"] == "json_object"
    assert gb["min_reasoning_level"] == "high"


def test_batch_extraction_keeps_claim_attached_to_its_exact_segment(monkeypatch):
    from dataclasses import replace

    from on_record_ingest.config import settings as load
    from on_record_ingest.extract import claims as claims_module

    text = (
        "I think the strongest product teams keep direct contact with customers "
        "because otherwise prioritization becomes detached from real problems."
    )
    response = {
        "claims": [
            {
                "segment_id": "segment-1",
                "speaker": "guest-one",
                "speaker_confidence": 0.99,
                "claim_type": "belief",
                "assertion": "The speaker believes product teams need direct customer contact.",
                "stance": "supports",
                "quote": text,
                "topics": [],
                "extraction_confidence": 0.95,
                "references": [],
            }
        ]
    }
    request_options = {}

    def fake_chat(*args, **kwargs):
        request_options.update(kwargs)
        return json.dumps(response), {"model": "local-test"}, 12

    monkeypatch.setattr(claims_module, "_chat", fake_chat)
    cfg = replace(load(), ai_base_url="http://127.0.0.1:1234/v1")
    accepted, rejected, run = claims_module.extract_segments_batch(
        cfg,
        [{"id": "segment-1", "speakerHint": "guest-one", "text": text}],
    )
    assert rejected == []
    assert accepted[0]["segmentId"] == "segment-1"
    assert accepted[0]["speakerRaw"] == "guest-one"
    assert accepted[0]["assertion"] == text
    assert run["requestJson"]["segmentIds"] == ["segment-1"]
    assert request_options["max_tokens"] == 2048


def test_recommendation_batch_uses_strict_focus_prompt_and_version(monkeypatch):
    from dataclasses import replace

    from on_record_ingest.config import settings as load
    from on_record_ingest.extract import claims as claims_module

    text = "I recommend Cursor because I use Cursor every day for production coding work."
    response = {
        "claims": [
            {
                "segment_id": "segment-1",
                "claim_type": "recommendation",
                "stance": "supports",
                "topics": [],
                "extraction_confidence": 0.95,
                "references": [{"kind": "app", "name": "Cursor", "role": "recommends"}],
            }
        ]
    }
    request = {}

    def fake_chat(_settings, _user_prompt, system_prompt, **kwargs):
        request["system_prompt"] = system_prompt
        request.update(kwargs)
        return json.dumps(response), {"model": "local-test"}, 12

    monkeypatch.setattr(claims_module, "_chat", fake_chat)
    cfg = replace(load(), ai_base_url="http://127.0.0.1:1234/v1")
    accepted, rejected, run = claims_module.extract_segments_batch(
        cfg,
        [{"id": "segment-1", "speakerHint": "guest-one", "text": text}],
        focus="recs",
    )
    assert rejected == []
    assert accepted[0]["references"] == [{"kind": "app", "name": "Cursor", "role": "recommends"}]
    assert "named recommendations" in request["system_prompt"]
    assert run["promptVersion"] == "extract-recs-v5"
    assert run["requestJson"]["focus"] == "recs"


def test_book_batch_accepts_contracted_reading_with_exact_title(monkeypatch):
    from dataclasses import replace

    from on_record_ingest.config import settings as load
    from on_record_ingest.extract import claims as claims_module

    text = "I've read The Beginning of Infinity three times because it keeps changing my mind."
    response = {
        "claims": [
            {
                "segment_id": "segment-1",
                "claim_type": "recommendation",
                "stance": "uses",
                "topics": [],
                "extraction_confidence": 0.95,
                "references": [
                    {"kind": "book", "name": "The Beginning of Infinity", "role": "uses"}
                ],
            }
        ]
    }
    request = {}

    def fake_chat(_settings, _user_prompt, system_prompt, **kwargs):
        request["system_prompt"] = system_prompt
        return json.dumps(response), {"model": "local-test"}, 12

    monkeypatch.setattr(claims_module, "_chat", fake_chat)
    cfg = replace(load(), ai_base_url="http://127.0.0.1:1234/v1")
    accepted, rejected, run = claims_module.extract_segments_batch(
        cfg,
        [{"id": "segment-1", "speakerHint": "guest-one", "text": text}],
        focus="books",
    )
    assert rejected == []
    assert accepted[0]["references"] == [
        {"kind": "book", "name": "The Beginning of Infinity", "role": "uses"}
    ]
    assert "named books" in request["system_prompt"]
    assert run["promptVersion"] == "extract-books-v1"


def test_book_answer_batch_uses_independent_checkpoint(monkeypatch):
    from dataclasses import replace

    from on_record_ingest.config import settings as load
    from on_record_ingest.extract import claims as claims_module

    monkeypatch.setattr(
        claims_module,
        "_chat",
        lambda *_args, **_kwargs: ('{"claims":[]}', {"model": "local-test"}, 4),
    )
    cfg = replace(load(), ai_base_url="http://127.0.0.1:1234/v1")
    _accepted, _rejected, run = claims_module.extract_segments_batch(
        cfg,
        [
            {
                "id": "answer",
                "speakerHint": "guest",
                "text": "The first is The Power Broker by Robert Caro, which changed how I think.",
                "bookQuestion": "Which books do you recommend most?",
            }
        ],
        focus="book_answers",
    )
    assert run["promptVersion"] == "extract-book-answers-v4"


def test_book_roles_accept_title_first_reading_and_explicit_positive_evaluation():
    from on_record_ingest.extract.validate import validate_references

    reading = "There's one called The Gruffalo, I read to my kids every night before bed."
    positive = "Functional Programming in Scala is the single best technical book I have ever read."
    deictic = "The Upside of Stress changed how I approach hard work, and I highly recommend it."
    assert validate_references(
        {"references": [{"kind": "book", "name": "The Gruffalo", "role": "uses"}]},
        reading,
    ) == [{"kind": "book", "name": "The Gruffalo", "role": "uses"}]
    assert validate_references(
        {
            "references": [
                {
                    "kind": "book",
                    "name": "Functional Programming in Scala",
                    "role": "likes",
                }
            ]
        },
        positive,
    ) == [{"kind": "book", "name": "Functional Programming in Scala", "role": "likes"}]
    assert validate_references(
        {"references": [{"kind": "book", "name": "The Upside of Stress", "role": "recommends"}]},
        deictic,
    ) == [{"kind": "book", "name": "The Upside of Stress", "role": "recommends"}]

    direct_emphasis = "I do love the Design of Everyday Things. I think that's such a classic."
    assert validate_references(
        {"references": [{"kind": "book", "name": "Design of Everyday Things", "role": "likes"}]},
        direct_emphasis,
    ) == [{"kind": "book", "name": "Design of Everyday Things", "role": "likes"}]


def test_book_answer_context_supports_a_bare_enumerated_title():
    quote = "The first is The Power Broker by Robert Caro, which changed how I think."
    assert validate_references(
        {
            "bookAnswer": True,
            "references": [{"kind": "book", "name": "The Power Broker", "role": "recommends"}],
        },
        quote,
    ) == [{"kind": "book", "name": "The Power Broker", "role": "recommends"}]
    assert (
        validate_references(
            {"references": [{"kind": "book", "name": "The Power Broker", "role": "recommends"}]},
            quote,
        )
        == []
    )
    code_quote = "Code by Charles Petzold explains the secret language of hardware and software."
    assert validate_references(
        {
            "bookAnswer": True,
            "references": [{"kind": "book", "name": "Code", "role": "recommends"}],
        },
        code_quote,
    ) == [{"kind": "book", "name": "Code", "role": "recommends"}]


def test_batch_extraction_rejects_a_segment_id_outside_the_batch(monkeypatch):
    from dataclasses import replace

    from on_record_ingest.config import settings as load
    from on_record_ingest.extract import claims as claims_module

    response = {
        "claims": [
            {
                "segment_id": "invented-segment",
                "speaker": "guest-one",
                "speaker_confidence": 0.99,
                "claim_type": "belief",
                "assertion": "An invented claim.",
                "quote": "This quote is deliberately long enough to pass the minimum length rule.",
                "topics": [],
                "extraction_confidence": 0.95,
                "references": [],
            }
        ]
    }
    monkeypatch.setattr(
        claims_module,
        "_chat",
        lambda *args, **kwargs: (json.dumps(response), {"model": "local-test"}, 12),
    )
    cfg = replace(load(), ai_base_url="http://127.0.0.1:1234/v1")
    accepted, rejected, _ = claims_module.extract_segments_batch(
        cfg,
        [
            {
                "id": "segment-1",
                "speakerHint": "guest-one",
                "text": "This source segment is long enough but does not contain the invented quote.",
            }
        ],
    )
    assert accepted == []
    assert rejected[0]["reason"] == "segment_not_in_batch"


def test_batch_request_schema_requires_the_exact_segment_id():
    from dataclasses import replace

    from on_record_ingest.config import settings as load
    from on_record_ingest.extract.claims import BATCH_CLAIMS_SCHEMA, build_body

    cfg = replace(load(), ai_base_url="http://127.0.0.1:1234/v1")
    body = build_body(cfg, "system", "user", schema=BATCH_CLAIMS_SCHEMA)
    item = body["response_format"]["json_schema"]["schema"]["properties"]["claims"]["items"]
    assert "segment_id" in item["required"]
