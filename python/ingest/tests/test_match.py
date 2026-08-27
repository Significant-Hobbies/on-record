from on_record_ingest.match import merge_discovery_items, merge_video, titles_close
from on_record_ingest.sources.podcast_index import items_from_response
from datetime import datetime, timezone


def test_titles_close():
    assert titles_close("Andrej Karpathy: Software agents", "Software agents with Andrej Karpathy")


def test_merge_video_by_title_and_date():
    episode = {
        "title": "Interview with Andrej Karpathy",
        "publishedAt": 1_700_000_000_000,
        "sourceUrl": "https://example.com/ep",
    }
    videos = [
        {
            "title": "Interview with Andrej Karpathy",
            "publishedAt": 1_700_000_000_000 + 3_600_000,
            "youtubeVideoId": "abc123",
            "sourceUrl": "https://youtu.be/abc123",
        }
    ]
    merged = merge_video(episode, videos)
    assert merged["youtubeVideoId"] == "abc123"


def test_rss_backed_show_does_not_admit_unmatched_channel_videos():
    published = 1_700_000_000_000
    rss = [{"guid": "rss-guid", "title": "A real episode", "publishedAt": published}]
    matching_video = {
        "guid": "yt:AAAAAAAAAAA",
        "title": "A real episode",
        "publishedAt": published,
        "youtubeVideoId": "AAAAAAAAAAA",
    }
    unmatched_video = {
        "guid": "yt:BBBBBBBBBBB",
        "title": "A separate video",
        "publishedAt": published,
        "youtubeVideoId": "BBBBBBBBBBB",
    }
    merged = merge_discovery_items(
        rss,
        [matching_video, unmatched_video],
        include_unmatched_videos=False,
    )
    assert [item["guid"] for item in merged] == ["rss-guid"]
    assert merged[0]["youtubeVideoId"] == "AAAAAAAAAAA"


def test_youtube_primary_show_can_admit_unmatched_channel_videos():
    rss = [{"guid": "rss-guid", "title": "A real episode", "publishedAt": 1}]
    video = {
        "guid": "yt:BBBBBBBBBBB",
        "title": "Unrelated channel upload",
        "publishedAt": 1,
        "youtubeVideoId": "BBBBBBBBBBB",
    }
    merged = merge_discovery_items(rss, [video], include_unmatched_videos=True)
    assert [item["guid"] for item in merged] == ["rss-guid", "yt:BBBBBBBBBBB"]


def test_podcast_index_filters_old_items():
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    payload = {
        "items": [
            {
                "id": 1,
                "guid": "g1",
                "title": "New episode",
                "datePublished": int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()),
                "link": "https://example.com/new",
            },
            {
                "id": 2,
                "guid": "g2",
                "title": "Old episode",
                "datePublished": int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()),
                "link": "https://example.com/old",
            },
        ]
    }
    items = items_from_response(payload, since)
    assert len(items) == 1
    assert items[0]["guid"] == "g1"


def test_guests_need_a_whole_word_name():
    from on_record_ingest.match import guests_from_text

    named = [g["personId"] for g in guests_from_text("Dario Amodei on scaling")]
    assert named == ["dario-amodei"]
    # A bare first name is not enough to credit an episode to someone.
    assert guests_from_text("Sam went to the shops") == []
    # Substrings of longer words must not match either.
    assert guests_from_text("Elad Gilbert is someone else") == []


def test_surname_only_titles_still_match():
    from on_record_ingest.match import guests_from_text

    assert [g["personId"] for g in guests_from_text("Karpathy on agents")] == ["andrej-karpathy"]


def test_hosts_are_added_and_outrank_metadata_guesses():
    from on_record_ingest.pipeline import host_people, with_hosts

    hosts = host_people({"hostPersonIds": ["dwarkesh-patel"]})
    merged = with_hosts(
        [
            {"personId": "dwarkesh-patel", "role": "guest", "attributionSource": "metadata_match"},
            {"personId": "dario-amodei", "role": "guest", "attributionSource": "metadata_match"},
        ],
        hosts,
    )
    roles = {row["personId"]: row["role"] for row in merged}
    assert roles == {"dwarkesh-patel": "host", "dario-amodei": "guest"}


def test_finds_a_video_id_only_when_the_source_itself_is_youtube():
    from on_record_ingest.match import video_id_from_source_url

    assert video_id_from_source_url("https://youtu.be/QbdbAhaJoCQ") == "QbdbAhaJoCQ"
    assert (
        video_id_from_source_url("https://www.youtube.com/watch?v=TfyPshgMbug&t=10s")
        == "TfyPshgMbug"
    )
    assert video_id_from_source_url("https://youtube.com/embed/U1FrhkLQnCI") == "U1FrhkLQnCI"
    assert video_id_from_source_url("https://youtube.com/live/BBBBBBBBBBB") == "BBBBBBBBBBB"
    assert video_id_from_source_url("https://youtube.com/shorts/CCCCCCCCCCC") == "CCCCCCCCCCC"
    assert video_id_from_source_url("https://example.com/ep") is None
    assert video_id_from_source_url("watch https://youtu.be/AAAAAAAAAAA now") is None
    assert video_id_from_source_url("<iframe src='https://youtube.com/embed/U1FrhkLQnCI'>") is None


def test_timestamps_arrive_in_three_shapes():
    from on_record_ingest.pipeline import _epoch_ms

    assert _epoch_ms(1_700_000_000_000) == 1_700_000_000_000
    assert _epoch_ms("1700000000000") == 1_700_000_000_000
    # The YouTube API and the database both answer with ISO.
    assert _epoch_ms("2026-08-03T17:32:13.000Z") == 1785778333000
    assert _epoch_ms(None) == 0
    assert _epoch_ms("not a date") == 0
