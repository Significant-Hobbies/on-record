from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .api_client import ApiClient
from .config import Settings, settings as load_settings
from .extract.claims import extract_segment
from .match import guests_from_text, merge_video
from .seed.people import PEOPLE
from .seed.shows import SHOWS
from .seed.topics import TOPICS
from .segment import cues_to_segments
from .sources import podcast_index, rss_feed, youtube_rss
from .transcripts.rss_transcript import parse_transcript
from .transcripts.youtube_captions import fetch_cues

LOGGER = logging.getLogger("on_record_ingest")
STAGES = ("discover", "transcripts", "extract", "publish")


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
    for item in by_guid.values():
        blob = json.dumps(item)
        people = remap_people(
            guests_from_text(f"{item.get('title', '')} {item.get('description', '')}"),
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
                raw = json.loads(api.get_raw(episode["id"]).get("content") or "{}")
            except Exception:
                raw = {
                    "transcriptUrl": "",
                    "youtubeVideoId": episode.get("youtubeVideoId"),
                }
            kind, cues = resolve_cues(
                {
                    "transcriptUrl": raw.get("transcriptUrl"),
                    "youtubeVideoId": episode.get("youtubeVideoId") or raw.get("youtubeVideoId"),
                },
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
                youtubeVideoId=episode.get("youtubeVideoId") or raw.get("youtubeVideoId"),
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


def run_extract(
    api: ApiClient,
    cfg: Settings,
    people_map: dict[str, str],
    episode_id: str | None,
    dry_run: bool,
    max_segments: int = 0,
) -> int:
    if not cfg.ai_api_key and not dry_run:
        raise SystemExit("AI_API_KEY is required for extract")
    episodes = api.list_episodes(status="segmented")
    if episode_id:
        episodes = [row for row in episodes if row["id"] == episode_id]
        if not episodes:
            detail = api.get_episode(episode_id)
            episodes = [detail["episode"]]
    extracted = 0
    for episode in episodes:
        detail = api.get_episode(episode["id"])
        prev_tail = ""
        all_claims: list[dict[str, Any]] = []
        runs: list[dict[str, Any]] = []
        segments = list(detail.get("segments") or [])
        if max_segments > 0:
            segments = segments[:max_segments]
        for segment in segments:
            if dry_run and not cfg.ai_api_key:
                LOGGER.info("extract dry-run skip llm segment %s", segment["idx"])
                continue
            accepted, rejected, run = extract_segment(cfg, segment["text"], prev_tail)
            for claim in accepted:
                claim["segmentId"] = segment["id"]
                claim["pipelineVersion"] = cfg.pipeline_version
                claim["model"] = cfg.extract_model
                claim["promptVersion"] = cfg.prompt_version
            all_claims.extend(attach_person_ids(accepted, people_map))
            runs.append(run)
            extracted += len(accepted)
            LOGGER.info(
                "segment %s accepted=%s rejected=%s",
                segment["idx"],
                len(accepted),
                len(rejected),
            )
            prev_tail = str(segment["text"])[-300:]
        if dry_run:
            LOGGER.info("extract dry-run episode=%s claims=%s", episode["id"], len(all_claims))
            continue
        if all_claims or runs:
            api.post_claims(episode["id"], all_claims, runs)
    return extracted


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
                discovered += discover_show(
                    show, show_id, people_map, _since(args.days), api, cfg, args.dry_run
                )
        transcribed = 0
        if args.stage in {"all", "transcripts"}:
            transcribed = run_transcripts(api, args.episode or None, args.force, args.dry_run)
        extracted = 0
        if args.stage in {"all", "extract", "publish"}:
            extracted = run_extract(
                api,
                cfg,
                people_map,
                args.episode or None,
                args.dry_run,
                args.max_segments,
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
