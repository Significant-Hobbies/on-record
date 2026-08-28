#!/usr/bin/env node

import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DatabaseSync } from 'node:sqlite';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const requestedSnapshot = process.argv[2];
const snapshot = requestedSnapshot
  ? resolve(repositoryRoot, requestedSnapshot)
  : join(repositoryRoot, 'workers/api/.wrangler/audits/2026-08-27-correctness-v9/v3');
const d1Dir = join(snapshot, 'd1/miniflare-D1DatabaseObject');
const d1Path = existsSync(d1Dir)
  ? join(
      d1Dir,
      // Miniflare creates one SQLite file for this project. Keeping discovery
      // out of the audit makes an accidental second database fail closed.
      '94acfb1e34b1b291b64ee58e19b507b7acff78987cac2ffcb030d2b4935ce34e.sqlite'
    )
  : snapshot;
const r2IndexPath = join(
  snapshot,
  'r2/miniflare-R2BucketObject/f2bf642351a580c8f559cdae7c13655dfcda32e398f22cc1261cfe0fa467f660.sqlite'
);
const r2BlobsPath = join(snapshot, 'r2/on-record-raw/blobs');

if (!existsSync(d1Path)) {
  throw new Error(`missing D1 snapshot: ${d1Path}`);
}

const genericAnchor =
  /^(?:here|this|link|website|site|source|learn more|read more|click here|listen|watch|subscribe|sign up|apply|youtube|spotify|apple podcasts?|twitter|x|linkedin|instagram|tiktok|discord|newsletter|show notes?|episode links?|full episode|transcript|video|audio)$/i;
const promotionalContext =
  /\b(?:sponsor(?:ed|s)?|brought to you by|use code|discount|off your first|free trial|apply to join|tickets?|hiring|subscribe|follow us|leave (?:a )?review)\b/i;
const recommendationContext =
  /\b(?:recommended books?|book recommendations?|recommended resources?|recommend(?:s|ed|ing)?|worth (?:reading|watching|trying|using)|must[- ]read|you should (?:read|try|use|watch|listen to|follow))\b/i;
const unstableNamedAnchor =
  /^(?:his|her|their|my|our|your|the|this|that|these|those|its|a|an)\s+|\b(?:here|there|it|them|this|that|these|those|something|anything|everything|more|list|links?|resources?|website|blog|post|essay|article|video|channel|account|page|work|stuff|store|community|newsletter|podcast|episode|show notes?)$/i;
