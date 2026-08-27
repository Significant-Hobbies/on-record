"""Small HTML parsing primitives shared by publisher transcript adapters."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Protocol

import httpx

Cue = dict[str, float | str]


class PublisherSourceUnavailable(RuntimeError):
    """A publisher source failed without proving transcript absence."""


class TurnParser(Protocol):
    title: str
    transcript_marker: bool
    turns: list[tuple[str, str]]

    def feed(self, data: str) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class CueValidation:
    min_title_score: float
    min_turns: int
    publisher_name: str
    empty_is_absent: bool = False


@dataclass(frozen=True)
class CoarsePublisherAdapter:
    is_url: Callable[[str], bool]
    parse_html: Callable[[str, str, dict[str, str] | None], tuple[str, list[Cue]]]
    title_score: Callable[[str, str], float]
    user_agent: str
    validation: CueValidation


def attr(attrs: list[tuple[str, str | None]], name: str) -> str:
    return str(next((value for key, value in attrs if key == name), "") or "")


def clean(parts: list[str]) -> str:
    return " ".join("".join(parts).split())


def append_turn(turns: list[tuple[str, str]], label: str, parts: list[str]) -> None:
    text = " ".join(" ".join(parts).split())
    if label and text:
        turns.append((label, text))


class CoarseTurnParser(HTMLParser):
    """Base state shared by ordered speaker-turn HTML parsers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.transcript_marker = False
        self.turns: list[tuple[str, str]] = []
        self._current_label = ""
        self._current_text: list[str] = []

    def _flush_turn(self) -> None:
        append_turn(self.turns, self._current_label, self._current_text)
        self._current_label = ""
        self._current_text = []


def parse_coarse_html(
    parser: TurnParser,
    html: str,
    speaker_map: dict[str, str] | None,
    speaker_key: Callable[[str], str],
) -> tuple[str, list[Cue]]:
    parser.feed(html)
    parser.close()
    if not parser.transcript_marker:
        return parser.title, []
    normalized_map = {speaker_key(key): value for key, value in (speaker_map or {}).items()}
    cues: list[Cue] = []
    for index, (label, text) in enumerate(parser.turns):
        cue: Cue = {
            "duration": 0.0,
            "speakerName": label,
            "speakerNameSource": "publisher",
            "start": float(index),
            "text": text,
        }
        speaker = normalized_map.get(speaker_key(label))
        if speaker:
            cue["speaker"] = speaker
        cues.append(cue)
    return parser.title, cues


def parse_official_coarse_html(
    parser: TurnParser,
    html: str,
    page_url: str,
    is_publisher_url: Callable[[str], bool],
    speaker_map: dict[str, str] | None,
    speaker_key: Callable[[str], str],
) -> tuple[str, list[Cue]]:
    if not is_publisher_url(page_url):
        return "", []
    return parse_coarse_html(parser, html, speaker_map, speaker_key)


def title_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(len(left), len(right))


def fetch_publisher_html(
    source_url: str,
    client: httpx.Client,
    is_publisher_url: Callable[[str], bool],
    user_agent: str,
) -> tuple[str, str] | None:
    if not is_publisher_url(source_url):
        return None
    try:
        response = client.get(source_url, headers={"User-Agent": user_agent}, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {404, 410}:
            return None
        raise PublisherSourceUnavailable(f"HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise PublisherSourceUnavailable(type(exc).__name__) from exc
    if not is_publisher_url(str(response.url)):
        return None
    return response.text, str(response.url)


def validate_cues(
    source_url: str,
    publisher_title: str,
    episode_title: str,
    cues: list[Cue],
    title_score: Callable[[str, str], float],
    validation: CueValidation,
    logger: logging.Logger,
) -> list[Cue]:
    if title_score(publisher_title, episode_title) < validation.min_title_score:
        logger.warning("%s publisher title mismatch: %s", validation.publisher_name, source_url)
        return []
    if not cues and validation.empty_is_absent:
        return []
    if len(cues) < validation.min_turns or sum(len(str(cue["text"])) for cue in cues) < 1000:
        raise PublisherSourceUnavailable("publisher transcript contained too few usable turns")
    return cues


def fetch_coarse_cues(
    source_url: str,
    client: httpx.Client,
    episode_title: str,
    speaker_map: dict[str, str] | None,
    adapter: CoarsePublisherAdapter,
) -> list[Cue]:
    fetched = fetch_publisher_html(source_url, client, adapter.is_url, adapter.user_agent)
    if not fetched:
        return []
    html, page_url = fetched
    publisher_title, cues = adapter.parse_html(html, page_url, speaker_map)
    return validate_cues(
        source_url,
        publisher_title,
        episode_title,
        cues,
        adapter.title_score,
        adapter.validation,
        logging.getLogger("on_record_ingest"),
    )


class AnchorParser(HTMLParser):
    """Collect anchor destinations and normalized visible labels."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a" and self._href is None:
            self._href = attr(attrs, "href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, clean(self._text)))
            self._href = None
            self._text = []
