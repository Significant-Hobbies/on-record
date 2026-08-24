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
