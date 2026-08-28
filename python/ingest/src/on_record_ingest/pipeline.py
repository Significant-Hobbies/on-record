from __future__ import annotations

import argparse
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .api_client import ApiClient
from .attributions import confidence_for, judge
from .config import Settings
from .config import settings as load_settings
from .extract.claims import BATCH_PROMPT_VERSION, extract_segment, extract_segments_batch, is_local
from .extract.triage import claim_candidate_score, triage_segment
from .guest_recovery import explicit_guest_names
from .identify import UNKNOWN, identify_speakers
from .match import guests_from_text, merge_discovery_items, merge_video, video_id_from_source_url
from .roster import slugify
from .seed.people import PEOPLE
from .seed.shows import SHOWS
from .seed.topics import TOPICS
from .segment import cues_to_segments
from .speaker_recovery import recover_self_identified_speakers
from .sources import podcast_index, rss_feed, youtube_api, youtube_rss
from .transcripts.acquired import TRANSCRIPT_KIND as ACQUIRED_PUBLISHER_HTML
from .transcripts.acquired import (
    PublisherSourceUnavailable as AcquiredPublisherSourceUnavailable,
)
from .transcripts.acquired import episode_url_from_source as acquired_episode_url_from_source
from .transcripts.acquired import fetch_cues as fetch_acquired_cues
from .transcripts.acquired import is_acquired_site_url
from .transcripts.conversations_with_tyler import TRANSCRIPT_KIND as CWT_PUBLISHER_HTML
from .transcripts.conversations_with_tyler import (
    PublisherSourceUnavailable as CwtPublisherSourceUnavailable,
)
from .transcripts.conversations_with_tyler import fetch_cues as fetch_cwt_cues
from .transcripts.conversations_with_tyler import is_cwt_url
from .transcripts.conversations_with_tyler import (
    transcript_url_from_metadata as cwt_transcript_url_from_metadata,
)
from .transcripts.lennys import TRANSCRIPT_KIND as LENNYS_PUBLISHER_JSON
from .transcripts.lennys import (
    PublisherSourceUnavailable as LennyPublisherSourceUnavailable,
)
from .transcripts.lennys import fetch_cues as fetch_lennys_cues
from .transcripts.lennys import is_lennys_url
from .transcripts.lex_fridman import TRANSCRIPT_KIND as PUBLISHER_HTML
from .transcripts.lex_fridman import (
    PublisherSourceUnavailable,
    is_lex_url,
    transcript_url_from_metadata,
    youtube_video_id,
)
from .transcripts.lex_fridman import fetch_cues as fetch_lex_cues
from .transcripts.rss_transcript import parse_transcript
from .transcripts.whisper_local import TranscriptionUnavailable
from .transcripts.whisper_local import transcribe as whisper_transcribe
from .transcripts.youtube_captions import CaptionSourceUnavailable, fetch_cues

