from on_record_ingest.speaker_recovery import recover_self_identified_speakers


def test_recovers_a_unique_self_introduction_and_propagates_the_label():
    detail = {
        "episode": {"transcriptKind": "youtube_manual"},
        "people": [
            {"personId": "host-id", "confidence": 1.0},
            {"personId": "guest-id", "confidence": 0.9},
        ],
        "segments": [
            {
                "idx": 0,
                "diarLabel": "SPEAKER_00",
                "speakerHint": "unknown",
                "text": "I'm your host, Alice Example, and today we're discussing product strategy.",
            },
            {
                "idx": 1,
                "diarLabel": "SPEAKER_01",
                "speakerHint": "unknown",
                "text": "I'm Bob Builder. The lesson is to talk to customers every week.",
            },
            {
                "idx": 2,
                "diarLabel": "SPEAKER_01",
                "speakerHint": "unknown",
                "text": "I think the strongest teams keep the feedback loop short.",
            },
        ],
    }
    people = {
        "host-id": {"name": "Alice Example", "slug": "alice-example"},
        "guest-id": {"name": "Bob Builder", "slug": "bob-builder"},
    }
    assert recover_self_identified_speakers(detail, people) == [
        {"diarLabel": "SPEAKER_00", "idx": 0, "speakerHint": "alice-example"},
        {"diarLabel": "SPEAKER_01", "idx": 1, "speakerHint": "bob-builder"},
        {"diarLabel": "SPEAKER_01", "idx": 2, "speakerHint": "bob-builder"},
    ]


def test_rejects_ambiguous_names_labels_and_coarse_transcripts():
    people = {
        "one": {"name": "John Smith", "slug": "john-smith"},
        "two": {"name": "John Jones", "slug": "john-jones"},
    }
    ambiguous = {
        "episode": {"transcriptKind": "youtube_auto"},
        "people": [{"personId": "one"}, {"personId": "two"}],
        "segments": [
            {
                "idx": 0,
                "diarLabel": "A",
                "speakerHint": "unknown",
                "text": "I'm John, and I think this market is still early.",
            },
            {
                "idx": 1,
                "diarLabel": "A",
                "speakerHint": "unknown",
                "text": "I am John Smith, and I believe distribution is the advantage.",
            },
            {
                "idx": 2,
                "diarLabel": "B",
                "speakerHint": "unknown",
                "text": "My name is John Smith, and I would argue the product is too broad.",
            },
        ],
    }
    assert recover_self_identified_speakers(ambiguous, people) == []
    ambiguous["episode"]["transcriptKind"] = "rss_text_coarse"
    assert recover_self_identified_speakers(ambiguous, people) == []


def test_recovers_the_only_remaining_title_named_guest_by_exclusion():
    detail = {
        "episode": {
            "title": "Jane Guest explains why markets change",
            "transcriptKind": "rss_text",
        },
        "people": [
            {"personId": "host", "confidence": 1.0},
            {"personId": "guest", "confidence": 0.7},
            {"personId": "mention", "confidence": 0.7},
        ],
        "segments": [
            {
                "idx": 0,
                "diarLabel": "A",
                "speakerHint": "host-person",
                "text": "Welcome to the show.",
            },
            {
                "idx": 1,
                "diarLabel": "B",
                "speakerHint": "unknown",
                "text": "I think the important change is how quickly customers respond.",
            },
        ],
    }
    people = {
        "host": {"name": "Host Person", "slug": "host-person"},
        "guest": {"name": "Jane Guest", "slug": "jane-guest"},
        "mention": {"name": "Merely Mentioned", "slug": "merely-mentioned"},
    }
    assert recover_self_identified_speakers(detail, people) == [
        {"diarLabel": "B", "idx": 1, "speakerHint": "jane-guest"}
    ]


