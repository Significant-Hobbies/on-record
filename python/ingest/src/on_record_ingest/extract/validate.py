from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from ..seed.people import PEOPLE

CLAIM_TYPES = {
    "belief",
    "prediction",
    "recommendation",
    "evaluation",
    "observation",
    "preference",
    "commitment",
    "disagreement",
    "uncertainty",
}
MIN_QUOTE_CHARS = 40
REFERENCE_KINDS = {
    "book",
    "app",
    "tool",
    "service",
    "paper",
    "course",
    "hardware",
    "person",
    "other",
}
REFERENCE_ROLES = {"recommends", "uses", "likes", "owns", "built", "avoids"}
REFERENCE_CLAUSE_BREAK = re.compile(
    r"(?:[.!?;]\s+|,\s*(?:and|but|while|whereas)\s+|\s+(?:but|whereas)\s+|"
    r"\s+and\s+(?=(?:i|we|you|they|personally|currently|actually|still|use|used|"
    r"recommend|avoid|built|created|made|read|love|like|prefer|own|bought)\b))",
    re.IGNORECASE,
)
REFERENCE_GENERIC_NAME = re.compile(
    r"^(?:it|this|that|these|those|him|his|her|them|ai|artificial intelligence|machine learning|"
    r"ai note[- ]taking|"
    r"software|hardware|books?|apps?|applications?|games?|tools?|services?|papers?|"
    r"courses?|devices?|accounts?|podcasts?|shows?|products?|platforms?|sources?|"
    r"(?:a|an|the|this|that|some|any|my|your|our|their)\s+"
    r"(?:app|application|book|game|tool|service|paper|course|device|hardware|account|"
    r"podcast|show|product|software|platform))$",
    re.IGNORECASE,
)
REFERENCE_DESCRIPTIVE_NAME = re.compile(
    r"^(?:his|her|their|my|your|our|a|an|the|this|that)\s+"
    r"(?:(?:new|latest|recent|current|favorite|favourite)\s+)?"
    r"(?:book|app|application|game|tool|service|paper|course|device|account|podcast|"
    r"show|series|channel|product|platform)\b",
    re.IGNORECASE,
)
REFERENCE_NON_TITLE_BOOK_NAME = re.compile(
    r"(?:['’]s\s+(?:new\s+)?book|\bbooks|\bbook\s+reviews)$|"
    r"^(?:the\s+)?(?:first|second|last)\s+(?:third|half|part|chapter|section)$|"
    r"^(?:the\s+)?(?:front|back)(?:\s+inside)?\s+cover\s+of\s+(?:this|the)\s+book$|"
    r"['’]s\s+(?:auto)?biography$|['’]s\s+encyclopedia$",
    re.IGNORECASE,
)
REFERENCE_AUDITED_NON_TITLE_BOOK_NAMES = {
    "amazon's management science",
    "andrew roberts latest book on winston churchill",
    "cialdini's persuasion book",
    "elon musk book",
    "kim scott's writing",
    "over my shoulder",
    "rick reuben's creativity book",
    "shakespearean comedies",
    "shawn theron",
    "the design sprint",
    "the economic history of chicago",
    "the how to book",
    "what is it in the first place",
}
REFERENCE_OBJECT_PRONOUN = re.compile(r"\b(?:it|them|this|that|these|those)\b", re.IGNORECASE)
REFERENCE_REPORTED_SPEECH = re.compile(
    r"\b(?:he|she|they|someone|a\s+woman|a\s+man|the\s+woman|the\s+man|my\s+friend)\s+"
    r"(?:said|told|wrote|asked)\b",
    re.IGNORECASE,
)
REFERENCE_WRAPPED_PERSON = re.compile(
    r"\b(?:conversation|interview|episode|talk|book|article|work|series|channel|podcast|show)\s+"
    r"(?:with|by|from)\b",
    re.IGNORECASE,
)
REFERENCE_ADVERBS = (
    r"(?:(?:personally|currently|actually|still|always|mostly|usually|daily|now|"
    r"highly|strongly|really|definitely|generally|originally)\s+)*"
)
REFERENCE_KIND_CONFLICTS = {
    "book": re.compile(
        r"\b(?:game|app|application|software|tool|service|platform|device|hardware|course|"
        r"paper|article|account|documentary|films?|movies?|songs?|albums?|magazines?|"
        r"newsletters?|website|blog|talk|video|channel|supplement|vitamin|"
        r"multivitamin|drug|medication)\b",
        re.IGNORECASE,
    ),
    "app": re.compile(
        r"\b(?:book|novel|memoir|game|games|gaming|paper|course|device|hardware|chip|account)\b",
        re.IGNORECASE,
    ),
    "tool": re.compile(
        r"\b(?:book|novel|memoir|paper|course|device|hardware|chip|account)\b", re.IGNORECASE
    ),
    "service": re.compile(
        r"\b(?:book|novel|memoir|paper|course|device|hardware|chip|account)\b", re.IGNORECASE
    ),
    "paper": re.compile(
        r"\b(?:game|app|software|tool|service|device|hardware|course|account)\b", re.IGNORECASE
    ),
    "course": re.compile(
        r"\b(?:game|app|software|tool|service|device|hardware|paper|account)\b", re.IGNORECASE
    ),
    "hardware": re.compile(
        r"\b(?:book|novel|memoir|game|app|software|service|course|paper|account)\b", re.IGNORECASE
    ),
    "person": re.compile(
        r"\b(?:book|novel|memoir|game|app|software|tool|service|device|course|paper|account)\b",
        re.IGNORECASE,
    ),
}
REFERENCE_KIND_OVERRIDES = {
    "antigravity": "app",
    "blade runner": "other",
    "claude": "app",
    "coda": "app",
    "creative destruction": "book",
    "demand-side sales 101": "book",
    "design sprint by google": "other",
    "devin": "app",
    "don giovanni": "other",
    "embrace the adventure": "other",
    "figjam": "app",
    "forbes": "other",
    "founders podcast": "other",
    "gong": "app",
    "goose": "tool",
    "gta 4": "other",
    "hey jude": "other",
    "marginal revolution": "other",
    "michael lewis": "person",
    "miro": "app",
    "mystery": "app",
    "new york times": "other",
    "nintendo power": "other",
    "notebooklm": "app",
    "nvidia": "other",
    "orb": "service",
    "pando": "app",
    "persona": "other",
    "pessimist archive": "other",
    "quantum country": "other",
    "red dead 1": "other",
    "reinhold niebuhr": "person",
    "rescuetime": "app",
    "roald dahl": "person",
    "scaling devtools": "other",
    "silent all these years": "other",
    "ted chiang": "person",
    "the princess bride": "other",
    "the peel": "other",
    "thomas mann": "person",
    "twitter": "app",
    "ulm fit": "paper",
    "v0": "app",
    "vercel": "service",
    "virgil": "person",
    "wikipedia": "other",
    "zoom": "app",
}


