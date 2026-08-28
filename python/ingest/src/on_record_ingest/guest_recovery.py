from __future__ import annotations

import html
import re

from .roster import looks_like_a_person, slugify

NAME_WORD = r"(?:[A-Z]\.|[A-ZÀ-ÖØ-Þ](?:[A-Za-zÀ-ÖØ-öø-ÿ'’-]*[A-Za-zÀ-ÖØ-öø-ÿ’])?)"
NAME = rf"{NAME_WORD}(?: {NAME_WORD}){{1,2}}"
ROLE_WORDS = {
    "bank",
    "bloomberg",
    "business",
    "capital",
    "chicago",
    "co-founder",
    "cofounder",
    "columbia",
    "company",
    "credit",
    "director",
    "estate",
    "fed",
    "federal",
    "florida",
    "doctor",
    "founder",
    "goldman",
    "group",
    "institute",
    "law",
    "lord",
    "money",
    "morgan",
    "mr",
    "mrs",
    "news",
    "of",
    "opinion",
    "pennsylvania",
    "planet",
    "president",
    "principal",
    "professor",
    "real",
    "reporter",
    "reserve",
    "richmond",
    "sachs",
    "school",
    "scientist",
    "senator",
    "senior",
    "stanford",
    "stanley",
    "suisse",
    "trustee",
    "umass",
    "university",
    "washington",
}
# Verified against both the episode's source URL and its host introduction.
# The publisher description transposes two letters in Fritz Bartel's name.
PUBLISHER_NAME_CORRECTIONS = {"Firtz Bartel": "Fritz Bartel"}
GUEST_PATTERNS = (
    re.compile(
        rf"(?i:\b(?:in this episode,?\s*)?we\s+(?:talk|speak|chat|sit down)\s+with\s+)"
        rf"(?P<name>{NAME})\b"
    ),
    re.compile(
        rf"(?i:\b(?:in this episode,?\s*)?we(?:'re| are)\s+"
        rf"(?:joined by|speaking with|talking with)\s+)(?P<name>{NAME})\b"
    ),
    re.compile(rf"(?i:\bour guest(?: today)? is\s+)(?P<name>{NAME})\b"),
)


def _plain_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return " ".join(without_tags.split())


def explicit_guest_names(description: str, title: str = "") -> list[str]:
    """Names explicitly presented as interview guests in publisher metadata.

    Capitalised names elsewhere in a description are deliberately ignored:
    authors, founders, and people being discussed are not necessarily present.
    """
    text = _plain_text(description)
    found: dict[str, str] = {}
    for pattern in GUEST_PATTERNS:
        for match in pattern.finditer(text):
            name = " ".join(match.group("name").split())
            name = PUBLISHER_NAME_CORRECTIONS.get(name, name)
            words = {word.casefold().strip(".'’") for word in name.split()}
            first_name = name.split()[0]
            title_names_first_person = bool(
                title
                and re.search(rf"\b{re.escape(first_name)}\b", title, re.IGNORECASE)
                and not re.search(rf"\b{re.escape(name)}\b", title, re.IGNORECASE)
            )
            possessive_token = any(word.casefold().endswith(("'s", "’s")) for word in name.split())
            if (
                looks_like_a_person(name)
                and not words.intersection(ROLE_WORDS)
                and not possessive_token
                and not title_names_first_person
            ):
                found.setdefault(slugify(name), name)
    return list(found.values())
