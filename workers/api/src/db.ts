import * as schema from '@on-record/db';
import { and, eq } from 'drizzle-orm';
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
