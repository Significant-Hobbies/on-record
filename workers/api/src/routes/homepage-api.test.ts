// The API test imports the web helper without Astro's generated environment types.
declare global {
  interface ImportMetaEnv {
    readonly DEV: boolean;
    readonly PUBLIC_API_BASE?: string;
  }
  interface ImportMeta {
    readonly env: ImportMetaEnv;
  }
}

import { describe, expect, it, vi } from 'vitest';
import { type Claim, homepageEvidence } from '../../../../apps/web/src/lib/api';

const claim: Claim = {
  id: 'claim-1',
  assertion: 'A synthetic published assertion.',
  attributionStatus: 'verified_speaker',
  claimType: 'belief',
  quote: 'A short synthetic transcript quote.',
  reviewStatus: 'published',
  sourceUrl: 'https://example.com/episode',
  saidOn: '2025-01-01',
};

function api(...responses: (Response | Error)[]) {
  const fetch = vi.fn(async (_input: string, _init?: RequestInit) => {
    const response = responses.shift();
    if (response instanceof Error) {
      throw response;
    }
    if (!response) {
      throw new Error('Unexpected request');
    }
    return response;
  });
  return { env: { API: { fetch } }, fetch };
}

describe('homepage public evidence', () => {
  it('fills existing slots even when no quotes meet the editorial length preference', async () => {
    const claims = Array.from({ length: 8 }, (_, index) => ({ ...claim, id: `claim-${index}` }));
    const { env, fetch } = api(Response.json({ claims }));
    const evidence = await homepageEvidence(env, { timeoutMs: 1200 });

    expect(evidence.status).toBe('ready');
    expect(evidence.origin).toBe('recent');
    expect(evidence.heroClaim).toEqual(claims[0]);
    expect(evidence.latestClaims.map((row) => row.id)).toEqual([
      'claim-1',
      'claim-2',
      'claim-3',
      'claim-4',
    ]);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0]?.[0]).toContain('/api/search');
    expect(fetch.mock.calls[0]?.[1]?.signal).toBeInstanceOf(AbortSignal);
  });

  it('keeps a genuine empty response empty without substituting a topical sample', async () => {
    const { env, fetch } = api(Response.json({ claims: [], evidence: 'insufficient' }));
    expect(await homepageEvidence(env)).toEqual({
      status: 'empty',
      origin: 'recent',
      heroClaim: undefined,
      latestClaims: [],
    });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each([
    new Error('network unavailable'),
    new Error('timeout'),
    new Response('unavailable', { status: 503 }),
    new Response('not JSON'),
    Response.json(null),
    Response.json({}),
    Response.json({ claims: 'not an array' }),
    Response.json({ claims: [{ ...claim, quote: null }] }),
    Response.json({ claims: [{ ...claim, episodeTitle: {} }] }),
    Response.json({ claims: [{ ...claim, reviewStatus: 'pending' }] }),
    Response.json({ claims: [{ ...claim, attributionStatus: 'guessed' }] }),
  ])(
    'uses labeled public search evidence after a failed or malformed stream: %#',
    async (failure) => {
      const unverified = { ...claim, attributionStatus: 'speaker_unverified' as const };
      const { env, fetch } = api(
        failure,
        Response.json({ claims: [unverified, { ...claim, id: 'claim-2' }] })
      );
      const evidence = await homepageEvidence(env);

      expect(evidence.status).toBe('ready');
      expect(evidence.origin).toBe('search');
      expect(evidence.heroClaim).toEqual(unverified);
      expect(evidence.heroClaim?.saidOn).toBe('2025-01-01');
      expect(evidence.latestClaims).toHaveLength(1);
      expect(fetch).toHaveBeenCalledTimes(2);
      expect(fetch.mock.calls[1]?.[0]).toContain('/api/search?q=AI');
    }
  );

  it.each([
    new Error('network unavailable'),
    new Response('unavailable', { status: 503 }),
    new Response('invalid JSON'),
    Response.json({ claims: null }),
    Response.json({ claims: [{ ...claim, quote: '' }] }),
    Response.json({ claims: [] }),
  ])(
    'does not call the corpus empty when the failed stream has no usable fallback: %#',
    async (fallback) => {
      const { env, fetch } = api(new Error('stream failed'), fallback);
      expect(await homepageEvidence(env)).toEqual({
        status: 'unavailable',
        origin: 'search',
        latestClaims: [],
      });
      expect(fetch).toHaveBeenCalledTimes(2);
    }
  );

  it('prefers readable examples but retains other published evidence for remaining slots', async () => {
    const readable = {
      ...claim,
      id: 'readable',
      quote:
        'A synthetic verbatim excerpt long enough to read as a complete homepage example, with its source retained.',
    };
    const { env } = api(Response.json({ claims: [claim, readable] }));
    const evidence = await homepageEvidence(env);
    expect(evidence.heroClaim?.id).toBe('readable');
    expect(evidence.latestClaims).toEqual([claim]);
  });
});