def test_recovers_metadata_named_guest_from_host_welcome_and_response():
    detail = {
        "episode": {
            "description": "In this episode, we talk with Austin Frerick about food systems.",
            "title": "The Hidden Supply Chain",
            "transcriptKind": "rss_text",
        },
        "people": [
            {"personId": "host", "confidence": 1.0},
            {"personId": "guest", "confidence": 1.0},
        ],
        "segments": [
            {
                "idx": 0,
                "diarLabel": "A",
                "speakerHint": "host-person",
                "text": "Austin, welcome back to the show.",
            },
            {
                "idx": 1,
                "diarLabel": "B",
                "speakerHint": "unknown",
                "text": "Thanks for having me on again.",
            },
            {
                "idx": 2,
                "diarLabel": "B",
                "speakerHint": "unknown",
                "text": "I think local food systems need different incentives.",
            },
            {
                "idx": 3,
                "diarLabel": "AD",
                "speakerHint": "unknown",
                "text": "Subscribe wherever you get podcasts.",
            },
        ],
    }
    people = {
        "host": {"name": "Host Person", "slug": "host-person"},
        "guest": {"name": "Austin Frerick", "slug": "austin-frerick"},
    }
    assert recover_self_identified_speakers(detail, people) == [
        {"diarLabel": "B", "idx": 1, "speakerHint": "austin-frerick"},
        {"diarLabel": "B", "idx": 2, "speakerHint": "austin-frerick"},
    ]


def test_does_not_recover_a_welcome_without_guest_acceptance():
    detail = {
        "episode": {"description": "We talk with Austin Frerick.", "transcriptKind": "rss_text"},
        "people": [{"personId": "guest", "confidence": 1.0}],
        "segments": [
            {
                "idx": 0,
                "diarLabel": "A",
                "speakerHint": "known-host",
                "text": "Austin, welcome to the show.",
            },
            {
                "idx": 1,
                "diarLabel": "B",
                "speakerHint": "unknown",
                "text": "The market structure changed over the last decade.",
            },
            {
                "idx": 2,
                "diarLabel": "AD",
                "speakerHint": "unknown",
                "text": "Listen every week.",
            },
        ],
    }
    people = {"guest": {"name": "Austin Frerick", "slug": "austin-frerick"}}
    assert recover_self_identified_speakers(detail, people) == []


def test_recovers_an_explicit_full_name_introduction_before_a_direct_answer():
    detail = {
        "episode": {
            "description": "A discussion of public spending and government credibility.",
            "title": "Fritz Bartel on Why Public Spending Is Hard to Cut",
            "transcriptKind": "rss_text",
        },
        "people": [
            {"personId": "host", "confidence": 1.0, "role": "host"},
            {
                "personId": "guest",
                "confidence": 1.0,
                "role": "guest",
                "attributionSource": "metadata_match",
            },
        ],
        "segments": [
            {
                "idx": 0,
                "diarLabel": "HOST",
                "speakerHint": "unknown",
                "text": (
                    "We are going to be speaking with Fritz Bartel about his research. "
                    "What is the core problem?"
                ),
            },
            {
                "idx": 1,
                "diarLabel": "GUEST",
                "speakerHint": "unknown",
                "text": "The core problem is that every spending cut breaks a prior promise.",
            },
            {
                "idx": 2,
                "diarLabel": "GUEST",
                "speakerHint": "unknown",
                "text": "Governments need public credibility to make those choices.",
            },
        ],
    }
    people = {
        "host": {"name": "Known Host", "slug": "known-host"},
        "guest": {"name": "Fritz Bartel", "slug": "fritz-bartel"},
    }
    assert recover_self_identified_speakers(detail, people) == [
        {"diarLabel": "GUEST", "idx": 1, "speakerHint": "fritz-bartel"},
        {"diarLabel": "GUEST", "idx": 2, "speakerHint": "fritz-bartel"},
    ]


