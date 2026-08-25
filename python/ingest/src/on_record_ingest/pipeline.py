from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .api_client import ApiClient
from .config import Settings, settings as load_settings
from .extract.claims import extract_segment
from .extract.triage import triage_segment
from .match import guests_from_text, merge_video
from .seed.people import PEOPLE
from .seed.shows import SHOWS
from .seed.topics import TOPICS
from .segment import cues_to_segments
from .sources import podcast_index, rss_feed, youtube_rss
from .transcripts.rss_transcript import parse_transcript
from .transcripts.youtube_captions import fetch_cues

LOGGER = logging.getLogger("on_record_ingest")
STAGES = ("discover", "transcripts", "extract", "publish", "retime")


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def seed_roster(api: ApiClient) -> tuple[dict[str, str], dict[str, str]]:
    people_ids = api.upsert_people(PEOPLE)
    show_ids = api.upsert_shows(SHOWS)
    api.upsert_topics(TOPICS)
    people_map = {person["slug"]: people_ids[idx] for idx, person in enumerate(PEOPLE)}
    show_map = {show["slug"]: show_ids[idx] for idx, show in enumerate(SHOWS)}
    return people_map, show_map


def remap_people(guests: list[dict[str, Any]], people_map: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for guest in guests:
        person_id = people_map.get(str(guest["personId"]))
        if not person_id:
            continue
        row = dict(guest)
        row["personId"] = person_id
        out.append(row)
    return out


def host_people(show: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "personId": str(slug),
            "role": "host",
            "attributionSource": "show_config",
            "confidence": 1.0,
        }
        for slug in show.get("hostPersonIds") or []
    ]


