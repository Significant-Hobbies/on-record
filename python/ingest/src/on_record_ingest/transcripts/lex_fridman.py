"""Structured publisher transcripts from lexfridman.com.

Lex's RSS item points at an episode page, not at the separate transcript page.
The transcript slug is not predictable, so the only trustworthy resolver is
the episode page's own Transcript link.
"""

from __future__ import annotations

import logging
import re
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

from ..match import norm_title, video_id_from_source_url
from ..seed.people import PEOPLE
from ._publisher_html import AnchorParser as _AnchorParser
from ._publisher_html import attr as _attr
from ._publisher_html import clean as _clean

LOGGER = logging.getLogger("on_record_ingest")
USER_AGENT = "on-record/0.1 publisher-transcript-ingest"
TRANSCRIPT_KIND = "publisher_html"
LEX_HOSTS = {"lexfridman.com", "www.lexfridman.com"}
CLOCK = re.compile(r"(?<!\d)(?:(\d+):)?(\d{1,2}):(\d{2})(?!\d)")
HTTP_URL = re.compile(r"https?://[^\s<>\"']+")
EPISODE_NUMBER = re.compile(r"(?:#|\bepisode\s+)(\d{2,4})\b", re.IGNORECASE)
# Publisher edits occasionally place adjacent turns one to three seconds out
# of clock order while leaving the conversation in the correct DOM order.
# Preserve those source timestamps; a larger jump indicates broken structure.
MAX_CLOCK_JITTER_S = 5.0


class PublisherSourceUnavailable(RuntimeError):
    """A publisher source failed without proving that a transcript is absent."""


Cue = dict[str, float | str]


def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
    raw = next((value for key, value in attrs if key == "class"), "") or ""
    return set(raw.split())


def is_lex_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and (parsed.hostname or "").casefold() in LEX_HOSTS


def _title_score(reference: str, episode_title: str) -> float:
    reference_number = EPISODE_NUMBER.search(reference)
    title_number = EPISODE_NUMBER.search(episode_title)
    if reference_number and title_number and reference_number.group(1) != title_number.group(1):
        return 0.0
    reference_tokens = norm_title(reference)
    title_tokens = norm_title(episode_title)
    if not reference_tokens or not title_tokens:
        return 0.0
    return len(reference_tokens & title_tokens) / max(len(reference_tokens), len(title_tokens))


def _pick_transcript_candidate(
    candidates: list[tuple[int, str, str]], episode_title: str, min_title_score: float
) -> str | None:
    """Choose by episode identity first and fail closed on an identity tie."""
    if not candidates:
        return None
    if not episode_title:
        return max(candidates, key=lambda item: item[0])[1]
    scored = [
        (_title_score(f"{label} {urlparse(url).path}", episode_title), link_score, url)
        for link_score, url, label in candidates
    ]
    best = max(scored)
    tied = [item for item in scored if item[:2] == best[:2]]
    if len(tied) > 1 or best[0] < min_title_score:
        return None
    return best[2]


def transcript_url_from_episode_html(
    html: str, episode_url: str, episode_title: str = ""
) -> str | None:
    """Return the publisher-linked transcript URL, never a synthesized slug."""
    if not is_lex_url(episode_url):
        return None
    parser = _AnchorParser()
    parser.feed(html)
    candidates: list[tuple[int, str, str]] = []
    for href, label in parser.links:
        absolute = urldefrag(urljoin(episode_url, href))[0]
        if not is_lex_url(absolute):
            continue
        path = urlparse(absolute).path.rstrip("/").casefold()
        normalized_label = label.strip().casefold()
        score = 0
        if normalized_label == "transcript":
            score = 3
        elif path.endswith("-transcript"):
            score = 2
        elif "transcript" in normalized_label:
            score = 1
        if score:
            candidates.append((score, absolute, label))
    return _pick_transcript_candidate(candidates, episode_title, min_title_score=0.45)


def transcript_url_from_metadata(*fields: str | None, episode_title: str = "") -> str | None:
    """An exact publisher transcript URL already present in episode metadata."""
    candidates: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for field in fields:
        text = unescape(field or "")
        parser = _AnchorParser()
        parser.feed(text)
        links = list(parser.links)
        links.extend((match.group(0).rstrip(".,;:!?*_)]"), "") for match in HTTP_URL.finditer(text))
        for url, label in links:
            if not is_lex_url(url):
                continue
            path = urlparse(url).path.rstrip("/").casefold()
            clean_url = urldefrag(url)[0]
            if path.endswith("-transcript") and clean_url not in seen:
                candidates.append((2, clean_url, label))
                seen.add(clean_url)
    return _pick_transcript_candidate(candidates, episode_title, min_title_score=0.15)


