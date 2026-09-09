/// <reference types="node" />
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { describe, expect, it } from 'vitest';
import type { Env } from '../env';
import {
  publishedReferenceCount,
  publishedReferences,
  publicRoute,
  REFERENCE_SCAN_CEILING,
} from './public';

const migrations = new URL('../../../../packages/db/migrations/', import.meta.url);
const schemaSql = readdirSync(migrations)
  .filter((name) => name.endsWith('.sql'))
  .sort()
  .map((name) => readFileSync(new URL(name, migrations), 'utf8'))
  .join('\n');
const seedSql = `
INSERT INTO shows (id,slug,name,created_at) VALUES ('trusted','trusted','Synthetic show',0),('withheld','tbpn','Withheld',0);
INSERT INTO people (id,slug,name,created_at,updated_at) VALUES ('p1','p1','Synthetic speaker one',0,0),('p2','p2','Synthetic speaker two',0,0);
INSERT INTO episodes (id,show_id,guid,title,source_url,created_at,updated_at) VALUES
 ('e1','trusted','e1','Synthetic episode with display text','https://example.invalid/episode',0,0),
 ('e2','withheld','e2','Withheld episode','https://example.invalid/withheld',0,0);
`;

function fixture(size = 0) {
  const sqlite = new DatabaseSync(':memory:');
  sqlite.exec(schemaSql + seedSql);
  const statements: { sql: string; params: unknown[]; bytes: number }[] = [];
  const d1 = {
    prepare: (sql: string) => ({
      bind: (...params: (string | number | null)[]) => ({
        raw: async () => {
          const statement = sqlite.prepare(sql);
          statement.setReturnArrays(true);
          const rows = statement.all(...params);
          statements.push({ sql, params, bytes: Buffer.byteLength(JSON.stringify(rows)) });
          return rows;
        },
      }),
    }),
  } as unknown as D1Database;
  const corpusSql = `
WITH RECURSIVE n(i) AS (SELECT 0 UNION ALL SELECT i+1 FROM n WHERE i+1<${Math.max(size, 1)})
INSERT INTO segments (id,episode_id,idx,start_s,end_s,text) SELECT 's'||i,'e1',i,0,1,'I personally use Cursor every day.' FROM n;
WITH RECURSIVE n(i) AS (SELECT 0 UNION ALL SELECT i+1 FROM n WHERE i+1<${Math.max(size, 1)})
INSERT INTO claims (id,dedupe_hash,person_id,episode_id,segment_id,speaker_raw,claim_type,assertion,quote,extraction_confidence,speaker_confidence,confidence_band,review_status,pipeline_version,created_at,said_on)
SELECT 'c'||i,'c'||i,'p1','e1','s'||(i/2),'Synthetic speaker','recommendation',
 'Synthetic display assertion '||printf('%0300d',i),'I personally use Cursor every day.',1,1,'high','published','fixture',0,0 FROM n;
INSERT INTO claim_references (id,claim_id,kind,name,role) SELECT id,id,'app','Cursor','uses' FROM claims;
INSERT INTO claim_evidence (id,claim_id,episode_id,quote,deep_link_url,role)
SELECT id,id,'e1',quote,'https://example.invalid/'||printf('%0300d',0),'primary' FROM claims;
`;
  if (size) {
    sqlite.exec(corpusSql);
  }
  return { sqlite, d1, statements, corpusSql };
}

