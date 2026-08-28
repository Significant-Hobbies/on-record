from __future__ import annotations

import json
import time
from typing import Any

import httpx

from ..config import Settings
from ..seed.people import PEOPLE
from ..seed.topics import TOPICS
from .validate import parse_claims_json, validate_claim
from .triage import claim_excerpt

SYSTEM_PROMPT = """Extract claims from one transcript segment. JSON only: {"claims":[...]}.
Each claim: speaker (roster slug, guest name, or unknown), claim_type (belief|prediction|recommendation|evaluation|observation|preference|commitment|disagreement|uncertainty), assertion (third-person), stance, quote (verbatim substring >=40 chars), topics (from list), extraction_confidence, speaker_confidence, references [{kind,name,role}].
kind=book|app|tool|service|paper|course|hardware|person|other. role=recommends|uses|likes|owns|built|avoids.
Only emit a reference when the quote itself explicitly says the speaker recommends it, uses or reads it, likes or prefers it, owns or bought it, built it, or avoids it. Never emit a mere mention. name must be words from the quote. Empty claims array if none.
The reference name must be the exact object of that speech act, not a platform, source, or company merely used to describe it. If someone recommends following an account on Twitter/X, name the account, not Twitter/X.
"""

RECOMMENDATIONS_PROMPT = """Extract only evidenced named recommendations or personal-stack actions from one transcript segment. JSON only: {"claims":[...]}.
Every claim must contain at least one reference in the JSON key references (plural): [{kind,name,role}]. references is always an array, even for one item. Include a third-person assertion and a verbatim quote of at least 40 characters. Empty claims array if there is no qualifying named thing.
kind=book|app|tool|service|paper|course|hardware|person|other. role=recommends|uses|likes|owns|built|avoids.
Qualifying speech acts are explicit: recommends is a direct recommendation or endorsement; uses includes direct use, reading, listening, watching, or subscribing; likes is direct love, preference, favorite, or personal approval; owns is direct ownership or purchase; built includes building, founding, authoring, or launching; avoids is direct rejection or discontinued use. Keep these roles distinct: liking or owning something is not the same as recommending or using it. A product description, passing mention, employer relationship, or statement that something is popular is not a qualifying personal action.
The reference name must be the exact words naming the object of the speech act. Do not return a hosting platform or source used only to describe that object. Example: for "the FFmpeg account on Twitter/X that I recommend everybody follow", name="FFmpeg account on Twitter/X", not "Twitter/X".
Kinds must match the quoted context. Never label a game as a book; use app or other for a game, and other for an account when no narrower kind is exact.
Each claim also includes speaker, speaker_confidence, claim_type, assertion, stance, topics, and extraction_confidence.
"""

BATCH_CLAIMS_PROMPT = """Classify durable, useful claims from a batch of attributed podcast transcript excerpts. JSON only: {"claims":[...]}.
Each input has segment_id, speaker, and an exact excerpt. Return at most one claim per excerpt and copy segment_id exactly into the claim.
Keep a claim only when it captures a substantive idea, opinion, prediction, evaluation, recommendation, preference, commitment, disagreement, or uncertainty that is useful outside the immediate sentence. Omit questions, biography, scene-setting, jokes, acknowledgements, ads, repeated wording, and generic factual narration.
Each claim includes segment_id, claim_type, stance, topics, extraction_confidence, and references. Do not repeat, summarize, or paraphrase the speaker or excerpt; the pipeline stores the exact excerpt as both assertion and evidence. Empty claims array when nothing qualifies.
References use kind=book|app|tool|service|paper|course|hardware|person|other and role=recommends|uses|likes|owns|built|avoids. Only emit a reference when the excerpt itself directly supports that personal action; a passing mention is not a reference.
Use a strict editorial threshold. Keep "I think distribution becomes the moat because software is easier to build." Omit "I watched the team use a whiteboard," "I started my career as an analyst," any interviewer question, and any fragment whose point depends on missing context. Most batches should contain omissions. Returning one claim for every input is an error. When unsure, omit it.
"""
BATCH_PROMPT_VERSION = "extract-v5"

