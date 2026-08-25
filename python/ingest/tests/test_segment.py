from on_record_ingest.segment import cue_time_at, cues_to_segments


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


def test_cue_map_points_at_the_cue_that_was_being_spoken():
    cues = [
        {"start": float(i) * 10.0, "duration": 10.0, "text": f"sentence{i} " + ("word " * 12)}
        for i in range(20)
    ]
    segments = cues_to_segments(cues, target_chars=400)
    assert len(segments) > 1
    for segment in segments:
        cue_map = segment["cueMap"]
        assert cue_map
        assert cue_map == sorted(cue_map)
        for i in range(20):
            needle = f"sentence{i} "
            at = segment["text"].find(needle)
            if at < 0:
                continue
            found = cue_time_at(cue_map, at)
            # Sampling means we may land on a slightly earlier cue, never a later one.
            assert found is not None
            assert found <= float(i) * 10.0
            assert float(i) * 10.0 - found <= 60.0


def test_cue_map_offsets_survive_the_overlap_prefix():
    cues = [{"start": float(i), "duration": 1.0, "text": ("tok%02d " % i) * 12} for i in range(30)]
    segments = cues_to_segments(cues, target_chars=300)
    later = segments[1]
    # Offset 0 is anchored to when the copied prefix was actually spoken, which
    # is earlier than the segment's own first cue.
    assert later["cueMap"][0][0] == 0
    assert later["cueMap"][0][1] < later["startS"]
    own = next(entry for entry in later["cueMap"] if entry[0] > 0)
    assert later["text"][own[0] :].startswith("tok")


def test_segments_never_span_two_speakers():
    cues = [
        {"start": 0.0, "duration": 1.0, "text": "host asks a question", "speaker": "A"},
        {"start": 1.0, "duration": 1.0, "text": "guest starts answering", "speaker": "B"},
        {"start": 2.0, "duration": 1.0, "text": "guest keeps going", "speaker": "B"},
        {"start": 3.0, "duration": 1.0, "text": "host again", "speaker": "A"},
    ]
    segments = cues_to_segments(cues, target_chars=10_000)
    assert [s["speakerHint"] for s in segments] == ["A", "B", "A"]
    assert "guest starts answering" in segments[1]["text"]
    assert "host asks" not in segments[1]["text"].replace(
        segments[1]["text"][: segments[1]["text"].find("guest")], ""
    )


def test_undiarized_cues_still_segment_by_length():
    cues = [{"start": float(i), "duration": 1.0, "text": "word " * 30} for i in range(8)]
    segments = cues_to_segments(cues, target_chars=200)
    assert len(segments) > 1
    assert all(s["speakerHint"] is None for s in segments)
