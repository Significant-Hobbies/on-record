from on_record_ingest.extract.triage import triage_segment


def test_keeps_personal_stack_as_a_recommendation_candidate():
    assert (
        triage_segment("Personally I use Cursor every day instead of writing every line by hand.")
        == "rec"
    )
    assert triage_segment("Claude and Codex don't replace the job yet, they just don't work.") == (
        "claim"
    )


def test_keeps_claim_speech():
    text = (
        "In my mind this is more accurately described as the decade of agents. "
        "It will take about a decade to work through all of those issues."
    )
    assert triage_segment(text) == "claim"


def test_focus_recs_does_not_promote_a_named_product_evaluation():
    assert triage_segment("Claude and Codex don't replace the job yet, they just don't work.") == (
        "claim"
    )


def test_skips_filler_and_short():
    assert triage_segment("Thanks for having me.") == "skip"
    assert (
        triage_segment(
            "Thanks for coming on, subscribe to the channel, we'll be right back after this."
        )
        == "skip"
    )
