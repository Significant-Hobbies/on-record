from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .api_client import ApiClient
from .attributions import confidence_for, judge
from .config import Settings, settings as load_settings
from .extract.claims import extract_segment
from .extract.triage import triage_segment
from .identify import UNKNOWN, identify_speakers
from .match import guests_from_text, merge_video, video_id_from_metadata
from .seed.people import PEOPLE
from .seed.shows import SHOWS
from .seed.topics import TOPICS
from .segment import cues_to_segments
from .sources import podcast_index, rss_feed, youtube_rss
from .transcripts.rss_transcript import parse_transcript
from .transcripts.whisper_local import TranscriptionUnavailable
from .transcripts.whisper_local import transcribe as whisper_transcribe
from .transcripts.youtube_captions import fetch_cues

LOGGER = logging.getLogger("on_record_ingest")
STAGES = (
    "discover",
    "youtube-ids",
    "transcripts",
    "extract",
    "publish",
    "retime",
    "identify",
    "attributions",
)


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def load_roster(api: ApiClient) -> dict[str, str]:
    """slug -> id for people already seeded.

    Extraction only needs the mapping. Re-upserting 1,255 people first meant
    ~2,500 D1 round-trips before a single claim was read.
    """
    return {str(p["slug"]): str(p["id"]) for p in api.list_people()}


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
            "youtubeVideoId": item.get("youtubeVideoId")
            or video_id_from_metadata(item.get("description"), item.get("sourceUrl")),
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
    item: dict[str, Any], client: httpx.Client, whisper: bool = False, speakers: int = 0
) -> tuple[str, list[dict[str, float | str]]]:
    """Publisher transcript, then YouTube captions, then our own ears.

    Whisper is last because it is the only step that costs real time, and it
    is opt-in because it only works where the machine can run it.
    """
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
    audio_url = str(item.get("audioUrl") or "")
    if whisper and audio_url:
        cues = whisper_transcribe(audio_url, client, speakers)
        if cues:
            return "whisper_local", cues
    return "none", []


def episode_roster(api: ApiClient, episode_id: str) -> list[dict[str, str]]:
    detail = api.get_episode(episode_id)
    people = {p["id"]: p for p in api.list_people()}
    out: list[dict[str, str]] = []
    for row in detail.get("people") or []:
        person = people.get(str(row.get("personId")))
        if person:
            out.append(
                {
                    "slug": str(person["slug"]),
                    "name": str(person["name"]),
                    "role": str(row.get("role") or "guest"),
                }
            )
    return out


