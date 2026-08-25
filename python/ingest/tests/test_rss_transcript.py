from pathlib import Path

from on_record_ingest.transcripts.rss_transcript import parse_srt, parse_transcript, parse_vtt

FIXTURE = Path(__file__).parent / "fixtures" / "sample.vtt"


def test_parse_vtt_keeps_timestamps():
    cues = parse_vtt(FIXTURE.read_text())
    assert len(cues) == 2
    assert cues[0]["start"] == 1.0
    assert cues[0]["duration"] == 3.0
    assert "software development" in str(cues[0]["text"])


def test_parse_srt():
    srt = "1\n00:00:01,000 --> 00:00:03,000\nHello from the transcript.\n"
    cues = parse_srt(srt)
    assert cues[0]["start"] == 1.0
    assert "Hello" in str(cues[0]["text"])


def test_parse_json_transcript():
    raw = '[{"start": 1.5, "duration": 2, "text": "coding agents change the work"}]'
    kind, cues = parse_transcript(raw, "application/json")
    assert kind == "rss_json"
    assert cues[0]["start"] == 1.5


def test_whisper_report_becomes_cues_without_control_tokens():
    from on_record_ingest.transcripts.whisper_local import cues_from_report

    cues = cues_from_report(
        {
            "segments": [
                {
                    "start": 0,
                    "end": 3.78,
                    "text": "<|startoftranscript|><|transcribe|><|0.00|> Right now,<|3.78|>",
                },
                {"start": 3.84, "end": 5.18, "text": "<|3.84|> they can use it.<|5.18|>"},
                {"start": 5.2, "end": 5.4, "text": "<|5.20|><|5.40|>"},
            ]
        }
    )
    assert [c["text"] for c in cues] == ["Right now,", "they can use it."]
    assert cues[0]["start"] == 0 and round(float(cues[0]["duration"]), 2) == 3.78
    # A segment that is only control tokens carries no words and is dropped.
    assert len(cues) == 2
