from pathlib import Path

from on_record_ingest.transcripts.rss_transcript import (
    parse_labelled_text,
    parse_parenthesized_speaker_text,
    parse_srt,
    parse_timestamped_text,
    parse_timed_html,
    parse_transcript,
    parse_vtt,
)

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


def test_parse_speaker_labelled_timestamped_text():
    raw = """[00:00:02.10] Lex Fridman
What do you think happens next?

[00:00:05.12] George Hotz
I think the software gets dramatically smaller.
"""
    kind, cues = parse_transcript(raw, "text/plain")
    assert kind == "rss_named_text"
    assert cues == parse_timestamped_text(raw)
    assert [cue.get("speaker") for cue in cues] == ["lex-fridman", "george-hotz"]
    assert cues[0]["start"] == 2.1
    assert round(float(cues[0]["duration"]), 2) == 3.02


def test_parse_parenthesized_speaker_timestamp_text():
    raw = """John Collison (00:00:17):
How should founders frame the business today?

Eric Glyman (00:00:34)
The pace has been pretty remarkable.
"""
    kind, cues = parse_transcript(raw, "text/plain")
    assert kind == "rss_named_text"
    assert cues == parse_parenthesized_speaker_text(raw)
    assert [cue.get("speaker") for cue in cues] == ["john-collison", "eric-glyman"]
    assert cues[0]["duration"] == 17.0


def test_parse_clock_then_speaker_label_text():
    raw = """00:00:03
Speaker 1: Hello from the first host.

00:00:06
Speaker 2: Hello from the second host.
"""
    kind, cues = parse_transcript(raw, "text/plain")
    assert kind == "rss_text"
    assert cues == parse_labelled_text(raw)
    assert [cue.get("speaker") for cue in cues] == ["Speaker 1", "Speaker 2"]
    assert cues[0]["duration"] == 3.0


def test_single_clock_block_is_explicitly_coarse():
    raw = "00:00:10\nSpeaker 1: The entire older transcript is one source block.\n"
    kind, cues = parse_transcript(raw, "text/plain")
    assert kind == "rss_text_coarse"
    assert len(cues) == 1
    assert cues[0]["start"] == 10.0


def test_parse_transistor_timed_html():
    raw = """<cite>Speaker 1:</cite>
<time>00:00</time>
<p>First turn.</p>
<cite>Speaker 2:</cite>
<time>00:12</time>
<p>Second turn.</p>"""
    kind, cues = parse_transcript(raw, "text/html")
    assert kind == "rss_text"
    assert cues == parse_timed_html(raw)
    assert cues[0] == {
        "duration": 12.0,
        "speaker": "Speaker 1",
        "start": 0.0,
        "text": "First turn.",
    }


def test_bracketed_plain_text_does_not_crash_as_fake_json():
    kind, cues = parse_transcript("[Music]\nNo timestamp here", "text/plain")
    assert kind == "rss_json"
    assert cues == []


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
