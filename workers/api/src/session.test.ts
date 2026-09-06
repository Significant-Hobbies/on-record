import { afterEach, describe, expect, it, vi } from 'vitest';
import { anchorFor, D1_BOOKMARK_HEADER, openSession, sessionAsDatabase } from './session';

const { publicCacheGeneration } = vi.hoisted(() => ({
  publicCacheGeneration: vi.fn(async () => 1),
}));

vi.mock('./db', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./db')>();
  return { ...actual, publicCacheGeneration };
});

afterEach(() => {
  vi.resetModules();
  vi.unstubAllGlobals();
  publicCacheGeneration.mockReset().mockResolvedValue(1);
});

describe('session anchor', () => {
  it('leaves public reads unconstrained so any consistent replica can answer', () => {
    expect(anchorFor(undefined, false)).toBe('first-unconstrained');
    expect(anchorFor('   ', false)).toBe('first-unconstrained');
  });

  it('anchors admin requests to the primary so a moderator reads their own write', () => {
    expect(anchorFor(undefined, true)).toBe('first-primary');
  });

  it('prefers a client bookmark over either default', () => {
    expect(anchorFor('bookmark-42', false)).toBe('bookmark-42');
    expect(anchorFor(' bookmark-42 ', true)).toBe('bookmark-42');
  });
});

/**
 * D1 stub in the shape the rest of this suite uses: `prepare().bind()` down to
 * `all/first/raw/run`. `withSession` hands back a session recording every
 * query issued through it, so a test can prove a call site went through the
 * session rather than around it.
 */
function stubD1(bookmark: string | null = 'bookmark-1') {
  const anchors: Array<string | undefined> = [];
  const sessionQueries: string[] = [];
  const directQueries: string[] = [];

  const statement = (sql: string, sink: string[]) => {
    sink.push(sql);
    const bound = {
      bind: () => bound,
      all: async () => ({ results: [] }),
      first: async () => null,
      raw: async () => [],
      run: async () => ({}),
    };
    return bound;
  };

  const d1 = {
    prepare: (sql: string) => statement(sql, directQueries),
    batch: async () => [],
    exec: async () => ({ count: 0, duration: 0 }),
    dump: async () => new ArrayBuffer(0),
    withSession: (anchor?: string) => {
      anchors.push(anchor);
      return {
        prepare: (sql: string) => statement(sql, sessionQueries),
        batch: async () => [],
        getBookmark: () => bookmark,
      };
    },
  };

  return { anchors, d1: d1 as unknown as D1Database, directQueries, sessionQueries };
}

describe('opening a session', () => {
  it('routes queries through the session while leaving exec on the raw binding', async () => {
    const { d1, directQueries, sessionQueries } = stubD1();
    const session = openSession(d1, 'first-unconstrained');
    expect(session).not.toBeNull();

    const wrapped = sessionAsDatabase(d1, session as D1DatabaseSession);
    wrapped.prepare('select 1');
    await wrapped.exec('pragma foreign_keys = on');

    expect(sessionQueries).toEqual(['select 1']);
    expect(directQueries).toEqual([]);
  });

  it('falls back to the plain binding when it cannot make a session', () => {
    expect(openSession({} as unknown as D1Database, 'first-unconstrained')).toBeNull();
  });
});

async function requestWith(
  url: string,
  init: RequestInit | undefined,
  d1: D1Database,
  cached: Response | null = Response.json({ cached: true })
) {
  const match = vi.fn(async () => cached ?? undefined);
  vi.stubGlobal('caches', { open: vi.fn(async () => ({ match, put: vi.fn() })) });
  const { default: app } = await import('./index');
  return app.request(url, init, { DB: d1 } as unknown as import('./env').Env);
}

describe('sessions across the app', () => {
  it('opens an unconstrained session for a public read', async () => {
    const { anchors, d1 } = stubD1();
    await requestWith('https://api.podcasts.highsignal.app/api/stats', undefined, d1);
    expect(anchors).toEqual(['first-unconstrained']);
  });

  it('opens a primary-anchored session for an admin request', async () => {
    const { anchors, d1 } = stubD1();
    await requestWith('https://api.podcasts.highsignal.app/admin/claims', undefined, d1);
    expect(anchors).toEqual(['first-primary']);
  });

  it('anchors to the bookmark a client sends back', async () => {
    const { anchors, d1 } = stubD1();
    await requestWith(
      'https://api.podcasts.highsignal.app/api/stats',
      { headers: { [D1_BOOKMARK_HEADER]: 'bookmark-99' } },
      d1
    );
    expect(anchors).toEqual(['bookmark-99']);
  });

  it('returns the session bookmark so the next request can anchor to it', async () => {
    const { d1 } = stubD1('bookmark-7');
    const response = await requestWith('https://api.podcasts.highsignal.app/health', undefined, d1);
    expect(response.headers.get(D1_BOOKMARK_HEADER)).toBe('bookmark-7');
  });

  it('omits the bookmark header when the request ran no query', async () => {
    const { d1 } = stubD1(null);
    const response = await requestWith('https://api.podcasts.highsignal.app/health', undefined, d1);
    expect(response.headers.get(D1_BOOKMARK_HEADER)).toBeNull();
  });

  it('exposes the bookmark header to browser clients', async () => {
    const { d1 } = stubD1();
    const response = await requestWith('https://api.podcasts.highsignal.app/health', undefined, d1);
    expect(response.headers.get('access-control-expose-headers')).toContain(D1_BOOKMARK_HEADER);
  });

  it('still serves requests when the binding cannot make a session', async () => {
    const response = await requestWith(
      'https://api.podcasts.highsignal.app/health',
      undefined,
      {} as unknown as D1Database
    );
    expect(response.status).toBe(200);
  });
});