LOGGER = logging.getLogger("on_record_ingest")
RESOLVED_TRANSCRIPT_KINDS = {
    ACQUIRED_PUBLISHER_HTML,
    CWT_PUBLISHER_HTML,
    LENNYS_PUBLISHER_JSON,
    PUBLISHER_HTML,
    "rss_named_text",
}
# Below this, a person was judged to be merely mentioned rather than present.
# They must not reach either speaker identification or extraction.
GUEST_CONFIDENCE_FLOOR = 0.5
STAGES = (
    "discover",
    "youtube-ids",
    "youtube-api",
    "youtube-verify",
    "transcripts",
    "extract",
    "publish",
    "retime",
    "identify",
    "attributions",
    "recover-speakers",
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
    hosts = host_people(show)
    include_unmatched_videos = not rss_items or bool(show.get("includeUnmatchedYoutube"))
    for item in merge_discovery_items(
        rss_items,
        videos,
        include_unmatched_videos=include_unmatched_videos,
    ):
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
            or video_id_from_source_url(item.get("sourceUrl")),
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


def structured_transcript_cues(
    transcript_url: str, client: httpx.Client
) -> tuple[str, list[dict[str, float | str]]] | None:
    if not transcript_url or is_cwt_url(transcript_url) or is_lex_url(transcript_url):
        return None
    try:
        response = client.get(transcript_url, timeout=30.0, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise PublisherSourceUnavailable(type(exc).__name__) from exc
    if response.status_code in {404, 410}:
        return None
    if response.status_code != 200:
        raise PublisherSourceUnavailable(f"HTTP {response.status_code}")
    if not response.text.strip():
        raise PublisherSourceUnavailable("structured transcript was empty")
    kind, cues = parse_transcript(response.text, response.headers.get("content-type", ""))
    if not cues:
        raise PublisherSourceUnavailable("structured transcript contained no usable cues")
    return kind, cues


def lex_transcript_cues(
    item: dict[str, Any], client: httpx.Client
) -> tuple[str, list[dict[str, float | str]]] | None:
    transcript_url = str(item.get("transcriptUrl") or "")
    source_url = str(item.get("sourceUrl") or "")
    episode_title = str(item.get("title") or "")
    if is_lex_url(source_url):
        cues = fetch_lex_cues(source_url, client, episode_title)
        if cues:
            return PUBLISHER_HTML, cues
    publisher_url = transcript_url_from_metadata(
        str(item.get("publisherTranscriptUrl") or ""),
        transcript_url,
        str(item.get("description") or ""),
        episode_title=episode_title,
    )
    if publisher_url:
        cues = fetch_lex_cues(publisher_url, client, episode_title)
        if cues:
            return PUBLISHER_HTML, cues
    return None


def _publisher_label_key(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _publisher_aliases(
    detail: dict[str, Any],
    people_by_id: dict[str, dict[str, Any]],
    *,
    include_first: bool = False,
    include_initials: bool = False,
) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for row in detail.get("people") or []:
        if float(row.get("confidence") or 1.0) < GUEST_CONFIDENCE_FLOOR:
            continue
        person = people_by_id.get(str(row.get("personId")))
        if not person:
            continue
        slug = str(person["slug"])
        parts = _publisher_label_key(str(person["name"])).split()
        keys = {" ".join(parts)}
        if len(parts) >= 2:
            keys.add(parts[-1])
            if include_first:
                keys.add(parts[0])
            if include_initials:
                keys.add("".join(part[0] for part in parts))
        for key in keys:
            aliases.setdefault(key, set()).add(slug)
    return aliases


def cwt_speaker_map(
    detail: dict[str, Any], people_by_id: dict[str, dict[str, Any]]
) -> dict[str, str]:
    """Map only unique publisher labels onto the reviewed episode roster."""
    aliases = _publisher_aliases(detail, people_by_id)
    if any("tyler-cowen" in slugs for slugs in aliases.values()):
        for key in {"cowen", "t cowen", "tyler", "tyler cowen"}:
            aliases.setdefault(key, set()).add("tyler-cowen")
    return {key: next(iter(slugs)) for key, slugs in aliases.items() if len(slugs) == 1}


def acquired_speaker_map(
    detail: dict[str, Any], people_by_id: dict[str, dict[str, Any]]
) -> dict[str, str]:
    """Resolve full, first, and last publisher labels only when unique."""
    aliases = _publisher_aliases(detail, people_by_id, include_first=True, include_initials=True)
    resolved = {key: next(iter(slugs)) for key, slugs in aliases.items() if len(slugs) == 1}
    available_slugs = {str(person["slug"]) for person in people_by_id.values()}
    if "ben-gilbert" in available_slugs:
        resolved["ben"] = "ben-gilbert"
    if "david-rosenthal" in available_slugs:
        resolved["david"] = "david-rosenthal"
    return resolved


def lennys_speaker_map(
    detail: dict[str, Any], people_by_id: dict[str, dict[str, Any]]
) -> dict[str, str]:
    """Resolve publisher full or unique short names onto the episode roster."""
    aliases = _publisher_aliases(detail, people_by_id, include_first=True)
    resolved = {key: next(iter(slugs)) for key, slugs in aliases.items() if len(slugs) == 1}
    if any("lenny-rachitsky" in slugs for slugs in aliases.values()):
        resolved["lenny"] = "lenny-rachitsky"
        # One approved publisher map truncates the host label to "Lenn" while
        # also labelling other turns as "Lenny" in the same episode.
        resolved["lenn"] = "lenny-rachitsky"
    return resolved


def lennys_transcript_cues(
    item: dict[str, Any], client: httpx.Client
) -> tuple[str, list[dict[str, float | str]]] | None:
    source_url = str(item.get("sourceUrl") or "")
    if not is_lennys_url(source_url):
        return None
    cues = fetch_lennys_cues(
        source_url,
        client,
        str(item.get("title") or ""),
        str(item.get("guid") or ""),
        dict(item.get("lennysSpeakerMap") or {}),
    )
    return (LENNYS_PUBLISHER_JSON, cues) if cues else None


def acquired_transcript_cues(
    item: dict[str, Any], client: httpx.Client
) -> tuple[str, list[dict[str, float | str]]] | None:
    source_url = str(item.get("sourceUrl") or "")
    publisher_url = acquired_episode_url_from_source(
        source_url, str(item.get("title") or ""), client
    )
    if not publisher_url:
        return None
    cues = fetch_acquired_cues(
        publisher_url,
        client,
        str(item.get("title") or ""),
        dict(item.get("acquiredSpeakerMap") or {}),
    )
    return (ACQUIRED_PUBLISHER_HTML, cues) if cues else None


def cwt_transcript_cues(
    item: dict[str, Any], client: httpx.Client
) -> tuple[str, list[dict[str, float | str]]] | None:
    candidates = [
        str(item.get("sourceUrl") or ""),
        str(item.get("cwtPublisherTranscriptUrl") or ""),
    ]
    tried: set[str] = set()
    for source_url in candidates:
        if not is_cwt_url(source_url) or source_url in tried:
            continue
        tried.add(source_url)
        cues = fetch_cwt_cues(
            source_url,
            client,
            str(item.get("title") or ""),
            dict(item.get("cwtSpeakerMap") or {}),
        )
        if cues:
            return CWT_PUBLISHER_HTML, cues
    return None


def resolve_cues(
    item: dict[str, Any], client: httpx.Client, whisper: bool = False, speakers: int = 0
) -> tuple[str, list[dict[str, float | str]]]:
    """Publisher transcript, then YouTube captions, then our own ears.

    Whisper is last because it is the only step that costs real time, and it
    is opt-in because it only works where the machine can run it.
    """
    resolved = lennys_transcript_cues(item, client)
    if resolved:
        return resolved
    resolved = acquired_transcript_cues(item, client)
    if resolved:
        return resolved
    resolved = cwt_transcript_cues(item, client)
    if resolved:
        return resolved
    resolved = lex_transcript_cues(item, client)
    if resolved:
        return resolved
    resolved = structured_transcript_cues(str(item.get("transcriptUrl") or ""), client)
    if resolved:
        return resolved
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
        if float(row.get("confidence") or 1.0) < GUEST_CONFIDENCE_FLOOR:
            continue
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
    """Turn diarized labels into people, or explicit unknowns.

    speakerHint carries a label like "B" out of diarization. From here it
    carries a roster slug, so extraction reads who is talking instead of
    guessing. A voice we cannot place is marked unknown and its claims stay
    unpublishable.
    """
    if episode.get("transcriptKind") in RESOLVED_TRANSCRIPT_KINDS:
        return segments
    if not any(segment.get("diarLabel") or segment.get("speakerHint") for segment in segments):
        for segment in segments:
            segment["speakerHint"] = UNKNOWN
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
        segment["speakerHint"] = UNKNOWN if not slug or slug == UNKNOWN else slug
    return segments


def discovery_payload(api: ApiClient, episode: dict[str, Any]) -> dict[str, Any]:
    """What discovery saved for this episode, or enough of a stand-in."""
    try:
        content = api.get_raw(episode["id"], key=f"episodes/{episode['id']}/discover.json").get(
            "content"
        )
        return json.loads(content or "{}")
    except Exception:
        return {
            "audioUrl": episode.get("audioUrl"),
            "sourceUrl": episode.get("sourceUrl"),
            "transcriptUrl": "",
            "youtubeVideoId": episode.get("youtubeVideoId"),
        }


def publisher_video_id(cues: list[dict[str, float | str]]) -> str | None:
    for cue in cues:
        found = youtube_video_id(str(cue.get("sourceUrl") or ""))
        if found:
            return found
    return None


def transcript_source_available(
    raw: dict[str, Any],
    publisher_url: Any,
    cwt_publisher_url: Any,
    source_url: Any,
    video_id: Any,
    audio_url: Any,
    whisper: bool,
) -> bool:
    return any(
        (
            raw.get("transcriptUrl"),
            publisher_url,
            cwt_publisher_url,
            is_acquired_site_url(str(source_url or "")),
            is_cwt_url(str(source_url or "")),
            is_lennys_url(str(source_url or "")),
            is_lex_url(str(source_url or "")),
            video_id,
            whisper and audio_url,
        )
    )


def transcript_request(
    api: ApiClient,
    episode: dict[str, Any],
    raw: dict[str, Any],
    people_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    publisher_url = transcript_url_from_metadata(
        str(raw.get("description") or ""),
        str(episode.get("description") or ""),
        str(raw.get("transcriptUrl") or ""),
        episode_title=str(episode.get("title") or ""),
    )
    cwt_publisher_url = cwt_transcript_url_from_metadata(
        str(raw.get("description") or ""),
        str(episode.get("description") or ""),
        str(raw.get("transcriptUrl") or ""),
        episode_title=str(episode.get("title") or ""),
        allow_title_override=is_cwt_url(
            str(episode.get("sourceUrl") or raw.get("sourceUrl") or "")
        ),
    )
    detail = api.get_episode(episode["id"])
    return {
        "acquiredSpeakerMap": acquired_speaker_map(detail, people_by_id or {}),
        "cwtPublisherTranscriptUrl": cwt_publisher_url,
        "cwtSpeakerMap": cwt_speaker_map(detail, people_by_id or {}),
        "description": raw.get("description") or episode.get("description"),
        "guid": episode.get("guid") or raw.get("guid"),
        "lennysSpeakerMap": lennys_speaker_map(detail, people_by_id or {}),
        "publisherTranscriptUrl": publisher_url,
        "sourceUrl": episode.get("sourceUrl") or raw.get("sourceUrl"),
        "title": episode.get("title"),
        "transcriptUrl": raw.get("transcriptUrl"),
        "youtubeVideoId": episode.get("youtubeVideoId") or raw.get("youtubeVideoId"),
        "audioUrl": episode.get("audioUrl") or raw.get("audioUrl"),
        "speakers": 1 + len(detail.get("people") or []),
    }


def transcript_video_id(kind: str, cues: list[dict[str, float | str]], existing: Any) -> str | None:
    publisher_id = publisher_video_id(cues)
    if kind == PUBLISHER_HTML and publisher_id:
        return publisher_id
    found = existing or publisher_id
    return str(found) if found else None


@dataclass(frozen=True)
class TranscriptOpts:
    dry_run: bool
    force: bool
    whisper: bool


def run_transcript_episode(
    api: ApiClient,
    cfg: Settings | None,
    episode: dict[str, Any],
    client: httpx.Client,
    opts: TranscriptOpts,
    people_by_id: dict[str, dict[str, Any]] | None = None,
) -> bool:
    if episode.get("status") == "no_transcript" and not opts.force:
        return False
    raw = discovery_payload(api, episode)
    request = transcript_request(api, episode, raw, people_by_id)
    if not transcript_source_available(
        raw,
        request["publisherTranscriptUrl"],
        request["cwtPublisherTranscriptUrl"],
        request["sourceUrl"],
        request["youtubeVideoId"],
        request["audioUrl"],
        opts.whisper,
    ):
        # Nothing to try yet. no_transcript means "we looked and there
        # is none", so leave this episode alone for a later pass rather
        # than retiring it on the strength of a throttled discovery.
        LOGGER.debug("transcripts %s no source yet", episode["id"])
        return False
    try:
        kind, cues = resolve_cues(request, client, opts.whisper, int(request["speakers"]))
    except (
        CaptionSourceUnavailable,
        AcquiredPublisherSourceUnavailable,
        CwtPublisherSourceUnavailable,
        LennyPublisherSourceUnavailable,
        PublisherSourceUnavailable,
        TranscriptionUnavailable,
    ) as exc:
        LOGGER.warning("episode %s left for a later pass: %s", episode["id"], exc)
        return False
    if opts.dry_run:
        LOGGER.info("transcripts dry-run %s kind=%s cues=%s", episode["id"], kind, len(cues))
        return True
    if not cues:
        # Only retire the episode when we actually looked and found nothing. A
        # stalled download is not evidence of absence.
        api.set_episode_status(episode["id"], status="no_transcript", transcriptKind="none")
        return True
    video_id = transcript_video_id(kind, cues, request["youtubeVideoId"])
    store_transcript(api, cfg, episode, cues, kind, video_id)
    return True


def run_transcripts(
    api: ApiClient,
    episode_id: str | None,
    force: bool,
    dry_run: bool,
    whisper: bool = False,
    cfg: Settings | None = None,
    show_id: str | None = None,
) -> int:
    if episode_id:
        episode = api.get_episode(episode_id)["episode"]
        episodes = [episode] if force or episode.get("status") == "discovered" else []
    else:
        list_kwargs = {"show_id": show_id} if show_id else {}
        episodes = api.list_episodes(status=None if force else "discovered", **list_kwargs)
    people_by_id: dict[str, dict[str, Any]] = {}
    if any(
        is_acquired_site_url(str(episode.get("sourceUrl") or ""))
        or is_cwt_url(str(episode.get("sourceUrl") or ""))
        or is_lennys_url(str(episode.get("sourceUrl") or ""))
        for episode in episodes
    ):
        people_by_id = {str(person["id"]): person for person in api.list_people()}
    count = 0
    opts = TranscriptOpts(dry_run=dry_run, force=force, whisper=whisper)
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for episode in episodes:
            count += int(run_transcript_episode(api, cfg, episode, client, opts, people_by_id))
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
    speakers_resolved = kind in RESOLVED_TRANSCRIPT_KINDS
    segments = cues_to_segments(cues, speakers_resolved=speakers_resolved)
    if not speakers_resolved:
        if cfg and (cfg.ai_api_key or is_local(cfg)):
            segments = resolve_segment_speakers(api, cfg, episode, segments)
        else:
            # Generic captions and transcript labels are not identities. If
            # no identification model is available, make every segment
            # explicitly unpublishable instead of letting extraction guess.
            for segment in segments:
                segment.setdefault("diarLabel", segment.get("speakerHint"))
                segment["speakerHint"] = UNKNOWN
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


def segment_action(
    segment: dict[str, Any],
    already: set[str],
    attempted: set[tuple[str, str, str]],
    force: bool,
    focus: str,
    prompt_version: str,
) -> str:
    if not force and segment.get("id") in already:
        return "extracted"
    attempt = (str(segment.get("id") or ""), prompt_version, focus)
    if not force and attempt in attempted:
        return "attempted"
    if segment.get("speakerHint") == UNKNOWN:
        return "skip"
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
    focus: str = "all",
) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    # A diarized segment already knows whose voice it is. Offering the model
    # one name stops it choosing between several and calling the choice 0.9.
    known = segment.get("speakerHint")
    roster = [str(known)] if known else guests
    accepted, rejected, run = extract_segment(cfg, segment["text"], prev_tail, roster, focus)
    if known:
        for claim in accepted:
            claim["speakerRaw"] = str(known)
    for claim in accepted:
        claim["segmentId"] = segment["id"]
        claim["pipelineVersion"] = cfg.pipeline_version
        # The model that answered, not the one we asked for.
        claim["model"] = run.get("model") or cfg.extract_model
        claim["promptVersion"] = cfg.prompt_version
    run["focus"] = focus
    run["segmentId"] = segment["id"]
    LOGGER.info(
        "segment %s accepted=%s rejected=%s",
        segment["idx"],
        len(accepted),
        len(rejected),
    )
    return attach_person_ids(accepted, people_map), run, len(accepted)


def claims_for_focus(claims: list[dict[str, Any]], focus: str) -> list[dict[str, Any]]:
    """A recommendations run persists only claims with surviving evidence."""
    if focus != "recs":
        return claims
    return [claim for claim in claims if claim.get("references")]


@dataclass
class ExtractOpts:
    episode_id: str | None
    dry_run: bool
    show_id: str | None = None
    max_segments: int = 0
    skip_segments: int = 0
    force: bool = False
    focus: str = "all"
    limit: int = 0
    batch_size: int = 0
    target_claims: int = 10


@dataclass
class EpisodeExtractContext:
    api: ApiClient
    cfg: Settings
    people_map: dict[str, str]
    episode: dict[str, Any]
    opts: ExtractOpts
    prompt_version: str
    already: set[str]
    attempted: set[tuple[str, str, str]]
    guests: list[str]
    published_claims: int


def _episode_guests(detail: dict[str, Any], people_map: dict[str, str]) -> list[str]:
    id_to_slug = {person_id: slug for slug, person_id in people_map.items()}
    return [
        id_to_slug[str(row["personId"])]
        for row in detail.get("people") or []
        if str(row.get("personId") or "") in id_to_slug
        and float(row.get("confidence") or 1.0) >= GUEST_CONFIDENCE_FLOOR
    ]


def extract_one_batch(
    cfg: Settings,
    people_map: dict[str, str],
    segments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    accepted, rejected, run = extract_segments_batch(cfg, segments)
    for claim in accepted:
        claim["pipelineVersion"] = cfg.pipeline_version
        claim["model"] = run.get("model") or cfg.extract_model
        claim["promptVersion"] = BATCH_PROMPT_VERSION
    LOGGER.info(
        "batch segments=%s accepted=%s rejected=%s",
        len(segments),
        len(accepted),
        len(rejected),
    )
    return attach_person_ids(accepted, people_map), run


def claims_are_near_duplicates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    def words(claim: dict[str, Any]) -> set[str]:
        return {
            word
            for word in re.findall(r"[a-z0-9]+", str(claim.get("quote") or "").lower())
            if len(word) > 2
        }

    left_words = words(left)
    right_words = words(right)
    if not left_words or not right_words:
        return False
    return len(left_words & right_words) / len(left_words | right_words) >= 0.8


def _segment_action(context: EpisodeExtractContext, segment: dict[str, Any]) -> str:
    return segment_action(
        segment,
        context.already,
        context.attempted,
        context.opts.force,
        context.opts.focus,
        context.prompt_version,
    )


def _batch_candidates(
    context: EpisodeExtractContext, segments: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    candidates: list[dict[str, Any]] = []
    skipped = 0
    for segment in segments:
        action = _segment_action(context, segment)
        if action in {"attempted", "extracted", "skip"}:
            skipped += 1
            continue
        candidates.append(segment)
    candidates.sort(
        key=lambda segment: (
            -claim_candidate_score(str(segment.get("text") or "")),
            int(segment.get("idx") or 0),
        )
    )
    return candidates, skipped


def _claims_within_target(
    posted: list[dict[str, Any]],
    accepted_claims: list[dict[str, Any]],
    published: int,
    target: int,
) -> tuple[list[dict[str, Any]], set[str]]:
    unique = [
        claim
        for claim in posted
        if not any(claims_are_near_duplicates(claim, kept) for kept in accepted_claims)
    ]
    if target <= 0:
        return unique, set()
    remaining = max(target - published, 0)
    ranked = sorted(
        unique,
        key=lambda claim: float(claim.get("extractionConfidence") or 0),
        reverse=True,
    )
    deferred = {str(claim.get("segmentId") or "") for claim in ranked[remaining:]}
    return ranked[:remaining], deferred


def _batch_runs(
    context: EpisodeExtractContext,
    batch: list[dict[str, Any]],
    posted: list[dict[str, Any]],
    deferred: set[str],
    run: dict[str, Any],
) -> list[dict[str, Any]]:
    accepted_segments = {str(claim.get("segmentId") or "") for claim in posted}
    batch_ids = [str(segment["id"]) for segment in batch]
    runs = []
    for index, segment in enumerate(batch):
        segment_id = str(segment["id"])
        # A quality claim deferred only because this episode hit its current
        # target remains eligible if the target is raised later.
        if segment_id in deferred:
            continue
        accepted = segment_id in accepted_segments
        runs.append(
            {
                "accepted": accepted,
                "focus": context.opts.focus,
                "latencyMs": run.get("latencyMs") if index == 0 else None,
                "model": run.get("model") or context.cfg.extract_model,
                "promptVersion": BATCH_PROMPT_VERSION,
                "reason": (
                    "ok"
                    if accepted
                    else (
                        str(run.get("reason"))
                        if run.get("reason") != "ok"
                        else "batch_no_quality_claim"
                    )
                ),
                "requestJson": (
                    run.get("requestJson")
                    if index == 0
                    else {"batchSegmentIds": batch_ids, "checkpoint": True}
                ),
                "responseJson": run.get("responseJson") if index == 0 else None,
                "segmentId": segment_id,
            }
        )
    return runs


def _extract_one_candidate_batch(
    context: EpisodeExtractContext,
    batch: list[dict[str, Any]],
    accepted_claims: list[dict[str, Any]],
    published: int,
) -> tuple[list[dict[str, Any]], int] | None:
    try:
        raw, run = extract_one_batch(context.cfg, context.people_map, batch)
    except httpx.HTTPError as exc:
        LOGGER.warning("batch extract failed: %s", exc)
        return None
    posted, deferred = _claims_within_target(
        raw, accepted_claims, published, context.opts.target_claims
    )
    runs = _batch_runs(context, batch, posted, deferred, run)
    result = context.api.post_claims(context.episode["id"], posted, runs)
    outcomes = list(result.get("results") or [])
    saved = [
        claim
        for claim, outcome in zip(posted, outcomes, strict=False)
        if outcome.get("id") and outcome.get("reviewStatus") != "rejected"
    ]
    newly_published = sum(1 for outcome in outcomes if outcome.get("reviewStatus") == "published")
    return saved, newly_published


def _extract_episode_batches(
    context: EpisodeExtractContext, segments: list[dict[str, Any]]
) -> tuple[int, int, int]:
    candidates, skipped = _batch_candidates(context, segments)
    batch_size = max(2, min(context.opts.batch_size, 20))
    extracted = 0
    published = context.published_claims
    llm_calls = 0
    accepted_claims: list[dict[str, Any]] = []
    for start in range(0, len(candidates), batch_size):
        if context.opts.target_claims > 0 and published >= context.opts.target_claims:
            break
        batch = candidates[start : start + batch_size]
        llm_calls += 1
        if context.opts.dry_run:
            continue
        result = _extract_one_candidate_batch(context, batch, accepted_claims, published)
        if result is None:
            continue
        saved, newly_published = result
        accepted_claims.extend(saved)
        extracted += len(saved)
        published += newly_published
    LOGGER.info(
        "episode %s batch_calls=%s candidates=%s skipped=%s new_claims=%s published_total=%s",
        context.episode["id"],
        llm_calls,
        len(candidates),
        skipped,
        extracted,
        published,
    )
    return extracted, llm_calls, skipped


def _extract_episode_segments(
    context: EpisodeExtractContext, segments: list[dict[str, Any]]
) -> tuple[int, int, int]:
    extracted = 0
    llm_calls = 0
    skipped = 0
    prev_tail = ""
    for segment in segments:
        action = _segment_action(context, segment)
        if action in {"attempted", "extracted", "skip"}:
            skipped += 1
            LOGGER.debug("segment %s skip %s", segment["idx"], action)
            continue
        llm_calls += 1
        if context.opts.dry_run:
            LOGGER.info("segment %s keep=%s dry-run", segment["idx"], action)
            continue
        try:
            posted, run, _ = extract_one_segment(
                context.cfg,
                context.people_map,
                segment,
                prev_tail,
                context.guests,
                context.opts.focus,
            )
        except httpx.HTTPError as exc:
            LOGGER.warning("segment %s extract failed: %s", segment["idx"], exc)
            continue
        posted = claims_for_focus(posted, context.opts.focus)
        if context.opts.focus == "recs":
            run["accepted"] = bool(posted)
            if not posted and run.get("reason") == "ok":
                run["reason"] = "no_evidenced_reference"
        extracted += len(posted)
        prev_tail = str(segment["text"])[-300:]
        if posted or run:
            context.api.post_claims(context.episode["id"], posted, [run])
    LOGGER.info(
        "episode %s llm_calls=%s skipped=%s claims=%s",
        context.episode["id"],
        llm_calls,
        skipped,
        extracted,
    )
    return extracted, llm_calls, skipped


def _extract_episode(
    api: ApiClient,
    cfg: Settings,
    people_map: dict[str, str],
    episode: dict[str, Any],
    opts: ExtractOpts,
) -> tuple[int, int, int]:
    detail = api.get_episode(episode["id"])
    prompt_version = (
        BATCH_PROMPT_VERSION
        if opts.batch_size > 1 and opts.focus == "all"
        else str(getattr(cfg, "prompt_version", "extract-v4"))
    )
    already = set(detail.get("extractedSegmentIds") or [])
    attempted = {
        (
            str(row.get("segmentId") or ""),
            str(row.get("promptVersion") or ""),
            str(row.get("focus") or ""),
        )
        for row in detail.get("extractionAttempts") or []
    }
    guests = _episode_guests(detail, people_map)
    segments = _slice_segments(
        list(detail.get("segments") or []), opts.skip_segments, opts.max_segments
    )
    has_identifiable_segment = any(
        str(segment.get("speakerHint") or "") not in {"", UNKNOWN} for segment in segments
    )
    if not guests and not has_identifiable_segment:
        # Nobody identifiable is on this episode, so every claim would be
        # attributed to "unknown" and never published. Exact publisher
        # segment identities are sufficient even when RSS omitted the roster.
        LOGGER.info("episode %s skipped: no identifiable speaker", episode["id"])
        return 0, 0, 0
    context = EpisodeExtractContext(
        api=api,
        cfg=cfg,
        people_map=people_map,
        episode=episode,
        opts=opts,
        prompt_version=prompt_version,
        already=already,
        attempted=attempted,
        guests=guests,
        published_claims=int(detail.get("publishedClaimCount") or 0),
    )
    if opts.batch_size > 1 and opts.focus == "all":
        return _extract_episode_batches(context, segments)
    return _extract_episode_segments(context, segments)


# An episode is only finished when its segments are, not when it first
# reaches `extracted`. Selecting on status alone stranded 185 of 250 segments
# in episodes that earlier runs had capped part way through.
EXTRACTABLE_STATUSES = ("segmented", "extracted", "published")


def _extract_targets(
    api: ApiClient, episode_id: str | None, show_id: str | None = None
) -> list[dict[str, Any]]:
    if episode_id:
        return [api.get_episode(episode_id)["episode"]]
    return [
        row
        for status in EXTRACTABLE_STATUSES
        for row in api.list_episodes(status=status, show_id=show_id)
    ]


def run_extract(
    api: ApiClient,
    cfg: Settings,
    people_map: dict[str, str],
    opts: ExtractOpts,
) -> int:
    if not cfg.ai_api_key and not is_local(cfg) and not opts.dry_run:
        raise SystemExit("AI_API_KEY is required for extract")
    extracted = 0
    targets = _extract_targets(api, opts.episode_id, opts.show_id)
    if opts.limit > 0:
        targets = targets[: opts.limit]
    for episode in targets:
        extracted += _extract_episode(api, cfg, people_map, episode, opts)[0]
    return extracted


RETIME_STATUSES = ("segmented", "extracted", "published")


def _epoch_ms(value: Any) -> int:
    """Epoch milliseconds from either a stored timestamp or an ISO string.

    The API answers with ISO; the database answers with ISO too once Drizzle
    has serialised it; discovery wrote milliseconds. All three arrive here.
    """
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return 0


def match_uploads(episodes: list[dict[str, Any]], videos: list[dict[str, Any]]) -> dict[str, str]:
    """Pair episodes with videos by title and publication date.

    Both signals are needed. Title alone once scored a cancer-research upload
    as a perfect match for an a16z episode, because a two word title sits
    inside any longer one.
    """
    pairs: dict[str, str] = {}
    for episode in episodes:
        if episode.get("youtubeVideoId"):
            continue
        merged = merge_video(
            {
                "title": episode.get("title"),
                "publishedAt": _epoch_ms(episode.get("publishedAt")),
                "sourceUrl": episode.get("sourceUrl"),
            },
            videos,
        )
        video_id = merged.get("youtubeVideoId")
        if video_id:
            pairs[str(episode["id"])] = str(video_id)
    return pairs


def run_youtube_verify(api: ApiClient, cfg: Settings) -> dict[str, int]:
    """Drop video links that are not on the show's own channel.

    Mining ids out of episode metadata takes the first YouTube link in the
    blurb, and show notes link the guest's other appearances: Lex episodes
    ended up pointing at Tucker Carlson's channel, at TED, at FloGrappling.
    A deep link to a stranger's video is worse than no link, because a reader
    clicks it expecting the quote.
    """
    if not cfg.youtube_api_key:
        raise SystemExit("YOUTUBE_API_KEY is required for this stage")
    shows = {s["slug"]: s.get("youtubeChannelId") for s in SHOWS}
    slug_of = {row["id"]: row["slug"] for row in api.list_shows()}
    episodes = [e for e in api.list_episodes() if e.get("youtubeVideoId")]
    tally = {"kept": 0, "wrong_channel": 0, "gone": 0, "unverified": 0}
    with httpx.Client() as client:
        owners = youtube_api.channels_for(
            [str(e["youtubeVideoId"]) for e in episodes], cfg.youtube_api_key, client
        )
    for episode in episodes:
        expected = shows.get(slug_of.get(str(episode.get("showId")), ""))
        if not expected:
            tally["unverified"] += 1
            continue
        owner = owners.get(str(episode["youtubeVideoId"]))
        if owner == expected:
            tally["kept"] += 1
            continue
        tally["gone" if owner is None else "wrong_channel"] += 1
        api.set_episode_status(
            episode["id"], status=str(episode.get("status") or "discovered"), youtubeVideoId=""
        )
    LOGGER.info("youtube verify %s", tally)
    return tally


def run_youtube_api(api: ApiClient, cfg: Settings) -> int:
    """Fill in video ids from each show's full uploads list."""
    if not cfg.youtube_api_key:
        raise SystemExit("YOUTUBE_API_KEY is required for this stage")
    shows = {s["slug"]: s for s in SHOWS}
    show_ids = {row["id"]: row["slug"] for row in api.list_shows()}
    episodes = api.list_episodes()
    filled = 0
    with httpx.Client() as client:
        for show_id, slug in show_ids.items():
            channel = (shows.get(slug) or {}).get("youtubeChannelId")
            if not channel:
                continue
            videos = youtube_api.fetch_uploads(channel, cfg.youtube_api_key, client)
            mine = [e for e in episodes if e.get("showId") == show_id]
            pairs = match_uploads(mine, [_as_video(v) for v in videos])
            LOGGER.info(
                "%s: %s videos, matched %s of %s episodes", slug, len(videos), len(pairs), len(mine)
            )
            for episode_id, video_id in pairs.items():
                episode = next(e for e in mine if e["id"] == episode_id)
                api.set_episode_status(
                    episode_id,
                    status=str(episode.get("status") or "discovered"),
                    youtubeVideoId=video_id,
                )
                filled += 1
    LOGGER.info("youtube api filled %s ids", filled)
    return filled


def _as_video(video: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": video.get("title"),
        "publishedAt": _epoch_ms(video.get("publishedAt")),
        "youtubeVideoId": video.get("youtubeVideoId"),
        "sourceUrl": f"https://www.youtube.com/watch?v={video.get('youtubeVideoId')}",
    }


def run_youtube_ids(api: ApiClient, limit: int = 0) -> int:
    """Recover video ids from canonical episode URLs that are YouTube.

    Nothing is fetched. Arbitrary description links are intentionally ignored:
    recurring recommendations and promos are not evidence that a link is the
    current episode. Full official-channel matching belongs to youtube-api.
    """
    found = 0
    for episode in api.list_episodes():
        if episode.get("youtubeVideoId"):
            continue
        video_id = video_id_from_source_url(episode.get("sourceUrl"))
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


def _recovery_episodes(api: ApiClient, episode_id: str | None, limit: int) -> list[dict[str, Any]]:
    episodes = (
        [api.get_episode(episode_id)["episode"]]
        if episode_id
        else [row for status in RETIME_STATUSES for row in api.list_episodes(status=status)]
    )
    return episodes[:limit] if limit else episodes


def _guest_recovery_index(
    episodes: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, list[str]]]:
    names_by_slug: dict[str, set[str]] = defaultdict(set)
    episode_guest_slugs: dict[str, list[str]] = {}
    for episode in episodes:
        names = explicit_guest_names(
            str(episode.get("description") or ""), str(episode.get("title") or "")
        )
        slugs = []
        for name in names:
            slug = slugify(name)
            names_by_slug[slug].add(name)
            slugs.append(slug)
        if slugs:
            episode_guest_slugs[str(episode["id"])] = slugs
    safe_names = {
        slug: next(iter(names)) for slug, names in names_by_slug.items() if len(names) == 1
    }
    return safe_names, episode_guest_slugs


def _ensure_recovery_people(
    api: ApiClient,
    dry_run: bool,
    safe_names: dict[str, str],
    people_by_id: dict[str, dict[str, Any]],
    people_by_slug: dict[str, dict[str, Any]],
) -> None:
    new_people = [
        {"aliases": [], "name": name, "slug": slug}
        for slug, name in safe_names.items()
        if slug not in people_by_slug
    ]
    if dry_run:
        stored_people = [{**person, "id": f"dry-run:{person['slug']}"} for person in new_people]
    elif new_people:
        ids = api.upsert_people(new_people)
        stored_people = [
            {**person, "id": person_id} for person, person_id in zip(new_people, ids, strict=True)
        ]
    else:
        stored_people = []
    for person in stored_people:
        people_by_id[str(person["id"])] = person
        people_by_slug[str(person["slug"])] = person


def _guest_roster_additions(
    detail: dict[str, Any],
    guest_slugs: list[str],
    safe_names: dict[str, str],
    people_by_slug: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    current_ids = {str(row.get("personId") or "") for row in detail.get("people") or []}
    additions = []
    for slug in guest_slugs:
        person = people_by_slug.get(slug)
        expected_name = safe_names.get(slug)
        if not person or not expected_name or str(person["id"]) in current_ids:
            continue
        if str(person["name"]).casefold() != expected_name.casefold():
            LOGGER.warning(
                "recover-speakers skipped slug collision slug=%s existing=%s candidate=%s",
                slug,
                person["name"],
                expected_name,
            )
            continue
        additions.append(
            {
                "attributionSource": "metadata_match",
                "confidence": 1.0,
                "personId": str(person["id"]),
                "role": "guest",
            }
        )
    return additions


def _recover_episode_speakers(
    api: ApiClient,
    episode: dict[str, Any],
    guest_slugs: list[str],
    safe_names: dict[str, str],
    people_by_slug: dict[str, dict[str, Any]],
    people_by_id: dict[str, dict[str, Any]],
    dry_run: bool,
) -> tuple[int, int]:
    detail = api.get_episode(episode["id"])
    additions = _guest_roster_additions(detail, guest_slugs, safe_names, people_by_slug)
    if additions:
        if not dry_run:
            api.set_episode_people(str(episode["id"]), additions)
        detail = {**detail, "people": [*(detail.get("people") or []), *additions]}
    repairs = recover_self_identified_speakers(detail, people_by_id)
    if not repairs:
        return len(additions), 0
    speakers = sorted({str(repair["speakerHint"]) for repair in repairs})
    if dry_run:
        LOGGER.info(
            "recover-speakers dry-run %s speakers=%s repairs=%s",
            episode["id"],
            speakers,
            len(repairs),
        )
        return len(additions), len(repairs)
    result = api.repair_speakers(episode["id"], repairs)
    LOGGER.info(
        "recover-speakers %s speakers=%s requested=%s updated=%s skipped=%s",
        episode["id"],
        speakers,
        len(repairs),
        result.get("updated"),
        len(result.get("skipped") or []),
    )
    return len(additions), int(result.get("updated") or 0)


def run_recover_speakers(
    api: ApiClient, episode_id: str | None, dry_run: bool, limit: int = 0
) -> int:
    """Recover explicit metadata guests and uniquely evidenced diarized voices."""
    episodes = _recovery_episodes(api, episode_id, limit)
    people_by_id = {str(person["id"]): person for person in api.list_people()}
    people_by_slug = {str(person["slug"]): person for person in people_by_id.values()}
    safe_names, episode_guest_slugs = _guest_recovery_index(episodes)
    _ensure_recovery_people(api, dry_run, safe_names, people_by_id, people_by_slug)
    roster_additions = 0
    repaired = 0
    for episode in episodes:
        added, updated = _recover_episode_speakers(
            api,
            episode,
            episode_guest_slugs.get(str(episode["id"]), []),
            safe_names,
            people_by_slug,
            people_by_id,
            dry_run,
        )
        roster_additions += added
        repaired += updated
    LOGGER.info(
        "recover-speakers scanned=%s roster_additions=%s repaired=%s",
        len(episodes),
        roster_additions,
        repaired,
    )
    return repaired


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
        kind = str(episode.get("transcriptKind") or "none")
        segments = cues_to_segments(cues, speakers_resolved=kind in RESOLVED_TRANSCRIPT_KINDS)
        if dry_run:
            LOGGER.info("retime dry-run %s segments=%s", episode["id"], len(segments))
            continue
        api.put_segments(episode["id"], segments, kind)
        result = api.retime(episode["id"])
        moved += int(result.get("moved") or 0)
        LOGGER.info(
            "retime %s claims=%s moved=%s", episode["id"], result.get("claims"), result.get("moved")
        )
    return moved


def seed_maps_for_stage(
    api: ApiClient, stage: str, dry_run: bool
) -> tuple[dict[str, str], dict[str, str]]:
    if stage == "extract" and not dry_run:
        return load_roster(api), {}
    if stage not in {"all", "discover", "extract"}:
        return {}, {}
    if not dry_run:
        return seed_roster(api)
    return (
        {person["slug"]: person["slug"] for person in PEOPLE},
        {show["slug"]: show["slug"] for show in SHOWS},
    )


def run_standalone_stage(api: ApiClient, cfg: Settings, args: argparse.Namespace) -> bool:
    """Run stages that do not participate in the discover/extract pipeline."""
    handlers = {
        "youtube-verify": lambda: run_youtube_verify(api, cfg),
        "youtube-api": lambda: run_youtube_api(api, cfg),
        "youtube-ids": lambda: run_youtube_ids(api, args.limit),
        "attributions": lambda: run_attributions(api, cfg, args.episode or None, args.limit),
        "identify": lambda: run_identify(api, cfg, args.episode or None),
        "retime": lambda: run_retime(api, args.episode or None, args.dry_run),
        "recover-speakers": lambda: run_recover_speakers(
            api, args.episode or None, args.dry_run, args.limit
        ),
    }
    handler = handlers.get(args.stage)
    if handler is None:
        return False
    handler()
    return True


def _argument_parser() -> argparse.ArgumentParser:
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
        "--batch-size",
        type=int,
        default=0,
        help="extract broad claims from 2-20 attributed candidate segments per local model call",
    )
    parser.add_argument(
        "--target-claims",
        type=int,
        default=10,
        help="stop broad batch extraction after reaching this many new claims per episode",
    )
    parser.add_argument(
        "--whisper",
        action="store_true",
        help="transcribe audio locally when no caption source exists",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # Per-request INFO logs turn a full archive run into hundreds of thousands
    # of lines and hide the show-level result. Pipeline warnings and summaries
    # stay visible; HTTP failures still surface through exceptions and warnings.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = _argument_parser().parse_args(argv)
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
        if run_standalone_stage(api, cfg, args):
            return 0
        target_show_id = None
        if args.show and args.stage in {"all", "transcripts", "extract", "publish"}:
            target_show_id = next(
                (row["id"] for row in api.list_shows() if row["slug"] == args.show),
                None,
            )
            if target_show_id is None:
                raise SystemExit(f"unknown show: {args.show}")
        transcribed = 0
        if args.stage in {"all", "transcripts"}:
            transcribed = run_transcripts(
                api,
                args.episode or None,
                args.force,
                args.dry_run,
                args.whisper,
                cfg,
                target_show_id,
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
                    show_id=target_show_id,
                    focus=args.focus,
                    force=args.force,
                    max_segments=args.max_segments,
                    skip_segments=args.skip_segments,
                    limit=args.limit,
                    batch_size=args.batch_size,
                    target_claims=args.target_claims,
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