def with_hosts(guests: list[dict[str, Any]], hosts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hosts are on every episode of their show; they outrank a metadata guess."""
    by_slug = {str(row["personId"]): row for row in guests}
    for host in hosts:
        by_slug[str(host["personId"])] = host
    return list(by_slug.values())


def discover_show(
    show: dict[str, Any],
    show_id: str,
    people_map: dict[str, str],
    since: datetime,
    api: ApiClient,
    cfg: Settings,
    dry_run: bool,
) -> int:
    found = 0
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        rss_items: list[dict[str, Any]] = []
        if show.get("feedUrl"):
            rss_items = rss_feed.fetch_feed(str(show["feedUrl"]), since, client)
        if show.get("podcastIndexFeedId") and cfg.podcast_index_key and cfg.podcast_index_secret:
            rss_items.extend(
                podcast_index.fetch_feed(
                    int(show["podcastIndexFeedId"]),
                    since,
                    cfg.podcast_index_key,
                    cfg.podcast_index_secret,
                    client,
                )
            )
        videos: list[dict[str, Any]] = []
        if show.get("youtubeChannelId"):
            videos = youtube_rss.fetch_channel(str(show["youtubeChannelId"]), since, client)
    by_guid: dict[str, dict[str, Any]] = {}
    for item in rss_items:
        by_guid[str(item["guid"])] = merge_video(item, videos)
    for video in videos:
        guid = str(video["guid"])
        if guid not in by_guid:
            by_guid[guid] = video
    hosts = host_people(show)
    for item in by_guid.values():
        blob = json.dumps(item)
        people = remap_people(
            with_hosts(
                guests_from_text(f"{item.get('title', '')} {item.get('description', '')}"), hosts
            ),
            people_map,
        )
        payload = {
            "showId": show_id,
            "guid": item["guid"],
            "title": item["title"],
            "description": item.get("description"),
            "publishedAt": item.get("publishedAt"),
            "sourceUrl": item.get("sourceUrl"),
            "audioUrl": item.get("audioUrl"),
            "youtubeVideoId": item.get("youtubeVideoId"),
            "durationS": item.get("durationS"),
            "people": people,
        }
        found += 1
        if dry_run:
            LOGGER.info("discover dry-run %s %s", show["slug"], item["title"])
            continue
        episode_id = api.upsert_episode(payload)
        api.put_raw(episode_id, f"episodes/{episode_id}/discover.json", blob, "application/json")
    return found


def resolve_cues(
    item: dict[str, Any], client: httpx.Client
) -> tuple[str, list[dict[str, float | str]]]:
    transcript_url = str(item.get("transcriptUrl") or "")
    if transcript_url:
        response = client.get(transcript_url, timeout=30.0, follow_redirects=True)
        if response.status_code == 200 and response.text.strip():
            kind, cues = parse_transcript(response.text, response.headers.get("content-type", ""))
            if cues:
                return kind, cues
    video_id = str(item.get("youtubeVideoId") or "")
    if video_id:
        cues = fetch_cues(video_id)
        if cues:
            return "youtube_captions", cues
    return "none", []


def run_transcripts(api: ApiClient, episode_id: str | None, force: bool, dry_run: bool) -> int:
    episodes = api.list_episodes(status=None if force else "discovered")
    if episode_id:
        episodes = [row for row in episodes if row["id"] == episode_id]
    count = 0
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for episode in episodes:
            if episode.get("status") == "no_transcript" and not force:
                continue
            raw = {}
            try:
                raw = json.loads(
                    api.get_raw(episode["id"], key=f"episodes/{episode['id']}/discover.json").get(
                        "content"
                    )
                    or "{}"
                )
            except Exception:
                raw = {
                    "transcriptUrl": "",
                    "youtubeVideoId": episode.get("youtubeVideoId"),
                }
            video_id = episode.get("youtubeVideoId") or raw.get("youtubeVideoId")
            if not (raw.get("transcriptUrl") or video_id):
                # Nothing to try yet. no_transcript means "we looked and there
                # is none", so leave this episode alone for a later pass rather
                # than retiring it on the strength of a throttled discovery.
                LOGGER.info("transcripts %s no source yet", episode["id"])
                continue
            kind, cues = resolve_cues(
                {"transcriptUrl": raw.get("transcriptUrl"), "youtubeVideoId": video_id},
                client,
            )
            count += 1
            if dry_run:
                LOGGER.info(
                    "transcripts dry-run %s kind=%s cues=%s", episode["id"], kind, len(cues)
                )
                continue
            if not cues:
                api.set_episode_status(episode["id"], status="no_transcript", transcriptKind="none")
                continue
            api.put_raw(
                episode["id"],
                f"episodes/{episode['id']}/cues.json",
                json.dumps(cues),
                "application/json",
            )
            segments = cues_to_segments(cues)
            api.put_segments(episode["id"], segments, kind)
            api.set_episode_status(
                episode["id"],
                status="segmented",
                transcriptKind=kind,
                youtubeVideoId=video_id,
            )
    return count


def attach_person_ids(
    claims: list[dict[str, Any]], people_map: dict[str, str]
) -> list[dict[str, Any]]:
    out = []
    for claim in claims:
        person_id = people_map.get(str(claim["speakerRaw"]))
        if not person_id:
            continue
        row = dict(claim)
        row["personId"] = person_id
        out.append(row)
    return out


def _slice_segments(
    segments: list[dict[str, Any]], skip_segments: int, max_segments: int
) -> list[dict[str, Any]]:
    out = segments
    if skip_segments > 0:
        out = out[skip_segments:]
    if max_segments > 0:
        out = out[:max_segments]
    return out


def segment_action(segment: dict[str, Any], already: set[str], force: bool, focus: str) -> str:
    if not force and segment.get("id") in already:
        return "extracted"
    reason = triage_segment(str(segment.get("text") or ""))
    if focus == "recs" and reason != "rec":
        return "skip"
    return reason


def extract_one_segment(
    cfg: Settings,
    people_map: dict[str, str],
    segment: dict[str, Any],
    prev_tail: str,
    guests: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    accepted, rejected, run = extract_segment(cfg, segment["text"], prev_tail, guests)
    for claim in accepted:
        claim["segmentId"] = segment["id"]
        claim["pipelineVersion"] = cfg.pipeline_version
        # The model that answered, not the one we asked for.
        claim["model"] = run.get("model") or cfg.extract_model
        claim["promptVersion"] = cfg.prompt_version
    LOGGER.info(
        "segment %s accepted=%s rejected=%s",
        segment["idx"],
        len(accepted),
        len(rejected),
    )
    return attach_person_ids(accepted, people_map), run, len(accepted)


@dataclass
class ExtractOpts:
    episode_id: str | None
    dry_run: bool
    max_segments: int = 0
    skip_segments: int = 0
    force: bool = False
    focus: str = "all"


def _episode_guests(detail: dict[str, Any], people_map: dict[str, str]) -> list[str]:
    id_to_slug = {person_id: slug for slug, person_id in people_map.items()}
    return [
        id_to_slug[str(row["personId"])]
        for row in detail.get("people") or []
        if str(row.get("personId") or "") in id_to_slug
    ]


def _extract_episode(
    api: ApiClient,
    cfg: Settings,
    people_map: dict[str, str],
    episode: dict[str, Any],
    opts: ExtractOpts,
) -> tuple[int, int, int]:
    detail = api.get_episode(episode["id"])
    already = set(detail.get("extractedSegmentIds") or [])
    guests = _episode_guests(detail, people_map)
    segments = _slice_segments(
        list(detail.get("segments") or []), opts.skip_segments, opts.max_segments
    )
    extracted = 0
    llm_calls = 0
    skipped = 0
    prev_tail = ""
    for segment in segments:
        action = segment_action(segment, already, opts.force, opts.focus)
        if action in {"extracted", "skip"}:
            skipped += 1
            LOGGER.info("segment %s skip %s", segment["idx"], action)
            continue
        llm_calls += 1
        if opts.dry_run:
            LOGGER.info("segment %s keep=%s dry-run", segment["idx"], action)
            continue
        try:
            posted, run, n = extract_one_segment(cfg, people_map, segment, prev_tail, guests)
        except httpx.HTTPError as exc:
            LOGGER.warning("segment %s extract failed: %s", segment["idx"], exc)
            continue
        extracted += n
        prev_tail = str(segment["text"])[-300:]
        if posted or run:
            api.post_claims(episode["id"], posted, [run])
    LOGGER.info(
        "episode %s llm_calls=%s skipped=%s claims=%s",
        episode["id"],
        llm_calls,
        skipped,
        extracted,
    )
    return extracted, llm_calls, skipped


# An episode is only finished when its segments are, not when it first
# reaches `extracted`. Selecting on status alone stranded 185 of 250 segments
# in episodes that earlier runs had capped part way through.
EXTRACTABLE_STATUSES = ("segmented", "extracted", "published")


def _extract_targets(api: ApiClient, episode_id: str | None) -> list[dict[str, Any]]:
    episodes = [row for status in EXTRACTABLE_STATUSES for row in api.list_episodes(status=status)]
    if not episode_id:
        return episodes
    matched = [row for row in episodes if row["id"] == episode_id]
    if matched:
        return matched
    return [api.get_episode(episode_id)["episode"]]


def run_extract(
    api: ApiClient,
    cfg: Settings,
    people_map: dict[str, str],
    opts: ExtractOpts,
) -> int:
    if not cfg.ai_api_key and not opts.dry_run:
        raise SystemExit("AI_API_KEY is required for extract")
    extracted = 0
    for episode in _extract_targets(api, opts.episode_id):
        extracted += _extract_episode(api, cfg, people_map, episode, opts)[0]
    return extracted


RETIME_STATUSES = ("segmented", "extracted", "published")


def run_retime(api: ApiClient, episode_id: str | None, dry_run: bool) -> int:
    """Re-derive cue maps from stored captions and re-time existing claims.

    Claims written before segments carried cue maps were all pinned to the
    start of their segment. The captions are still in R2, so the exact moment
    is recoverable without re-running extraction.
    """
    if episode_id:
        episodes = [api.get_episode(episode_id)["episode"]]
    else:
        episodes = [row for status in RETIME_STATUSES for row in api.list_episodes(status=status)]
    moved = 0
    for episode in episodes:
        key = f"episodes/{episode['id']}/cues.json"
        try:
            cues = json.loads(api.get_raw(episode["id"], key=key).get("content") or "[]")
        except Exception as exc:
            LOGGER.warning("retime %s no cues: %s", episode["id"], exc)
            continue
        if not cues:
            continue
        segments = cues_to_segments(cues)
        if dry_run:
            LOGGER.info("retime dry-run %s segments=%s", episode["id"], len(segments))
            continue
        api.put_segments(episode["id"], segments, str(episode.get("transcriptKind") or "none"))
        result = api.retime(episode["id"])
        moved += int(result.get("moved") or 0)
        LOGGER.info(
            "retime %s claims=%s moved=%s", episode["id"], result.get("claims"), result.get("moved")
        )
    return moved


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="on-record-ingest")
    parser.add_argument("--stage", default="all", choices=["all", *STAGES])
    parser.add_argument("--show", default="")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--episode", default="")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-segments", type=int, default=0)
    parser.add_argument("--skip-segments", type=int, default=0)
    parser.add_argument("--focus", choices=["all", "recs"], default="all")
    args = parser.parse_args(argv)
    cfg = load_settings()
    api = ApiClient(cfg)
    try:
        people_map, show_map = ({}, {})
        if args.stage in {"all", "discover", "extract"}:
            people_map, show_map = (
                seed_roster(api)
                if not args.dry_run
                else (
                    {p["slug"]: p["slug"] for p in PEOPLE},
                    {s["slug"]: s["slug"] for s in SHOWS},
                )
            )
        discovered = 0
        if args.stage in {"all", "discover"}:
            shows = [show for show in SHOWS if not args.show or show["slug"] == args.show]
            for show in shows:
                show_id = show_map.get(show["slug"], "")
                try:
                    discovered += discover_show(
                        show, show_id, people_map, _since(args.days), api, cfg, args.dry_run
                    )
                except Exception as exc:
                    LOGGER.warning("discover %s failed: %s", show["slug"], exc)
        if args.stage == "retime":
            run_retime(api, args.episode or None, args.dry_run)
            return 0
        transcribed = 0
        if args.stage in {"all", "transcripts"}:
            transcribed = run_transcripts(api, args.episode or None, args.force, args.dry_run)
        extracted = 0
        if args.stage in {"all", "extract", "publish"}:
            extracted = run_extract(
                api,
                cfg,
                people_map,
                ExtractOpts(
                    dry_run=args.dry_run,
                    episode_id=args.episode or None,
                    focus=args.focus,
                    force=args.force,
                    max_segments=args.max_segments,
                    skip_segments=args.skip_segments,
                ),
            )
        if not args.dry_run:
            api.ingest_run(
                {
                    "stage": args.stage,
                    "showSlug": args.show or None,
                    "days": args.days,
                    "episodesDiscovered": discovered,
                    "transcriptsFound": transcribed,
                    "claimsExtracted": extracted,
                }
            )
        LOGGER.info(
            "done stage=%s discovered=%s transcribed=%s extracted=%s",
            args.stage,
            discovered,
            transcribed,
            extracted,
        )
    finally:
        api.close()
    return 0