function add(
  sqlite: DatabaseSync,
  id: string,
  overrides: Record<string, string | number | null> = {}
) {
  const row = {
    id,
    dedupe_hash: id,
    person_id: 'p1',
    episode_id: 'e1',
    segment_id: id,
    speaker_raw: 'Synthetic speaker',
    claim_type: 'recommendation',
    assertion: 'Synthetic assertion',
    quote: 'I personally use Cursor every day.',
    extraction_confidence: 1,
    speaker_confidence: 1,
    confidence_band: 'high',
    review_status: 'published',
    pipeline_version: 'fixture',
    created_at: 0,
    said_on: 0,
    ...overrides,
  };
  if (row.segment_id) {
    sqlite
      .prepare(
        "INSERT OR IGNORE INTO segments (id,episode_id,idx,start_s,end_s,text) VALUES (?, 'e1', (SELECT count(*) FROM segments), 0, 1, ?)"
      )
      .run(row.segment_id, row.quote);
  }
  sqlite
    .prepare(
      `INSERT INTO claims (${Object.keys(row).join(',')}) VALUES (${Object.keys(row)
        .map(() => '?')
        .join(',')})`
    )
    .run(...Object.values(row));
  sqlite.prepare("INSERT INTO claim_references VALUES (?,?, 'app','Cursor','uses')").run(id, id);
  sqlite
    .prepare(
      "INSERT INTO claim_evidence (id,claim_id,episode_id,quote,role) VALUES (?,?, 'e1',?,'primary')"
    )
    .run(id, id, row.quote);
}

