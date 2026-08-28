from __future__ import annotations

import argparse
import json
from typing import Any

from .api_client import ApiClient
from .config import settings
from .extract.claims import extract_segments_batch
from .extract.triage import claim_candidate_score, triage_segment

UNKNOWN = "unknown"


def candidate_batch(
    segments: list[dict[str, Any]], limit: int, max_chars: int
) -> list[dict[str, Any]]:
    candidates = [
        segment
        for segment in segments
        if str(segment.get("speakerHint") or "") not in {"", UNKNOWN}
        and triage_segment(str(segment.get("text") or "")) != "skip"
    ]
    candidates.sort(
        key=lambda segment: (
            -claim_candidate_score(str(segment.get("text") or "")),
            int(segment.get("idx") or 0),
        )
    )
    selected: list[dict[str, Any]] = []
    characters = 0
    for segment in candidates:
        text = str(segment.get("text") or "")
        if selected and characters + len(text) > max_chars:
            continue
        selected.append(segment)
        characters += len(text)
        if len(selected) >= limit:
            break
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only quality benchmark for batched transcript claim extraction."
    )
    parser.add_argument("--episode", required=True)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--max-chars", type=int, default=18000)
    args = parser.parse_args()

    cfg = settings()
    api = ApiClient(cfg)
    try:
        detail = api.get_episode(args.episode)
    finally:
        api.close()
    batch = candidate_batch(
        list(detail.get("segments") or []),
        max(1, min(args.limit, 20)),
        max(1000, args.max_chars),
    )
    accepted, rejected, run = extract_segments_batch(cfg, batch)
    report = {
        "episodeId": args.episode,
        "episodeTitle": detail.get("episode", {}).get("title"),
        "model": run.get("model"),
        "latencyMs": run.get("latencyMs"),
        "segmentsSent": len(batch),
        "charactersSent": sum(len(str(segment["text"])) for segment in batch),
        "acceptedClaims": len(accepted),
        "rejectedClaims": len(rejected),
        "claims": [
            {
                "segmentId": claim.get("segmentId"),
                "speaker": claim.get("speakerRaw"),
                "type": claim.get("claimType"),
                "assertion": claim.get("assertion"),
                "quote": claim.get("quote"),
                "references": claim.get("references"),
            }
            for claim in accepted
        ],
        "rejections": [str(row.get("reason")) for row in rejected],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
