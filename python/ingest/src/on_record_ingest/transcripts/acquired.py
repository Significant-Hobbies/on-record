"""Speaker-labelled publisher transcripts from acquired.fm episode pages."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

import httpx

from . import _publisher_html as _shared

Cue = _shared.Cue
PublisherSourceUnavailable = _shared.PublisherSourceUnavailable
_attr = _shared.attr
_clean = _shared.clean

USER_AGENT = "on-record/0.1 publisher-transcript-ingest"
TRANSCRIPT_KIND = "publisher_html_coarse"
ACQUIRED_HOSTS = {"acquired.fm", "www.acquired.fm"}
SITEMAP_URL = "https://www.acquired.fm/sitemap.xml"
MIN_TURNS = 10
MIN_TITLE_SCORE = 0.5


def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
    return set(_attr(attrs, "class").split())


def _speaker_key(label: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", label.casefold()).split())


def _speaker_prefix(text: str) -> tuple[str, str] | None:
    prefix, separator, remainder = text.partition(":")
    label = prefix.strip()
    if (
        not separator
        or not label
        or len(label) > 80
        or not label[0].isalnum()
        or not any(character.isalpha() for character in label)
    ):
        return None
    return label, remainder.strip()


def is_acquired_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and (parsed.hostname or "").casefold() in ACQUIRED_HOSTS
        and parsed.path.startswith("/episodes/")
        and parsed.path.rstrip("/") != "/episodes"
    )


def is_acquired_site_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"} and (parsed.hostname or "").casefold() in ACQUIRED_HOSTS
    )


def _title_tokens(value: str) -> set[str]:
    generic = {
        "a",
        "acquired",
        "an",
        "and",
        "episode",
        "episodes",
        "is",
        "of",
        "season",
        "special",
        "the",
        "to",
        "what",
        "with",
    }
    roman_numbers = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5"}
    joined_domains = re.sub(r"(?<=[a-z0-9])\.(?=[a-z0-9])", "", value.casefold())
    separated = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", joined_domains)
    normalized = re.sub(r"[^a-z0-9]+", " ", separated)
    normalized = re.sub(r"\badapting\s+episode\s+\d+\b", " ", normalized)
    normalized = re.sub(r"\b(?:episode|season)\s+\d+\b", " ", normalized)
    tokens = normalized.split()
    if "with" in tokens:
        tokens = tokens[: tokens.index("with")]
    return {
        roman_numbers.get(token, token)
        for token in tokens
        if token not in generic and (len(token) > 2 or token.isdigit() or token in roman_numbers)
    }


def _candidate_score(episode_title: str, url: str) -> float:
    title = _title_tokens(episode_title)
    slug = _title_tokens(unquote(urlparse(url).path.rsplit("/", 1)[-1]))
    if not title or not slug:
        return 0.0
    return len(title & slug) / max(len(title), len(slug))


def _identity_title_tokens(value: str) -> set[str]:
    structural = {"inc", "part", "volume"}
    return {
        token[:-1] if token.endswith("s") and not token.endswith("ss") else token
        for token in _title_tokens(value)
        if token not in structural and not token.isdigit()
    }


def match_episode_url(episode_title: str, urls: list[str]) -> str | None:
    """Return one unambiguous official sitemap URL for the episode title."""
    ranked = sorted(
        ((_candidate_score(episode_title, url), url) for url in urls),
        reverse=True,
    )
    if not ranked or ranked[0][0] < 0.6:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.1:
        return None
    return ranked[0][1]


def _sitemap_urls(client: httpx.Client) -> list[str]:
    cache_name = "_on_record_acquired_sitemap_urls"
    cached = getattr(client, cache_name, None)
    if cached is not None:
        return list(cached)
    try:
        response = client.get(SITEMAP_URL, headers={"User-Agent": USER_AGENT}, timeout=30.0)
        response.raise_for_status()
        root = ElementTree.fromstring(response.text)
    except (ElementTree.ParseError, httpx.HTTPError) as exc:
        raise PublisherSourceUnavailable("publisher sitemap unavailable") from exc
    urls = sorted(
        {
            str(node.text or "").strip()
            for node in root.iter()
            if node.tag.rsplit("}", 1)[-1] == "loc"
            and is_acquired_url(str(node.text or "").strip())
        }
    )
    setattr(client, cache_name, urls)
    return urls


def episode_url_from_source(
    source_url: str, episode_title: str, client: httpx.Client
) -> str | None:
    if is_acquired_url(source_url):
        return source_url
    if not is_acquired_site_url(source_url):
        return None
    return match_episode_url(episode_title, _sitemap_urls(client))


class _PageParser(_shared.CoarseTurnParser):
    def __init__(self) -> None:
        super().__init__()
        self._transcript_div_depth = 0
        self._body_div_depth = 0
        self._in_paragraph = False
        self._paragraph: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta" and _attr(attrs, "property") == "og:title":
            self.title = _attr(attrs, "content")
        if tag == "div":
            if not self._transcript_div_depth and (
                _attr(attrs, "id") == "transcript" or "episode-transcript" in _classes(attrs)
            ):
                self._transcript_div_depth = 1
                self.transcript_marker = True
                return
            if self._transcript_div_depth:
                self._transcript_div_depth += 1
                if not self._body_div_depth and "episode-rich-text" in _classes(attrs):
                    self._body_div_depth = self._transcript_div_depth
        if self._body_div_depth and tag == "p" and not self._in_paragraph:
            self._in_paragraph = True
            self._paragraph = []

    def handle_data(self, data: str) -> None:
        if self._in_paragraph:
            self._paragraph.append(data)

    def _finish_paragraph(self) -> None:
        text = _clean(self._paragraph)
        self._in_paragraph = False
        self._paragraph = []
        if not text:
            return
        labelled = _speaker_prefix(text)
        if labelled:
            label, body = labelled
            if self._current_label and _speaker_key(label) != _speaker_key(self._current_label):
                self._flush_turn()
            self._current_label = label
            if body:
                self._current_text.append(body)
            return
        if self._current_label:
            self._current_text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if self._in_paragraph and tag == "p":
            self._finish_paragraph()
        if tag != "div" or not self._transcript_div_depth:
            return
        if self._body_div_depth == self._transcript_div_depth:
            self._flush_turn()
            self._body_div_depth = 0
        self._transcript_div_depth -= 1

    def close(self) -> None:
        super().close()
        if self._in_paragraph:
            self._finish_paragraph()
        self._flush_turn()


def _title_score(publisher_title: str, episode_title: str) -> float:
    publisher = _identity_title_tokens(
        re.sub(r"\s*[|–—-]\s*Acquired.*$", "", publisher_title, flags=re.IGNORECASE)
    )
    return _shared.title_overlap(publisher, _identity_title_tokens(episode_title))


def parse_transcript_html(
    html: str, page_url: str, speaker_map: dict[str, str] | None = None
) -> tuple[str, list[Cue]]:
    """Return the publisher title and ordered, speaker-labelled coarse cues."""
    return _shared.parse_official_coarse_html(
        _PageParser(), html, page_url, is_acquired_url, speaker_map, _speaker_key
    )


_ADAPTER = _shared.CoarsePublisherAdapter(
    is_url=is_acquired_url,
    parse_html=parse_transcript_html,
    title_score=_title_score,
    user_agent=USER_AGENT,
    validation=_shared.CueValidation(MIN_TITLE_SCORE, MIN_TURNS, "Acquired", empty_is_absent=True),
)


def fetch_cues(
    source_url: str,
    client: httpx.Client,
    episode_title: str,
    speaker_map: dict[str, str] | None = None,
) -> list[Cue]:
    """Fetch one official episode page and fail closed on identity or structure."""
    return _shared.fetch_coarse_cues(source_url, client, episode_title, speaker_map, _ADAPTER)
