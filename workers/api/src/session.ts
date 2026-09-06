// D1 Sessions API wiring.
//
// `on-record-db` is APAC-primary. Issue #11 measured every D1 round trip at
// ~90ms from a colo in that same region and materially more from anywhere
// else, which is the floor under every uncached public response. Read
// replication puts a replica in each region and the Sessions API is how a
// request opts into reading from one: `withSession()` anchors a request to a
// bookmark so every query it makes is sequentially consistent, and D1 is then
// free to answer from whichever replica already satisfies that bookmark.
//
// Two anchors are used here:
//   - public read routes open `first-unconstrained` - the first query may go
//     to any replica, and the rest of the request follows that same bookmark.
//     These routes serve a published corpus that changes in release batches,
//     so a replica a beat behind the primary is fine.
//   - admin routes open `first-primary` - the first query goes to the primary,
//     so a moderator who just published sees their own write on the next read.
//
// Writes always land on the primary regardless of the anchor, so
// `bumpPublicCacheGeneration()` and every publish/unpublish path stay on
// primary by construction. What the anchor changes is only where *reads* may
// be answered from.
//
// The bookmark is threaded across requests with the documented
// `x-d1-bookmark` header: a client that sends back the bookmark it last
// received never reads older data than it has already seen.

import type { Env } from './env';

export const D1_BOOKMARK_HEADER = 'x-d1-bookmark';

export type D1Anchor = D1SessionBookmark | D1SessionConstraint;

/**
 * Chooses the session anchor for a request.
 *
 * An explicit client bookmark always wins - it is the caller telling us how
 * far forward they have already read. Otherwise admin paths anchor to the
 * primary and public reads are left unconstrained.
 */
export function anchorFor(bookmark: string | undefined, isAdminPath: boolean): D1Anchor {
  const trimmed = bookmark?.trim();
  if (trimmed) {
    return trimmed;
  }
  return isAdminPath ? 'first-primary' : 'first-unconstrained';
}

/**
 * Opens a session, or returns null when the binding cannot make one.
 *
 * Test stubs and any older binding shape simply do not have `withSession`;
 * falling back to the plain binding keeps those paths working unchanged
 * instead of throwing at the very front of every request.
 */
export function openSession(d1: D1Database, anchor: D1Anchor): D1DatabaseSession | null {
  if (typeof d1?.withSession !== 'function') {
    return null;
  }
  return d1.withSession(anchor);
}

/**
 * Presents a session with the full `D1Database` surface so the request can be
 * routed through it without touching a single call site.
 *
 * Queries (`prepare`, `batch`) go through the session, which is the whole
 * point: drizzle only ever calls those two, and so does the hand-written SQL
 * in the admin routes. `exec`/`dump`/`withSession` have no session equivalent
 * and fall through to the real binding rather than being stubbed out, so
 * nothing silently breaks if a future caller reaches for one.
 */
export function sessionAsDatabase(base: D1Database, session: D1DatabaseSession): D1Database {
  return {
    prepare: (query: string) => session.prepare(query),
    batch: <T = unknown>(statements: D1PreparedStatement[]) => session.batch<T>(statements),
    exec: (query: string) => base.exec(query),
    dump: () => base.dump(),
    withSession: (anchor?: D1Anchor) => base.withSession(anchor),
  } as D1Database;
}

/**
 * Swaps `env.DB` for the session-backed database for the life of one request.
 */
export function envWithSession(env: Env, session: D1DatabaseSession): Env {
  return { ...env, DB: sessionAsDatabase(env.DB, session) };
}
