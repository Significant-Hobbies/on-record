import * as schema from '@on-record/db';
import { and, eq, sql } from 'drizzle-orm';
import { drizzle } from 'drizzle-orm/d1';

export function db(d1: D1Database) {
  return drizzle(d1, { schema });
}

export { schema };

export async function markShowHasPublishedClaims(d1: D1Database, showId: string): Promise<void> {
  await db(d1)
    .update(schema.shows)
    .set({ hasPublishedClaims: true })
    .where(and(eq(schema.shows.id, showId), eq(schema.shows.hasPublishedClaims, false)));
}

// Every request behind the public cache reads this once to build its Cache
// API key, so it has to stay a single indexed point read - the whole reason
// the cache exists is to avoid the six-table join this generation guards.
//
// The read still sits in front of the cache lookup rather than behind it, so
// it is on the hot path of every public response, hit or miss. `on-record-db`
// runs in APAC with read replication disabled, which measured at ~90ms per
// round trip from a colo in that same region and more from anywhere else
// (issue #11): a cached /api/stats answered in ~350ms where the binding-free
// /health answered in ~265ms, and the homepage fans out to five of these
// routes. Holding the generation in the isolate for a few seconds takes that
// read off almost every request. It does not weaken invalidation in any way
// that matters - a publish still busts the cache within this window, against
// a cached response TTL of an hour - and the bump path drops the memo so the
// isolate that wrote the new generation never serves the old one.
const GENERATION_MEMO_MS = 5000;
let generationMemo: { generation: number; readAt: number } | null = null;

export async function publicCacheGeneration(d1: D1Database): Promise<number> {
  const now = Date.now();
  if (generationMemo && now - generationMemo.readAt < GENERATION_MEMO_MS) {
    return generationMemo.generation;
  }
  const [row] = await db(d1)
    .select({ generation: schema.publicCacheState.generation })
    .from(schema.publicCacheState)
    .where(eq(schema.publicCacheState.id, 1))
    .limit(1);
  const generation = row?.generation ?? 1;
  generationMemo = { generation, readAt: Date.now() };
  return generation;
}

// Bumping this is the invalidation hook: every cached response's key embeds
// the generation, so the next read after a publish or unpublish can no
// longer match a cache entry from before it, on any route or colo.
export async function bumpPublicCacheGeneration(d1: D1Database): Promise<void> {
  generationMemo = null;
  await db(d1)
    .update(schema.publicCacheState)
    .set({ generation: sql`${schema.publicCacheState.generation} + 1` })
    .where(eq(schema.publicCacheState.id, 1));
}