def test_recovers_one_explicit_guest_from_a_dominant_unknown_label():
    guest_text = "The important structural change is that incentives now reward scale. " * 5
    detail = {
        "episode": {
            "description": "In this episode, we talk with Austin Frerick about food systems.",
            "title": "The Hidden Supply Chain",
            "transcriptKind": "rss_text",
        },
        "people": [
            {"personId": "host", "confidence": 1.0, "role": "host"},
            {
                "personId": "guest",
                "confidence": 1.0,
                "role": "guest",
                "attributionSource": "metadata_match",
            },
        ],
        "segments": [
            {
                "idx": 0,
                "diarLabel": "HOST",
                "speakerHint": "host-person",
                "text": "Welcome to the show.",
            },
            *[
                {
                    "idx": idx,
                    "diarLabel": "GUEST",
                    "speakerHint": "unknown",
                    "text": guest_text,
                }
                for idx in range(1, 13)
            ],
            {
                "idx": 13,
                "diarLabel": "AD",
                "speakerHint": "unknown",
                "text": "Subscribe to the newsletter for more episodes.",
            },
        ],
    }
    people = {
        "host": {"name": "Host Person", "slug": "host-person"},
        "guest": {"name": "Austin Frerick", "slug": "austin-frerick"},
    }
    assert recover_self_identified_speakers(detail, people) == [
        {"diarLabel": "GUEST", "idx": idx, "speakerHint": "austin-frerick"} for idx in range(1, 13)
    ]


def test_rejects_dominance_when_metadata_or_labels_are_ambiguous():
    substantive = "This is a durable explanation of how the market changed. " * 5
    detail = {
        "episode": {
            "description": "We talk with Jane Guest and we speak with Bob Builder.",
            "transcriptKind": "rss_text",
        },
        "people": [
            {
                "personId": "one",
                "confidence": 1.0,
                "role": "guest",
                "attributionSource": "metadata_match",
            },
            {
                "personId": "two",
                "confidence": 1.0,
                "role": "guest",
                "attributionSource": "metadata_match",
            },
        ],
        "segments": [
            {
                "idx": 0,
                "diarLabel": "HOST",
                "speakerHint": "known-host",
                "text": "Welcome.",
            },
            *[
                {
                    "idx": idx,
                    "diarLabel": "UNKNOWN",
                    "speakerHint": "unknown",
                    "text": substantive,
                }
                for idx in range(1, 13)
            ],
        ],
    }
    people = {
        "one": {"name": "Jane Guest", "slug": "jane-guest"},
        "two": {"name": "Bob Builder", "slug": "bob-builder"},
    }
    assert recover_self_identified_speakers(detail, people) == []


def test_corrected_guest_does_not_assign_an_old_metadata_typo_to_an_ad_label():
    guest_text = "The state needs credibility before it can break difficult promises. " * 5
    detail = {
        "episode": {
            "description": "We speak with Firtz Bartel about public spending.",
            "title": "Why Public Spending Is Hard to Cut",
            "transcriptKind": "rss_text",
        },
        "people": [
            {"personId": "host", "confidence": 1.0, "role": "host"},
            {
                "personId": "typo",
                "confidence": 1.0,
                "role": "guest",
                "attributionSource": "metadata_match",
            },
            {
                "personId": "correct",
                "confidence": 1.0,
                "role": "guest",
                "attributionSource": "metadata_match",
            },
        ],
        "segments": [
            {
                "idx": 0,
                "diarLabel": "HOST",
                "speakerHint": "known-host",
                "text": "Professor Bartel, thank you for joining us.",
            },
            *[
                {
                    "idx": idx,
                    "diarLabel": "GUEST",
                    "speakerHint": "unknown",
                    "text": guest_text,
                }
                for idx in range(1, 13)
            ],
            {
                "idx": 13,
                "diarLabel": "AD",
                "speakerHint": "unknown",
                "text": "Bloomberg Audio Studios.",
            },
        ],
    }
    people = {
        "host": {"name": "Known Host", "slug": "known-host"},
        "typo": {"name": "Firtz Bartel", "slug": "firtz-bartel"},
        "correct": {"name": "Fritz Bartel", "slug": "fritz-bartel"},
    }
    assert recover_self_identified_speakers(detail, people) == [
        {"diarLabel": "GUEST", "idx": idx, "speakerHint": "fritz-bartel"} for idx in range(1, 13)
    ]


