from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .guest_recovery import explicit_guest_names

UNKNOWN = "unknown"
SKIP_TRANSCRIPT_KINDS = {"rss_text_coarse"}
MAIN_PROGRAM_MARKERS = ("bloomberg audio studios",)


def _introduced_as(text: str, name: str) -> bool:
    escaped = re.escape(name).replace(r"\ ", r"\s+")
    pattern = re.compile(
        rf"\b(?:i['’]m|i am|my name is)\s+"
        rf"(?:your\s+(?:host|guest)[,:]?\s+)?{escaped}\b",
        re.IGNORECASE,
    )
    return bool(pattern.search(text))


def _contains_name(text: str, name: str) -> bool:
    escaped = re.escape(name).replace(r"\ ", r"\s+")
    return bool(re.search(rf"\b{escaped}\b", text, re.IGNORECASE))


def _welcomes_person(text: str, names: list[str]) -> bool:
    for name in names:
        escaped = re.escape(name).replace(r"\ ", r"\s+")
        if re.search(
            rf"\b{escaped}\b.{{0,45}}\b(?:welcome|thanks? for joining|great to have you)\b",
            text,
            re.IGNORECASE,
        ):
            return True
    return False


def _accepts_welcome(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:thanks?|thank you)\b.{0,40}\b(?:having|inviting|welcome)\b|"
            r"\b(?:happy|glad|great) to (?:be (?:here|back)|join (?:you|everyone))\b",
            text,
            re.IGNORECASE,
        )
    )


def _introduces_guest(text: str, full_name: str) -> bool:
    escaped = re.escape(full_name).replace(r"\ ", r"\s+")
    return bool(
        re.search(
            rf"\b(?:speaking|talking|speak|talk|joined)\s+(?:to|with|by)\b"
            rf".{{0,120}}\b{escaped}\b|\bour guest(?: today)? is\b"
            rf".{{0,80}}\b{escaped}\b",
            text,
            re.IGNORECASE,
        )
    )