class _SegmentParser(HTMLParser):
    _field_classes = {
        "ts-name": "name",
        "ts-text": "text",
        "ts-timestamp": "timestamp",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, str]] = []
        self._current: dict[str, Any] | None = None
        self._div_depth = 0
        self._stack: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = _classes(attrs)
        if self._current is None:
            if tag == "div" and "ts-segment" in classes:
                self._current = {"name": [], "text": [], "timestamp": [], "url": ""}
                self._div_depth = 1
                self._stack = [(tag, None)]
            return

        if tag == "div":
            self._div_depth += 1
        inherited = self._stack[-1][1] if self._stack else None
        field = next(
            (field for class_name, field in self._field_classes.items() if class_name in classes),
            inherited,
        )
        self._stack.append((tag, field))
        if tag == "a" and field == "timestamp":
            self._current["url"] = _attr(attrs, "href")
        elif tag == "br" and field:
            self._current[field].append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._current is not None and tag == "br" and self._stack and self._stack[-1][1]:
            self._current[self._stack[-1][1]].append(" ")

    def handle_data(self, data: str) -> None:
        if self._current is None or not self._stack:
            return
        field = self._stack[-1][1]
        if field:
            self._current[field].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                break
        if tag != "div":
            return
        self._div_depth -= 1
        if self._div_depth == 0:
            self.rows.append(
                {
                    "name": _clean(self._current["name"]),
                    "text": _clean(self._current["text"]),
                    "timestamp": _clean(self._current["timestamp"]),
                    "url": str(self._current["url"]),
                }
            )
            self._current = None
            self._stack = []


def _clock_seconds(raw: str) -> float | None:
    match = CLOCK.search(raw)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    if minutes >= 60 or seconds >= 60:
        return None
    return float(hours * 3600 + minutes * 60 + seconds)


def youtube_video_id(url: str) -> str | None:
    return video_id_from_source_url(url)


_SPEAKER_SLUGS = {
    " ".join(str(person["name"]).split()).casefold(): str(person["slug"]) for person in PEOPLE
}


def _speaker_slug(name: str) -> str | None:
    return _SPEAKER_SLUGS.get(" ".join(name.split()).casefold())


def parse_transcript_html(html: str, page_url: str) -> list[Cue]:
    parser = _SegmentParser()
    parser.feed(html)
    cues: list[Cue] = []
    previous_name = ""
    for row in parser.rows:
        start = _clock_seconds(row["timestamp"])
        if start is None or not row["text"]:
            continue
        explicit_name = row["name"]
        if explicit_name:
            previous_name = explicit_name
        speaker_name = explicit_name or previous_name
        cue: Cue = {"duration": 0.0, "start": start, "text": row["text"]}
        speaker = _speaker_slug(speaker_name)
        if speaker:
            cue["speaker"] = speaker
        if speaker_name:
            cue["speakerName"] = speaker_name
            cue["speakerNameSource"] = "publisher" if explicit_name else "publisher_continuation"
        source_url = urljoin(page_url, row["url"])
        if youtube_video_id(source_url):
            cue["sourceUrl"] = source_url
        cues.append(cue)
    starts = [float(cue["start"]) for cue in cues]
    for previous, current in zip(starts, starts[1:], strict=False):
        if previous - current > MAX_CLOCK_JITTER_S:
            LOGGER.warning("Lex transcript timestamps regress sharply: %s", page_url)
            return []
    for current, following in zip(cues, cues[1:], strict=False):
        current["duration"] = max(0.0, float(following["start"]) - float(current["start"]))
    return cues


def fetch_cues(source_url: str, client: httpx.Client, episode_title: str = "") -> list[Cue]:
    """Resolve one Lex transcript; absence is empty and operational failure is retryable."""
    if not is_lex_url(source_url):
        return []
    try:
        episode = client.get(source_url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
        episode.raise_for_status()
        if not is_lex_url(str(episode.url)):
            return []
        direct = parse_transcript_html(episode.text, str(episode.url))
        if direct:
            return direct
        transcript_url = transcript_url_from_episode_html(
            episode.text, str(episode.url), episode_title
        )
        if not transcript_url:
            return []
        transcript = client.get(
            transcript_url,
            headers={"User-Agent": USER_AGENT},
            timeout=30.0,
        )
        transcript.raise_for_status()
        if not is_lex_url(str(transcript.url)):
            return []
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {404, 410}:
            return []
        error = f"HTTP {exc.response.status_code}"
        LOGGER.warning("Lex publisher transcript unavailable for %s: %s", source_url, error)
        raise PublisherSourceUnavailable(error) from exc
    except httpx.HTTPError as exc:
        error = type(exc).__name__
        LOGGER.warning("Lex publisher transcript unavailable for %s: %s", source_url, error)
        raise PublisherSourceUnavailable(error) from exc
    cues = parse_transcript_html(transcript.text, str(transcript.url))
    if cues:
        LOGGER.info("resolved Lex transcript %s cues=%s", transcript.url, len(cues))
        return cues
    raise PublisherSourceUnavailable("publisher transcript contained no usable cues")
