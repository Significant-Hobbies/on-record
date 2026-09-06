import { afterEach, describe, expect, it, vi } from 'vitest';

/**
 * D1 stub for the generation point read. Drizzle runs `.select(...).limit(1)`
 * through `prepare(sql).bind(...).raw()`, so the row is positional.
 */
function generationD1(reads: { count: number }, generation = 7) {
  return {
    prepare: () => ({
      bind: () => ({
        all: async () => ({ results: [] }),
        first: async () => null,
        raw: async () => {
          reads.count += 1;
          return [[generation]];
        },
        run: async () => {
          reads.count += 1;
          return {};
        },
      }),
    }),
  } as unknown as D1Database;
}

afterEach(() => {
  vi.resetModules();
  vi.useRealTimers();
});

describe('public cache generation memo', () => {
  it('reads D1 once and serves the rest of the window from the isolate', async () => {
    const reads = { count: 0 };
    const d1 = generationD1(reads);
    const { publicCacheGeneration } = await import('./db');

    await expect(publicCacheGeneration(d1)).resolves.toBe(7);
    await expect(publicCacheGeneration(d1)).resolves.toBe(7);
    await expect(publicCacheGeneration(d1)).resolves.toBe(7);

    expect(reads.count).toBe(1);
  });

  it('re-reads D1 once the window has passed', async () => {
    vi.useFakeTimers();
    const reads = { count: 0 };
    const d1 = generationD1(reads);
    const { publicCacheGeneration } = await import('./db');

    await publicCacheGeneration(d1);
    vi.advanceTimersByTime(5001);
    await publicCacheGeneration(d1);

    expect(reads.count).toBe(2);
  });

  // A publish is exactly when a stale generation would matter, so the bump
  // has to drop the memo rather than wait the window out.
  it('drops the memo when a publish bumps the generation', async () => {
    const reads = { count: 0 };
    const d1 = generationD1(reads);
    const { bumpPublicCacheGeneration, publicCacheGeneration } = await import('./db');

    await publicCacheGeneration(d1);
    const readsAfterFirst = reads.count;
    await bumpPublicCacheGeneration(d1);
    await publicCacheGeneration(d1);

    expect(readsAfterFirst).toBe(1);
    expect(reads.count).toBeGreaterThan(readsAfterFirst + 1);
  });
});
