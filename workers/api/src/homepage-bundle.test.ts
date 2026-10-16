import { Hono } from 'hono';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Env } from './env';
import { publicRoute } from './routes/public';

let currentGeneration = 1;
let generationRead: (() => Promise<number>) | undefined;
vi.mock('./db', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./db')>();
  return {
    ...actual,
    publicCacheGenerationFresh: async () => (generationRead ? generationRead() : currentGeneration),
  };
});

const { homepageBundle, warmHomepageBundle } = await import('./homepage-bundle');
const key = 'public/homepage/v1/current-bundle.json';

function payload(path: string): unknown {
  if (path.includes('/people?')) {
    return { people: [] };
  }
  if (path.includes('/search')) {
    return { claims: [] };
  }
  if (path.includes('/recommendation-groups?')) {
    return { groups: [] };
  }
  if (path.includes('/sources?')) {
    return { sources: [] };
  }
  return { people: 0, episodes: 0, publishedClaims: 0 };
}

function fixture() {
  let stored: string | undefined;
  let uploaded = new Date();
  const get = vi.fn(async () =>
    stored === undefined ? null : { size: stored.length, uploaded, text: async () => stored }
  );
  const put = vi.fn(async (_key: string, text: string) => {
    stored = text;
    uploaded = new Date();
  });
  const env = { DB: {}, RAW: { get, put } } as unknown as Env;
  const waits: Promise<unknown>[] = [];
  const executionCtx = {
    waitUntil: (promise: Promise<unknown>) => waits.push(promise),
  } as unknown as ExecutionContext;
  const app = new Hono<{ Bindings: Env }>();
  app.get('/api/homepage-bundle', homepageBundle);
  const request = () =>
    app.request(
      'https://api.podcasts.highsignal.app/api/homepage-bundle',
      undefined,
      env,
      executionCtx
    );
  return {
    env,
    get,
    put,
    request,
    waits,
    set: (value: unknown, ageMs = 0) => {
      stored = JSON.stringify(value);
      uploaded = new Date(Date.now() - ageMs);
    },
    setRaw: (text: string, ageMs = 0) => {
      stored = text;
      uploaded = new Date(Date.now() - ageMs);
    },
    stored: () => stored,
  };
}

function bundle(generation = 1, ageMs = 0) {
  return {
    generation,
    capturedAt: new Date(Date.now() - ageMs).toISOString(),
    stats: payload('/stats'),
    people: payload('/people?limit=8'),
    evidence: payload('/search'),
    groups: payload('/recommendation-groups?limit=8'),
    sources: payload('/sources?limit=5'),
  };
}

afterEach(() => {
  currentGeneration = 1;
  generationRead = undefined;
  vi.restoreAllMocks();
});

