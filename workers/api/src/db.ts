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
export async function publicCacheGeneration(d1: D1Database): Promise<number> {
  const [row] = await db(d1)
    .select({ generation: schema.publicCacheState.generation })
    .from(schema.publicCacheState)
    .where(eq(schema.publicCacheState.id, 1))
    .limit(1);
  return row?.generation ?? 1;
}

// Bumping this is the invalidation hook: every cached response's key embeds
// the generation, so the next read after a publish or unpublish can no
// longer match a cache entry from before it, on any route or colo.
export async function bumpPublicCacheGeneration(d1: D1Database): Promise<void> {
  await db(d1)
    .update(schema.publicCacheState)
    .set({ generation: sql`${schema.publicCacheState.generation} + 1` })
    .where(eq(schema.publicCacheState.id, 1));
}
