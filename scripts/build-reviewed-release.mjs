import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DatabaseSync } from 'node:sqlite';
import {
  createValidationDatabase,
  insertStatements,
  invariant,
  rowsFor,
  stableReferenceId,
} from './release-sql.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const auditRoot = join(root, 'workers/api/.wrangler/audits');
const sourceDb = join(
  auditRoot,
  '2026-08-27-correctness-v9/v3/d1/miniflare-D1DatabaseObject/94acfb1e34b1b291b64ee58e19b507b7acff78987cac2ffcb030d2b4935ce34e.sqlite'
);
const r2Index = join(
  auditRoot,
  '2026-08-27-correctness-v9/v3/r2/miniflare-R2BucketObject/f2bf642351a580c8f559cdae7c13655dfcda32e398f22cc1261cfe0fa467f660.sqlite'
);
const r2Blobs = join(auditRoot, '2026-08-27-correctness-v9/v3/r2/on-record-raw/blobs');
const finalDir = join(auditRoot, '2026-08-27-insights-v5/analysis/final-v9');
const reviewedPath = join(finalDir, 'recommendations-sorted.json');
const outDir = join(root, 'workers/api/.wrangler/releases/2026-08-27-reviewed-v9');

function quoteIdentifier(value) {
  return `"${String(value).replaceAll('"', '""')}"`;
}

for (const required of [sourceDb, r2Index, reviewedPath]) {
  invariant(existsSync(required), `missing release input: ${required}`);
}

const reviewed = JSON.parse(readFileSync(reviewedPath, 'utf8'));
invariant(Array.isArray(reviewed), 'reviewed recommendations must be an array');

const claimIds = [...new Set(reviewed.map((row) => String(row.claim_id)))].sort();
invariant(claimIds.length === 166, `expected 166 accepted claims, found ${claimIds.length}`);
invariant(reviewed.length === 189, `expected 189 accepted references, found ${reviewed.length}`);

const db = new DatabaseSync(sourceDb, { readOnly: true });
const placeholders = claimIds.map(() => '?').join(',');
const claims = rowsFor(db, 'claims', `id IN (${placeholders})`, claimIds);
invariant(claims.length === claimIds.length, 'one or more accepted claims are absent from D1');

const reviewedByClaim = new Map();
for (const row of reviewed) {
  const rows = reviewedByClaim.get(row.claim_id) ?? [];
  rows.push(row);
  reviewedByClaim.set(row.claim_id, rows);
}

for (const claim of claims) {
  const rows = reviewedByClaim.get(claim.id) ?? [];
  invariant(rows.length > 0, `claim ${claim.id} has no reviewed reference`);
  invariant(
    rows.every((row) => row.quote === claim.quote),
    `claim ${claim.id} quote drift`
  );
  const assertions = [...new Set(rows.map((row) => String(row.assertion).trim()))].filter(Boolean);
  claim.assertion = assertions.join(' ');
  claim.review_status = 'published';
  claim.publish_reason = 'manual_review_approved_v9';
}

const episodeIds = [...new Set(claims.map((claim) => String(claim.episode_id)))].sort();
const segmentIds = [...new Set(claims.map((claim) => String(claim.segment_id)))].sort();
invariant(!segmentIds.includes('null'), 'an accepted claim has no segment anchor');

const tables = {
  people: rowsFor(db, 'people'),
  shows: rowsFor(db, 'shows'),
  topics: rowsFor(db, 'topics'),
  episodes: rowsFor(db, 'episodes').map((row) => ({ ...row, description: null })),
  episode_people: rowsFor(db, 'episode_people'),
  segments: rowsFor(db, 'segments', `id IN (${segmentIds.map(() => '?').join(',')})`, segmentIds),
  claims,
  claim_evidence: rowsFor(db, 'claim_evidence', `claim_id IN (${placeholders})`, claimIds),
  claim_topics: rowsFor(db, 'claim_topics', `claim_id IN (${placeholders})`, claimIds),
  claim_references: reviewed.map((row) => ({
    claim_id: row.claim_id,
    id: stableReferenceId(row),
    kind: row.kind,
    name: row.name,
    role: row.role,
  })),
};

invariant(tables.shows.length === 25, `expected 25 shows, found ${tables.shows.length}`);
invariant(
  tables.episodes.length === 10_305,
  `expected 10305 episodes, found ${tables.episodes.length}`
);
invariant(tables.segments.length === segmentIds.length, 'accepted segment anchors are incomplete');
invariant(
  tables.claim_evidence.length === claimIds.length,
  'accepted claims must each have one evidence row'
);

