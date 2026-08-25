from on_record_ingest.match import merge_video, titles_close
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


def test_finds_a_video_id_in_any_link_shape():
    from on_record_ingest.match import video_id_from_metadata

    assert video_id_from_metadata("watch https://youtu.be/QbdbAhaJoCQ now") == "QbdbAhaJoCQ"
    assert (
        video_id_from_metadata(None, "https://www.youtube.com/watch?v=TfyPshgMbug&t=10s")
        == "TfyPshgMbug"
    )
    assert (
        video_id_from_metadata("<iframe src='https://youtube.com/embed/U1FrhkLQnCI'>")
        == "U1FrhkLQnCI"
    )
    assert video_id_from_metadata("no link here", "https://example.com/ep") is None
    # The first field that has one wins.
    assert (
        video_id_from_metadata("https://youtu.be/AAAAAAAAAAA", "https://youtu.be/BBBBBBBBBBB")
        == "AAAAAAAAAAA"
    )