REFERENCE_KINDS_LIST = [
    "book",
    "app",
    "tool",
    "service",
    "paper",
    "course",
    "hardware",
    "person",
    "other",
]
REFERENCE_ROLES_LIST = ["recommends", "uses", "likes", "owns", "built", "avoids"]


def roster_slugs() -> set[str]:
    return {str(person["slug"]) for person in PEOPLE}


def topic_slugs() -> set[str]:
    return {str(topic["slug"]) for topic in TOPICS}


def build_user_prompt(
    roster: list[str],
    prev_tail: str,
    segment_text: str,
    topics: list[str],
    guests: list[str] | None = None,
) -> str:
    tail = f"\nPrev: {prev_tail}" if prev_tail else ""
    guest_line = f"Guests: {', '.join(guests)}\n" if guests else ""
    return (
        f"Roster: {', '.join(roster)}\n{guest_line}"
        f"Topics: {', '.join(topics)}{tail}\nSegment:\n{segment_text}\n"
    )


CLAIM_TYPES_LIST = [
    "belief",
    "prediction",
    "recommendation",
    "evaluation",
    "observation",
    "preference",
    "commitment",
    "disagreement",
    "uncertainty",
]

# A local runtime enforces this shape token by token, so malformed answers stop
# being possible rather than being salvaged after the fact.
REFERENCE_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": REFERENCE_KINDS_LIST},
        "name": {"type": "string"},
        "role": {"type": "string", "enum": REFERENCE_ROLES_LIST},
    },
    "required": ["kind", "name", "role"],
}
COMMON_CLAIM_PROPERTIES: dict[str, Any] = {
    "claim_type": {"type": "string", "enum": CLAIM_TYPES_LIST},
    "stance": {"type": "string"},
    "topics": {"type": "array", "items": {"type": "string"}},
    "extraction_confidence": {"type": "number"},
    "references": {"type": "array", "items": REFERENCE_ITEM_SCHEMA},
}

CLAIMS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {"type": "string"},
                    "segment_id": {"type": "string"},
                    "speaker_confidence": {"type": "number"},
                    "quote": {"type": "string"},
                    **COMMON_CLAIM_PROPERTIES,
                },
                "required": [
                    "speaker",
                    "speaker_confidence",
                    "claim_type",
                    "assertion",
                    "quote",
                    "extraction_confidence",
                ],
            },
        }
    },
    "required": ["claims"],
}

BATCH_CLAIMS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "segment_id": {"type": "string"},
                    "assertion": {"type": "string"},
                    **COMMON_CLAIM_PROPERTIES,
                },
                "required": [
                    "segment_id",
                    "claim_type",
                    "stance",
                    "topics",
                    "extraction_confidence",
                    "references",
                ],
            },
        }
    },
    "required": ["claims"],
}


def is_local(settings: Settings) -> bool:
    """A model served from this machine, rather than through the gateway."""
    return "localhost" in settings.ai_base_url or "127.0.0.1" in settings.ai_base_url


def build_body(
    settings: Settings,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2048,
    schema: dict[str, Any] = CLAIMS_SCHEMA,
) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    if is_local(settings):
        # LM Studio rejects json_object and wants a schema, which is the
        # stronger guarantee anyway. None of the gateway's routing fields mean
        # anything here.
        return {
            "model": settings.force_model or settings.extract_model,
            "temperature": 0,
            # A bounded segment should yield a handful of compact objects.
            # An 8k allowance let malformed local generations occupy the
            # model for several minutes before the HTTP timeout could recover.
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "claims", "strict": True, "schema": schema},
            },
            # Qwen3.5 is a hybrid reasoning model and defaults to thinking.
            # Left on, it spent 588 of 589 tokens reasoning and returned an
            # empty message. Extraction is a reading task, not a puzzle.
            "reasoning_effort": "none",
            "messages": messages,
        }
    return {
        "model": settings.force_model or "auto",
        "temperature": 0,
        # The gateway caps max_tokens at 8192 whatever the model allows.
        "max_tokens": min(max_tokens, 8000),
        "project_id": settings.ai_project_id,
        # Supported by every model we pin, and it is what stops the answer
        # arriving wrapped in prose that then fails to parse.
        "response_format": {"type": "json_object"},
        # These two do the work a pinned model was doing, without giving up
        # the fallback. response_format filters the pool to models that can
        # emit JSON; the floor drops the low-reasoning tier, which is where
        # ministral-3b lives. 38 candidates across nine providers survive.
        "min_reasoning_level": "high",
        "messages": messages,
    }