describe('published reference count over real SQLite joins', () => {
  it('counts transcript episodes once, preserving trust and inactive-show semantics', async () => {
    const { sqlite, d1, statements } = fixture();
    try {
      sqlite.exec(`
INSERT INTO shows (id,slug,name,active,created_at) VALUES ('inactive','inactive','Inactive trusted',0,0);
INSERT INTO episodes (id,show_id,guid,title,source_url,created_at,updated_at) VALUES
 ('empty','trusted','empty','No transcript','https://example.invalid/empty',0,0),
 ('inactive','inactive','inactive','Inactive transcript','https://example.invalid/inactive',0,0);
WITH RECURSIVE n(i) AS (SELECT 0 UNION ALL SELECT i+1 FROM n WHERE i<9999)
INSERT INTO segments (id,episode_id,idx,start_s,end_s,text) SELECT 's'||i,'e1',i,0,1,'Synthetic transcript' FROM n;
INSERT INTO segments (id,episode_id,idx,start_s,end_s,text) VALUES
 ('withheld','e2',0,0,1,'Withheld transcript'),('inactive','inactive',0,0,1,'Inactive transcript');
`);
      const response = await publicRoute.request('/stats', {}, { DB: d1 } as Env);
      expect(response.status).toBe(200);
      expect(((await response.json()) as { transcriptEpisodes: number }).transcriptEpisodes).toBe(
        2
      );
      const query = statements.find(({ sql }) => sql.includes('exists (select 1'));
      expect(query).toBeDefined();
      const plan = sqlite
        .prepare(`EXPLAIN QUERY PLAN ${query!.sql}`)
        .all(...(query!.params as string[]));
      expect(JSON.stringify(plan)).toMatch(
        /SEARCH segments(?: EXISTS)? USING COVERING INDEX segments_episode/
      );
      expect(JSON.stringify(plan)).not.toContain('SCAN segments');
    } finally {
      sqlite.close();
    }
  });

  it('matches the public list through trust, quote, role, speaker, prompt and dedupe gates', async () => {
    const { sqlite, d1 } = fixture();
    try {
      add(sqlite, 'valid');
      add(sqlite, 'duplicate', { segment_id: 'valid' });
      add(sqlite, 'other-person', { segment_id: 'valid', person_id: 'p2' });
      add(sqlite, 'unknown1', { segment_id: 'unknown', attribution_status: 'speaker_unverified' });
      add(sqlite, 'unknown2', {
        segment_id: 'unknown',
        attribution_status: 'speaker_unverified',
        person_id: 'p2',
      });
      add(sqlite, 'no-segment', { segment_id: null });
      add(sqlite, 'no-segment2', { segment_id: null });
      add(sqlite, 'withheld', { episode_id: 'e2' });
      add(sqlite, 'draft', { review_status: 'draft' });
      add(sqlite, 'unsupported', { quote: 'I do not recommend any software.' });
      add(sqlite, 'mentions');
      sqlite.exec("UPDATE claim_references SET role='mentions' WHERE id='mentions'");
      add(sqlite, 'no-evidence');
      sqlite.exec("DELETE FROM claim_evidence WHERE id='no-evidence'");
      add(sqlite, 'book-answer', {
        quote: 'The Beginning of Infinity.',
        prompt_version: 'extract-book-answers-v1',
      });
      sqlite.exec(
        "UPDATE claim_references SET kind='book',name='The Beginning of Infinity',role='recommends' WHERE id='book-answer'"
      );
      const rows = await publishedReferences(d1, {}, REFERENCE_SCAN_CEILING);
      expect(rows).toHaveLength(6);
      expect(rows.filter((row) => row.personId === null)).toHaveLength(1);
      expect(await publishedReferenceCount(d1)).toBe(rows.length);
      const response = await publicRoute.request('/stats', {}, {
        DB: d1,
        RAW: {},
      } as unknown as Env);
      expect(response.status).toBe(200);
      expect(((await response.json()) as { publishedReferences: number }).publishedReferences).toBe(
        6
      );
    } finally {
      sqlite.close();
    }
  });

  it('preserves the exact bounded window even with duplicate primary evidence', async () => {
    const { sqlite, d1, statements, corpusSql } = fixture(11_000);
    try {
      sqlite.exec(
        "INSERT INTO claim_evidence SELECT id||'-second',claim_id,episode_id,quote,timestamp_s,deep_link_url,role FROM claim_evidence"
      );
      const rows = await publishedReferences(d1, {}, REFERENCE_SCAN_CEILING);
      const count = await publishedReferenceCount(d1);
      expect(count).toBe(rows.length);
      // Lexical reference-id order cuts through one duplicate segment at the window edge.
      expect(count).toBe(5001);
      const [full, narrow] = statements;
      expect(narrow!.bytes).toBeLessThan(full!.bytes * 0.6);
      const project = process.env['REFERENCE_BENCH_OUTPUT'];
      if (project) {
        mkdirSync(project, { recursive: true });
        const samples: { full: number; narrow: number }[] = [];
        for (let i = 0; i < 7; i += 1) {
          const start = performance.now();
          await publishedReferences(d1, {}, REFERENCE_SCAN_CEILING);
          const middle = performance.now();
          await publishedReferenceCount(d1);
          samples.push({ full: middle - start, narrow: performance.now() - middle });
        }
        const plans = [full!, narrow!].map(({ sql, params }) =>
          sqlite.prepare(`EXPLAIN QUERY PLAN ${sql}`).all(...(params as (string | number)[]))
        );
        const literal = (value: unknown) =>
          typeof value === 'number' ? String(value) : `'${String(value).replaceAll("'", "''")}'`;
        const explain = [full!, narrow!]
          .map(({ sql, params }) => {
            let i = 0;
            return `EXPLAIN QUERY PLAN ${sql.replaceAll('?', () => {
              const value = literal(params[i]);
              i += 1;
              return value;
            })};`;
          })
          .join('\n');
        writeFileSync(`${project}/explain.sql`, explain);
        writeFileSync(
          `${project}/fixture.sql`,
          schemaSql +
            seedSql +
            corpusSql +
            "INSERT INTO claim_evidence SELECT id||'-second',claim_id,episode_id,quote,timestamp_s,deep_link_url,role FROM claim_evidence;"
        );
        writeFileSync(
          `${project}/receipt.json`,
          JSON.stringify(
            {
              syntheticClaims: 11_000,
              rawWindow: REFERENCE_SCAN_CEILING,
              count,
              bytes: { full: full!.bytes, narrow: narrow!.bytes },
              samples,
              plans,
            },
            null,
            2
          )
        );
      }
    } finally {
      sqlite.close();
    }
  });
});
