import { and, desc, eq } from 'drizzle-orm';
import { Hono } from 'hono';
import { requireAdmin } from '../auth';
import { isClaimType } from '../claim-types';
import { db, markShowHasPublishedClaims, schema } from '../db';
import type { Env } from '../env';
import { newId } from '../ids';
import { adminClaimsRoute } from './admin-claims';
import { adminEpisodesRoute } from './admin-episodes';

export const adminRoute = new Hono<{ Bindings: Env }>();

adminRoute.use('*', requireAdmin);

type PersonInput = {
  id?: string;
  slug: string;
  name: string;
  title?: string;
  org?: string;
  aliases?: string[];
  bio?: string;
  links?: Record<string, string>;
  status?: 'active' | 'hidden';
};

type ShowInput = {
  id?: string;
  slug: string;
  name: string;
  feedUrl?: string;
  podcastIndexFeedId?: number;
  youtubeChannelId?: string;
  hostPersonIds?: string[];
  active?: boolean;
};

type TopicInput = {
  id?: string;
  slug: string;
  name: string;
  status?: 'proposed' | 'approved';
};

adminRoute.get('/people', async (c) => {
  const rows = await db(c.env.DB)
    .select({
      id: schema.people.id,
      name: schema.people.name,
      slug: schema.people.slug,
    })
    .from(schema.people);
  return c.json({ people: rows });
});

adminRoute.post('/people/upsert', async (c) => {
  const body = (await c.req.json()) as { people?: PersonInput[] };
  const database = db(c.env.DB);
  const ids: string[] = [];
  for (const person of body.people ?? []) {
    const [existing] = await database
      .select()
      .from(schema.people)
      .where(eq(schema.people.slug, person.slug))
      .limit(1);
    const id = existing?.id ?? person.id ?? newId();
    const now = new Date();
    if (existing) {
      await database
        .update(schema.people)
        .set({
          aliases: person.aliases ?? [],
          bio: person.bio ?? null,
          links: person.links ?? {},
          name: person.name,
          org: person.org ?? null,
          status: person.status ?? 'active',
          title: person.title ?? null,
          updatedAt: now,
        })
        .where(eq(schema.people.id, id));
    } else {
      await database.insert(schema.people).values({
        aliases: person.aliases ?? [],
        bio: person.bio ?? null,
        createdAt: now,
        id,
        links: person.links ?? {},
        name: person.name,
        org: person.org ?? null,
        slug: person.slug,
        status: person.status ?? 'active',
        title: person.title ?? null,
        updatedAt: now,
      });
    }
    ids.push(id);
  }
  return c.json({ ids });
});

adminRoute.get('/shows', async (c) => {
  const rows = await db(c.env.DB).select().from(schema.shows);
  return c.json({ shows: rows });
});

adminRoute.post('/shows/upsert', async (c) => {
  const body = (await c.req.json()) as { shows?: ShowInput[] };
  const database = db(c.env.DB);
  const ids: string[] = [];
  for (const show of body.shows ?? []) {
    const [existing] = await database
      .select()
      .from(schema.shows)
      .where(eq(schema.shows.slug, show.slug))
      .limit(1);
    const id = existing?.id ?? show.id ?? newId();
    const now = new Date();
    if (existing) {
      await database
        .update(schema.shows)
        .set({
          active: show.active ?? true,
          feedUrl: show.feedUrl ?? null,
          hostPersonIds: show.hostPersonIds ?? [],
          name: show.name,
          podcastIndexFeedId: show.podcastIndexFeedId ?? null,
          youtubeChannelId: show.youtubeChannelId ?? null,
        })
        .where(eq(schema.shows.id, id));
    } else {
      await database.insert(schema.shows).values({
        active: show.active ?? true,
        createdAt: now,
        feedUrl: show.feedUrl ?? null,
        hostPersonIds: show.hostPersonIds ?? [],
        id,
        name: show.name,
        podcastIndexFeedId: show.podcastIndexFeedId ?? null,
        slug: show.slug,
        youtubeChannelId: show.youtubeChannelId ?? null,
      });
    }
    ids.push(id);
  }
  return c.json({ ids });
});

adminRoute.post('/topics/upsert', async (c) => {
  const body = (await c.req.json()) as { topics?: TopicInput[] };
  const database = db(c.env.DB);
  const ids: string[] = [];
  for (const topic of body.topics ?? []) {
    const [existing] = await database
      .select()
      .from(schema.topics)
      .where(eq(schema.topics.slug, topic.slug))
      .limit(1);
    const id = existing?.id ?? topic.id ?? newId();
    if (existing) {
      await database
        .update(schema.topics)
        .set({ name: topic.name, status: topic.status ?? 'approved' })
        .where(eq(schema.topics.id, id));
    } else {
      await database.insert(schema.topics).values({
        id,
        name: topic.name,
        slug: topic.slug,
        status: topic.status ?? 'approved',
      });
    }
    ids.push(id);
  }
  return c.json({ ids });
});

