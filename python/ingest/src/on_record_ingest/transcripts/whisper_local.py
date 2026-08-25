"""Transcribe an episode's audio on this machine.

YouTube blocks datacenter IPs, and only a handful of these shows publish a
transcript, so most episodes have no caption source at all. The feeds do give
us an audio URL, and WhisperKit runs Whisper large-v3-turbo on the Neural
Engine at roughly 20x realtime — a ninety minute episode in about four
minutes.

Storage discipline: audio is downloaded to a temporary directory, converted,
transcribed, and deleted in a finally block. Nothing but cues ever persists,
and those go to R2. A single episode's audio is ~60MB; keeping 2,600 of them
would be 150GB for material we read exactly once.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

LOGGER = logging.getLogger("on_record_ingest")

Cue = dict[str, float | str]

MODEL_DIR = (
    Path.home()
    / "Documents/huggingface/models/argmaxinc/whisperkit-coreml"
    / "openai_whisper-large-v3-v20240930_turbo"
)
# Whisper emits its control tokens inline: <|startoftranscript|>, <|3.78|>.
SPECIAL_TOKEN = re.compile(r"<\|[^|>]*\|>")


def available() -> bool:
    return bool(shutil.which("whisperkit-cli") and shutil.which("ffmpeg") and MODEL_DIR.is_dir())


DOWNLOAD_HEADERS = {"User-Agent": "on-record/0.1 (+https://podcasts.highsignal.app)"}


def _download(url: str, target: Path, attempts: int = 3) -> None:
    """Fetch episode audio on its own connection.

    Podcast CDNs are slow and stall; the shared client's short timeout is
    tuned for feed fetches and kills a 60MB download mid-stream.
    """
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            timeout = httpx.Timeout(connect=30.0, read=120.0, write=60.0, pool=30.0)
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                with client.stream("GET", url, headers=DOWNLOAD_HEADERS) as response:
                    response.raise_for_status()
                    with target.open("wb") as handle:
                        for chunk in response.iter_bytes(1 << 20):
                            handle.write(chunk)
            return
        except (httpx.HTTPError, OSError) as exc:
            last = exc
            LOGGER.warning("audio download attempt %s failed: %s", attempt + 1, exc)
            target.unlink(missing_ok=True)
    raise last if last else RuntimeError("download failed")


def _to_wav(source: Path, target: Path) -> None:
    """16kHz mono is what Whisper wants; it also shrinks the file ~10x."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(source), "-ar", "16000", "-ac", "1", str(target), "-y"],
        check=True,
        capture_output=True,
    )


def cues_from_report(report: dict[str, Any]) -> list[Cue]:
    cues: list[Cue] = []
    for segment in report.get("segments") or []:
        text = SPECIAL_TOKEN.sub("", str(segment.get("text") or "")).strip()
        if not text:
            continue
        start = float(segment.get("start") or 0.0)
        end = float(segment.get("end") or start)
        cues.append({"start": start, "duration": max(0.0, end - start), "text": text})
    return cues


def turns_from_rttm(rttm: str) -> list[dict[str, Any]]:
    """Speaker turns from WhisperKit's RTTM output.

    Lines look like: SPEAKER clip 1 <start> <duration> <text...> <NA> A <NA> <NA>
    The transcript sits inline, so the speaker label is counted from the end.
    """
    turns: list[dict[str, Any]] = []
    for line in rttm.splitlines():
        fields = line.split()
        if len(fields) < 9 or fields[0] != "SPEAKER":
            continue
        try:
            start = float(fields[3])
            duration = float(fields[4])
        except ValueError:
            continue
        turns.append({"start": start, "end": start + duration, "speaker": fields[-3]})
    return sorted(turns, key=lambda t: t["start"])


def speaker_at(turns: list[dict[str, Any]], start: float, end: float) -> str | None:
    """Whichever turn overlaps this cue the most."""
    best: str | None = None
    best_overlap = 0.0
    for turn in turns:
        overlap = min(end, turn["end"]) - max(start, turn["start"])
        if overlap > best_overlap:
            best_overlap = overlap
            best = str(turn["speaker"])
    return best


def _run_whisper(wav: Path, workdir: Path, speakers: int = 0) -> list[Cue]:
    command = [
        "whisperkit-cli",
        "transcribe",
        "--audio-path",
        str(wav),
        "--model-path",
        str(MODEL_DIR),
        "--report",
        "--report-path",
        str(workdir),
    ]
    if speakers:
        # Left unconstrained it split one host across two labels. The roster
        # already tells us how many voices to expect.
        command += ["--diarization", "--diarization-num-speakers", str(speakers)]
    result = subprocess.run(command, check=True, capture_output=True, timeout=7200)
    report = workdir / f"{wav.stem}.json"
    if not report.is_file():
        return []
    cues = cues_from_report(json.loads(report.read_text()))
    if not speakers:
        return cues
    turns = turns_from_rttm(result.stdout.decode("utf-8", "replace"))
    for cue in cues:
        start = float(cue["start"])
        speaker = speaker_at(turns, start, start + float(cue["duration"]))
        if speaker:
            cue["speaker"] = speaker
    return cues


class TranscriptionUnavailable(RuntimeError):
    """The audio could not be fetched or decoded — try again another day.

    Distinct from "this episode has no transcript", which is permanent. A CDN
    that stalls must not retire an episode forever.
    """


def transcribe(audio_url: str, client: httpx.Client | None = None, speakers: int = 0) -> list[Cue]:
    """Cues for an episode. Raises TranscriptionUnavailable on a transient failure."""
    if not available():
        LOGGER.warning("whisper unavailable: need whisperkit-cli, ffmpeg and the turbo model")
        return []
    workdir = Path(tempfile.mkdtemp(prefix="on-record-audio-"))
    try:
        source = workdir / "episode.audio"
        _download(audio_url, source)
        wav = workdir / "episode.wav"
        _to_wav(source, wav)
        source.unlink(missing_ok=True)
        return _run_whisper(wav, workdir, speakers)
    except subprocess.CalledProcessError as exc:
        LOGGER.warning("whisper failed: %s", (exc.stderr or b"")[:200])
        return []
    except (httpx.HTTPError, OSError, ValueError) as exc:
        LOGGER.warning("whisper could not transcribe %s: %s", audio_url[:60], exc)
        raise TranscriptionUnavailable(str(exc)) from exc
    finally:
        # The audio is the bulk of what this touches and we never need it again.
        shutil.rmtree(workdir, ignore_errors=True)
