import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DatabaseSync } from 'node:sqlite';
import {
  createValidationDatabase,
  invariant,
  rowsFor,
  stableReferenceId,
  upsertStatements,
} from './release-sql.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const snapshot = join(root, 'workers/api/.wrangler/audits/2026-08-27-recommendations-v10/v3');
const d1Path = join(
  snapshot,
  'd1/miniflare-D1DatabaseObject/94acfb1e34b1b291b64ee58e19b507b7acff78987cac2ffcb030d2b4935ce34e.sqlite'
);
const r2IndexPath = join(
  snapshot,
  'r2/miniflare-R2BucketObject/f2bf642351a580c8f559cdae7c13655dfcda32e398f22cc1261cfe0fa467f660.sqlite'
);
const r2BlobsPath = join(snapshot, 'r2/on-record-raw/blobs');
const reviewDir = join(
  root,
  'workers/api/.wrangler/audits/2026-08-27-insights-v5/analysis/final-v9'
);
const reviewedPath = join(reviewDir, 'recommendations-sorted.json');
const rejectedPath = join(reviewDir, 'recommendations-rejected.json');
const outDir = join(root, 'workers/api/.wrangler/releases/2026-08-29-trusted-v10');

for (const required of [d1Path, r2IndexPath, r2BlobsPath, reviewedPath, rejectedPath]) {
  invariant(existsSync(required), `missing trusted release input: ${required}`);
}

const reviewed = JSON.parse(readFileSync(reviewedPath, 'utf8'));
const rejected = JSON.parse(readFileSync(rejectedPath, 'utf8'));
const reviewedIds = new Set(reviewed.map((row) => String(row.claim_id)));
const rejectedIds = new Set(rejected.map((row) => String(row.claimId)));
invariant(reviewedIds.size === 166, `expected 166 v9 accepted claims, found ${reviewedIds.size}`);
invariant(rejectedIds.size === 28, `expected 28 v9 rejected claims, found ${rejectedIds.size}`);

const reviewedByClaim = new Map();
for (const row of reviewed) {
  const rows = reviewedByClaim.get(row.claim_id) ?? [];
  rows.push(row);
  reviewedByClaim.set(row.claim_id, rows);
}

const db = new DatabaseSync(d1Path, { readOnly: true });
const trustedWhere = "c.review_status = 'published' AND sh.slug NOT IN ('tbpn', 'odd-lots')";
const claims = db
  .prepare(
    `SELECT c.* FROM claims c
     JOIN episodes e ON e.id = c.episode_id
     JOIN shows sh ON sh.id = e.show_id
     WHERE ${trustedWhere}
     ORDER BY c.id`
  )
  .all();

for (const claim of claims) {
  const rows = reviewedByClaim.get(claim.id);
  if (!rows) {
    continue;
  }
  invariant(
    rows.every((row) => row.quote === claim.quote),
    `reviewed quote drift: ${claim.id}`
  );
  claim.assertion = [...new Set(rows.map((row) => String(row.assertion).trim()))]
    .filter(Boolean)
    .join(' ');
  claim.publish_reason = 'manual_review_approved_v9';
}

invariant(
  claims.every((claim) => !rejectedIds.has(String(claim.id))),
  'a manually rejected v9 claim remains published'
);
invariant(
  [...reviewedIds].every((id) => claims.some((claim) => claim.id === id)),
  'a manually accepted v9 claim is absent from the trusted corpus'
);

const localReferences = db
  .prepare(
    `SELECT cr.* FROM claim_references cr
     JOIN claims c ON c.id = cr.claim_id
     JOIN episodes e ON e.id = c.episode_id
     JOIN shows sh ON sh.id = e.show_id
     WHERE ${trustedWhere}
     ORDER BY cr.id`
  )
  .all()
  .filter((row) => !reviewedIds.has(String(row.claim_id)));
const reviewedReferences = reviewed.map((row) => ({
  id: stableReferenceId(row),
  claim_id: row.claim_id,
  kind: row.kind,
  name: row.name,
  role: row.role,
}));
const claimReferences = [...localReferences, ...reviewedReferences];