def _chat(
    settings: Settings,
    user_prompt: str,
    system_prompt: str = SYSTEM_PROMPT,
    max_tokens: int = 2048,
    schema: dict[str, Any] = CLAIMS_SCHEMA,
) -> tuple[str, dict[str, Any], int]:
    started = time.perf_counter()
    headers = {"Content-Type": "application/json"}
    if settings.ai_api_key:
        headers["Authorization"] = f"Bearer {settings.ai_api_key}"
    elif not is_local(settings):
        raise RuntimeError("AI_API_KEY is required for remote inference")
    if not is_local(settings):
        headers["X-Gateway-Project-Id"] = settings.ai_project_id
        if settings.force_model:
            # Pinning wins the model but loses the fallback: when that one
            # model is rate limited every call 503s. Only pin deliberately.
            headers["X-Gateway-Force-Model"] = settings.force_model
    body = build_body(settings, system_prompt, user_prompt, max_tokens, schema)
    last_error: Exception | None = None
    payload: dict[str, Any] = {}
    local = is_local(settings)
    # LM Studio can briefly answer "Model unloaded" while it restores an
    # already-selected model. Retrying the same batch preserves coverage;
    # advancing immediately leaves strong excerpts unattempted until a rerun.
    attempts = 4 if local else 3
    local_timeout = (
        120.0 if "27b" in (settings.force_model or settings.extract_model).lower() else 45.0
    )
    with httpx.Client(timeout=local_timeout if local else 90.0) as client:
        for attempt in range(attempts):
            try:
                response = client.post(
                    f"{settings.ai_base_url}/chat/completions", headers=headers, json=body
                )
                if response.status_code in {400, 429, 500, 502, 503}:
                    last_error = httpx.HTTPStatusError(
                        _http_error_message(response),
                        request=response.request,
                        response=response,
                    )
                    time.sleep(2.0 * (attempt + 1))
                    continue
                response.raise_for_status()
                payload = response.json()
                last_error = None
                break
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(2.0 * (attempt + 1))
    if last_error:
        raise last_error
    latency_ms = int((time.perf_counter() - started) * 1000)
    content = payload["choices"][0]["message"]["content"]
    return str(content), payload, latency_ms


def served_model(response_json: dict[str, Any], requested: str) -> str:
    """Which model actually answered. Claims record this, not what we asked for."""
    gateway = response_json.get("x_gateway")
    if isinstance(gateway, dict) and gateway.get("model"):
        return str(gateway["model"])
    return str(response_json.get("model") or requested)


def _http_error_message(response: httpx.Response) -> str:
    """Keep provider diagnostics useful without logging request content."""
    try:
        error = response.json().get("error")
    except (ValueError, AttributeError):
        error = None
    if isinstance(error, dict) and error.get("message"):
        detail = " ".join(str(error["message"]).split())[:300]
        return f"{response.status_code} {detail}"
    if isinstance(error, str) and error.strip():
        detail = " ".join(error.split())[:300]
        return f"{response.status_code} {detail}"
    detail = " ".join(response.text.split())[:300]
    if detail:
        return f"{response.status_code} {detail}"
    return str(response.status_code)