def normalize_ws(text: str) -> str:
    return " ".join(text.split())


def is_stable_reference_name(name: str) -> bool:
    """Reject descriptive noun phrases; references must identify a stable named thing."""
    normalized = normalize_ws(name)
    if REFERENCE_GENERIC_NAME.fullmatch(normalized) or REFERENCE_DESCRIPTIVE_NAME.search(
        normalized
    ):
        return False
    if " " not in normalized:
        return bool(re.search(r"[A-Z0-9./+#@]", normalized))
    first_token = normalized.split(" ", 1)[0]
    if re.fullmatch(r"[a-z]+", first_token):
        return False
    return any(char.isupper() for char in normalized) or bool(re.search(r"[./+#@]", normalized))


def find_verbatim_anchor(
    segment: str, quote: str, min_chars: int = MIN_QUOTE_CHARS
) -> tuple[int, int] | None:
    needle = normalize_ws(quote)
    if len(needle) < min_chars:
        return None
    norm_chars: list[str] = []
    mapping: list[int] = []
    i = 0
    length = len(segment)
    while i < length and segment[i].isspace():
        i += 1
    while i < length:
        ch = segment[i]
        if ch.isspace():
            while i < length and segment[i].isspace():
                i += 1
            if i < length:
                mapping.append(i)
                norm_chars.append(" ")
            continue
        mapping.append(i)
        norm_chars.append(ch)
        i += 1
    haystack = "".join(norm_chars)
    at = haystack.find(needle)
    if at < 0:
        return None
    start = mapping[at]
    end = mapping[at + len(needle) - 1] + 1
    return start, end