const tables = {
  people: rowsFor(db, 'people'),
  shows: rowsFor(db, 'shows'),
  topics: rowsFor(db, 'topics'),
  episodes: db
    .prepare(
      `SELECT id, show_id, guid, title, published_at, source_url, audio_url,
              youtube_video_id, duration_s, transcript_kind, raw_r2_key, raw_hash,
              status, status_detail, pipeline_version, created_at, updated_at
       FROM episodes ORDER BY id`
    )
    .all(),
  episode_people: rowsFor(db, 'episode_people'),
  segments: db
    .prepare(
      `SELECT sg.* FROM segments sg
       JOIN episodes e ON e.id = sg.episode_id
       JOIN shows sh ON sh.id = e.show_id
       WHERE sh.slug NOT IN ('tbpn', 'odd-lots')
       ORDER BY sg.episode_id, sg.idx`
    )
    .all(),
  claims,
  claim_evidence: db
    .prepare(
      `SELECT ce.* FROM claim_evidence ce
       JOIN claims c ON c.id = ce.claim_id
       JOIN episodes e ON e.id = c.episode_id
       JOIN shows sh ON sh.id = e.show_id
       WHERE ${trustedWhere}
       ORDER BY ce.id`
    )
    .all(),
  claim_topics: db
    .prepare(
      `SELECT ct.* FROM claim_topics ct
       JOIN claims c ON c.id = ct.claim_id
       JOIN episodes e ON e.id = c.episode_id
       JOIN shows sh ON sh.id = e.show_id
       WHERE ${trustedWhere}
       ORDER BY ct.claim_id, ct.topic_id`
    )
    .all(),
  claim_references: claimReferences,
};

const transcriptEpisodeIds = db
  .prepare(
    `SELECT DISTINCT e.id FROM episodes e
     JOIN shows sh ON sh.id = e.show_id
     JOIN segments sg ON sg.episode_id = e.id
     WHERE sh.slug NOT IN ('tbpn', 'odd-lots')
     ORDER BY e.id`
  )
  .all()
  .map((row) => String(row.id));
db.close();

const r2 = new DatabaseSync(r2IndexPath, { readOnly: true });
const objectQuery = r2.prepare('SELECT key, blob_id, size FROM _mf_objects WHERE key = ?');
const bodiesByEpisode = new Map();
const r2Uploads = [];
for (const episodeId of transcriptEpisodeIds) {
  const key = `episodes/${episodeId}/segments.json`;
  const object = objectQuery.get(key);
  invariant(object, `missing R2 segment object: ${episodeId}`);
  const file = join(r2BlobsPath, String(object.blob_id));
  invariant(existsSync(file), `missing R2 segment blob: ${episodeId}`);
  invariant(statSync(file).size === Number(object.size), `R2 segment size drift: ${episodeId}`);
  r2Uploads.push({ file, key, size: Number(object.size) });
  bodiesByEpisode.set(episodeId, JSON.parse(readFileSync(file, 'utf8')));
}
r2.close();

const segmentById = new Map(tables.segments.map((segment) => [segment.id, segment]));
for (const claim of claims) {
  const segment = segmentById.get(claim.segment_id);
  const body = bodiesByEpisode.get(claim.episode_id)?.[String(segment?.idx)];
  invariant(body && String(body.text).includes(claim.quote), `claim is not verbatim: ${claim.id}`);
}

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
const claimSegmentIds = new Set(claims.map((claim) => String(claim.segment_id)));
const claimSegments = tables.segments.filter((segment) => claimSegmentIds.has(String(segment.id)));
invariant(
  claimSegments.length === claimSegmentIds.size,
  'trusted claims reference segments missing from the release source'
);
const ftsStatements = [];
const ftsClaimBatchSize = 1000;
for (let offset = 0; offset < claims.length; offset += ftsClaimBatchSize) {
  const claimIds = claims.slice(offset, offset + ftsClaimBatchSize).map((claim) => {
    invariant(/^[0-9a-f-]+$/u.test(claim.id), `unsafe claim ID for FTS release: ${claim.id}`);
    return `'${claim.id}'`;
  });
  ftsStatements.push(`INSERT INTO claims_fts (claim_id, assertion, quote)
   SELECT c.id, c.assertion, c.quote
   FROM claims c
   WHERE c.id IN (${claimIds.join(', ')})
     AND NOT EXISTS (SELECT 1 FROM claims_fts f WHERE f.claim_id = c.id);`);
}
const releaseStatements = [
  ...insertOrder.flatMap((table) => upsertStatements(table, tables[table])),
  ...ftsStatements,
];
const releaseHeader = [
  '-- Incremental trusted-corpus release generated from the verified v10 snapshot.',
  '-- This file contains no DELETE statements and preserves newer production rows.',
];
const sql = [...releaseHeader, 'PRAGMA foreign_keys = ON;', ...releaseStatements, ''].join('\n\n');

