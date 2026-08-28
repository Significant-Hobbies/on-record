from on_record_ingest.extract.triage import (
    book_answer_candidate,
    book_excerpt,
    claim_candidate_score,
    claim_excerpt,
    deterministic_excerpt_is_complete,
    triage_book_segment,
    triage_segment,
)


def test_book_focus_keeps_explicit_reading_and_preference_actions():
    assert triage_book_segment("I've read The Beginning of Infinity three times now.") == "book"
    assert (
        triage_book_segment(
            "One book I really loved was Thinking in Systems because it changed how I plan."
        )
        == "book"
    )
    assert triage_book_segment("The guest mentioned The Beginning of Infinity in passing.") == (
        "skip"
    )


def test_book_excerpt_centers_the_exact_book_action():
    text = (
        "This is unrelated scene-setting. "
        "I'm reading The Power Broker because its account of institutions is extraordinary. "
        "This is unrelated closing narration."
    )
    excerpt = book_excerpt(text)
    assert excerpt in text
    assert excerpt.startswith("I'm reading The Power Broker")
    assert "closing narration" not in excerpt


def test_book_answer_candidate_requires_an_explicit_question_and_title_shape():
    question = "What are two or three books that you recommend most to other people?"
    assert book_answer_candidate(
        question,
        "The first is The Power Broker by Robert Caro, which changed how I understand cities.",
    )
    assert not book_answer_candidate(
        "What product do you recommend?",
        "The first is The Power Broker by Robert Caro, which changed how I understand cities.",
    )


def test_keeps_personal_stack_as_a_recommendation_candidate():
    assert (
        triage_segment("Personally I use Cursor every day instead of writing every line by hand.")
        == "rec"
    )
    assert triage_segment("Claude and Codex don't replace the job yet, they just don't work.") == (
        "claim"
    )


def test_keeps_distinct_preference_ownership_and_authorship_candidates():
    assert triage_segment("I love Figma for sketching product ideas with my team.") == "rec"
    assert triage_segment("I've bought every edition of The Pragmatic Programmer.") == "rec"
    assert triage_segment("We authored Designing Data-Intensive Applications together.") == "rec"


def test_keeps_claim_speech():
    text = (
        "In my mind this is more accurately described as the decade of agents. "
        "It will take about a decade to work through all of those issues."
    )
    assert triage_segment(text) == "claim"


def test_keeps_opinions_predictions_explanations_and_commitments():
    assert (
        triage_segment(
            "I would argue that the durable advantage is direct access to customers, "
            "because the team learns faster than competitors."
        )
        == "claim"
    )
    assert (
        triage_segment(
            "We predict the current generation of agents will become reliable enough "
            "to own narrow workflows within two years."
        )
        == "claim"
    )
    assert (
        triage_segment(
            "The lesson is that distribution compounds only when the product keeps "
            "earning repeat use from the same customers."
        )
        == "claim"
    )
    assert (
        triage_segment(
            "We will stop shipping broad features and commit to solving the onboarding "
            "problem for one customer segment."
        )
        == "claim"
    )


def test_rejects_questions_ads_and_generic_named_mentions():
    assert (
        triage_segment(
            "Do you think artificial intelligence will replace every job in the next few years?"
        )
        == "skip"
    )
    assert (
        triage_segment(
            "What would be a couple things you recommend people do to be more successful "
            "in this future?"
        )
        == "skip"
    )
    assert (
        triage_segment(
            "This episode is sponsored by Acme Cloud, where you can start a free trial "
            "and use code PODCAST for twenty percent off."
        )
        == "skip"
    )
    assert (
        triage_segment(
            "What is the latest with OneSchema? I know you now work with companies like "
            "Ramp and Vanta. We see our customers all the time getting stuck with hacks "
            "and workarounds, so we just launched OneSchema FileFeeds."
        )
        == "skip"
    )
    assert (
        triage_segment(
            "The team opened ChatGPT during the meeting and then moved to the next item "
            "on the agenda."
        )
        == "skip"
    )


def test_claim_excerpt_is_an_exact_compact_window_around_the_signal():
    text = (
        "This is scene-setting that should not be the quote. "
        "I think direct customer contact is the strongest product advantage because it "
        "shortens the learning loop. More narration follows after the useful idea."
    )
    excerpt = claim_excerpt(text)
    assert excerpt in text
    assert excerpt.startswith("I think direct customer contact")
    assert "More narration" not in excerpt


def test_candidate_score_prefers_substantive_supported_positions_over_fragments():
    strong = (
        "I would argue that direct customer contact is the durable advantage because "
        "it shortens the learning loop in practice."
    )
    fragment = "And I think this is probably better-"
    assert claim_candidate_score(strong) > claim_candidate_score(fragment)
    assert claim_candidate_score(fragment) == 0
    assert (
        claim_candidate_score(
            "And I would argue that it is not yet a platform, but it is important."
        )
        == 0
    )


def test_deterministic_excerpt_rejects_fragments_and_interview_meta():
    assert deterministic_excerpt_is_complete(
        "I think direct customer contact is the durable advantage because it shortens "
        "the learning loop for every product decision."
    )
    assert not deterministic_excerpt_is_complete(
        "Because if the instructions are precise, the whole process is already scripted "
        "for you and there is no ambiguity."
    )
    assert not deterministic_excerpt_is_complete(
        "The interesting part, I don't know if it was where your question was going, "
        "is that those labs are managing researchers."
    )
    assert not deterministic_excerpt_is_complete(
        "heavily cloud code is used throughout the company and I think that gives the "
        "team a better view of where the product breaks."
    )


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
