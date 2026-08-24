from on_record_ingest.segment import cues_to_segments


def test_segments_split_on_cue_boundaries_and_overlap():
    cues = [
        {"start": 0.0, "duration": 1.0, "text": "alpha " + ("word " * 40)},
        {"start": 1.0, "duration": 1.0, "text": "bravo " + ("word " * 40)},
        {"start": 2.0, "duration": 1.0, "text": "charlie " + ("word " * 40)},
    ]
    segments = cues_to_segments(cues, target_chars=120)
    assert len(segments) >= 2
    assert segments[0]["startS"] == 0.0
    assert segments[-1]["endS"] == 3.0
    assert segments[1]["idx"] == 1
