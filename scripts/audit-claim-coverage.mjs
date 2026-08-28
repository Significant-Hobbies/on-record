#!/usr/bin/env node

import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DatabaseSync } from 'node:sqlite';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const requestedSnapshot = process.argv[2];
const snapshot = requestedSnapshot
  ? resolve(root, requestedSnapshot)
  : join(root, 'workers/api/.wrangler/audits/2026-08-27-correctness-v9/v3');
const d1Path = join(
  snapshot,
  'd1/miniflare-D1DatabaseObject/94acfb1e34b1b291b64ee58e19b507b7acff78987cac2ffcb030d2b4935ce34e.sqlite'
);
const r2IndexPath = join(
  snapshot,
  'r2/miniflare-R2BucketObject/f2bf642351a580c8f559cdae7c13655dfcda32e398f22cc1261cfe0fa467f660.sqlite'
);
const r2BlobsPath = join(snapshot, 'r2/on-record-raw/blobs');

for (const path of [d1Path, r2IndexPath, r2BlobsPath]) {
  if (!existsSync(path)) {
    throw new Error(`missing snapshot input: ${path}`);
  }
}

const signals = {
  commitment:
    /\b(?:i|we) (?:will|won['’]t|am going to|are going to|plan to|intend to|refuse to|commit(?:ted)? to)\b/i,
  evaluation:
    /\b(?:the|this|that|it) (?:is|was|will be) (?:the )?(?:best|worst|better|worse|important|critical|essential|valuable|useless|dangerous|powerful|wrong|right|mistake|advantage|disadvantage)\b/i,
  explanation:
    /\b(?:the (?:reason|problem|lesson|key|point|trade[- ]off) is|what matters is|because|that means|which means|the way to|the only way)\b/i,
  position:
    /\b(?:i|we) (?:think|believe|argue|expect|predict|prefer|disagree|agree|suspect|doubt|would say|would argue|have learned|learned|realized|realised|found that|care about)\b|\b(?:my|our) (?:view|opinion|belief|take|thesis|experience|prediction)\b/i,
  recommendation:
    /\b(?:recommend(?:s|ed|ing|ation)?|you should (?:read|try|use|watch|listen(?: to)?|follow|get|buy)|worth (?:reading|watching|listening to|trying|using|buying)|must[- ](?:read|use|watch|try)|(?:i|we) (?:use|used|read|love|prefer|built|created|founded|avoid))\b/i,
  uncertainty:
    /\b(?:i|we) (?:don['’]t know|do not know|am not sure|are not sure|might be wrong|could be wrong)|\bit['’]s unclear\b|\bthere is uncertainty\b/i,
};
const reject =
  /\b(?:brought to you by|sponsored by|use code|percent off|free trial|subscribe to the podcast|leave (?:us )?a review|we['’]ll be right back|thanks for (?:listening|watching))\b/i;

function scoreText(text) {
  const body = text.replace(/\s+/g, ' ').trim();
  if (body.length < 80 || reject.test(body)) {
    return { score: 0, signals: [] };
  }
  const matched = Object.entries(signals)
    .filter(([, pattern]) => pattern.test(body))
    .map(([name]) => name);
  let score = matched.length * 2;
  if (body.length >= 160 && body.length <= 1800) {
    score += 1;
  }
  if (/[.!]$/.test(body)) {
    score += 1;
  }
  if (/\b(?:for example|for instance|specifically|in practice|as a result)\b/i.test(body)) {
    score += 1;
  }
  if (/\?$/.test(body) && !matched.includes('position')) {
    score -= 2;
  }
  return { score, signals: matched };
}

const db = new DatabaseSync(d1Path, { readOnly: true });
const r2 = new DatabaseSync(r2IndexPath, { readOnly: true });
const objectQuery = r2.prepare('SELECT blob_id FROM _mf_objects WHERE key = ?');
const segmentQuery = db.prepare(
  `SELECT id, idx, speaker_hint
   FROM segments
   WHERE episode_id = ? AND speaker_hint IS NOT NULL AND speaker_hint != 'unknown'
   ORDER BY idx`
);
const existingClaimQuery = db.prepare(
  `SELECT count(*) AS n
   FROM claims
   WHERE episode_id = ? AND review_status = 'published'`
);
const episodes = db
  .prepare(
    `SELECT e.id, e.title, s.slug AS show_slug
     FROM episodes e
     JOIN shows s ON s.id = e.show_id
     WHERE EXISTS (SELECT 1 FROM segments sg WHERE sg.episode_id = e.id)
     ORDER BY s.slug, e.id`
  )
  .all();
const allEpisodeCount = Number(db.prepare('SELECT count(*) AS n FROM episodes').get()?.n ?? 0);

const totals = {
  candidateSegments: 0,
  currentPublishedClaims: 0,
  episodes: episodes.length,
  episodesAtLeast10Candidates: 0,
  episodesBelow10Candidates: 0,
  exactSpeakerSegments: 0,
  exactSpeakerTenPerEpisodeCapacity: 0,
  episodesAtLeast10ExactSpeakerSegments: 0,
  episodesAtLeast10PublishedClaims: 0,
  publishedClaimGapTo10: 0,
  tenPerEpisodeCapacity: 0,
};
const byShow = new Map();
const belowTarget = [];
const samples = [];

for (const episode of episodes) {
  const object = objectQuery.get(`episodes/${episode.id}/segments.json`);
  const segments = segmentQuery.all(episode.id);
  totals.exactSpeakerSegments += segments.length;
  totals.exactSpeakerTenPerEpisodeCapacity += Math.min(segments.length, 10);
  totals.episodesAtLeast10ExactSpeakerSegments += Number(segments.length >= 10);
  const existing = Number(existingClaimQuery.get(episode.id)?.n ?? 0);
  totals.currentPublishedClaims += existing;
  totals.episodesAtLeast10PublishedClaims += Number(existing >= 10);
  totals.publishedClaimGapTo10 += Math.max(10 - existing, 0);
  let candidateCount = 0;
  if (object) {
    const blobPath = join(r2BlobsPath, String(object.blob_id));
    if (existsSync(blobPath)) {
      const bodies = JSON.parse(readFileSync(blobPath, 'utf8'));
      for (const segment of segments) {
        const text = String(bodies[String(segment.idx)]?.text ?? '');
        const result = scoreText(text);
        if (result.score < 3 || result.signals.length === 0) {
          continue;
        }
        candidateCount += 1;
        if (samples.length < 50 && result.score >= 5) {
          samples.push({
            episode: episode.title,
            score: result.score,
            show: episode.show_slug,
            signals: result.signals,
            speaker: segment.speaker_hint,
            text,
          });
        }
      }
    }
  }
  totals.candidateSegments += candidateCount;
  totals.tenPerEpisodeCapacity += Math.min(candidateCount, 10);
  if (candidateCount >= 10) {
    totals.episodesAtLeast10Candidates += 1;
  } else {
    totals.episodesBelow10Candidates += 1;
    if (belowTarget.length < 100) {
      belowTarget.push({
        candidates: candidateCount,
        currentPublishedClaims: existing,
        episode: episode.title,
        show: episode.show_slug,
      });
    }
  }
  const show = byShow.get(episode.show_slug) ?? {
    candidateSegments: 0,
    episodes: 0,
    episodesAtLeast10Candidates: 0,
    tenPerEpisodeCapacity: 0,
  };
  show.episodes += 1;
  show.candidateSegments += candidateCount;
  show.tenPerEpisodeCapacity += Math.min(candidateCount, 10);
  show.episodesAtLeast10Candidates += Number(candidateCount >= 10);
  byShow.set(episode.show_slug, show);
}

db.close();
r2.close();
process.stdout.write(
  `${JSON.stringify(
    {
      totals: {
        ...totals,
        averageCandidatesPerTranscriptEpisode:
          Math.round((totals.candidateSegments / Math.max(totals.episodes, 1)) * 10) / 10,
        targetAt10PerTranscriptEpisode: totals.episodes * 10,
        allEpisodes: allEpisodeCount,
        episodesWithoutTranscripts: allEpisodeCount - totals.episodes,
        targetAt10PerAllEpisode: allEpisodeCount * 10,
      },
      byShow: [...byShow.entries()]
        .map(([show, counts]) => ({ show, ...counts }))
        .sort((left, right) => right.candidateSegments - left.candidateSegments),
      belowTarget,
      samples,
    },
    null,
    2
  )}\n`
);