def resolve_segment_speakers(
    api: ApiClient, cfg: Settings, episode: dict[str, Any], segments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Turn diarized labels into people, or into nothing.

    speakerHint carries a label like "B" out of diarization. From here it
    carries a roster slug, so extraction reads who is talking instead of
    guessing. A voice we cannot place is left unset and its claims stay
    unpublishable.
    """
    if not any(segment.get("diarLabel") or segment.get("speakerHint") for segment in segments):
        return segments
    for segment in segments:
        segment.setdefault("diarLabel", segment.get("speakerHint"))
    roster = episode_roster(api, episode["id"])
    mapping = identify_speakers(
        cfg,
        segments,
        roster,
        str(episode.get("title") or ""),
        str(episode.get("description") or ""),
    )
    for segment in segments:
        label = segment.get("diarLabel")
        slug = mapping.get(str(label)) if label else None
        segment["speakerHint"] = None if not slug or slug == UNKNOWN else slug
    return segments


def discovery_payload(api: ApiClient, episode: dict[str, Any]) -> dict[str, Any]:
    """What discovery saved for this episode, or enough of a stand-in."""
    try:
        content = api.get_raw(episode["id"], key=f"episodes/{episode['id']}/discover.json").get(
            "content"
        )
        return json.loads(content or "{}")
    except Exception:
        return {"transcriptUrl": "", "youtubeVideoId": episode.get("youtubeVideoId")}


def expected_speakers(api: ApiClient, episode_id: str) -> int:
    """Voices to expect: everyone attached, plus one for whoever we missed."""
    return 1 + len(api.get_episode(episode_id).get("people") or [])


def run_transcripts(
    api: ApiClient,
    episode_id: str | None,
    force: bool,
    dry_run: bool,
    whisper: bool = False,
    cfg: Settings | None = None,
) -> int:
    episodes = api.list_episodes(status=None if force else "discovered")
    if episode_id:
        episodes = [row for row in episodes if row["id"] == episode_id]
    count = 0
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for episode in episodes:
            if episode.get("status") == "no_transcript" and not force:
                continue
            raw = discovery_payload(api, episode)
            video_id = episode.get("youtubeVideoId") or raw.get("youtubeVideoId")
            audio_url = episode.get("audioUrl") or raw.get("audioUrl")
            if not (raw.get("transcriptUrl") or video_id or (whisper and audio_url)):
                # Nothing to try yet. no_transcript means "we looked and there
                # is none", so leave this episode alone for a later pass rather
                # than retiring it on the strength of a throttled discovery.
                LOGGER.info("transcripts %s no source yet", episode["id"])
                continue
            try:
                kind, cues = resolve_cues(
                    {
                        "transcriptUrl": raw.get("transcriptUrl"),
                        "youtubeVideoId": video_id,
                        "audioUrl": audio_url,
                    },
                    client,
                    whisper,
                    expected_speakers(api, episode["id"]),
                )
            except TranscriptionUnavailable as exc:
                LOGGER.warning("episode %s left for a later pass: %s", episode["id"], exc)
                continue
            count += 1
            if dry_run:
                LOGGER.info(
                    "transcripts dry-run %s kind=%s cues=%s", episode["id"], kind, len(cues)
                )
                continue
            if not cues:
                # Only retire the episode when we actually looked and found
                # nothing. A stalled download is not evidence of absence.
                api.set_episode_status(episode["id"], status="no_transcript", transcriptKind="none")
                continue
            store_transcript(api, cfg, episode, cues, kind, video_id)
    return count


def store_transcript(
    api: ApiClient,
    cfg: Settings | None,
    episode: dict[str, Any],
    cues: list[dict[str, float | str]],
    kind: str,
    video_id: str | None,
) -> None:
    api.put_raw(
        episode["id"],
        f"episodes/{episode['id']}/cues.json",
        json.dumps(cues),
        "application/json",
    )
    segments = cues_to_segments(cues)
    if cfg:
        segments = resolve_segment_speakers(api, cfg, episode, segments)
    api.put_segments(episode["id"], segments, kind)
    api.set_episode_status(
        episode["id"], status="segmented", transcriptKind=kind, youtubeVideoId=video_id
    )


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
    # A diarized segment already knows whose voice it is. Offering the model
    # one name stops it choosing between several and calling the choice 0.9.
    known = segment.get("speakerHint")
    roster = [str(known)] if known else guests
    accepted, rejected, run = extract_segment(cfg, segment["text"], prev_tail, roster)
    if known:
        for claim in accepted:
            claim["speakerRaw"] = str(known)
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


# Below this, a person was judged to be merely mentioned rather than present.
# They must not reach the extractor: a name on the roster is a name it is
# allowed to put quotes into the mouth of.
GUEST_CONFIDENCE_FLOOR = 0.5


def _episode_guests(detail: dict[str, Any], people_map: dict[str, str]) -> list[str]:
    id_to_slug = {person_id: slug for slug, person_id in people_map.items()}
    return [
        id_to_slug[str(row["personId"])]
        for row in detail.get("people") or []
        if str(row.get("personId") or "") in id_to_slug
        and float(row.get("confidence") or 1.0) >= GUEST_CONFIDENCE_FLOOR
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
    if not guests:
        # Nobody identifiable is on this episode, so every claim would be
        # attributed to "unknown" and never published. Skip before spending.
        LOGGER.info("episode %s skipped: no identifiable speaker", episode["id"])
        return 0, 0, 0
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


def run_youtube_ids(api: ApiClient, limit: int = 0) -> int:
    """Recover video ids already linked in metadata we hold.

    Nothing is fetched: the links sit in descriptions and episode URLs saved at
    discovery. They matter because a claim's deep link is built from the video
    id, and without one a quote cannot be checked by clicking.
    """
    found = 0
    for episode in api.list_episodes():
        if episode.get("youtubeVideoId"):
            continue
        video_id = video_id_from_metadata(episode.get("description"), episode.get("sourceUrl"))
        if not video_id:
            continue
        api.set_episode_status(
            episode["id"],
            status=str(episode.get("status") or "discovered"),
            youtubeVideoId=video_id,
        )
        found += 1
        if limit and found >= limit:
            break
    LOGGER.info("youtube ids recovered: %s", found)
    return found


def run_attributions(
    api: ApiClient, cfg: Settings, episode_id: str | None, limit: int = 0
) -> dict[str, int]:
    """Ask a small local model whether each named person is really on the episode.

    Half of metadata matches are people the blurb merely mentions, and a false
    guest is worse than a missing one: it becomes a name the extractor may
    attribute quotes to.
    """
    people = {p["id"]: p["name"] for p in api.list_people()}
    episodes = [api.get_episode(episode_id)["episode"]] if episode_id else api.list_episodes()
    tally = {"appears": 0, "mentioned": 0, "undecided": 0}
    judged = 0
    with httpx.Client() as client:
        for episode in episodes:
            detail = api.get_episode(episode["id"])
            rows = [r for r in detail.get("people") or [] if r.get("role") == "guest"]
            if not rows:
                continue
            updates = []
            for row in rows:
                if limit and judged >= limit:
                    break
                name = people.get(str(row.get("personId")))
                if not name:
                    continue
                judged += 1
                verdict = judge(
                    client,
                    cfg.ai_base_url,
                    cfg.attribution_model,
                    name,
                    str(episode.get("title") or ""),
                    str(episode.get("description") or ""),
                )
                confidence = confidence_for(verdict, name, str(episode.get("title") or ""))
                if confidence is None:
                    tally["undecided"] += 1
                    continue
                tally["appears" if confidence > 0.5 else "mentioned"] += 1
                updates.append(
                    {
                        "personId": str(row["personId"]),
                        "confidence": confidence,
                        "attributionSource": "llm",
                    }
                )
            if updates:
                api.set_episode_people(episode["id"], updates)
            if limit and judged >= limit:
                break
    LOGGER.info("attributions %s", tally)
    return tally


def run_identify(api: ApiClient, cfg: Settings, episode_id: str | None) -> int:
    """Redo speaker identification on stored segments.

    Transcribing again costs minutes of audio processing for a decision that
    only reads text, so naming the voices is separately re-runnable.
    """
    episodes = (
        [api.get_episode(episode_id)["episode"]]
        if episode_id
        else [row for s in RETIME_STATUSES for row in api.list_episodes(status=s)]
    )
    named = 0
    for episode in episodes:
        detail = api.get_episode(episode["id"])
        segments = list(detail.get("segments") or [])
        if not segments:
            continue
        resolved = resolve_segment_speakers(api, cfg, episode, segments)
        api.put_segments(episode["id"], resolved, str(episode.get("transcriptKind") or "none"))
        named += sum(1 for s in resolved if s.get("speakerHint"))
    return named


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


def seed_maps_for_stage(
    api: ApiClient, stage: str, dry_run: bool
) -> tuple[dict[str, str], dict[str, str]]:
    if stage not in {"all", "discover", "extract"}:
        return {}, {}
    if not dry_run:
        return seed_roster(api)
    return (
        {person["slug"]: person["slug"] for person in PEOPLE},
        {show["slug"]: show["slug"] for show in SHOWS},
    )


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
    parser.add_argument("--limit", type=int, default=0, help="cap how many items a stage handles")
    parser.add_argument("--focus", choices=["all", "recs"], default="all")
    parser.add_argument(
        "--whisper",
        action="store_true",
        help="transcribe audio locally when no caption source exists",
    )
    args = parser.parse_args(argv)
    cfg = load_settings()
    api = ApiClient(cfg)
    try:
        people_map, show_map = seed_maps_for_stage(api, args.stage, args.dry_run)
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
        if args.stage == "youtube-ids":
            run_youtube_ids(api, args.limit)
            return 0
        if args.stage == "attributions":
            run_attributions(api, cfg, args.episode or None, args.limit)
            return 0
        if args.stage == "identify":
            run_identify(api, cfg, args.episode or None)
            return 0
        if args.stage == "retime":
            run_retime(api, args.episode or None, args.dry_run)
            return 0
        transcribed = 0
        if args.stage in {"all", "transcripts"}:
            transcribed = run_transcripts(
                api, args.episode or None, args.force, args.dry_run, args.whisper, cfg
            )
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
