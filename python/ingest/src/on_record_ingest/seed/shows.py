"""Shows the pipeline watches.

`feedUrl` and `youtubeChannelId` were resolved from the Apple podcast
directory and each channel's canonical link, then checked against the live
feeds. A wrong channel id fails silently — every episode simply ends up
`no_transcript` — so change these only against a verified lookup.

`hostPersonIds` are slugs from `seed/people.py`. Hosts are attached to every
episode of their show, which is what makes host statements attributable at all;
without them a roster is only whoever the episode title happens to name.
"""

SHOWS: list[dict] = [
    {
        "slug": "dwarkesh",
        "name": "Dwarkesh Podcast",
        "feedUrl": "https://apple.dwarkesh-podcast.workers.dev/feed.rss",
        "youtubeChannelId": "UCXl4i9dYBrFOabk0xGmbkRA",
        "hostPersonIds": ["dwarkesh-patel"],
    },
    {
        "slug": "lex-fridman",
        "name": "Lex Fridman Podcast",
        "feedUrl": "https://lexfridman.com/feed/podcast/",
        "youtubeChannelId": "UCSHZKyawb77ixDdsGog4iWA",
        "hostPersonIds": ["lex-fridman"],
    },
    {
        "slug": "no-priors",
        "name": "No Priors",
        "feedUrl": "https://feeds.megaphone.fm/nopriors",
        "youtubeChannelId": "UCSI7h9hydQ40K5MJHnCrQvw",
        "hostPersonIds": ["sarah-guo", "elad-gil"],
    },
    {
        "slug": "latent-space",
        "name": "Latent Space",
        "feedUrl": "https://api.substack.com/feed/podcast/1084089.rss",
        "podcastIndexFeedId": 5731786,
        "youtubeChannelId": "UCxBcwypKK-W3GHd_RZ9FZrQ",
        "hostPersonIds": ["shawn-wang", "alessio-fanelli"],
    },
    {
        "slug": "a16z",
        "name": "The a16z Show",
        "feedUrl": "https://feeds.simplecast.com/JGE3yC0V",
        "youtubeChannelId": "UC9cn0TuPq4dnbTY-CBsm8XA",
        "hostPersonIds": [],
    },
    {
        "slug": "acquired",
        "name": "Acquired",
        "feedUrl": "https://feeds.transistor.fm/acquired",
        "youtubeChannelId": "UCyFqFYfTW2VoIQKylJ04Rtw",
        "hostPersonIds": ["ben-gilbert", "david-rosenthal"],
    },
    {
        "slug": "twenty-vc",
        "name": "The Twenty Minute VC",
        "feedUrl": "https://rss.libsyn.com/shows/61840/destinations/240976.xml",
        "youtubeChannelId": "UCf0PBRjhf0rF8fWBIxTuoWA",
        "hostPersonIds": ["harry-stebbings"],
    },
    {
        "slug": "cognitive-revolution",
        "name": "The Cognitive Revolution",
        "feedUrl": "https://feeds.megaphone.fm/RINTP3108857801",
        "youtubeChannelId": "UCjNRVMBVI30Sak_p6HRWhIA",
        "hostPersonIds": ["nathan-labenz"],
    },
    # The anchor.fm feeds for bg2 and lightcone are stale mirrors (last items
    # Jun 2026 and Dec 2025). Both shows are discovered through their YouTube
    # channels instead; the feed is kept only as a fallback if it revives.
    {
        "slug": "bg2",
        "name": "BG2Pod",
        "feedUrl": "https://anchor.fm/s/f06c2370/podcast/rss",
        "youtubeChannelId": "UC-yRDvpR99LUc5l7i7jLzew",
        "hostPersonIds": ["brad-gerstner", "bill-gurley"],
    },
    {
        "slug": "lightcone",
        "name": "Lightcone Podcast",
        "feedUrl": "https://anchor.fm/s/f58d3330/podcast/rss",
        "youtubeChannelId": "UCcefcZRL2oaA_uBNeo5UOWg",
        "hostPersonIds": ["garry-tan"],
    },
]
