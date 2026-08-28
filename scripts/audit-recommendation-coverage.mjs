#!/usr/bin/env node

import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DatabaseSync } from 'node:sqlite';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const auditRoot = join(root, 'workers/api/.wrangler/audits');
const requestedSnapshot = process.argv[2];
const snapshotRoot = requestedSnapshot
  ? resolve(root, requestedSnapshot)
  : join(auditRoot, '2026-08-27-correctness-v9/v3');
const d1Path = join(
  snapshotRoot,
  'd1/miniflare-D1DatabaseObject/94acfb1e34b1b291b64ee58e19b507b7acff78987cac2ffcb030d2b4935ce34e.sqlite'
);
const r2IndexPath = join(
  snapshotRoot,
  'r2/miniflare-R2BucketObject/f2bf642351a580c8f559cdae7c13655dfcda32e398f22cc1261cfe0fa467f660.sqlite'
);
const r2BlobsPath = join(snapshotRoot, 'r2/on-record-raw/blobs');

const patterns = {
  endorsement:
    /\b(?:recommend(?:s|ed|ing|ation)?|endorse(?:s|d|ment)?|you should (?:read|try|use|watch|listen(?: to)?|follow|get|buy)|check (?:it|this|them|that|[a-z0-9'’.-]+) out|worth (?:reading|watching|listening to|trying|using|buying)|give (?:it|this|them|that) a try|must[- ](?:read|use|watch|try))\b/i,
  preference:
    /\b(?:my favou?rite|(?:i|we) (?:really )?(?:love|like|prefer|enjoy|adore)|i['’]m (?:a )?(?:(?:big|huge) )?fan of|i am (?:a )?(?:(?:big|huge) )?fan of|i['’]m obsessed with|i am obsessed with|i swear by|my go[- ]to)\b/i,
  use: /\b(?:(?:i|we) (?:use|used|am using|are using|have been using|have used|rely on|work with|run|wear|take|play|drive|keep|carry)|i['’]m using|we['’]re using|(?:i|we)['’]ve been using|personally use|my daily driver|my (?:tech )?stack|our (?:tech )?stack|(?:i|we) (?:switched|moved) to)\b/i,
  consumption:
    /\b(?:(?:i|we) (?:read|are reading|am reading|listen to|listened to|watch|watched|subscribe to|subscribed to)|i['’]m reading|we['’]re reading|(?:i|we)['’]ve (?:read|been reading|listened to|watched|subscribed to))\b/i,
  ownership: /\b(?:(?:i|we) (?:bought|own|have purchased)|(?:i|we)['’]ve (?:bought|purchased))\b/i,
  built:
    /\b(?:(?:i|we) (?:built|build|created|create|made|make|developed|develop|founded|found|launched|launch|wrote|write|authored|author|designed|design|shipped|ship|started|start))\b/i,
  avoids:
    /\b(?:don['’]t use|do not use|never use|stop(?:ped)? using|(?:i|we) avoid|switched away from|(?:i|we) (?:quit|uninstalled)|stay away from|wouldn['’]t use|would not use|can['’]t use|cannot use|cancelled|canceled)\b/i,
};

const currentTriage =
  /\b(?:recommend(?:s|ed|ing)?|i use|i used|i['’]ve been using|personally use|favorite (?:book|app|tool)|reading list|i read|worth reading|i built|don['’]t use|stop using|switched to)\b/i;

function invariant(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function emptyCounts() {
  return {
    avoids: 0,
    built: 0,
    consumption: 0,
    currentTriage: 0,
    endorsement: 0,
    exactSegments: 0,
    expandedUnion: 0,
    missingBodies: 0,
    ownership: 0,
    preference: 0,
    use: 0,
  };
}

function escapePattern(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function selfIdentificationPattern(name) {
  return new RegExp(
    `(?:^|[.!?]\\s+)(?:hello(?: everyone| everybody)?[,!. ]*|hi[,!. ]*|hey[,!. ]*|and\\s+)?(?:i['’]m|i am|my name is)\\s+${escapePattern(name)}(?=$|[\\s,!.?])`,
    'i'
  );
}

function increment(counts, text) {
  counts.exactSegments += 1;
  const matched = Object.fromEntries(
    Object.entries(patterns).map(([name, pattern]) => [name, pattern.test(text)])
  );
  for (const [name, didMatch] of Object.entries(matched)) {
    if (didMatch) {
      counts[name] += 1;
    }
  }
  if (currentTriage.test(text)) {
    counts.currentTriage += 1;
  }
  if (Object.values(matched).some(Boolean)) {
    counts.expandedUnion += 1;
  }
}

for (const required of [d1Path, r2IndexPath, r2BlobsPath]) {
  invariant(existsSync(required), `missing snapshot input: ${required}`);
}

const db = new DatabaseSync(d1Path, { readOnly: true });
const r2 = new DatabaseSync(r2IndexPath, { readOnly: true });
const episodes = db
  .prepare(
    `SELECT e.id, e.transcript_kind, s.slug AS show_slug
     FROM episodes e
     JOIN shows s ON s.id = e.show_id
     WHERE EXISTS (
       SELECT 1 FROM segments sg WHERE sg.episode_id = e.id
     )
     ORDER BY s.slug, e.id`
  )
  .all();
const segmentQuery = db.prepare(
  `SELECT idx, speaker_hint
   FROM segments
   WHERE episode_id = ?
   ORDER BY idx`
);
const rosterQuery = db.prepare(
  `SELECT p.slug, p.name
   FROM episode_people ep
   JOIN people p ON p.id = ep.person_id
   WHERE ep.episode_id = ?
     AND COALESCE(ep.confidence, 1.0) >= 0.5`
);
const objectQuery = r2.prepare('SELECT blob_id FROM _mf_objects WHERE key = ?');
const total = emptyCounts();
const unknownTotal = emptyCounts();
const recoveredTotal = emptyCounts();
const byShow = new Map();
const unknownByShow = new Map();
const recoveredByShow = new Map();
let episodesWithRecovery = 0;
let recoveredMappings = 0;

for (const [episodeOffset, episode] of episodes.entries()) {
  const showCounts = byShow.get(episode.show_slug) ?? emptyCounts();
  byShow.set(episode.show_slug, showCounts);
  const unknownShowCounts = unknownByShow.get(episode.show_slug) ?? emptyCounts();
  unknownByShow.set(episode.show_slug, unknownShowCounts);
  const recoveredShowCounts = recoveredByShow.get(episode.show_slug) ?? emptyCounts();
  recoveredByShow.set(episode.show_slug, recoveredShowCounts);
  const object = objectQuery.get(`episodes/${episode.id}/segments.json`);
  if (!object) {
    const segments = segmentQuery.all(episode.id);
    const exactCount = segments.filter(
      (segment) => segment.speaker_hint && segment.speaker_hint !== 'unknown'
    ).length;
    showCounts.missingBodies += exactCount;
    total.missingBodies += exactCount;
    continue;
  }
  const blobPath = join(r2BlobsPath, String(object.blob_id));
  invariant(existsSync(blobPath), `missing R2 blob: ${blobPath}`);
  const bodies = JSON.parse(readFileSync(blobPath, 'utf8'));
  const segments = segmentQuery.all(episode.id);
  const roster = rosterQuery.all(episode.id);
  const labelsByPerson = new Map();
  const peopleByLabel = new Map();
  const firstNameCounts = new Map();
  for (const person of roster) {
    const firstName = String(person.name).split(/\s+/)[0].toLocaleLowerCase('en-US');
    firstNameCounts.set(firstName, (firstNameCounts.get(firstName) ?? 0) + 1);
  }
  for (const person of roster) {
    if (String(episode.transcript_kind).endsWith('_coarse')) {
      continue;
    }
    const fullName = String(person.name);
    const firstName = fullName.split(/\s+/)[0];
    const names = [fullName];
    if (firstNameCounts.get(firstName.toLocaleLowerCase('en-US')) === 1) {
      names.push(firstName);
    }
    const identityPatterns = names.map(selfIdentificationPattern);
    for (const segment of segments) {
      if (segment.idx > 120 || segment.speaker_hint !== 'unknown') {
        continue;
      }
      const body = bodies[String(segment.idx)];
      const label = String(body?.diarLabel ?? '');
      const text = String(body?.text ?? '');
      if (!(label && text && identityPatterns.some((pattern) => pattern.test(text)))) {
        continue;
      }
      const labels = labelsByPerson.get(person.slug) ?? new Set();
      labels.add(label);
      labelsByPerson.set(person.slug, labels);
      const people = peopleByLabel.get(label) ?? new Set();
      people.add(person.slug);
      peopleByLabel.set(label, people);
    }
  }
  const recoveredLabels = new Set();
  for (const labels of labelsByPerson.values()) {
    if (labels.size !== 1) {
      continue;
    }
    const [label] = labels;
    if (peopleByLabel.get(label)?.size === 1) {
      recoveredLabels.add(label);
      recoveredMappings += 1;
    }
  }
  if (recoveredLabels.size > 0) {
    episodesWithRecovery += 1;
  }
  for (const segment of segments) {
    const body = bodies[String(segment.idx)];
    const text = String(body?.text ?? '');
    if (segment.speaker_hint && segment.speaker_hint !== 'unknown') {
      if (!text) {
        showCounts.missingBodies += 1;
        total.missingBodies += 1;
        continue;
      }
      increment(showCounts, text);
      increment(total, text);
      continue;
    }
    if (text) {
      increment(unknownShowCounts, text);
      increment(unknownTotal, text);
    } else {
      unknownShowCounts.missingBodies += 1;
      unknownTotal.missingBodies += 1;
    }
    if (!recoveredLabels.has(String(body?.diarLabel ?? ''))) {
      continue;
    }
    if (!text) {
      recoveredShowCounts.missingBodies += 1;
      recoveredTotal.missingBodies += 1;
      continue;
    }
    increment(recoveredShowCounts, text);
    increment(recoveredTotal, text);
  }
  if ((episodeOffset + 1) % 250 === 0) {
    process.stderr.write(`Audited ${episodeOffset + 1}/${episodes.length} episodes\n`);
  }
}

db.close();
r2.close();

const shows = [...byShow.entries()]
  .map(([show, counts]) => ({
    show,
    exact: counts,
    unknown: unknownByShow.get(show) ?? emptyCounts(),
    recovered: recoveredByShow.get(show) ?? emptyCounts(),
  }))
  .filter((row) => row.exact.exactSegments > 0 || row.recovered.exactSegments > 0)
  .sort(
    (left, right) =>
      right.exact.expandedUnion +
      right.recovered.expandedUnion -
      (left.exact.expandedUnion + left.recovered.expandedUnion)
  );
process.stdout.write(
  `${JSON.stringify(
    {
      transcriptEpisodes: episodes.length,
      exact: total,
      unknown: unknownTotal,
      selfIdentificationRecovery: {
        episodes: episodesWithRecovery,
        mappings: recoveredMappings,
        ...recoveredTotal,
      },
      combined: Object.fromEntries(
        Object.keys(total).map((key) => [key, total[key] + recoveredTotal[key]])
      ),
      shows,
    },
    null,
    2
  )}\n`
);
