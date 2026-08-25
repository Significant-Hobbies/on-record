from on_record_ingest.roster import candidates, looks_like_a_person, names_in_title, slugify


def test_reads_the_shapes_podcast_titles_actually_use():
    assert "Dario Amodei" in names_in_title("Dario Amodei — We are near the end of the exponential")
    assert "Max Hodak" in names_in_title(
        "From Restoring Sight to Reimagining the Brain, with Max Hodak"
    )
    assert "Andrej Karpathy" in names_in_title("#500 – Andrej Karpathy: AGI is a decade away")
    assert "Martin Casado" in names_in_title("Martin Casado on Where the Value Is Going in AI")


def test_rejects_things_that_are_not_people():
    assert not looks_like_a_person("The Cognitive")
    assert not looks_like_a_person("AI Agents")
    assert not looks_like_a_person("OpenAI")
    assert not looks_like_a_person("Building Great")
    assert looks_like_a_person("Sarah Guo")
    assert looks_like_a_person("Sam A. Altman")


def test_ranks_by_how_often_a_name_is_booked_and_skips_the_roster():
    rows = candidates(
        [
            {"title": "Guest One — topic"},
            {"title": "Guest One: another topic"},
            {"title": "Guest Two — topic"},
            {"title": "Dario Amodei — already on the roster"},
        ]
    )
    assert [r["name"] for r in rows] == ["Guest One", "Guest Two"]
    assert rows[0]["episodes"] == 2
    assert "already on the roster" not in str(rows)


def test_slug_matches_the_seed_convention():
    assert slugify("Sarah Guo") == "sarah-guo"
    assert slugify("Sam A. Altman") == "sam-a-altman"


def test_recurring_names_need_no_model():
    from on_record_ingest.roster import split_by_evidence

    recurring, singles = split_by_evidence(
        [{"name": "A", "episodes": 4}, {"name": "B", "episodes": 2}, {"name": "C", "episodes": 1}]
    )
    assert [r["name"] for r in recurring] == ["A", "B"]
    assert [r["name"] for r in singles] == ["C"]


def test_a_failed_batch_is_retried_not_dropped():
    from on_record_ingest import roster

    calls = []

    def flaky(settings, chunk, keep):
        calls.append(list(chunk))
        if len(calls) == 1:
            return False
        keep.update(chunk)
        return True

    original = roster._validate_chunk
    roster._validate_chunk = flaky
    try:
        kept = roster.validate_names(None, ["Real Person"], batch=15)
    finally:
        roster._validate_chunk = original
    assert kept == {"Real Person"}
    assert len(calls) == 2
