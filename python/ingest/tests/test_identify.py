from on_record_ingest.identify import UNKNOWN, build_prompt, parse_mapping, sample_by_speaker

ROSTER = [
    {"slug": "dwarkesh-patel", "name": "Dwarkesh Patel", "role": "host"},
    {"slug": "martin-casado", "name": "Martin Casado", "role": "guest"},
    {"slug": "steven-sinofsky", "name": "Steven Sinofsky", "role": "guest"},
]
LABELS = {"A", "B", "C"}
SLUGS = {p["slug"] for p in ROSTER}


def test_samples_are_grouped_and_capped_per_voice():
    segs = [{"speakerHint": "A", "text": f"turn {i}"} for i in range(10)]
    segs += [{"speakerHint": "B", "text": "other"}, {"speakerHint": None, "text": "no label"}]
    samples = sample_by_speaker(segs)
    assert set(samples) == {"A", "B"}
    assert len(samples["A"]) == 6


def test_prompt_names_the_roster_and_every_voice():
    prompt = build_prompt({"A": ["hello"], "B": ["hi"]}, ROSTER, "The New Economics of AI")
    assert "martin-casado" in prompt and "steven-sinofsky" in prompt
    assert "Speaker A" in prompt and "Speaker B" in prompt
    assert "The New Economics of AI" in prompt


def test_a_clean_mapping_is_taken_as_given():
    raw = '{"speakers": {"A": "dwarkesh-patel", "B": "martin-casado", "C": "steven-sinofsky"}}'
    assert parse_mapping(raw, LABELS, SLUGS) == {
        "A": "dwarkesh-patel",
        "B": "martin-casado",
        "C": "steven-sinofsky",
    }


def test_one_person_cannot_be_two_voices():
    # A duplicate slug means the model guessed; the second becomes unknown.
    raw = '{"speakers": {"A": "martin-casado", "B": "martin-casado"}}'
    mapping = parse_mapping(raw, LABELS, SLUGS)
    assert mapping["A"] == "martin-casado"
    assert mapping["B"] == UNKNOWN


def test_names_outside_the_roster_are_refused():
    raw = '{"speakers": {"A": "elon-musk", "B": "unknown"}}'
    mapping = parse_mapping(raw, LABELS, SLUGS)
    assert mapping["A"] == UNKNOWN and mapping["B"] == UNKNOWN


def test_unparseable_reply_maps_nobody():
    assert parse_mapping("I think speaker A is the host", LABELS, SLUGS) == {}


def test_a_diarized_segment_decides_its_own_speaker(monkeypatch):
    """The model is handed one name, and the segment overrides whatever it says."""
    from on_record_ingest import pipeline

    seen = {}

    def fake_extract(cfg, text, prev_tail, roster, focus):
        seen["roster"] = roster
        seen["focus"] = focus
        return ([{"speakerRaw": "someone-else", "assertion": "a"}], [], {"model": "m"})

    monkeypatch.setattr(pipeline, "extract_segment", fake_extract)
    monkeypatch.setattr(pipeline, "attach_person_ids", lambda claims, m: claims)

    class Cfg:
        pipeline_version = "claims-v1"
        extract_model = "m"
        prompt_version = "extract-v2"

    segment = {"id": "s1", "idx": 0, "text": "words", "speakerHint": "martin-casado"}
    claims, _run, _n = pipeline.extract_one_segment(
        Cfg(), {}, segment, "", ["dwarkesh-patel", "steven-sinofsky"]
    )
    assert seen["roster"] == ["martin-casado"]
    assert seen["focus"] == "all"
    assert claims[0]["speakerRaw"] == "martin-casado"


def test_the_model_may_answer_with_the_wording_it_was_shown():
    # It is shown "Speaker B" and answers "Speaker B"; the label is "B".
    raw = '{"speakers": {"Speaker A": "unknown", "Speaker B": "martin-casado"}}'
    mapping = parse_mapping(raw, LABELS, SLUGS)
    assert mapping["B"] == "martin-casado"
    assert mapping["A"] == UNKNOWN


def test_label_matching_is_forgiving_but_not_loose():
    from on_record_ingest.identify import match_label

    assert match_label("Speaker C", {"A", "B", "C"}) == "C"
    assert match_label("speaker c", {"A", "B", "C"}) == "C"
    assert match_label(" B ", {"A", "B", "C"}) == "B"
    assert match_label("Speaker Z", {"A", "B", "C"}) is None
    assert match_label("Martin Casado", {"A", "B", "C"}) is None


def test_a_title_match_is_never_buried():
    from on_record_ingest.attributions import confidence_for

    # Lex's "#500 - Guest: topics" was misread twice; the title still counts.
    held = confidence_for(
        {"appears": False}, "Khabib Nurmagomedov", "#500 - Khabib Nurmagomedov: MMA"
    )
    assert held is not None and held >= 0.6
    # Not in the title and judged a mention: safe to bury.
    buried = confidence_for({"appears": False}, "Sundar Pichai", "Dylan Patel: GPT-5, NVIDIA")
    assert buried is not None and buried < 0.2
    # Confirmed appearance is confident either way.
    assert confidence_for({"appears": True}, "Anyone", "Some title") == 0.95
    # An undecided verdict must not change anything.
    assert confidence_for(None, "Anyone", "Some title") is None