def timestamp_for_offset(
    cues: list[dict[str, Any]], offset: int, segment_text: str
) -> float | None:
    if offset < 0 or offset > len(segment_text):
        return None
    running = 0
    for cue in cues:
        text = str(cue.get("text") or "")
        nxt = running + len(text) + 1
        if offset < nxt:
            return float(cue.get("start") or 0)
        running = nxt
    if cues:
        return float(cues[0].get("start") or 0)
    return None


def _balanced_spans(text: str) -> list[tuple[int, int]]:
    """Every complete {...} region in ``text``, innermost first, quotes respected."""
    spans: list[tuple[int, int]] = []
    stack: list[int] = []
    in_string = False
    escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            spans.append((stack.pop(), i + 1))
    return spans


def salvage_claim_objects(text: str) -> list[dict[str, Any]]:
    """Pull whole claim objects out of a response that stopped mid-array.

    A truncated answer still carries every claim before the cut. Dropping the
    lot because the final object lost its closing brace throws away good
    extractions and buys a second call that truncates in the same place.
    """
    rows: list[tuple[int, dict[str, Any]]] = []
    for opened, closed in _balanced_spans(text):
        try:
            row = json.loads(text[opened:closed])
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and isinstance(row.get("claims"), list):
            return [item for item in row["claims"] if isinstance(item, dict)]
        if isinstance(row, dict) and "quote" in row:
            rows.append((opened, row))
    return [row for _, row in sorted(rows, key=lambda pair: pair[0])]


def parse_claims_json(raw: str) -> list[dict[str, Any]] | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        salvaged = salvage_claim_objects(text)
        return salvaged or None
    if isinstance(payload, dict) and isinstance(payload.get("claims"), list):
        payload = payload["claims"]
    if not isinstance(payload, list):
        return None
    return [row for row in payload if isinstance(row, dict)]


def _reference_fields(item: Any) -> tuple[str, str, str] | None:
    if not isinstance(item, dict):
        return None
    kind = str(item.get("kind") or "").strip().lower()
    role = str(item.get("role") or "").strip().lower()
    name = str(item.get("name") or "").strip()
    normalized_name = normalize_ws(name)
    invalid_book_name = kind == "book" and (
        REFERENCE_NON_TITLE_BOOK_NAME.search(normalized_name)
        or normalized_name.lower() in REFERENCE_AUDITED_NON_TITLE_BOOK_NAMES
    )
    if (
        kind not in REFERENCE_KINDS
        or role not in REFERENCE_ROLES
        or len(name) < 2
        or not is_stable_reference_name(name)
        or invalid_book_name
    ):
        return None
    return kind, role, name


