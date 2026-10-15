/// <reference types="node" />
import { readFileSync, readdirSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { describe, expect, it } from 'vitest';
import type { Env } from '../env';
import { publicRoute } from './public';

const migrations = new URL('../../../../packages/db/migrations/', import.meta.url);
const schemaSql = readdirSync(migrations)
  .filter((name) => name.endsWith('.sql'))
  .sort()
  .map((name) => readFileSync(new URL(name, migrations), 'utf8'))
  .join('\n');

function fixture() {
  const sqlite = new DatabaseSync(':memory:');
  sqlite.exec(schemaSql);
  sqlite.exec(`
    INSERT INTO shows (id, slug, name, has_published_claims, created_at) VALUES
      ('trusted', 'trusted', 'Trusted show', 1, 0),
      ('second', 'second', 'Another show', 1, 0),
      ('withheld', 'tbpn', 'Withheld show', 1, 0);
    INSERT INTO people (id, slug, name, created_at, updated_at) VALUES
      ('p1', 'p1', 'Speaker one', 0, 0), ('p2', 'p2', 'Speaker two', 0, 0);
    INSERT INTO episodes (id, show_id, guid, title, published_at, created_at, updated_at) VALUES
      ('a', 'trusted', 'a', 'Alpha episode', 1000, 0, 0),
      ('b', 'trusted', 'b', 'Beta episode', 1000, 0, 0),
      ('c', 'trusted', 'c', 'Draft episode', 900, 0, 0),
      ('d', 'trusted', 'd', 'Delta episode', 800, 0, 0),
      ('e', 'withheld', 'e', 'Withheld episode', 700, 0, 0),
      ('f', 'second', 'f', 'Other episode', 600, 0, 0),
      ('g', 'trusted', 'g', 'Gamma episode', 500, 0, 0);
    INSERT INTO claims (id, dedupe_hash, person_id, episode_id, speaker_raw, claim_type,
      assertion, quote, extraction_confidence, speaker_confidence, confidence_band,
      review_status, attribution_status, pipeline_version, created_at) VALUES
      ('a1', 'a1', 'p1', 'a', 'Speaker one', 'belief', 'A', 'A', 1, 1, 'high', 'published', 'verified_speaker', 'fixture', 0),
      ('a2', 'a2', 'p2', 'a', 'Unknown', 'belief', 'A', 'A', 1, 1, 'high', 'published', 'speaker_unverified', 'fixture', 0),
      ('a3', 'a3', 'p1', 'a', 'Speaker one', 'belief', 'A', 'A', 1, 1, 'high', 'draft', 'verified_speaker', 'fixture', 0),
      ('b1', 'b1', 'p2', 'b', 'Speaker two', 'belief', 'B', 'B', 1, 1, 'high', 'published', 'verified_speaker', 'fixture', 0),
      ('c1', 'c1', 'p1', 'c', 'Speaker one', 'belief', 'C', 'C', 1, 1, 'high', 'draft', 'verified_speaker', 'fixture', 0),
      ('d1', 'd1', 'p1', 'd', 'Speaker one', 'belief', 'D', 'D', 1, 1, 'high', 'published', 'verified_speaker', 'fixture', 0),
      ('e1', 'e1', 'p1', 'e', 'Speaker one', 'belief', 'E', 'E', 1, 1, 'high', 'published', 'verified_speaker', 'fixture', 0),
      ('f1', 'f1', 'p2', 'f', 'Speaker two', 'belief', 'F', 'F', 1, 1, 'high', 'published', 'verified_speaker', 'fixture', 0),
      ('g1', 'g1', 'p1', 'g', 'Speaker one', 'belief', 'G', 'G', 1, 1, 'high', 'published', 'verified_speaker', 'fixture', 0);
  `);
  const statements: Array<{ sql: string; params: (string | number | null)[] }> = [];
  const d1 = {
    prepare: (sql: string) => ({
      bind: (...params: (string | number | null)[]) => ({
        raw: async () => {
          statements.push({ sql, params });
          const statement = sqlite.prepare(sql);
          statement.setReturnArrays(true);
          return statement.all(...params);
        },
      }),
    }),
  } as unknown as D1Database;
  return { d1, sqlite, statements };
}

type SourcesPayload = {
  sources: Array<{ id: string; claimCount: number; peopleCount: number; showSlug: string }>;
  total: number;
  publishers: Array<{ name: string; slug: string }>;
};

describe('bounded source candidate page', () => {
  it.each([
    ['/sources?limit=2', ['a', 'b'], 5],
    ['/sources?limit=2&offset=1', ['b', 'd'], 5],
    ['/sources?limit=2&q=episode&show=second', ['f'], 1],
    ['/sources?limit=2&q=Delta', ['d'], 1],
    ['/sources?limit=2&show=tbpn', [], 0],
    ['/sources?limit=2&offset=10', [], 5],
  ])('%s retains published, trusted, filtered and paginated results', async (path, ids, total) => {
    const { d1, sqlite, statements } = fixture();
    try {
      const response = await publicRoute.request(path, {}, { DB: d1, RAW: {} } as Env);
      const payload = (await response.json()) as SourcesPayload;
      expect(response.status).toBe(200);
      expect(payload.sources.map((source) => source.id)).toEqual(ids);
      expect(payload.total).toBe(total);
      expect(payload.publishers).toEqual([
        { name: 'Another show', slug: 'second' },
        { name: 'Trusted show', slug: 'trusted' },
      ]);
      const list = statements.find((statement) =>
        statement.sql.includes('with "candidate_sources"')
      );
      expect(list?.sql).toMatch(/with "candidate_sources" as \(.+ limit \?(?: offset \?)?\)/s);
    } finally {
      sqlite.close();
    }
  });

  it('counts only published claims and verified distinct speakers after selecting candidates', async () => {
    const { d1, sqlite, statements } = fixture();
    try {
      const response = await publicRoute.request('/sources?limit=2', {}, {
        DB: d1,
        RAW: {},
      } as Env);
      const payload = (await response.json()) as SourcesPayload;
      expect(
        payload.sources.map((source) => ({
          id: source.id,
          claimCount: source.claimCount,
          peopleCount: source.peopleCount,
          showSlug: source.showSlug,
        }))
      ).toEqual([
        { id: 'a', claimCount: 2, peopleCount: 1, showSlug: 'trusted' },
        { id: 'b', claimCount: 1, peopleCount: 1, showSlug: 'trusted' },
      ]);
      const list = statements.find((statement) =>
        statement.sql.includes('with "candidate_sources"')
      );
      const plan = sqlite
        .prepare(`EXPLAIN QUERY PLAN ${list?.sql}`)
        .all(...(list?.params ?? []))
        .map((row) => row['detail'] as string);
      expect(plan).toContainEqual(expect.stringContaining('episodes_published_idx'));
      expect(plan).toContainEqual(expect.stringContaining('claims_episode_idx'));
    } finally {
      sqlite.close();
    }
  });
});

describe('public people count', () => {
  it('counts distinct people with published, trusted, verified claims', async () => {
    const { d1, sqlite, statements } = fixture();
    try {
      const response = await publicRoute.request('/people?limit=8', {}, { DB: d1, RAW: {} } as Env);
      const payload = (await response.json()) as {
        people: Array<{ id: string; claimCount: number; sourceCount: number }>;
        total: number;
      };
      expect(response.status).toBe(200);
      expect(payload.total).toBe(2);
      expect(
        payload.people.map(({ id, claimCount, sourceCount }) => ({ id, claimCount, sourceCount }))
      ).toEqual([
        { id: 'p1', claimCount: 3, sourceCount: 3 },
        { id: 'p2', claimCount: 2, sourceCount: 2 },
      ]);
      const count = statements.find((statement) =>
        statement.sql.startsWith('select count(*) from "people"')
      );
      const plan = sqlite
        .prepare(`EXPLAIN QUERY PLAN ${count?.sql}`)
        .all(...(count?.params ?? []))
        .map((row) => row['detail'] as string);
      expect(plan).toContainEqual(expect.stringContaining('claims_person_status_idx'));
    } finally {
      sqlite.close();
    }
  });

  it('applies a person filter before the existence count', async () => {
    const { d1, sqlite } = fixture();
    try {
      const response = await publicRoute.request('/people?limit=8&q=Speaker%20two', {}, {
        DB: d1,
        RAW: {},
      } as Env);
      const payload = (await response.json()) as { people: Array<{ id: string }>; total: number };
      expect(payload.people.map(({ id }) => id)).toEqual(['p2']);
      expect(payload.total).toBe(1);
    } finally {
      sqlite.close();
    }
  });
});
