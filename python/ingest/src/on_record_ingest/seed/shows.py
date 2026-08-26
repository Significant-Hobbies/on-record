"""Shows the pipeline watches.

`feedUrl` and `youtubeChannelId` were resolved from the Apple podcast
directory and each channel's canonical link, then checked against the live
feeds. A wrong channel id fails silently — every episode simply ends up
`no_transcript` — so change these only against a verified lookup.

`transcript` records where a show publishes its own transcript, measured
2026-08-26 by fetching one real episode page per show. This matters more than
it looks: a publisher transcript names its speakers, so it skips diarization,
the speaker-identification pass, and the confidence gate entirely — the three
places attribution has gone wrong. Lex's pages carry speaker, timestamp, text
and a YouTube deep link per turn, which is strictly better than anything the
pipeline can produce.

| kind | meaning |
|---|---|
| `structured` | speaker-labelled turns with timestamps, parseable |
| `full-text` | complete transcript, no reliable speaker or time markers |
| `none` | nothing usable on the episode page |

`hostPersonIds` are slugs from `seed/people.py`. Hosts are attached to every
episode of their show, which is what makes host statements attributable at all;
without them a roster is only whoever the episode title happens to name.
"""

SHOWS: list[dict] = [
    {
        "slug": "dwarkesh",
        # 78k chars on the Substack post; few timestamps, no speaker markers.
        "transcript": "full-text",
        "name": "Dwarkesh Podcast",
        "feedUrl": "https://apple.dwarkesh-podcast.workers.dev/feed.rss",
        "youtubeChannelId": "UCXl4i9dYBrFOabk0xGmbkRA",
        "hostPersonIds": ["dwarkesh-patel"],
    },
    {
        "slug": "lex-fridman",
        # The episode page is a stub; the transcript lives at <slug>-transcript
        # as div.ts-segment blocks: ts-name, ts-timestamp (with a YouTube deep
        # link) and ts-text. 513 turns and 29k words on the one measured.
        "transcript": "structured",
        "transcriptUrlSuffix": "-transcript",
        "name": "Lex Fridman Podcast",
        "feedUrl": "https://lexfridman.com/feed/podcast/",
        "youtubeChannelId": "UCSHZKyawb77ixDdsGog4iWA",
        "hostPersonIds": ["lex-fridman"],
    },
    {
        "slug": "no-priors",
        # no-priors.com refused the connection when probed; unverified.
        "transcript": "unknown",
        "name": "No Priors",
        "feedUrl": "https://feeds.megaphone.fm/nopriors",
        "youtubeChannelId": "UCSI7h9hydQ40K5MJHnCrQvw",
        "hostPersonIds": ["sarah-guo", "elad-gil"],
    },
    {
        "slug": "latent-space",
        # 80k chars with 269 timestamps on the Substack post.
        "transcript": "full-text",
        "name": "Latent Space",
        "feedUrl": "https://api.substack.com/feed/podcast/1084089.rss",
        "podcastIndexFeedId": 5731786,
        "youtubeChannelId": "UCxBcwypKK-W3GHd_RZ9FZrQ",
        "hostPersonIds": ["shawn-wang", "alessio-fanelli"],
    },
    {
        "slug": "a16z",
        # simplecast episode pages render empty without JavaScript.
        "transcript": "none",
        "name": "The a16z Show",
        "feedUrl": "https://feeds.simplecast.com/JGE3yC0V",
        "youtubeChannelId": "UC9cn0TuPq4dnbTY-CBsm8XA",
        "hostPersonIds": [],
    },
    {
        "slug": "acquired",
        # 280k chars of transcript, but no timestamps to anchor a quote to.
        "transcript": "full-text",
        "name": "Acquired",
        "feedUrl": "https://feeds.transistor.fm/acquired",
        "youtubeChannelId": "UCyFqFYfTW2VoIQKylJ04Rtw",
        "hostPersonIds": ["ben-gilbert", "david-rosenthal"],
    },
    {
        "slug": "twenty-vc",
        # libsyn page carries 94 characters. Nothing there.
        "transcript": "none",
        "name": "The Twenty Minute VC",
        "feedUrl": "https://rss.libsyn.com/shows/61840/destinations/240976.xml",
        "youtubeChannelId": "UCf0PBRjhf0rF8fWBIxTuoWA",
        "hostPersonIds": ["harry-stebbings"],
    },
    {
        "slug": "cognitive-revolution",
        # 205k chars, 327 timestamps and 169 "Name:" turns. Worth parsing.
        "transcript": "structured",
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
        # Spotify-hosted page carries 59k chars, 494 timestamps, 48 turns.
        "transcript": "structured",
        "name": "BG2Pod",
        "feedUrl": "https://anchor.fm/s/f06c2370/podcast/rss",
        "youtubeChannelId": "UC-yRDvpR99LUc5l7i7jLzew",
        "hostPersonIds": ["brad-gerstner", "bill-gurley"],
    },
    {
        "slug": "lightcone",
        # 18k chars on the Spotify page; thinner than the others.
        "transcript": "full-text",
        "name": "Lightcone Podcast",
        "feedUrl": "https://anchor.fm/s/f58d3330/podcast/rss",
        "youtubeChannelId": "UCcefcZRL2oaA_uBNeo5UOWg",
        "hostPersonIds": ["garry-tan"],
    },
    {
        "slug": "lennys",
        "name": "Lenny's Podcast",
        "feedUrl": "https://api.substack.com/feed/podcast/10845.rss",
        "youtubeChannelId": "UC6t1O76G0jYXOAoYCm153dA",
        "hostPersonIds": ["lenny-rachitsky"],
        "transcript": "none",
    },
    {
        "slug": "invest-like-the-best",
        "name": "Invest Like the Best",
        "feedUrl": "https://feeds.megaphone.fm/CLS2859450455",
        "youtubeChannelId": "UCpQBb0fToph3jrDulwz1iUQ",
        "hostPersonIds": ["patrick-o-shaughnessy"],
        "transcript": "none",
    },
    {
        "slug": "all-in",
        "name": "All-In Podcast",
        "feedUrl": "https://rss.libsyn.com/shows/254861/destinations/1928300.xml",
        "youtubeChannelId": "UCESLZhusAkFfsNsApnjF_Cg",
        "hostPersonIds": [
            "chamath-palihapitiya",
            "jason-calacanis",
            "david-sacks",
            "david-friedberg",
        ],
        "transcript": "none",
    },
    {
        "slug": "founders-senra",
        "name": "Founders",
        "feedUrl": "https://feeds.megaphone.fm/DSLLC6297708582",
        "youtubeChannelId": "UCy2FPslt0LLPsIV0iukvHpQ",
        "hostPersonIds": ["david-senra"],
        "transcript": "none",
    },
    {
        "slug": "my-first-million",
        "name": "My First Million",
        "feedUrl": "https://feeds.megaphone.fm/HS2300184645",
        "youtubeChannelId": "UCyaN6mg5u8Cjy2ZI4ikWaug",
        "hostPersonIds": ["sam-parr", "shaan-puri"],
        "transcript": "none",
    },
    {
        "slug": "this-week-in-startups",
        "name": "This Week in Startups",
        "feedUrl": "https://rss.libsyn.com/shows/624860/destinations/5500155.xml",
        "youtubeChannelId": "UCkkhmBWfS7pILYIk0izkc3A",
        "hostPersonIds": ["jason-calacanis"],
        "transcript": "none",
    },
    {
        "slug": "hard-fork",
        "name": "Hard Fork",
        "feedUrl": "https://feeds.simplecast.com/6HKOhNgS",
        "youtubeChannelId": "UCZcR2SVWaGWNlMqPxvQS3vw",
        "hostPersonIds": ["kevin-roose", "casey-newton"],
        "transcript": "none",
    },
    {
        "slug": "conversations-with-tyler",
        "name": "Conversations with Tyler",
        "feedUrl": "https://rss.libsyn.com/shows/137081/destinations/850607.xml",
        "youtubeChannelId": "UC_AnpBvnhXTcipgGEHLWoOg",
        "hostPersonIds": ["tyler-cowen"],
        "transcript": "none",
    },
    {
        "slug": "odd-lots",
        "name": "Odd Lots",
        "feedUrl": "https://www.omnycontent.com/d/playlist/e73c998e-6e60-432f-8610-ae210140c5b1/8a94442e-5a74-4fa2-8b8d-ae27003a8d6b/982f5071-765c-403d-969d-ae27003a8d83/podcast.rss",
        "youtubeChannelId": "UChF5O40UBqAc82I7-i5ig6A",
        "hostPersonIds": ["joe-weisenthal", "tracy-alloway"],
        "transcript": "none",
    },
    {
        "slug": "mlst",
        "name": "Machine Learning Street Talk",
        "feedUrl": "https://anchor.fm/s/1e4a0eac/podcast/rss",
        "youtubeChannelId": "UCMLtBahI5DMrt0NPvDSoIRQ",
        "hostPersonIds": ["tim-scarfe"],
        "transcript": "structured",
    },
    {
        "slug": "unsupervised-learning",
        "name": "Unsupervised Learning",
        "feedUrl": "https://feeds.simplecast.com/dOSE_bdP",
        "youtubeChannelId": "UCUl-s_Vp-Kkk_XVyDylNwLA",
        "hostPersonIds": ["jacob-effron"],
        "transcript": "none",
    },
    {
        "slug": "logan-bartlett",
        "name": "The Logan Bartlett Show",
        "feedUrl": "https://rss2.flightcast.com/jlx9l0yn04wt3r710o051jtm.xml",
        "youtubeChannelId": "UCugS0jD5IAdoqzjaNYzns7w",
        "hostPersonIds": ["logan-bartlett"],
        "transcript": "none",
    },
    {
        "slug": "tbpn",
        "name": "TBPN",
        "feedUrl": "https://feeds.transistor.fm/technology-brother",
        "youtubeChannelId": "UC-DRzaGnL_vtBUpCFH5M0tg",
        "hostPersonIds": ["john-coogan", "jordi-hays"],
        "transcript": "full-text",
    },
    {
        "slug": "cheeky-pint",
        "name": "Cheeky Pint",
        "feedUrl": "https://feeds.transistor.fm/cheeky-pint-with-john-collison",
        "youtubeChannelId": "UCM1guA1E-RHLO2OyfQPOkEQ",
        "hostPersonIds": ["john-collison"],
        "transcript": "full-text",
    },
    {
        "slug": "the-peel",
        "name": "The Peel",
        "feedUrl": "https://api.substack.com/feed/podcast/3340718.rss",
        "youtubeChannelId": "UCtgBGZihRzzJnbRU7FPpJJw",
        "hostPersonIds": ["turner-novak"],
        "transcript": "none",
    },
]