def validate_references(
    row: dict[str, Any], claim_quote: str, kind_context: str | None = None
) -> list[dict[str, str]]:
    raw = row.get("references") or []
    if not isinstance(raw, list):
        return []
    haystack = normalize_ws(claim_quote).lower()
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    allow_book_answer = bool(row.get("bookAnswer") or row.get("book_answer"))
    for item in raw:
        fields = _reference_fields(item)
        if fields is None:
            continue
        kind, role, name = fields
        if normalize_ws(name).lower() not in haystack:
            continue
        if not reference_role_supported(
            name,
            role,
            claim_quote,
            kind,
            allow_book_answer=allow_book_answer,
        ):
            continue
        kind = normalized_reference_kind(
            name, kind, kind_context or claim_quote, allow_book_answer=allow_book_answer
        )
        key = (role, name.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": kind, "name": name, "role": role})
    return out


@dataclass(frozen=True)
class ReferenceMatch:
    role: str
    kind: str | None
    name_pattern: str
    matching: list[str]
    full: str


def _active_reference_object(
    context: ReferenceMatch, verbs: str, clause: str, distance: int = 100
) -> bool:
    pattern = re.compile(
        rf"\b(?:i|we)(?:\s+|['’](?:m|re|ve)\s+){REFERENCE_ADVERBS}(?:{verbs})\b"
        rf"(?P<gap>.{{0,{distance}}}?){context.name_pattern}",
        re.IGNORECASE,
    )
    for match in pattern.finditer(clause):
        gap = match.group("gap")
        if REFERENCE_OBJECT_PRONOUN.search(gap):
            continue
        if context.kind == "book" and re.search(
            r"\b(?:book|biography)\s+(?:about|on)\b", gap, re.IGNORECASE
        ):
            continue
        if re.search(r"\b(?:said|told|wrote|asked)\b", gap, re.IGNORECASE):
            continue
        if REFERENCE_REPORTED_SPEECH.search(clause[: match.start()]):
            continue
        if context.role == "recommends" and re.search(
            r"\b(?:about|regarding|concerning)\b", gap, re.IGNORECASE
        ):
            continue
        if context.kind == "person" and (
            REFERENCE_WRAPPED_PERSON.search(gap)
            or re.search(r"\b(?:with|by|from)\b", gap, re.IGNORECASE)
        ):
            continue
        return True
    return False


def _recommendation_supported(context: ReferenceMatch) -> bool:
    should = re.compile(
        rf"\b(?:you|people|everyone|founders|engineers|teams|we)\s+(?:really\s+)?"
        rf"should\s+(?:read|try|use|watch|listen\s+to|check\s+out|follow)\b"
        rf".{{0,80}}?{context.name_pattern}",
        re.IGNORECASE,
    )
    relative = re.compile(
        rf"{context.name_pattern}.{{0,60}}?\b(?:that|which)\s+(?:i|we)\s+"
        rf"{REFERENCE_ADVERBS}recommend(?:ed)?\b",
        re.IGNORECASE,
    )
    worth = re.compile(
        rf"(?:\bmust[- ](?:read|use|watch)\b.{{0,50}}?{context.name_pattern}|"
        rf"{context.name_pattern}.{{0,40}}?\bworth\s+"
        rf"(?:reading|trying|using|watching|listening\s+to)\b)",
        re.IGNORECASE,
    )
    deictic = re.compile(
        rf"{context.name_pattern}.{{0,100}}?\b(?:i|we)(?:\s+|['’](?:m|re|ve)\s+)"
        rf"{REFERENCE_ADVERBS}recommend(?:ed)?\s+(?:it|that|this)\b",
        re.IGNORECASE,
    )
    my_recommendations = re.compile(
        rf"\bmy\s+recommendations?\b.{{0,180}}?{context.name_pattern}", re.IGNORECASE
    )
    return bool(deictic.search(context.full) or my_recommendations.search(context.full)) or any(
        _active_reference_object(context, r"recommend(?:ed)?", clause)
        or should.search(clause)
        or (context.kind != "person" and relative.search(clause))
        or worth.search(clause)
        for clause in context.matching
    )


def _use_supported(context: ReferenceMatch) -> bool:
    verbs = (
        r"use|used|using|rely\s+on|run|work\s+with|read|reread|reading|"
        r"finished\s+reading|started\s+reading|am\s+reading|are\s+reading|"
        r"have\s+read|have\s+been\s+reading|have\s+been\s+using|have\s+used|"
        r"listen\s+to|listened\s+to|watch|watched|"
        r"subscribe\s+to|subscribed\s+to|wear|drive|play"
    )
    fronted = re.compile(
        rf"{context.name_pattern}\s*,\s*(?:i|we)\s+{REFERENCE_ADVERBS}(?:{verbs})\b",
        re.IGNORECASE,
    )
    title_first = re.compile(
        rf"{context.name_pattern}.{{0,100}}?\b(?:i|we)(?:\s+|['’](?:m|re|ve)\s+)"
        rf"{REFERENCE_ADVERBS}(?:{verbs})\b",
        re.IGNORECASE,
    )
    return any(
        _active_reference_object(context, verbs, clause)
        or fronted.search(clause)
        or title_first.search(clause)
        for clause in context.matching
    )


def _preference_supported(context: ReferenceMatch) -> bool:
    verbs = (
        r"love|loved|like|liked|prefer|preferred|enjoy|enjoyed|adore|adored|swear\s+by|"
        r"do\s+(?:love|like|prefer|enjoy|adore)"
    )
    fan = re.compile(
        rf"\b(?:i|we)(?:['’]m|\s+am|['’]re|\s+are)\s+(?:a\s+)?"
        rf"(?:(?:big|huge)\s+)?fan\s+of\s+.{{0,80}}?{context.name_pattern}",
        re.IGNORECASE,
    )
    favorite = re.compile(
        rf"(?:\bmy\s+favou?rite(?:\s+\w+){{0,3}}\s+is\s+{context.name_pattern}|"
        rf"{context.name_pattern}.{{0,40}}?\bis\s+my\s+favou?rite\b)",
        re.IGNORECASE,
    )
    obsessed = re.compile(
        rf"\b(?:i|we)(?:['’]m|\s+am|['’]re|\s+are)\s+obsessed\s+with\s+"
        rf".{{0,60}}?{context.name_pattern}",
        re.IGNORECASE,
    )
    described_book = re.compile(
        rf"\b(?:book|novel|memoir|biography)\b.{{0,60}}?"
        rf"\b(?:i|we)(?:\s+|['’](?:m|re|ve)\s+){REFERENCE_ADVERBS}"
        rf"(?:love|loved|like|liked|prefer|preferred|enjoy|enjoyed|adore|adored)\b"
        rf".{{0,80}}?{context.name_pattern}",
        re.IGNORECASE,
    )
    positive_book = re.compile(
        rf"(?:{context.name_pattern}.{{0,100}}?\b(?:best|great|excellent|incredible|"
        rf"fantastic|extraordinary|exceptionally\s+good|wonderful)\b.{{0,40}}?\bbook\b|"
        rf"\b(?:best|great|excellent|incredible|fantastic|extraordinary|"
        rf"exceptionally\s+good|wonderful)\b.{{0,40}}?\bbook\b.{{0,100}}?"
        rf"{context.name_pattern})",
        re.IGNORECASE,
    )
    title_then_approval = re.compile(
        rf"{context.name_pattern}.{{0,100}}?\b(?:i|we)\s+(?:thought|think)\s+"
        rf"(?:it|that|this)\s+(?:is|was)\s+(?:great|excellent|incredible|fantastic|"
        rf"extraordinary|wonderful)\b",
        re.IGNORECASE,
    )
    return any(
        _active_reference_object(context, verbs, clause)
        or fan.search(clause)
        or favorite.search(clause)
        or obsessed.search(clause)
        or described_book.search(clause)
        or positive_book.search(clause)
        or title_then_approval.search(clause)
        for clause in context.matching
    )


def reference_role_supported(
    name: str,
    role: str,
    claim_quote: str,
    kind: str | None = None,
    allow_book_answer: bool = False,
) -> bool:
    """Require a direct grammatical link between the named thing and speech act."""
    if role not in REFERENCE_ROLES:
        return False
    needle = normalize_ws(name)
    if REFERENCE_GENERIC_NAME.fullmatch(needle):
        return False
    clauses = REFERENCE_CLAUSE_BREAK.split(normalize_ws(claim_quote))
    context = ReferenceMatch(
        role=role,
        kind=kind,
        name_pattern=re.escape(needle).replace(r"\ ", r"\s+"),
        matching=[clause for clause in clauses if needle.casefold() in clause.casefold()],
        full=normalize_ws(claim_quote),
    )
    if role == "recommends":
        if allow_book_answer and kind == "book":
            return True
        return _recommendation_supported(context)
    if role == "uses":
        return _use_supported(context)
    if role == "likes":
        return _preference_supported(context)
    verbs_by_role = {
        "owns": r"own|bought|purchased|have\s+purchased|have\s+bought",
        "built": (
            r"built|created|made|founded|developed|launched|wrote|authored|designed|"
            r"shipped|started"
        ),
        "avoids": (
            r"avoid|avoided|never\s+use|stopped\s+using|quit|uninstalled|"
            r"stay\s+away\s+from|do\s+not\s+use|don['’]?t\s+use|"
            r"would\s+not\s+use|wouldn['’]?t\s+use|cannot\s+use|can['’]?t\s+use"
        ),
    }
    verbs = verbs_by_role.get(role)
    return bool(verbs) and any(
        _active_reference_object(context, verbs, clause) for clause in context.matching
    )


def normalized_reference_kind(
    name: str, kind: str, claim_quote: str, allow_book_answer: bool = False
) -> str:
    """Downgrade an explicitly contradicted model category to safe `other`."""
    override = REFERENCE_KIND_OVERRIDES.get(normalize_ws(name).casefold())
    if override:
        return override
    if kind == "book" and allow_book_answer:
        return kind
    context = normalize_ws(claim_quote)
    name_pattern = re.escape(normalize_ws(name)).replace(r"\ ", r"\s+")
    media_wrapper = re.compile(
        rf"\b(?:channel|podcast|show|series|episode)"
        rf"(?:\s+(?:called|named|of))?\s*,?\s*{name_pattern}\b",
        re.IGNORECASE,
    )
    if kind != "other" and media_wrapper.search(context):
        return "other"
    return _kind_after_conflict_check(name, kind, context, name_pattern)


def _kind_after_conflict_check(name: str, kind: str, context: str, name_pattern: str) -> str:
    conflict = REFERENCE_KIND_CONFLICTS.get(kind)
    if conflict is None:
        return kind
    needle = normalize_ws(name).casefold()
    folded = context.casefold()
    if kind == "book" and re.search(rf"\bread\s+in\s+{name_pattern}", context, re.IGNORECASE):
        return "other"
    at = folded.find(needle)
    while at >= 0:
        nearby = context[max(0, at - 160) : at + len(needle) + 160]
        if conflict.search(nearby):
            return "other"
        at = folded.find(needle, at + len(needle))
    return kind


def _confidence(row: dict[str, Any], *keys: str) -> float | None:
    try:
        return float(next((row[key] for key in keys if row.get(key) is not None), 0))
    except (TypeError, ValueError):
        return None


def speaker_alias_map(people: list[dict[str, Any]] | None = None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for person in people or PEOPLE:
        slug = str(person["slug"])
        mapping[slug.lower()] = slug
        mapping[str(person.get("name") or "").lower()] = slug
        for alias in person.get("aliases") or []:
            mapping[str(alias).lower()] = slug
    mapping.pop("", None)
    return mapping


def resolve_speaker(raw: str, roster: set[str], aliases: dict[str, str] | None = None) -> str:
    speaker = raw.strip()
    if speaker in roster or speaker == "unknown":
        return speaker
    mapped = (aliases or speaker_alias_map()).get(speaker.lower())
    if mapped and mapped in roster:
        return mapped
    return speaker


def validate_claim(
    row: dict[str, Any],
    segment_text: str,
    roster: set[str],
    topics: set[str],
) -> tuple[dict[str, Any] | None, str | None]:
    speaker = resolve_speaker(str(row.get("speaker") or row.get("speakerRaw") or ""), roster)
    if speaker not in roster and speaker != "unknown":
        return None, "speaker_not_in_roster"
    claim_type = str(row.get("claim_type") or row.get("claimType") or "").strip()
    if claim_type not in CLAIM_TYPES:
        return None, "bad_claim_type"
    quote = str(row.get("quote") or "").strip()
    assertion = str(row.get("assertion") or row.get("normalized_claim") or "").strip()
    if not assertion:
        return None, "missing_assertion"
    return _validated_body(row, speaker, claim_type, quote, assertion, segment_text, topics)


def _validated_body(
    row: dict[str, Any],
    speaker: str,
    claim_type: str,
    quote: str,
    assertion: str,
    segment_text: str,
    topics: set[str],
) -> tuple[dict[str, Any] | None, str | None]:
    anchor = find_verbatim_anchor(segment_text, quote)
    if anchor is None:
        return None, "quote_not_verbatim"
    topic_list = row.get("topics") or []
    if not isinstance(topic_list, list):
        return None, "bad_topics"
    extraction = _confidence(row, "extraction_confidence", "extractionConfidence")
    speaker_conf = _confidence(row, "speaker_confidence", "speakerConfidence")
    if extraction is None or speaker_conf is None:
        return None, "bad_confidence"
    return {
        "speakerRaw": speaker,
        "claimType": claim_type,
        "assertion": assertion,
        "stance": str(row.get("stance") or "") or None,
        "quote": quote,
        "quoteStartChar": anchor[0],
        "quoteEndChar": anchor[1],
        "extractionConfidence": extraction,
        "speakerConfidence": speaker_conf,
        "topics": [str(slug) for slug in topic_list if str(slug) in topics],
        "references": validate_references(row, quote, segment_text),
        "bookAnswer": bool(row.get("bookAnswer") or row.get("book_answer")),
    }, None
