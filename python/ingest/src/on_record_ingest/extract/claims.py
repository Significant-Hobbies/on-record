from __future__ import annotations

import time
from typing import Any

import httpx

from ..config import Settings
from ..seed.people import PEOPLE
from ..seed.topics import TOPICS
from .validate import parse_claims_json, validate_claim

SYSTEM_PROMPT = """Extract claims from one transcript segment. JSON only: {"claims":[...]}.
Each claim: speaker (roster slug, guest name, or unknown), claim_type (belief|prediction|recommendation|evaluation|observation|preference|commitment|disagreement|uncertainty), assertion (third-person), stance, quote (verbatim substring >=40 chars), topics (from list), extraction_confidence, speaker_confidence, references [{kind,name,role}].
kind=book|app|tool|service|paper|course|hardware|person|other. role=recommends|uses|built|avoids|mentions.
name must be words from the quote. Prefer I use / I recommend / I built. Empty claims array if none.
"""


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


def _chat(settings: Settings, user_prompt: str) -> tuple[str, dict[str, Any], int]:
    started = time.perf_counter()
    headers = {
        "Authorization": f"Bearer {settings.ai_api_key}",
        "Content-Type": "application/json",
        "X-Gateway-Project-Id": settings.ai_project_id,
    }
    if settings.force_model:
        # Pinning wins the model but loses the fallback: when that one model
        # is rate limited every call 503s. Only pin deliberately.
        headers["X-Gateway-Force-Model"] = settings.force_model
    body = {
        "model": settings.force_model or "auto",
        "temperature": 0,
        # The gateway caps max_tokens at 8192 whatever the model allows.
        "max_tokens": 8000,
        "project_id": settings.ai_project_id,
        # Supported by every model we pin, and it is what stops the answer
        # arriving wrapped in prose that then fails to parse.
        "response_format": {"type": "json_object"},
        # These two do the work a pinned model was doing, without giving up
        # the fallback. response_format filters the pool to models that can
        # emit JSON; the floor drops the low-reasoning tier, which is where
        # ministral-3b lives. 38 candidates across nine providers survive.
        "min_reasoning_level": "high",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    last_error: Exception | None = None
    payload: dict[str, Any] = {}
    with httpx.Client(timeout=90.0) as client:
        for attempt in range(3):
            try:
                response = client.post(
                    f"{settings.ai_base_url}/chat/completions", headers=headers, json=body
                )
                if response.status_code in {400, 429, 500, 502, 503}:
                    last_error = httpx.HTTPStatusError(
                        f"{response.status_code}", request=response.request, response=response
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


def extract_segment(
    settings: Settings,
    segment_text: str,
    prev_tail: str,
    guests: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    user_prompt = build_user_prompt(
        sorted(roster_slugs()),
        prev_tail,
        segment_text,
        sorted(topic_slugs()),
        guests,
    )
    raw, response_json, latency_ms = _chat(settings, user_prompt)
    parsed = parse_claims_json(raw)
    retry_used = False
    if parsed is None:
        retry_used = True
        raw, response_json, latency_ms = _chat(settings, user_prompt + "\nRespond with JSON only.")
        parsed = parse_claims_json(raw)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in parsed or []:
        claim, reason = validate_claim(row, segment_text, roster_slugs(), topic_slugs())
        if claim is None:
            rejected.append({"reason": reason, "row": row})
            continue
        accepted.append(claim)
    run = {
        "model": served_model(response_json, settings.force_model or "auto"),
        "promptVersion": settings.prompt_version,
        "accepted": bool(accepted),
        "reason": "ok" if parsed is not None else "json_parse_failed",
        "requestJson": {"prompt": user_prompt, "retry": retry_used},
        "responseJson": response_json,
        "latencyMs": latency_ms,
    }
    return accepted, rejected, run
