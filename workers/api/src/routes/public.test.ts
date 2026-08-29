import { getTableColumns } from 'drizzle-orm';
import { describe, expect, it } from 'vitest';
import { claimTranscriptContext } from '../claim-context';
import { schema } from '../db';
import type { Env } from '../env';
import {
  isTrustedPublicShowSlug,
  publicClaimFields,
  publicRoute,
  WITHHELD_PUBLIC_SHOW_SLUGS,
} from './public';

describe('trusted public show boundary', () => {
  it('withholds shows whose diarized speakers remain unresolved', () => {
    expect(WITHHELD_PUBLIC_SHOW_SLUGS).toEqual(['odd-lots', 'tbpn']);
    expect(isTrustedPublicShowSlug('odd-lots')).toBe(false);
    expect(isTrustedPublicShowSlug('tbpn')).toBe(false);
  });

  it('keeps verified publisher-transcript shows public', () => {
    expect(isTrustedPublicShowSlug('lennys')).toBe(true);
    expect(isTrustedPublicShowSlug('lex-fridman')).toBe(true);
  });
});

const QUOTE = 'The only durable advantage is shipping something people keep using.';
const BEFORE = 'You asked what actually compounds for a small team.';
const OWN = `Honestly, ${QUOTE} Everything else is noise.`;
const AFTER = 'Which is why we stopped counting launches.';

type Row = Record<string, unknown>;

/**
 * D1 stub. Drizzle reads `.select(fields)` through `stmt.bind(...).raw()`, so
 * each stubbed table returns positional rows in its own select-list order.
 */
function stubD1(tables: { claim?: Row[]; segment?: Row[] }, seen: { params: unknown[][] }) {
  const claimColumns = Object.keys(publicClaimFields);
  const segmentColumns = ['episodeId', 'idx'];
  const evidenceColumns = Object.keys(getTableColumns(schema.claimEvidence));
  const referenceColumns = Object.keys(getTableColumns(schema.claimReferences));

  function plan(sql: string): { columns: string[]; rows: Row[] } {
    if (sql.includes('from "segments"')) {
      return { columns: segmentColumns, rows: tables.segment ?? [] };
    }
    if (sql.includes('from "claims"')) {
      return { columns: claimColumns, rows: tables.claim ?? [] };
    }
    if (sql.includes('from "claim_evidence"')) {
      return { columns: evidenceColumns, rows: [] };
    }
    return { columns: referenceColumns, rows: [] };
  }

  return {
    prepare: (sql: string) => ({
      bind: (...params: unknown[]) => {
        seen.params.push(params);
        const { columns, rows } = plan(sql);
        const positional = rows.map((row) => columns.map((column) => row[column] ?? null));
        return {
          all: async () => ({ results: rows }),
          first: async () => rows[0] ?? null,
          raw: async () => positional,
          run: async () => ({}),
        };
      },
    }),
  } as unknown as D1Database;
}

function stubR2(body: Record<string, unknown> | null, reads: { count: number }) {
  return {
    get: async (_key: string) => {
      reads.count += 1;
      return body === null ? null : { text: async () => JSON.stringify(body) };
    },
  } as unknown as R2Bucket;
}

const publishedClaim: Row = {
  assertion: 'Retention beats launch count.',
  attributionStatus: 'verified_speaker',
  claimType: 'belief',
  episodeId: 'episode-1',
  episodeTitle: 'What compounds',
  id: 'claim-1',
  quote: QUOTE,
  reviewStatus: 'published',
  showName: "Lenny's Podcast",
  showSlug: 'lennys',
  transcriptKind: 'publisher_json',
};

const segmentRow: Row = { episodeId: 'episode-1', idx: 4 };

const episodeBody = {
  '3': { cueMap: null, diarLabel: null, text: BEFORE },
  '4': { cueMap: null, diarLabel: null, text: OWN },
  '5': { cueMap: null, diarLabel: null, text: AFTER },
};

async function getClaim(
  path: string,
  options: { d1: D1Database; raw: R2Bucket }
): Promise<Response> {
  return await publicRoute.request(path, {}, {
    DB: options.d1,
    RAW: options.raw,
  } satisfies Env);
}

describe('claim transcript context', () => {
  it('anchors the verbatim quote inside the stored neighbouring segments', async () => {
    const context = await claimTranscriptContext(
      stubR2(episodeBody, { count: 0 }),
      'episode-1',
      4,
      QUOTE
    );

    expect(context).not.toBeNull();
    expect(context?.text).toContain(BEFORE);
    expect(context?.text).toContain(AFTER);
    expect(context?.text.slice(context.quoteStart, context.quoteEnd)).toBe(QUOTE);
  });

  it('returns no context when the quote cannot be found in the stored segment', async () => {
    const otherEpisode = {
      '4': { cueMap: null, diarLabel: null, text: 'A different transcript.' },
    };
    const context = await claimTranscriptContext(
      stubR2(otherEpisode, { count: 0 }),
      'episode-1',
      4,
      QUOTE
    );

    expect(context).toBeNull();
  });

  it('serves the context window when the episode body exists', async () => {
    const response = await getClaim('/claims/claim-1?context=1', {
      d1: stubD1({ claim: [publishedClaim], segment: [segmentRow] }, { params: [] }),
      raw: stubR2(episodeBody, { count: 0 }),
    });
    const payload = (await response.json()) as {
      context: { text: string; quoteStart: number; quoteEnd: number } | null;
    };

    expect(response.status).toBe(200);
    expect(payload.context?.text).toContain(BEFORE);
    expect(payload.context?.text.slice(payload.context.quoteStart, payload.context.quoteEnd)).toBe(
      QUOTE
    );
  });

  it('degrades to null context when the episode body is missing from R2', async () => {
    const response = await getClaim('/claims/claim-1?context=1', {
      d1: stubD1({ claim: [publishedClaim], segment: [segmentRow] }, { params: [] }),
      raw: stubR2(null, { count: 0 }),
    });
    const payload = (await response.json()) as { claim: { id: string }; context: unknown };

    expect(response.status).toBe(200);
    expect(payload.claim.id).toBe('claim-1');
    expect(payload.context).toBeNull();
  });

  it('does not touch R2 unless context is explicitly requested', async () => {
    const reads = { count: 0 };
    const response = await getClaim('/claims/claim-1', {
      d1: stubD1({ claim: [publishedClaim], segment: [segmentRow] }, { params: [] }),
      raw: stubR2(episodeBody, reads),
    });
    const payload = (await response.json()) as Record<string, unknown>;

    expect(response.status).toBe(200);
    expect('context' in payload).toBe(false);
    expect(reads.count).toBe(0);
  });

  it('keeps the published and trusted-show gate ahead of any transcript read', async () => {
    const reads = { count: 0 };
    const seen = { params: [] as unknown[][] };
    const response = await getClaim('/claims/claim-1?context=1', {
      d1: stubD1({ claim: [], segment: [segmentRow] }, seen),
      raw: stubR2(episodeBody, reads),
    });

    expect(response.status).toBe(404);
    await expect(response.json()).resolves.toEqual({ error: 'not_found' });
    expect(reads.count).toBe(0);
    expect(seen.params[0]).toEqual(
      expect.arrayContaining(['published', ...WITHHELD_PUBLIC_SHOW_SLUGS])
    );
  });
});