mkdirSync(outDir, { recursive: true });
const sqlPath = join(outDir, 'release.sql');
writeFileSync(sqlPath, sql);
const claimPrerequisiteSql = [
  ...releaseHeader,
  '-- Minimal segment prerequisites for the claims layer.',
  'PRAGMA foreign_keys = ON;',
  ...upsertStatements('segments', claimSegments),
  '',
].join('\n\n');
const claimPrerequisitePath = join(outDir, 'claim-prerequisites.sql');
writeFileSync(claimPrerequisitePath, claimPrerequisiteSql);
const statementsPerChunk = 1000;
const maxChunkBytes = 12 * 1024 * 1024;

function writeStatementChunks({
  directory,
  filePrefix,
  label,
  maxBytes = maxChunkBytes,
  maxStatements = statementsPerChunk,
  statements,
}) {
  mkdirSync(directory, { recursive: true });
  const chunks = [];
  let chunkStatements = [];
  let chunkBytes = 0;

  function writeChunk() {
    const chunkNumber = chunks.length + 1;
    const chunkSql = [
      ...releaseHeader,
      `-- Ordered ${label} chunk ${chunkNumber}; safe to rerun because every write is an upsert.`,
      'PRAGMA foreign_keys = ON;',
      ...chunkStatements,
      '',
    ].join('\n\n');
    const chunkPath = join(directory, `${filePrefix}-${String(chunkNumber).padStart(2, '0')}.sql`);
    writeFileSync(chunkPath, chunkSql);
    chunks.push({
      bytes: Buffer.byteLength(chunkSql),
      path: chunkPath,
      sha256: createHash('sha256').update(chunkSql).digest('hex'),
      statements: chunkStatements.length,
    });
  }

  for (const statement of statements) {
    const statementBytes = Buffer.byteLength(statement) + 2;
    if (
      chunkStatements.length > 0 &&
      (chunkStatements.length >= maxStatements || chunkBytes + statementBytes > maxBytes)
    ) {
      writeChunk();
      chunkStatements = [];
      chunkBytes = 0;
    }
    chunkStatements.push(statement);
    chunkBytes += statementBytes;
  }
  if (chunkStatements.length > 0) {
    writeChunk();
  }
  return chunks;
}

const releaseChunks = writeStatementChunks({
  directory: join(outDir, 'release-chunks'),
  filePrefix: 'release',
  label: 'release',
  statements: releaseStatements,
});
const claimLayerChunks = writeStatementChunks({
  directory: join(outDir, 'claim-layer-chunks'),
  filePrefix: 'claims',
  label: 'claims layer',
  statements: upsertStatements('claims', claims),
});
const dependentLayerChunks = writeStatementChunks({
  directory: join(outDir, 'dependent-layer-chunks'),
  filePrefix: 'dependents',
  label: 'dependent layer',
  statements: [
    ...upsertStatements('claim_evidence', tables.claim_evidence),
    ...upsertStatements('claim_topics', tables.claim_topics),
    ...upsertStatements('claim_references', tables.claim_references),
    ...ftsStatements,
  ],
});
const claimEvidenceChunks = writeStatementChunks({
  directory: join(outDir, 'claim-evidence-chunks'),
  filePrefix: 'claim-evidence',
  label: 'claim evidence',
  maxBytes: 4 * 1024 * 1024,
  maxStatements: 200,
  statements: upsertStatements('claim_evidence', tables.claim_evidence),
});
const claimTopicChunks = writeStatementChunks({
  directory: join(outDir, 'claim-topic-chunks'),
  filePrefix: 'claim-topics',
  label: 'claim topics',
  maxBytes: 4 * 1024 * 1024,
  maxStatements: 200,
  statements: upsertStatements('claim_topics', tables.claim_topics),
});
const claimReferenceChunks = writeStatementChunks({
  directory: join(outDir, 'claim-reference-chunks'),
  filePrefix: 'claim-references',
  label: 'claim references',
  maxBytes: 4 * 1024 * 1024,
  maxStatements: 200,
  statements: upsertStatements('claim_references', tables.claim_references),
});
const ftsChunks = writeStatementChunks({
  directory: join(outDir, 'fts-chunks'),
  filePrefix: 'fts',
  label: 'FTS',
  maxStatements: 1,
  statements: ftsStatements,
});
writeFileSync(join(outDir, 'r2-uploads.json'), `${JSON.stringify(r2Uploads, null, 2)}\n`);