describe('generation-validated homepage bundle', () => {
  it('starts the generation and R2 reads together on a cold request', async () => {
    const fixtureState = fixture();
    fixtureState.set(bundle());
    let resolveGeneration: ((value: number) => void) | undefined;
    generationRead = () =>
      new Promise<number>((resolve) => {
        resolveGeneration = resolve;
      });
    const response = fixtureState.request();
    await vi.waitFor(() => expect(fixtureState.get).toHaveBeenCalledTimes(1));
    resolveGeneration?.(1);
    expect((await response).status).toBe(200);
  });

  it('serves the complete matching copy without calling public routes', async () => {
    const fixtureState = fixture();
    fixtureState.set(bundle());
    const route = vi.spyOn(publicRoute, 'request');
    const response = await fixtureState.request();
    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toBe('no-store');
    await expect(response.json()).resolves.toMatchObject({ generation: 1, people: { people: [] } });
    expect(route).not.toHaveBeenCalled();
  });

  it('rejects an old generation and rebuilds from the gated public routes', async () => {
    const fixtureState = fixture();
    fixtureState.set(bundle(1));
    currentGeneration = 2;
    const route = vi
      .spyOn(publicRoute, 'request')
      .mockImplementation(async (url) => Response.json(payload(String(url))));
    const response = await fixtureState.request();
    await expect(response.json()).resolves.toMatchObject({ generation: 2 });
    expect(route).toHaveBeenCalledTimes(5);
    await Promise.all(fixtureState.waits);
    expect(JSON.parse(fixtureState.stored() ?? '{}').generation).toBe(2);
    expect(fixtureState.put).toHaveBeenCalledWith(key, expect.any(String), expect.any(Object));
  });

  it.each([
    ['missing', undefined, 0],
    ['malformed', '{bad JSON', 0],
    ['partial', JSON.stringify({ generation: 1, people: { people: [] } }), 0],
    ['expired', JSON.stringify(bundle(1, 25 * 60 * 60 * 1000)), 25 * 60 * 60 * 1000],
  ])(
    'fails closed when the %s copy and public fallback are unavailable',
    async (_name, text, age) => {
      const fixtureState = fixture();
      if (text !== undefined) {
        fixtureState.setRaw(text, Number(age));
      }
      vi.spyOn(publicRoute, 'request').mockResolvedValue(
        new Response('unavailable', { status: 503 })
      );
      const response = await fixtureState.request();
      expect(response.status).toBe(503);
      expect(fixtureState.put).not.toHaveBeenCalled();
    }
  );

  it('refreshes a five-minute copy without extending the 24-hour hard age', async () => {
    const fixtureState = fixture();
    fixtureState.set(bundle(1, 6 * 60 * 1000), 6 * 60 * 1000);
    const route = vi
      .spyOn(publicRoute, 'request')
      .mockImplementation(async (url) => Response.json(payload(String(url))));
    const response = await fixtureState.request();
    expect(response.status).toBe(200);
    await Promise.all(fixtureState.waits);
    expect(route).toHaveBeenCalledTimes(5);
    expect(JSON.parse(fixtureState.stored() ?? '{}').capturedAt).not.toBe(
      bundle(1, 6 * 60 * 1000).capturedAt
    );
  });

  it('never publishes a partial response from the public routes', async () => {
    const fixtureState = fixture();
    vi.spyOn(publicRoute, 'request').mockImplementation(async (url) =>
      Response.json(String(url).includes('/sources?') ? { sources: [{}] } : payload(String(url)))
    );
    const response = await fixtureState.request();
    expect(response.status).toBe(503);
    expect(fixtureState.put).not.toHaveBeenCalled();
  });

  it('does not let a late older warm overwrite a newer publication', async () => {
    const fixtureState = fixture();
    let resumeOld: (() => void) | undefined;
    let oldStarted: (() => void) | undefined;
    const started = new Promise<void>((resolve) => {
      oldStarted = resolve;
    });
    const oldWait = new Promise<void>((resolve) => {
      resumeOld = resolve;
    });
    vi.spyOn(publicRoute, 'request').mockImplementation(async (url) => {
      if (currentGeneration === 1) {
        oldStarted?.();
        await oldWait;
      }
      return Response.json(payload(String(url)));
    });
    const oldWarm = warmHomepageBundle(fixtureState.env);
    await started;
    currentGeneration = 2;
    await warmHomepageBundle(fixtureState.env);
    resumeOld?.();
    await oldWarm;
    expect(JSON.parse(fixtureState.stored() ?? '{}').generation).toBe(2);
  });

  it('rejects an older write that completes after a newer bundle write', async () => {
    const fixtureState = fixture();
    const originalPut = fixtureState.put.getMockImplementation();
    let releaseOldPut: (() => void) | undefined;
    let oldPutStarted: (() => void) | undefined;
    const oldPutWait = new Promise<void>((resolve) => {
      releaseOldPut = resolve;
    });
    const oldPutEntered = new Promise<void>((resolve) => {
      oldPutStarted = resolve;
    });
    fixtureState.put.mockImplementation(async (objectKey, text) => {
      if (JSON.parse(text).generation === 1) {
        oldPutStarted?.();
        await oldPutWait;
      }
      await originalPut?.(objectKey, text);
    });
    vi.spyOn(publicRoute, 'request').mockImplementation(async (url) =>
      Response.json(payload(String(url)))
    );
    const oldWarm = warmHomepageBundle(fixtureState.env);
    await oldPutEntered;
    currentGeneration = 2;
    await warmHomepageBundle(fixtureState.env);
    releaseOldPut?.();
    await oldWarm;
    expect(JSON.parse(fixtureState.stored() ?? '{}').generation).toBe(1);

    const response = await fixtureState.request();
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({ generation: 2 });
  });
});
