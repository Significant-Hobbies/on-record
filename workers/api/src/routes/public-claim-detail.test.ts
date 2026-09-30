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

function fixture(
  overrides: { reviewStatus?: string; personStatus?: string; showSlug?: string } = {}
) {
  const sqlite = new DatabaseSync(':memory:');
  sqlite.exec(schemaSql);
  sqlite
    .prepare("INSERT INTO shows (id,slug,name,created_at) VALUES ('show',?,'Test show',0)")
    .run(overrides.showSlug ?? 'trusted');
  sqlite
    .prepare(
      "INSERT INTO people (id,slug,name,status,created_at,updated_at) VALUES ('person','speaker','Test speaker',?,0,0)"
    )
    .run(overrides.personStatus ?? 'active');
  sqlite.exec(`
    INSERT INTO episodes (id,show_id,guid,title,source_url,transcript_kind,created_at,updated_at)
    VALUES ('episode','show','episode-guid','Test episode','https://example.invalid/episode','youtube_captions',0,0);
    INSERT INTO segments (id,episode_id,idx,start_s,end_s,text)
    VALUES ('segment','episode',0,0,1,'I use Cursor every day.');
  `);
  sqlite
    .prepare(`INSERT INTO claims (
      id,dedupe_hash,person_id,episode_id,segment_id,speaker_raw,claim_type,assertion,quote,
      extraction_confidence,speaker_confidence,confidence_band,review_status,pipeline_version,created_at,said_on
    ) VALUES ('claim','hash','person','episode','segment','Test speaker','belief','Test assertion',
      'I use Cursor every day.',1,1,'high',?,'fixture',0,0)`)
    .run(overrides.reviewStatus ?? 'published');
  sqlite.exec(`
    INSERT INTO claim_evidence (id,claim_id,episode_id,quote,timestamp_s,deep_link_url,role)
    VALUES ('evidence','claim','episode','I use Cursor every day.',12.5,'https://youtube.invalid/watch?t=12','primary');
    INSERT INTO claim_references (id,claim_id,kind,name,role) VALUES
      ('reference','claim','app','Cursor','uses'),
      ('non-actionable','claim','app','Private note','mentions');
  `);
  const statements: string[] = [];
  const DB = {
    prepare(sql: string) {
      return {
        bind(...params: (string | number | null)[]) {
          return {
            async raw() {
              statements.push(sql);
              const statement = sqlite.prepare(sql);
              statement.setReturnArrays(true);
              return statement.all(...params);
            },
          };
        },
      };
    },
  } as unknown as D1Database;
  const RAW = { get: async () => null } as unknown as R2Bucket;
  return { DB, RAW, sqlite, statements };
}

async function getClaim(f: ReturnType<typeof fixture>) {
  return await publicRoute.request('/claims/claim', {}, { DB: f.DB, RAW: f.RAW } as Env);
}

describe('public claim detail uses one publication-gated D1 read', () => {
  it('returns the same evidence/reference fields and excludes non-actionable references', async () => {
    const f = fixture();
    try {
      const response = await getClaim(f);
      const payload = (await response.json()) as {
        claim: { id: string; assertion: string; transcriptKind: string };
        evidence: Record<string, unknown>[];
        references: Record<string, unknown>[];
      };

      expect(response.status).toBe(200);
      expect(payload.claim).toMatchObject({ id: 'claim', assertion: 'Test assertion' });
      expect(payload.evidence).toEqual([
        {
          claimId: 'claim',
          deepLinkUrl: 'https://youtube.invalid/watch?t=12',
          episodeId: 'episode',
          id: 'evidence',
          quote: 'I use Cursor every day.',
          role: 'primary',
          timestampS: 12.5,
        },
      ]);
      expect(payload.references).toEqual([{ kind: 'app', name: 'Cursor', role: 'uses' }]);
      expect(f.statements).toHaveLength(1);
      expect(f.statements[0]).toContain('json_group_array');
      expect(f.statements[0]).toContain('review_status');
      expect(f.statements[0]).toContain('people');
      expect(f.statements[0]).toContain('shows');
    } finally {
      f.sqlite.close();
    }
  });

  it.each([
    ['unpublished', { reviewStatus: 'held' }],
    ['inactive speaker', { personStatus: 'hidden' }],
    ['withheld show', { showSlug: 'tbpn' }],
  ])('keeps the publication gate for %s', async (_label, overrides) => {
    const f = fixture(overrides);
    try {
      const response = await getClaim(f);
      expect(response.status).toBe(404);
      await expect(response.json()).resolves.toEqual({ error: 'not_found' });
      expect(f.statements).toHaveLength(1);
    } finally {
      f.sqlite.close();
    }
  });

  it('returns empty arrays when a visible claim has no child rows', async () => {
    const f = fixture();
    try {
      f.sqlite.exec(
        "DELETE FROM claim_evidence WHERE claim_id='claim'; DELETE FROM claim_references WHERE claim_id='claim';"
      );
      const response = await getClaim(f);
      const payload = (await response.json()) as { evidence: unknown[]; references: unknown[] };

      expect(response.status).toBe(200);
      expect(payload.evidence).toEqual([]);
      expect(payload.references).toEqual([]);
      expect(f.statements).toHaveLength(1);
    } finally {
      f.sqlite.close();
    }
  });
});