const validationDb = createValidationDatabase(root);
validationDb.exec(sql);
const scalar = (statement) => Number(validationDb.prepare(statement).get().n);
const validatedCounts = {
  catalogEpisodes: scalar('SELECT count(*) AS n FROM episodes'),
  people: scalar(
    "SELECT count(DISTINCT person_id) AS n FROM claims WHERE review_status = 'published'"
  ),
  publishedClaims: scalar("SELECT count(*) AS n FROM claims WHERE review_status = 'published'"),
  publishedReferences: scalar('SELECT count(*) AS n FROM claim_references'),
  representedEpisodes: scalar(
    "SELECT count(DISTINCT episode_id) AS n FROM claims WHERE review_status = 'published'"
  ),
  segments: scalar('SELECT count(*) AS n FROM segments'),
  shows: scalar('SELECT count(*) AS n FROM shows'),
  transcriptEpisodes: scalar('SELECT count(DISTINCT episode_id) AS n FROM segments'),
};
const foreignKeyViolations = validationDb.prepare('PRAGMA foreign_key_check').all();
const integrity = validationDb.prepare('PRAGMA integrity_check').get().integrity_check;
const duplicateQuoteGroups = scalar(
  "SELECT count(*) AS n FROM (SELECT quote FROM claims WHERE review_status = 'published' GROUP BY quote HAVING count(*) > 1)"
);
validationDb.close();

const namedItemGroups = new Set(
  claimReferences.map(
    (row) =>
      `${row.kind}\0${String(row.name).normalize('NFKC').replace(/\s+/gu, ' ').trim().toLowerCase()}`
  )
).size;
invariant(foreignKeyViolations.length === 0, 'trusted release has foreign-key violations');
invariant(integrity === 'ok', `trusted release integrity check failed: ${integrity}`);
invariant(duplicateQuoteGroups === 0, 'trusted release contains duplicate quote groups');
invariant(validatedCounts.publishedClaims === 30_561, 'trusted claim count drifted');
invariant(validatedCounts.publishedReferences === 1314, 'trusted reference count drifted');
invariant(validatedCounts.transcriptEpisodes === 1208, 'trusted transcript count drifted');

const manifest = {
  generatedAt: new Date().toISOString(),
  mode: 'incremental-upsert-no-delete',
  inputs: { rejectedReview: rejectedPath, reviewedRecommendations: reviewedPath, sourceDb: d1Path },
  counts: {
    ...validatedCounts,
    episodePeople: tables.episode_people.length,
    namedItemGroups,
    r2Bytes: r2Uploads.reduce((sum, upload) => sum + upload.size, 0),
    r2EpisodeObjects: r2Uploads.length,
  },
  releaseSql: {
    bytes: Buffer.byteLength(sql),
    claimPrerequisites: {
      bytes: Buffer.byteLength(claimPrerequisiteSql),
      path: claimPrerequisitePath,
      rows: claimSegments.length,
      sha256: createHash('sha256').update(claimPrerequisiteSql).digest('hex'),
    },
    claimLayerChunks,
    claimEvidenceChunks,
    claimReferenceChunks,
    claimTopicChunks,
    chunks: releaseChunks,
    dependentLayerChunks,
    ftsChunks,
    path: sqlPath,
    sha256: createHash('sha256').update(sql).digest('hex'),
  },
  validation: {
    duplicateQuoteGroups,
    foreignKeyViolations: foreignKeyViolations.length,
    integrity,
    verbatimClaims: claims.length,
  },
};
writeFileSync(join(outDir, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(JSON.stringify(manifest, null, 2));