def extract_segment(
    settings: Settings,
    segment_text: str,
    prev_tail: str,
    guests: list[str] | None = None,
    focus: str = "all",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    # Only the people who could plausibly be talking in this episode: its host
    # and whoever its metadata names. Pasting the whole roster in was 329
    # characters at 23 people and would be 18,000 at 1,236, on every call, for
    # a list the model has to ignore all but two lines of.
    episode_roster = sorted(set(guests or ()))
    user_prompt = build_user_prompt(
        episode_roster,
        prev_tail,
        segment_text,
        sorted(topic_slugs()),
        guests,
    )
    system_prompt = RECOMMENDATIONS_PROMPT if focus == "recs" else SYSTEM_PROMPT
    raw, response_json, latency_ms = _chat(settings, user_prompt, system_prompt)
    parsed = parse_claims_json(raw)
    retry_used = False
    if parsed is None:
        retry_used = True
        raw, response_json, latency_ms = _chat(
            settings,
            user_prompt + "\nRespond with JSON only.",
            system_prompt,
        )
        parsed = parse_claims_json(raw)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in parsed or []:
        # Validate against the same short list. A speaker the episode gives no
        # reason to expect is a misattribution, not a discovery.
        claim, reason = validate_claim(row, segment_text, set(episode_roster), topic_slugs())
        if claim is None:
            rejected.append({"reason": reason, "row": row})
            continue
        accepted.append(claim)
    run = {
        "model": served_model(response_json, settings.force_model or "auto"),
        "promptVersion": settings.prompt_version,
        "accepted": bool(accepted),
        "reason": "ok" if parsed is not None else "json_parse_failed",
        "requestJson": {"focus": focus, "prompt": user_prompt, "retry": retry_used},
        "responseJson": response_json,
        "latencyMs": latency_ms,
    }
    return accepted, rejected, run


def extract_segments_batch(
    settings: Settings,
    segments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Extract at most one durable claim from each already-attributed segment."""
    segment_by_id = {
        str(segment.get("id") or ""): segment
        for segment in segments
        if segment.get("id") and segment.get("speakerHint") and segment.get("text")
    }
    quote_by_id = {
        segment_id: claim_excerpt(str(segment["text"]))
        for segment_id, segment in segment_by_id.items()
    }
    payload = [
        {
            "segment_id": segment_id,
            "speaker": str(segment["speakerHint"]),
            "excerpt": quote_by_id[segment_id],
        }
        for segment_id, segment in segment_by_id.items()
    ]
    user_prompt = f"Segments:\n{json.dumps(payload, ensure_ascii=False)}\n"
    raw, response_json, latency_ms = _chat(
        settings,
        user_prompt,
        BATCH_CLAIMS_PROMPT,
        # Eight compact classifications fit comfortably in 2k tokens. Asking
        # the local runtime to reserve 4k on top of long real-text excerpts can
        # push an otherwise valid prompt beyond the model context window.
        max_tokens=2048,
        schema=BATCH_CLAIMS_SCHEMA,
    )
    parsed = parse_claims_json(raw)
    retry_used = False
    if parsed is None:
        retry_used = True
        raw, response_json, latency_ms = _chat(
            settings,
            user_prompt + "\nRespond with JSON only.",
            BATCH_CLAIMS_PROMPT,
            max_tokens=2048,
            schema=BATCH_CLAIMS_SCHEMA,
        )
        parsed = parse_claims_json(raw)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_segments: set[str] = set()
    for row in parsed or []:
        segment_id = str(row.get("segment_id") or row.get("segmentId") or "")
        segment = segment_by_id.get(segment_id)
        if not segment:
            rejected.append({"reason": "segment_not_in_batch", "row": row})
            continue
        if segment_id in seen_segments:
            rejected.append({"reason": "duplicate_segment_claim", "row": row})
            continue
        speaker = str(segment["speakerHint"])
        evidenced_row = {
            **row,
            "assertion": quote_by_id[segment_id],
            "quote": quote_by_id[segment_id],
            "speaker": speaker,
            "speaker_confidence": 1.0,
        }
        claim, reason = validate_claim(
            evidenced_row,
            str(segment["text"]),
            {speaker},
            topic_slugs(),
        )
        if claim is None:
            rejected.append({"reason": reason, "row": row})
            continue
        claim["speakerRaw"] = speaker
        claim["segmentId"] = segment_id
        accepted.append(claim)
        seen_segments.add(segment_id)
    run = {
        "model": served_model(response_json, settings.force_model or "auto"),
        "promptVersion": BATCH_PROMPT_VERSION,
        "accepted": bool(accepted),
        "reason": "ok" if parsed is not None else "json_parse_failed",
        "requestJson": {
            "focus": "all",
            "segmentIds": list(segment_by_id),
            "retry": retry_used,
        },
        "responseJson": response_json,
        "latencyMs": latency_ms,
    }
    return accepted, rejected, run