const uppercaseName = /[A-Z]/;
const stableUppercaseName = /^[A-Z0-9][A-Z0-9 .&:+#'’_-]+$/;

function decodeHtml(value) {
  return value
    .replace(/<[^>]+>/g, ' ')
    .replace(/&#(?:x([0-9a-f]+)|(\d+));/gi, (_, hex, decimal) =>
      String.fromCodePoint(Number.parseInt(hex ?? decimal, hex ? 16 : 10))
    )
    .replace(/&(?:amp|#38);/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&apos;|&#39;/gi, "'")
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&nbsp;/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function hostname(rawUrl) {
  try {
    return new URL(rawUrl).hostname.replace(/^www\./, '').toLowerCase();
  } catch {
    return '';
  }
}

function likelyNamedAnchor(name) {
  if (name.length < 2 || name.length > 140 || genericAnchor.test(name)) {
    return false;
  }
  if (/^(?:https?:\/\/|www\.)/i.test(name) || /^[\W_]+$/u.test(name)) {
    return false;
  }
  return /[\p{L}\p{N}]/u.test(name);
}

function stableMentionName(name) {
  return (
    likelyNamedAnchor(name) &&
    !unstableNamedAnchor.test(name) &&
    (uppercaseName.test(name) ||
      ['.', '/', '+', '#', '@'].some((character) => name.includes(character)) ||
      stableUppercaseName.test(name))
  );
}

function canonicalName(name) {
  return name.normalize('NFKC').replace(/\s+/g, ' ').trim().toLocaleLowerCase('en-US');
}

function strictGlobalMentionName(name, reviewedNames) {
  if (reviewedNames.has(canonicalName(name))) {
    return true;
  }
  const words = name.match(/[\p{L}\p{N}][\p{L}\p{N}.+#@'’_-]*/gu) ?? [];
  if (words.length === 1) {
    return /[A-Z].*[A-Z]/.test(name) || /[\d./+#@_-]/.test(name) || /^[A-Z\d]{2,12}$/.test(name);
  }
  if (/^(?:a|an|the|this|that|these|those|on|in|at|to|for|from|with|by|of)\b/i.test(name)) {
    return false;
  }
  return words.filter((word) => /^[A-Z\d]/.test(word)).length >= Math.ceil(words.length / 2);
}

function episodeBodies(objectQuery, episodeId) {
  const object = objectQuery.get(`episodes/${episodeId}/segments.json`);
  if (!object) {
    return null;
  }
  const blobPath = join(r2BlobsPath, String(object.blob_id));
  return existsSync(blobPath) ? JSON.parse(readFileSync(blobPath, 'utf8')) : null;
}

const db = new DatabaseSync(d1Path, { readOnly: true });
const rows = db
  .prepare(
    `SELECT e.id, e.title, e.description, s.slug AS show_slug
     FROM episodes e
     JOIN shows s ON s.id = e.show_id
     WHERE e.description IS NOT NULL AND length(e.description) > 0`
  )
  .all();
const peopleQuery = db.prepare(
  `SELECT count(*) AS n
   FROM episode_people
   WHERE episode_id = ? AND COALESCE(confidence, 1.0) >= 0.5`
);

const totals = {
  anchors: 0,
  episodes: rows.length,
  episodesWithCandidate: 0,
  episodesWithRecommendationCandidate: 0,
  namedCandidates: 0,
  namedCandidatesWithRoster: 0,
  promotionalCandidates: 0,
  recommendationCandidates: 0,
  exactTranscriptMentionRows: 0,
  exactTranscriptMentionPeople: 0,
  exactTranscriptMentionItems: 0,
  globalTranscriptMentionRows: 0,
  globalUniqueEpisodePersonItems: 0,
  globalTranscriptMentionPeople: 0,
  globalTranscriptMentionItems: 0,
  globalTranscriptMentionEpisodes: 0,
  strictGlobalMentionRows: 0,
  strictGlobalUniqueEpisodePersonItems: 0,
  strictGlobalMentionItems: 0,
  strictCaseMentionRows: 0,
  strictCaseUniqueEpisodePersonItems: 0,
  strictCaseMentionItems: 0,
};
const byShow = new Map();
const samples = [];
const candidatesByEpisode = new Map();
const reviewedNames = new Set(
  db
    .prepare(
      `SELECT DISTINCT lower(trim(name)) AS name
       FROM claim_references
       WHERE role IN ('recommends', 'uses', 'likes', 'owns', 'built', 'avoids')`
    )
    .all()
    .map((row) => canonicalName(String(row.name)))
);

for (const row of rows) {
  const description = String(row.description);
  const show = byShow.get(row.show_slug) ?? {
    anchors: 0,
    episodes: 0,
    episodesWithCandidate: 0,
    namedCandidates: 0,
    recommendationCandidates: 0,
  };
  show.episodes += 1;
  const people = Number(peopleQuery.get(row.id)?.n ?? 0);
  const matches = [
    ...description.matchAll(/<a\b[^>]*href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi),
  ];
  totals.anchors += matches.length;
  show.anchors += matches.length;
  let episodeCandidates = 0;
  let episodeRecommendations = 0;
  for (const match of matches) {
    const url = decodeHtml(match[1]);
    const name = decodeHtml(match[2]);
    if (!likelyNamedAnchor(name)) {
      continue;
    }
    const contextStart = Math.max(0, match.index - 240);
    const contextEnd = Math.min(description.length, match.index + match[0].length + 120);
    const context = decodeHtml(description.slice(contextStart, contextEnd));
    const promotional = promotionalContext.test(context);
    const recommended = recommendationContext.test(context);
    totals.namedCandidates += 1;
    show.namedCandidates += 1;
    episodeCandidates += 1;
    if (people > 0) {
      totals.namedCandidatesWithRoster += 1;
    }
    if (promotional) {
      totals.promotionalCandidates += 1;
    }
    if (!promotional && stableMentionName(name)) {
      const candidates = candidatesByEpisode.get(row.id) ?? new Map();
      const key = name.normalize('NFKC').replace(/\s+/g, ' ').trim().toLocaleLowerCase('en-US');
      if (!candidates.has(key)) {
        candidates.set(key, name);
      }
      candidatesByEpisode.set(row.id, candidates);
    }
    if (recommended && !promotional) {
      totals.recommendationCandidates += 1;
      show.recommendationCandidates += 1;
      episodeRecommendations += 1;
      if (samples.length < 40) {
        samples.push({
          context,
          episode: row.title,
          host: hostname(url),
          name,
          show: row.show_slug,
        });
      }
    }
  }
  if (episodeCandidates > 0) {
    totals.episodesWithCandidate += 1;
    show.episodesWithCandidate += 1;
  }
  if (episodeRecommendations > 0) {
    totals.episodesWithRecommendationCandidate += 1;
  }
  byShow.set(row.show_slug, show);
}

if (existsSync(r2IndexPath) && existsSync(r2BlobsPath)) {
  const r2 = new DatabaseSync(r2IndexPath, { readOnly: true });
  const objectQuery = r2.prepare('SELECT blob_id FROM _mf_objects WHERE key = ?');
  const segmentsQuery = db.prepare(
    `SELECT idx, speaker_hint
     FROM segments
     WHERE episode_id = ? AND speaker_hint IS NOT NULL AND speaker_hint != 'unknown'
     ORDER BY idx`
  );
  const people = new Set();
  const items = new Set();
  const confirmedNames = new Map();
  const mentionSamples = [];
  for (const [episodeId, candidates] of candidatesByEpisode) {
    const bodies = episodeBodies(objectQuery, episodeId);
    if (!bodies) {
      continue;
    }
    for (const segment of segmentsQuery.all(episodeId)) {
      const text = String(bodies[String(segment.idx)]?.text ?? '');
      const folded = text.normalize('NFKC').toLocaleLowerCase('en-US');
      for (const [key, name] of candidates) {
        if (!folded.includes(key)) {
          continue;
        }
        totals.exactTranscriptMentionRows += 1;
        people.add(String(segment.speaker_hint));
        items.add(key);
        confirmedNames.set(key, name);
        if (mentionSamples.length < 40) {
          mentionSamples.push({ episodeId, name, speaker: segment.speaker_hint, text });
        }
      }
    }
  }
  totals.exactTranscriptMentionPeople = people.size;
  totals.exactTranscriptMentionItems = items.size;

  const candidatesByToken = new Map();
  for (const [key, name] of confirmedNames) {
    const [token] = key.match(/[\p{L}\p{N}][\p{L}\p{N}.+#@'’_-]*/u) ?? [];
    if (!token) {
      continue;
    }
    const candidates = candidatesByToken.get(token) ?? [];
    candidates.push([key, name]);
    candidatesByToken.set(token, candidates);
  }
  const transcriptEpisodes = db
    .prepare(
      `SELECT DISTINCT episode_id
       FROM segments
       WHERE speaker_hint IS NOT NULL AND speaker_hint != 'unknown'`
    )
    .all();
  const globalPeople = new Set();
  const globalItems = new Set();
  const globalEpisodes = new Set();
  const globalEpisodePersonItems = new Set();
  const globalItemRows = new Map();
  const globalItemUnique = new Map();
  const strictRows = new Set();
  const strictItems = new Set();
  const strictItemRows = new Map();
  const strictItemUnique = new Map();
  const strictCaseRows = new Set();
  const strictCaseItems = new Set();
  const globalSamples = [];
  for (const episode of transcriptEpisodes) {
    const bodies = episodeBodies(objectQuery, episode.episode_id);
    if (!bodies) {
      continue;
    }
    for (const segment of segmentsQuery.all(episode.episode_id)) {
      const text = String(bodies[String(segment.idx)]?.text ?? '');
      const folded = text.normalize('NFKC').replace(/\s+/g, ' ').toLocaleLowerCase('en-US');
      const tokens = new Set(folded.match(/[\p{L}\p{N}][\p{L}\p{N}.+#@'’_-]*/gu) ?? []);
      const segmentCandidates = new Map();
      for (const token of tokens) {
        for (const candidate of candidatesByToken.get(token) ?? []) {
          segmentCandidates.set(candidate[0], candidate[1]);
        }
      }
      for (const [key, name] of segmentCandidates) {
        if (!folded.includes(key)) {
          continue;
        }
        totals.globalTranscriptMentionRows += 1;
        globalPeople.add(`${segment.speaker_hint}\0${key}`);
        globalItems.add(key);
        globalEpisodes.add(String(episode.episode_id));
        const uniqueKey = `${episode.episode_id}\0${segment.speaker_hint}\0${key}`;
        globalEpisodePersonItems.add(uniqueKey);
        globalItemRows.set(key, (globalItemRows.get(key) ?? 0) + 1);
        const uniqueForItem = globalItemUnique.get(key) ?? new Set();
        uniqueForItem.add(uniqueKey);
        globalItemUnique.set(key, uniqueForItem);
        if (strictGlobalMentionName(name, reviewedNames)) {
          totals.strictGlobalMentionRows += 1;
          strictRows.add(uniqueKey);
          strictItems.add(key);
          strictItemRows.set(key, (strictItemRows.get(key) ?? 0) + 1);
          const strictUniqueForItem = strictItemUnique.get(key) ?? new Set();
          strictUniqueForItem.add(uniqueKey);
          strictItemUnique.set(key, strictUniqueForItem);
          if (reviewedNames.has(key) || text.includes(name)) {
            totals.strictCaseMentionRows += 1;
            strictCaseRows.add(uniqueKey);
            strictCaseItems.add(key);
          }
        }
        if (globalSamples.length < 40) {
          globalSamples.push({
            episodeId: episode.episode_id,
            name,
            speaker: segment.speaker_hint,
            text,
          });
        }
      }
    }
  }
  totals.globalTranscriptMentionPeople = new Set(
    [...globalPeople].map((key) => key.split('\0', 1)[0])
  ).size;
  totals.globalTranscriptMentionItems = globalItems.size;
  totals.globalTranscriptMentionEpisodes = globalEpisodes.size;
  totals.globalUniqueEpisodePersonItems = globalEpisodePersonItems.size;
  totals.strictGlobalUniqueEpisodePersonItems = strictRows.size;
  totals.strictGlobalMentionItems = strictItems.size;
  totals.strictCaseUniqueEpisodePersonItems = strictCaseRows.size;
  totals.strictCaseMentionItems = strictCaseItems.size;
  r2.close();
  samples.push({
    exactTranscriptMentions: mentionSamples,
    globalTranscriptMentions: globalSamples,
    globalTopItems: [...globalItemRows]
      .map(([key, rows]) => ({
        name: confirmedNames.get(key),
        rows,
        uniqueEpisodePersonItems: globalItemUnique.get(key)?.size ?? 0,
      }))
      .sort(
        (left, right) =>
          right.uniqueEpisodePersonItems - left.uniqueEpisodePersonItems || right.rows - left.rows
      )
      .slice(0, 100),
    strictTopItems: [...strictItemRows]
      .map(([key, rows]) => ({
        name: confirmedNames.get(key),
        rows,
        uniqueEpisodePersonItems: strictItemUnique.get(key)?.size ?? 0,
      }))
      .sort(
        (left, right) =>
          right.uniqueEpisodePersonItems - left.uniqueEpisodePersonItems || right.rows - left.rows
      )
      .slice(0, 100),
  });
}

db.close();
process.stdout.write(
  `${JSON.stringify(
    {
      totals,
      byShow: [...byShow.entries()]
        .map(([show, counts]) => ({ show, ...counts }))
        .sort((left, right) => right.namedCandidates - left.namedCandidates),
      samples,
    },
    null,
    2
  )}\n`
);