def test_publisher_bumper_excludes_pre_roll_from_recovery():
    detail = {
        "episode": {
            "description": "We talk with Nick Bostrom about artificial intelligence.",
            "transcriptKind": "rss_text",
        },
        "people": [
            {
                "personId": "guest",
                "confidence": 1.0,
                "role": "guest",
                "attributionSource": "metadata_match",
            }
        ],
        "segments": [
            {
                "idx": 0,
                "diarLabel": "GUEST",
                "speakerHint": "unknown",
                "text": "I'm Joe, and I'm Tracy. Get tickets for our live show.",
            },
            {
                "idx": 1,
                "diarLabel": "BUMPER",
                "speakerHint": "unknown",
                "text": "Bloomberg Audio Studios, Podcasts, Radio News.",
            },
            {
                "idx": 2,
                "diarLabel": "HOST",
                "speakerHint": "unknown",
                "text": "We are speaking with Nick Bostrom about his new book.",
            },
            {
                "idx": 3,
                "diarLabel": "GUEST",
                "speakerHint": "unknown",
                "text": "Happy to join you. The range of possible outcomes is unusually wide.",
            },
        ],
    }
    people = {"guest": {"name": "Nick Bostrom", "slug": "nick-bostrom"}}
    assert recover_self_identified_speakers(detail, people) == [
        {"diarLabel": "GUEST", "idx": 3, "speakerHint": "nick-bostrom"}
    ]


def test_generic_rss_rejects_label_propagation_across_a_long_multi_guest_show():
    detail = {
        "episode": {
            "description": "A long live show with many interviews.",
            "title": "Andrew Feldman and Many More Guests",
            "transcriptKind": "rss_text",
        },
        "people": [
            {
                "personId": "guest",
                "confidence": 0.7,
                "role": "guest",
                "attributionSource": "metadata_match",
            }
        ],
        "segments": [
            {
                "idx": idx,
                "diarLabel": "Speaker 1" if idx % 2 == 0 else "Speaker 2",
                "speakerHint": "unknown",
                "text": (
                    "We are speaking with Andrew Feldman now."
                    if idx == 100
                    else "A label reused across a long live show."
                ),
            }
            for idx in range(301)
        ],
    }
    people = {"guest": {"name": "Andrew Feldman", "slug": "andrew-feldman"}}
    assert recover_self_identified_speakers(detail, people) == []


def test_does_not_treat_a_cohost_continuing_the_intro_as_the_named_guest():
    detail = {
        "episode": {
            "description": "We talk with Tom McGee about choosing retail locations.",
            "transcriptKind": "rss_text",
        },
        "people": [
            {
                "personId": "guest",
                "confidence": 1.0,
                "role": "guest",
                "attributionSource": "metadata_match",
            }
        ],
        "segments": [
            {
                "idx": 0,
                "diarLabel": "HOST_A",
                "speakerHint": "known-host-a",
                "text": "We are going to talk with Tom McGee about shopping centers.",
            },
            {
                "idx": 1,
                "diarLabel": "HOST_B",
                "speakerHint": "unknown",
                "text": "That's right, and after our conversation we have a second guest.",
            },
            {
                "idx": 2,
                "diarLabel": "GUEST",
                "speakerHint": "unknown",
                "text": "Retailers usually begin with their growth objectives.",
            },
        ],
    }
    people = {"guest": {"name": "Tom McGee", "slug": "tom-mcgee"}}
    assert recover_self_identified_speakers(detail, people) == []
