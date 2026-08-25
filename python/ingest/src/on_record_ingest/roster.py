"""Mine roster candidates out of episode titles.

Podcast titles are a ranked list of who matters in a field, written by the
people who book them. Rather than guessing a roster, take the names the shows
themselves put in their titles and rank by how often they appear.

The output is a review list, never a direct write to the seed. A wrong name in
the roster is worse than a missing one: it becomes a speaker the extractor is
allowed to attribute quotes to.
"""

from __future__ import annotations

import json
import re
import logging
from collections import Counter
from typing import Any, Iterable

from .seed.people import PEOPLE

LOGGER = logging.getLogger("on_record_ingest")

# "Dwarkesh Podcast", "Part 2", "AI" — capitalised, but not people.
STOPWORDS = {
    "ai",
    "ceo",
    "cto",
    "gpt",
    "llm",
    "the",
    "how",
    "why",
    "what",
    "who",
    "when",
    "part",
    "episode",
    "podcast",
    "show",
    "live",
    "new",
    "open",
    "best",
    "top",
    "inside",
    "building",
    "future",
    "state",
    "special",
    "series",
    "full",
    "deep",
    "dive",
    "great",
    "big",
    "next",
    "first",
    "last",
    "year",
    "week",
    "day",
    "vs",
    "club",
    "pod",
    "pods",
    "recap",
    "roundup",
    "hours",
    "lessons",
    "rules",
    "and",
    "with",
    "from",
    "for",
    "his",
    "her",
    "their",
}
# Titles name people in a handful of shapes. Anchor on those rather than
# hunting capitalised words anywhere, which drags in company and product names.
PATTERNS = (
    re.compile(
        r"^(?:#?\d+\s*[–—:-]\s*)?(?P<name>[A-Z][a-z'’-]+(?: [A-Z][a-zA-Z'’.-]+){1,2})\s*[–—:|]"
    ),
    re.compile(r"\bwith (?P<name>[A-Z][a-z'’-]+(?: [A-Z][a-zA-Z'’.-]+){1,2})\b"),
    re.compile(r"[|–—]\s*(?P<name>[A-Z][a-z'’-]+(?: [A-Z][a-zA-Z'’.-]+){1,2})\s*$"),
    re.compile(r"^(?P<name>[A-Z][a-z'’-]+(?: [A-Z][a-zA-Z'’.-]+){1,2}) on \b"),
)


def looks_like_a_person(name: str) -> bool:
    parts = name.split()
    if not 2 <= len(parts) <= 3:
        return False
    if any(part.lower().strip(".'’-") in STOPWORDS for part in parts):
        return False
    # A single initial is fine ("Sam A. Altman"); a run of capitals is an
    # acronym, which means it is an organisation rather than a person.
    letters = [part.strip(".'’-") for part in parts]
    return not any(word.isupper() and len(word) > 1 for word in letters)


def names_in_title(title: str) -> set[str]:
    found: set[str] = set()
    for pattern in PATTERNS:
        for match in pattern.finditer(title):
            name = match.group("name").strip()
            if looks_like_a_person(name):
                found.add(name)
    return found


def known_names() -> set[str]:
    known: set[str] = set()
    for person in PEOPLE:
        known.add(str(person["name"]).lower())
        for alias in person.get("aliases") or []:
            known.add(str(alias).lower())
    return known


def candidates(episodes: Iterable[dict[str, Any]], minimum: int = 1) -> list[dict[str, Any]]:
    """Names by how many episodes mention them, most-booked first."""
    counts: Counter[str] = Counter()
    examples: dict[str, str] = {}
    for episode in episodes:
        title = str(episode.get("title") or "")
        for name in names_in_title(title):
            counts[name] += 1
            examples.setdefault(name, title)
    already = known_names()
    return [
        {"name": name, "episodes": n, "example": examples[name]}
        for name, n in counts.most_common()
        if n >= minimum and name.lower() not in already
    ]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


RECURRING = 2


def split_by_evidence(rows: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """Names booked more than once vs one-offs.

    A name the shows put in two or more titles is already evidenced by the
    corpus; sending it to a model only adds a way to lose it when a provider
    behind the gateway fails. Only the one-offs need judgement.
    """
    recurring = [row for row in rows if row["episodes"] >= RECURRING]
    singles = [row for row in rows if row["episodes"] < RECURRING]
    return recurring, singles


def as_seed_entries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shape candidates like seed/people.py so promoting one is a paste."""
    return [
        {
            "slug": slugify(str(row["name"])),
            "name": row["name"],
            "title": "",
            "org": "",
            "aliases": [],
            "matchAliases": [],
        }
        for row in rows
    ]


VALIDATE_SYSTEM = (
    'You classify strings. Reply with JSON only, shaped {"people": [...]}. No prose, no other keys.'
)
VALIDATE_PROMPT = (
    "Which of these strings are the name of a real, identifiable person? "
    "Podcast episode titles are noisy, so many are fragments, show segment "
    'names, or company names. Reply JSON only: {"people": ["<exact input>", ...]} '
    "containing only the entries that are a person's name. Include a name even "
    "if the person is not famous. Exclude anything you are unsure about."
)


def validate_names(settings: Any, names: list[str], batch: int = 15, attempts: int = 3) -> set[str]:
    """Ask the model which candidates are actually people.

    Names only. Titles and employers are left blank on purpose — a guessed job
    title is exactly the confident misinformation this index is meant to avoid,
    and nothing matches on them anyway.

    Batches are small because the failures are upstream: a batch of sixty routes
    to a provider that answers 402 or a bodyless 400, and fifteen does not.
    Failed batches are retried rather than dropped — batches used to be ordered
    by how often a name appears, so losing one deleted the most-booked people
    first and nothing said so.
    """
    keep: set[str] = set()
    pending = [names[i : i + batch] for i in range(0, len(names), batch)]
    for _attempt in range(attempts):
        failed = [chunk for chunk in pending if not _validate_chunk(settings, chunk, keep)]
        if not failed:
            return keep
        LOGGER.warning("roster validation: retrying %s batches", len(failed))
        pending = failed
    LOGGER.warning("roster validation: %s batches never succeeded", len(pending))
    return keep


def _validate_chunk(settings: Any, chunk: list[str], keep: set[str]) -> bool:
    """One batch. Returns False so the caller can retry it rather than lose it."""
    from .extract.claims import _chat

    try:
        raw, _, _ = _chat(settings, VALIDATE_PROMPT + "\n" + "\n".join(chunk), VALIDATE_SYSTEM)
    except Exception as exc:
        LOGGER.warning("roster validation batch failed (%s...): %s", chunk[0], exc)
        return False
    keep.update(_people_from_reply(raw, chunk))
    return True


def _people_from_reply(raw: str, chunk: list[str]) -> set[str]:
    """Names the reply kept, whether it answered with JSON or just a list."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    allowed = set(chunk)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Fall back to any candidate quoted verbatim in the reply.
        return {name for name in chunk if f'"{name}"' in raw}
    people = payload.get("people") if isinstance(payload, dict) else payload
    if not isinstance(people, list):
        return set()
    return {str(v) for v in people if str(v) in allowed}