def _main_program_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop publisher pre-roll when an explicit program bumper is present."""
    start = 0
    for offset, segment in enumerate(segments[:12]):
        text = str(segment.get("text") or "").casefold()
        if any(marker in text for marker in MAIN_PROGRAM_MARKERS):
            start = offset + 1
    return segments[start:]


@dataclass(frozen=True)
class RecoveryContext:
    segments: list[dict[str, Any]]
    roster: list[dict[str, Any]]
    roster_rows: dict[str, dict[str, Any]]
    first_name_counts: dict[str, int]
    explicit_names: set[str]
    title_guest_names: set[str]
    title: str


def _metadata_guest(row: dict[str, Any]) -> bool:
    return row.get("role") == "guest" and row.get("attributionSource") == "metadata_match"


def _eligible_roster(
    detail: dict[str, Any], people_by_id: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, int]]:
    roster = []
    roster_rows: dict[str, dict[str, Any]] = {}
    for row in detail.get("people") or []:
        if float(row.get("confidence") or 1.0) < 0.5:
            continue
        person = people_by_id.get(str(row.get("personId") or ""))
        if person and person.get("slug") and person.get("name"):
            roster.append(person)
            roster_rows[str(person["slug"])] = row
    first_name_counts: dict[str, int] = defaultdict(int)
    for person in roster:
        first_name_counts[str(person["name"]).split()[0].casefold()] += 1
    return roster, roster_rows, dict(first_name_counts)


def _recovery_context(
    detail: dict[str, Any], people_by_id: dict[str, dict[str, Any]]
) -> RecoveryContext | None:
    episode = detail.get("episode") or {}
    transcript_kind = str(episode.get("transcriptKind") or "")
    if transcript_kind in SKIP_TRANSCRIPT_KINDS:
        return None
    segments = _main_program_segments(list(detail.get("segments") or []))
    if transcript_kind == "rss_text" and len(segments) > 300:
        return None
    roster, roster_rows, first_name_counts = _eligible_roster(detail, people_by_id)
    explicit_names = {
        name.casefold()
        for name in explicit_guest_names(
            str(episode.get("description") or ""), str(episode.get("title") or "")
        )
    }
    title = str(episode.get("title") or "")
    title_guest_names = {
        str(person["name"]).casefold()
        for person in roster
        if _metadata_guest(roster_rows[str(person["slug"])])
        and _contains_name(title, str(person["name"]))
    }
    return RecoveryContext(
        segments=segments,
        roster=roster,
        roster_rows=roster_rows,
        first_name_counts=first_name_counts,
        explicit_names=explicit_names,
        title_guest_names=title_guest_names,
        title=title,
    )


def _person_names(person: dict[str, Any], first_name_counts: dict[str, int]) -> list[str]:
    full_name = str(person["name"]).strip()
    first_name = full_name.split()[0]
    if first_name_counts[first_name.casefold()] == 1:
        return [full_name, first_name]
    return [full_name]


def _known_label_mappings(
    context: RecoveryContext,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    label_to_speakers: dict[str, set[str]] = defaultdict(set)
    speaker_to_labels: dict[str, set[str]] = defaultdict(set)
    for segment in context.segments:
        label = str(segment.get("diarLabel") or "")
        speaker = str(segment.get("speakerHint") or "")
        if label and speaker not in {"", UNKNOWN}:
            label_to_speakers[label].add(speaker)
            speaker_to_labels[speaker].add(label)
    return label_to_speakers, speaker_to_labels


def _add_self_introductions(
    context: RecoveryContext,
    label_to_speakers: dict[str, set[str]],
    speaker_to_labels: dict[str, set[str]],
    intro_limit: int,
) -> None:
    for segment in context.segments[:intro_limit]:
        label = str(segment.get("diarLabel") or "")
        text = str(segment.get("text") or "")
        if not label or not text:
            continue
        for person in context.roster:
            names = _person_names(person, context.first_name_counts)
            if any(_introduced_as(text, name) for name in names):
                slug = str(person["slug"])
                label_to_speakers[label].add(slug)
                speaker_to_labels[slug].add(label)


def _adjacent_guest_is_evidenced(
    context: RecoveryContext,
    previous: dict[str, Any],
    current: dict[str, Any],
    person: dict[str, Any],
) -> bool:
    previous_speaker = str(previous.get("speakerHint") or "")
    previous_label = str(previous.get("diarLabel") or "")
    current_label = str(current.get("diarLabel") or "")
    current_text = str(current.get("text") or "")
    previous_text = str(previous.get("text") or "")
    slug = str(person["slug"])
    full_name = str(person["name"]).strip()
    names = _person_names(person, context.first_name_counts)
    welcomed = (
        previous_speaker not in {"", UNKNOWN}
        and _accepts_welcome(current_text)
        and _welcomes_person(previous_text, names)
    )
    explicitly_introduced = (
        previous_label
        and previous_label != current_label
        and full_name.casefold() in context.explicit_names.union(context.title_guest_names)
        and _metadata_guest(context.roster_rows[slug])
        and _introduces_guest(previous_text, full_name)
        and (_accepts_welcome(current_text) or "?" in previous_text[-240:])
    )
    return slug != previous_speaker and bool(welcomed or explicitly_introduced)


def _add_adjacent_guest_mappings(
    context: RecoveryContext,
    label_to_speakers: dict[str, set[str]],
    speaker_to_labels: dict[str, set[str]],
    intro_limit: int,
) -> None:
    window = context.segments[:intro_limit]
    for previous, current in zip(window, window[1:]):
        current_label = str(current.get("diarLabel") or "")
        if not current_label or str(current.get("speakerHint") or "") not in {"", UNKNOWN}:
            continue
        for person in context.roster:
            if _adjacent_guest_is_evidenced(context, previous, current, person):
                slug = str(person["slug"])
                label_to_speakers[current_label].add(slug)
                speaker_to_labels[slug].add(current_label)


def _unambiguous_label_map(
    label_to_speakers: dict[str, set[str]], speaker_to_labels: dict[str, set[str]]
) -> dict[str, str]:
    return {
        label: next(iter(speakers))
        for label, speakers in label_to_speakers.items()
        if len(speakers) == 1 and len(speaker_to_labels[next(iter(speakers))]) == 1
    }


def _dominant_unknown_label(context: RecoveryContext, label_map: dict[str, str]) -> str | None:
    chars: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    for segment in context.segments:
        label = str(segment.get("diarLabel") or "")
        if (
            label
            and label not in label_map
            and str(segment.get("speakerHint") or "") in {"", UNKNOWN}
        ):
            chars[label] += len(str(segment.get("text") or "").strip())
            counts[label] += 1
    ranked = sorted(chars, key=chars.get, reverse=True)
    if not ranked:
        return None
    dominant = ranked[0]
    runner_up_chars = chars[ranked[1]] if len(ranked) > 1 else 0
    if (
        chars[dominant] >= 2_000
        and counts[dominant] >= 10
        and chars[dominant] >= 4 * max(1, runner_up_chars)
        and chars[dominant] >= 0.75 * sum(chars.values())
    ):
        return dominant
    return None


def _add_dominant_guest(context: RecoveryContext, label_map: dict[str, str]) -> None:
    explicit_guest_slugs = {
        str(person["slug"])
        for person in context.roster
        if str(person["name"]).casefold() in context.explicit_names
        and _metadata_guest(context.roster_rows[str(person["slug"])])
        and str(person["slug"]) not in set(label_map.values())
    }
    if len(explicit_guest_slugs) != 1 or not label_map:
        return
    dominant = _dominant_unknown_label(context, label_map)
    if dominant:
        label_map[dominant] = next(iter(explicit_guest_slugs))


def _add_sole_metadata_guest(context: RecoveryContext, label_map: dict[str, str]) -> None:
    unknown_labels = {
        str(segment["diarLabel"])
        for segment in context.segments
        if str(segment.get("speakerHint") or "") in {"", UNKNOWN}
        and segment.get("diarLabel")
        and str(segment["diarLabel"]) not in label_map
    }
    mapped_speakers = set(label_map.values())
    metadata_candidates = {
        str(person["slug"])
        for person in context.roster
        if str(person["slug"]) not in mapped_speakers
        and (
            _contains_name(context.title, str(person["name"]))
            or str(person["name"]).casefold() in context.explicit_names
        )
    }
    if len(unknown_labels) == 1 and len(metadata_candidates) == 1:
        label_map[next(iter(unknown_labels))] = next(iter(metadata_candidates))


def recover_self_identified_speakers(
    detail: dict[str, Any], people_by_id: dict[str, dict[str, Any]], intro_limit: int = 120
) -> list[dict[str, Any]]:
    """Propagate only unique first-person introductions across one diarization label."""
    context = _recovery_context(detail, people_by_id)
    if context is None:
        return []
    label_to_speakers, speaker_to_labels = _known_label_mappings(context)
    _add_self_introductions(context, label_to_speakers, speaker_to_labels, intro_limit)
    _add_adjacent_guest_mappings(context, label_to_speakers, speaker_to_labels, intro_limit)
    label_map = _unambiguous_label_map(label_to_speakers, speaker_to_labels)
    _add_dominant_guest(context, label_map)
    _add_sole_metadata_guest(context, label_map)
    return [
        {
            "diarLabel": str(segment["diarLabel"]),
            "idx": int(segment["idx"]),
            "speakerHint": label_map[str(segment["diarLabel"])],
        }
        for segment in context.segments
        if str(segment.get("speakerHint") or "") in {"", UNKNOWN}
        and str(segment.get("diarLabel") or "") in label_map
    ]