const r2 = new DatabaseSync(r2Index, { readOnly: true });
const r2Uploads = [];
for (const episodeId of episodeIds) {
  const key = `episodes/${episodeId}/segments.json`;
  const object = r2.prepare('SELECT key, blob_id, size FROM _mf_objects WHERE key = ?').get(key);
  invariant(object, `missing R2 segment object for ${episodeId}`);
  const file = join(r2Blobs, String(object.blob_id));
  invariant(existsSync(file), `missing R2 blob for ${episodeId}`);
  r2Uploads.push({ file, key, size: Number(object.size) });
}

for (const claim of claims) {
  const episodeKey = `episodes/${claim.episode_id}/segments.json`;
  const upload = r2Uploads.find((row) => row.key === episodeKey);
  const bodies = JSON.parse(readFileSync(upload.file, 'utf8'));
  const segment = tables.segments.find((row) => row.id === claim.segment_id);
  const body = bodies[String(segment.idx)];
  invariant(body && String(body.text).includes(claim.quote), `claim ${claim.id} is not verbatim`);
}

db.close();
r2.close();

mkdirSync(outDir, { recursive: true });

const deleteOrder = [
  'llm_runs',
  'ingest_runs',
  'claim_references',
  'claim_topics',
  'claim_evidence',
  'claims_fts',
  'claims',
  'segments',
  'episode_people',
  'episodes',
  'topics',
  'shows',
  'people',
];
const insertOrder = [
  'people',
  'shows',
  'topics',
  'episodes',
  'episode_people',
  'segments',
  'claims',
  'claim_evidence',
  'claim_topics',
  'claim_references',
];

const sql = [
  '-- Generated from the manually reviewed 2026-08-27 v9 evidence snapshot.',
  '-- Production must be backed up before this file is applied.',
  ...deleteOrder.map((table) => `DELETE FROM ${quoteIdentifier(table)};`),
  ...insertOrder.flatMap((table) => insertStatements(table, tables[table])),
  "INSERT INTO claims_fts (claim_id, assertion, quote) SELECT id, assertion, quote FROM claims WHERE review_status = 'published';",
  '',
].join('\n\n');

const sqlPath = join(outDir, 'release.sql');
writeFileSync(sqlPath, sql);
writeFileSync(join(outDir, 'r2-uploads.json'), `${JSON.stringify(r2Uploads, null, 2)}\n`);

const validationDb = createValidationDatabase(root);
validationDb.exec(sql);
const validatedCounts = {
  episodes: validationDb.prepare('SELECT count(*) AS n FROM episodes').get().n,
  people: validationDb.prepare('SELECT count(*) AS n FROM people').get().n,
  publishedClaims: validationDb
    .prepare("SELECT count(*) AS n FROM claims WHERE review_status = 'published'")
    .get().n,
  publishedReferences: validationDb.prepare('SELECT count(*) AS n FROM claim_references').get().n,
  segments: validationDb.prepare('SELECT count(*) AS n FROM segments').get().n,
  shows: validationDb.prepare('SELECT count(*) AS n FROM shows').get().n,
};
const foreignKeyViolations = validationDb.prepare('PRAGMA foreign_key_check').all();
const integrity = validationDb.prepare('PRAGMA integrity_check').get().integrity_check;
validationDb.close();
invariant(foreignKeyViolations.length === 0, 'release SQL has foreign-key violations');
invariant(integrity === 'ok', `release SQL integrity check failed: ${integrity}`);
invariant(
  Number(validatedCounts.publishedClaims) === claimIds.length &&
    Number(validatedCounts.publishedReferences) === reviewed.length,
  'release SQL validation counts drifted'
);

const manifest = {
  generatedAt: new Date().toISOString(),
  inputs: {
    recommendations: reviewedPath,
    sourceDb,
  },
  counts: {
    episodes: tables.episodes.length,
    episodePeople: tables.episode_people.length,
    people: tables.people.length,
    publishedClaims: tables.claims.length,
    publishedReferences: tables.claim_references.length,
    r2EpisodeObjects: r2Uploads.length,
    segments: tables.segments.length,
    shows: tables.shows.length,
  },
  releaseSql: {
    bytes: Buffer.byteLength(sql),
    sha256: createHash('sha256').update(sql).digest('hex'),
  },
  validation: {
    counts: validatedCounts,
    foreignKeyViolations: foreignKeyViolations.length,
    integrity,
  },
};
writeFileSync(join(outDir, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(JSON.stringify(manifest, null, 2));