adminRoute.get('/episodes', async (c) => {
  const status = c.req.query('status');
  const showId = c.req.query('showId');
  const filters = [];
  if (status) {
    filters.push(
      eq(schema.episodes.status, status as (typeof schema.episodes.status.enumValues)[number])
    );
  }
  if (showId) {
    filters.push(eq(schema.episodes.showId, showId));
  }
  const database = db(c.env.DB).select().from(schema.episodes);
  const filtered = filters.length ? database.where(and(...filters)) : database;
  // The pipeline pages through the whole archive; 200 silently truncated
  // every caller that wanted more than the most recent page.
  const limit = Math.min(Number(c.req.query('limit') ?? 200) || 200, 2000);
  const offset = Math.max(Number(c.req.query('offset') ?? 0) || 0, 0);
  const rows = await filtered
    .orderBy(desc(schema.episodes.publishedAt))
    .limit(limit)
    .offset(offset);
  return c.json({ episodes: rows });
});

const reviewColumns = {
  assertion: schema.claims.assertion,
  confidenceBand: schema.claims.confidenceBand,
  id: schema.claims.id,
  personId: schema.claims.personId,
  personSlug: schema.people.slug,
  publishReason: schema.claims.publishReason,
  quote: schema.claims.quote,
  reviewStatus: schema.claims.reviewStatus,
};

function reviewQueue(d1: D1Database, status: 'held' | 'draft', limit: number) {
  return db(d1)
    .select(reviewColumns)
    .from(schema.claims)
    .innerJoin(schema.people, eq(schema.claims.personId, schema.people.id))
    .where(eq(schema.claims.reviewStatus, status))
    .orderBy(desc(schema.claims.createdAt))
    .limit(limit);
}

export function reviewStatusIsIndexed(status: string): boolean {
  return status === 'published';
}

adminRoute.get('/review-queue', async (c) => {
  const held = await reviewQueue(c.env.DB, 'held', 200);
  const drafts = await reviewQueue(c.env.DB, 'draft', 100);
  return c.json({ claims: [...held, ...drafts] });
});

adminRoute.post('/claims/:id/status', async (c) => {
  const id = c.req.param('id');
  const body = (await c.req.json()) as { reviewStatus?: string };
  const allowed = new Set(['draft', 'held', 'published', 'killed', 'corrected']);
  if (!(body.reviewStatus && allowed.has(body.reviewStatus))) {
    return c.json({ error: 'bad_status' }, 400);
  }
  const publishedAt = body.reviewStatus === 'published' ? new Date() : null;
  const database = db(c.env.DB);
  await database
    .update(schema.claims)
    .set({
      publishedAt,
      reviewStatus: body.reviewStatus as (typeof schema.claims.reviewStatus.enumValues)[number],
    })
    .where(eq(schema.claims.id, id));
  await c.env.DB.prepare('DELETE FROM claims_fts WHERE claim_id = ?').bind(id).run();
  if (reviewStatusIsIndexed(body.reviewStatus)) {
    const [claim] = await database
      .select({
        assertion: schema.claims.assertion,
        quote: schema.claims.quote,
        showId: schema.episodes.showId,
      })
      .from(schema.claims)
      .innerJoin(schema.episodes, eq(schema.claims.episodeId, schema.episodes.id))
      .where(eq(schema.claims.id, id))
      .limit(1);
    if (claim) {
      await c.env.DB.prepare('INSERT INTO claims_fts (claim_id, assertion, quote) VALUES (?, ?, ?)')
        .bind(id, claim.assertion, claim.quote)
        .run();
      await markShowHasPublishedClaims(c.env.DB, claim.showId);
    }
  }
  return c.json({ ok: true });
});

adminRoute.post('/claims/:id/classification', async (c) => {
  const id = c.req.param('id');
  const body = (await c.req.json()) as { claimType?: string };
  if (!(body.claimType && isClaimType(body.claimType))) {
    return c.json({ error: 'bad_claim_type' }, 400);
  }
  await db(c.env.DB)
    .update(schema.claims)
    .set({ claimType: body.claimType })
    .where(eq(schema.claims.id, id));
  return c.json({ ok: true });
});

adminRoute.post('/ingest-runs', async (c) => {
  const body = (await c.req.json()) as {
    id?: string;
    stage: string;
    showSlug?: string;
    days?: number;
    startedAt?: number;
    finishedAt?: number;
    episodesDiscovered?: number;
    transcriptsFound?: number;
    claimsExtracted?: number;
    claimsPublished?: number;
    claimsRejectedQuote?: number;
    claimsRejectedSpeaker?: number;
    error?: string;
  };
  const id = body.id ?? newId();
  await db(c.env.DB)
    .insert(schema.ingestRuns)
    .values({
      claimsExtracted: body.claimsExtracted ?? 0,
      claimsPublished: body.claimsPublished ?? 0,
      claimsRejectedQuote: body.claimsRejectedQuote ?? 0,
      claimsRejectedSpeaker: body.claimsRejectedSpeaker ?? 0,
      days: body.days ?? null,
      episodesDiscovered: body.episodesDiscovered ?? 0,
      error: body.error ?? null,
      finishedAt: body.finishedAt ? new Date(body.finishedAt) : new Date(),
      id,
      showSlug: body.showSlug ?? null,
      stage: body.stage,
      startedAt: body.startedAt ? new Date(body.startedAt) : new Date(),
      transcriptsFound: body.transcriptsFound ?? 0,
    });
  return c.json({ id });
});

adminRoute.route('/', adminEpisodesRoute);
adminRoute.route('/', adminClaimsRoute);
