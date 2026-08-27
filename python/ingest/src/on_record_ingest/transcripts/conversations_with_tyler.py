"""Speaker-labelled publisher transcripts from conversationswithtyler.com.

The show's RSS descriptions link to the matching official episode page. Those
pages label turns but do not provide playback timestamps, so cues preserve DOM
order and must be stored as coarse publisher evidence.
"""

from __future__ import annotations

import re
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

from ..match import norm_title
from ._publisher_html import AnchorParser as _AnchorParser
from ._publisher_html import CoarsePublisherAdapter, CoarseTurnParser, Cue, CueValidation
from ._publisher_html import PublisherSourceUnavailable as PublisherSourceUnavailable
from ._publisher_html import attr as _attr
from ._publisher_html import clean as _clean
from ._publisher_html import fetch_coarse_cues as _fetch_coarse_cues
from ._publisher_html import parse_official_coarse_html as _parse_official_coarse_html
from ._publisher_html import title_overlap as _title_overlap

USER_AGENT = "on-record/0.1 publisher-transcript-ingest"
TRANSCRIPT_KIND = "publisher_html_coarse"
CWT_HOSTS = {"conversationswithtyler.com", "www.conversationswithtyler.com"}
MIN_TURNS = 10
MIN_TITLE_SCORE = 0.4
LEADING_LABEL_NOISE = " .…—-"
PLAIN_TEXT_LABEL_ALIASES = {"cowen", "tyler cowen"}
TITLE_URL_OVERRIDES = {
    "Conversations with Tyler 2020 Retrospective": (
        "https://conversationswithtyler.com/episodes/conversations-with-tyler-2020-retrospective/"
    ),
    "Conversations with Tyler 2023 Retrospective": (
        "https://conversationswithtyler.com/episodes/conversations-with-tyler-2023-retrospective/"
    ),
    "Conversations with Tyler 2025 Retrospective": (
        "https://conversationswithtyler.com/episodes/conversations-with-tyler-2025-retrospective/"
    ),
}


def _speaker_key(label: str) -> str:
    return " ".join(label.rstrip(":").split()).casefold()


def _is_publisher_label_candidate(label: str) -> bool:
    if not label.endswith(":"):
        return False
    body = label[:-1].strip()
    if not body or len(body) > 80 or not body[0].isalnum():
        return False
    return any(character.isalpha() for character in body)


def _leading_strong_text(text: str, strongs: list[str]) -> str:
    leading = ""
    for part in strongs:
        candidate = f"{leading}{part}"
        if not text.startswith(candidate):
            break
        leading = candidate
        remainder = text[len(leading) :].lstrip()
        if leading.endswith(":") or remainder.startswith(":"):
            break
    if leading:
        return leading.strip()
    for part in strongs:
        offset = text.find(part)
        colon_index = part.find(":")
        if 0 <= offset <= 20 and colon_index >= 0:
            candidate = text[: offset + colon_index + 1].strip()
            if _is_publisher_label_candidate(candidate):
                return candidate
    return ""


def _plain_text_speaker_prefix(text: str) -> str:
    prefix, separator, _ = text.partition(":")
    if not separator or len(prefix) > 80:
        return ""
    label = prefix.lstrip(LEADING_LABEL_NOISE).strip()
    if not _is_publisher_label_candidate(f"{label}:"):
        return ""
    cased_letters = [
        character
        for character in label
        if character.isalpha() and character.lower() != character.upper()
    ]
    if (
        len(label) >= 4
        and cased_letters
        and all(character.isupper() for character in cased_letters)
    ):
        return f"{prefix}:"
    if _speaker_key(label) in PLAIN_TEXT_LABEL_ALIASES:
        return f"{prefix}:"
    return ""


def _speaker_paragraph(text: str, leading: str) -> tuple[str, str] | None:
    if not leading or not text.startswith(leading):
        return None
    colon_index = leading.find(":")
    if colon_index >= 0:
        label = leading[: colon_index + 1].lstrip(LEADING_LABEL_NOISE)
        remainder = text[colon_index + 1 :].lstrip()
    else:
        remainder = text[len(leading) :].lstrip()
        label = f"{leading}:"
        if remainder.startswith(":"):
            remainder = remainder[1:].lstrip()
        else:
            return None
    if not _is_publisher_label_candidate(label):
        return None
    return label.rstrip(":").strip(), remainder


def is_cwt_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and (parsed.hostname or "").casefold() in CWT_HOSTS
        and parsed.path.startswith("/episodes/")
    )


