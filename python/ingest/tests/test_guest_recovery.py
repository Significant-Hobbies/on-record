from on_record_ingest.guest_recovery import explicit_guest_names


def test_extracts_only_people_explicitly_presented_as_guests():
    description = """
    <p>Sysco changed American dining. In this episode, we talk with
    Austin Frerick, author of <em>Barons</em>, about the food system.
    Howard Schultz and Starbucks are also discussed.</p>
    """
    assert explicit_guest_names(description) == ["Austin Frerick"]


def test_supports_strong_guest_phrasings_and_deduplicates_names():
    description = (
        "We're joined by Jane Doe to discuss markets. "
        "Later, we speak with Jane Doe about her new research. "
        "Our guest today is Sam O'Neill."
    )
    assert explicit_guest_names(description) == ["Jane Doe", "Sam O'Neill"]


def test_rejects_unanchored_names_and_non_person_phrases():
    description = (
        "A history of Sam Altman and OpenAI. In this episode we talk with "
        "The Future about strategy. We're joined by Principal Scientist Oliver. "
        "We speak with Box Co-Founder and later chat with Simon Eski. Of."
    )
    assert explicit_guest_names(description) == []


def test_preserves_unicode_names_and_real_initials():
    description = "We talk with Simon Hørup Eskildsen and later we speak with Sam A. Altman."
    assert explicit_guest_names(description) == ["Simon Hørup Eskildsen", "Sam A. Altman"]


def test_rejects_truncated_or_possessive_metadata_names():
    assert (
        explicit_guest_names(
            "We talk with Simon Eski. Of Modal about retrieval.",
            "Retrieval — Simon Hørup Eskildsen of Turbopuffer",
        )
        == []
    )
    assert explicit_guest_names("We're joined by Republic's Kendrick Nguyen.") == []
    assert explicit_guest_names("We talk with Federal Reserve Bank about rates.") == []
    assert explicit_guest_names("We're joined by Columbia Business School.") == []
    assert explicit_guest_names("We speak with Florida Senator Marco about trade.") == []


def test_applies_a_source_verified_publisher_name_correction():
    assert explicit_guest_names("We speak with Firtz Bartel about public spending.") == [
        "Fritz Bartel"
    ]