def transcript_url_from_metadata(
    *fields: str | None,
    episode_title: str = "",
    allow_title_override: bool = False,
) -> str | None:
    """Return one exact official transcript link embedded by the RSS publisher."""
    if allow_title_override and episode_title in TITLE_URL_OVERRIDES:
        return TITLE_URL_OVERRIDES[episode_title]
    found: set[str] = set()
    for field in fields:
        parser = _AnchorParser()
        parser.feed(field or "")
        for href, label in parser.links:
            absolute = urldefrag(urljoin("https://conversationswithtyler.com/", href))[0]
            if is_cwt_url(absolute) and "transcript" in label.casefold():
                found.add(absolute)
    return next(iter(found)) if len(found) == 1 else None


class _PageParser(CoarseTurnParser):
    def __init__(self) -> None:
        super().__init__()
        self.recorded_marker = False
        self._in_main = False
        self._main_depth = 0
        self._skip_depth = 0
        self._in_paragraph = False
        self._paragraph_depth = 0
        self._paragraph: list[str] = []
        self._strong_depth = 0
        self._strong: list[str] = []
        self._strongs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta" and _attr(attrs, "property") == "og:title":
            self.title = _attr(attrs, "content")
        if tag == "main" and _attr(attrs, "id") == "main" and not self._in_main:
            self._in_main = True
            self._main_depth = 1
            return
        if not self._in_main:
            return
        if tag == "main":
            self._main_depth += 1
        if tag in {"blockquote", "script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "p" and not self._in_paragraph:
            self._in_paragraph = True
            self._paragraph_depth = 1
            self._paragraph = []
            self._strongs = []
            return
        if self._in_paragraph:
            if tag == "p":
                self._paragraph_depth += 1
            if tag in {"strong", "b"}:
                self._strong_depth += 1
                if self._strong_depth == 1:
                    self._strong = []
            elif tag == "br":
                self._paragraph.append(" ")
                if self._strong_depth:
                    self._strong.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in {"br", "meta", "img", "input", "source"}:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if not self._in_main or self._skip_depth or not self._in_paragraph:
            return
        self._paragraph.append(data)
        if self._strong_depth:
            self._strong.append(data)

    def _finish_paragraph(self) -> None:
        text = _clean(self._paragraph)
        leading_strong = _leading_strong_text(text, self._strongs)
        leading_label = leading_strong or _plain_text_speaker_prefix(text)
        normalized = text.casefold()
        if not self.transcript_marker:
            self.transcript_marker = normalized in {
                "read the full conversation",
                "read the full transcript",
            }
            self.recorded_marker = self.recorded_marker or normalized.startswith("recorded ")
        if text and (self.transcript_marker or self.recorded_marker):
            speaker = _speaker_paragraph(text, leading_label)
            if speaker:
                label, remainder = speaker
                self.transcript_marker = True
                self._flush_turn()
                self._current_label = label
                if remainder:
                    self._current_text.append(remainder)
            elif self.transcript_marker and self._current_label:
                self._current_text.append(text)
        self._in_paragraph = False
        self._paragraph_depth = 0
        self._paragraph = []
        self._strongs = []

    def handle_endtag(self, tag: str) -> None:
        if not self._in_main:
            return
        if tag in {"blockquote", "script", "style"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if self._in_paragraph and tag in {"strong", "b"} and self._strong_depth:
            self._strong_depth -= 1
            if self._strong_depth == 0:
                self._strongs.append(_clean(self._strong))
                self._strong = []
        if self._in_paragraph and tag == "p":
            self._paragraph_depth -= 1
            if self._paragraph_depth == 0:
                self._finish_paragraph()
        if tag == "main":
            self._main_depth -= 1
            if self._main_depth == 0:
                self._flush_turn()
                self._in_main = False

    def close(self) -> None:
        super().close()
        self._flush_turn()


def _title_score(publisher_title: str, episode_title: str) -> float:
    publisher = norm_title(
        re.sub(
            r"\(ep\.?\s*\d+[^)]*\)",
            "",
            publisher_title,
            flags=re.IGNORECASE,
        )
    )
    return _title_overlap(publisher, norm_title(episode_title))


def parse_transcript_html(
    html: str, page_url: str, speaker_map: dict[str, str] | None = None
) -> tuple[str, list[Cue]]:
    """Return the publisher title and ordered, speaker-labelled coarse cues."""
    return _parse_official_coarse_html(
        _PageParser(), html, page_url, is_cwt_url, speaker_map, _speaker_key
    )


_ADAPTER = CoarsePublisherAdapter(
    is_url=is_cwt_url,
    parse_html=parse_transcript_html,
    title_score=_title_score,
    user_agent=USER_AGENT,
    validation=CueValidation(MIN_TITLE_SCORE, MIN_TURNS, "CWT"),
)


def fetch_cues(
    source_url: str,
    client: httpx.Client,
    episode_title: str,
    speaker_map: dict[str, str] | None = None,
) -> list[Cue]:
    """Fetch one exact official page and fail closed on identity or structure."""
    return _fetch_coarse_cues(source_url, client, episode_title, speaker_map, _ADAPTER)
