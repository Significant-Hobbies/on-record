import { and, desc, eq, gte, lte, sql } from 'drizzle-orm';
import type { SQL } from 'drizzle-orm';
import { Hono } from 'hono';
import { isClaimType } from '../claim-types';
import { db, schema } from '../db';
import type { Env } from '../env';
import { sanitizeFtsQuery } from '../fts';

export const publicRoute = new Hono<{ Bindings: Env }>();

publicRoute.get('/people', async (c) => {
  const rows = await db(c.env.DB)
    .select()
    .from(schema.people)
    .where(eq(schema.people.status, 'active'))
    .orderBy(schema.people.name);
  return c.json({ people: rows });
});

publicRoute.get('/people/:slug', async (c) => {
  const slug = c.req.param('slug');
  const [person] = await db(c.env.DB)
    .select()
    .from(schema.people)
    .where(eq(schema.people.slug, slug))
    .limit(1);
  if (!person || person.status !== 'active') {
    return c.json({ error: 'not_found' }, 404);
  }
  const claims = await db(c.env.DB)
    .select()
    .from(schema.claims)
    .where(and(eq(schema.claims.personId, person.id), eq(schema.claims.reviewStatus, 'published')))
    .orderBy(desc(schema.claims.saidOn));
  return c.json({ claims, person });
});

publicRoute.get('/claims/:id', async (c) => {
  const id = c.req.param('id');
  const [claim] = await db(c.env.DB)
    .select()
    .from(schema.claims)
    .where(eq(schema.claims.id, id))
    .limit(1);
  if (!claim || claim.reviewStatus !== 'published') {
    return c.json({ error: 'not_found' }, 404);
  }
  const evidence = await db(c.env.DB)
    .select()
    .from(schema.claimEvidence)
    .where(eq(schema.claimEvidence.claimId, claim.id));
  return c.json({ claim, evidence });
});

publicRoute.get('/sources', async (c) => {
  const rows = await db(c.env.DB)
    .select()
    .from(schema.episodes)
    .orderBy(desc(schema.episodes.publishedAt))
    .limit(100);
  return c.json({ sources: rows });
});

publicRoute.get('/sources/:id', async (c) => {
  const id = c.req.param('id');
  const [episode] = await db(c.env.DB)
    .select()
    .from(schema.episodes)
    .where(eq(schema.episodes.id, id))
    .limit(1);
  if (!episode) {
    return c.json({ error: 'not_found' }, 404);
  }
  const claims = await db(c.env.DB)
    .select()
    .from(schema.claims)
    .where(
      and(eq(schema.claims.episodeId, episode.id), eq(schema.claims.reviewStatus, 'published'))
    );
  return c.json({ claims, source: episode });
});

publicRoute.get('/topics/:slug', async (c) => {
  const slug = c.req.param('slug');
  const [topic] = await db(c.env.DB)
    .select()
    .from(schema.topics)
    .where(eq(schema.topics.slug, slug))
    .limit(1);
  if (!topic) {
    return c.json({ error: 'not_found' }, 404);
  }
  const linked = await db(c.env.DB)
    .select({ claim: schema.claims })
    .from(schema.claimTopics)
    .innerJoin(schema.claims, eq(schema.claimTopics.claimId, schema.claims.id))
    .where(
      and(eq(schema.claimTopics.topicId, topic.id), eq(schema.claims.reviewStatus, 'published'))
    );
  return c.json({ claims: linked.map((row) => row.claim), topic });
});

function publishedFilters(query: {
  person?: string;
  type?: string;
  from?: string;
  to?: string;
}): SQL[] {
  const filters: SQL[] = [eq(schema.claims.reviewStatus, 'published')];
  if (query.person) {
    filters.push(eq(schema.people.slug, query.person));
  }
  if (query.type && isClaimType(query.type)) {
    filters.push(eq(schema.claims.claimType, query.type));
  }
  if (query.from) {
    filters.push(gte(schema.claims.saidOn, new Date(query.from)));
  }
  if (query.to) {
    filters.push(lte(schema.claims.saidOn, new Date(query.to)));
  }
  return filters;
}

async function ftsClaimIds(d1: D1Database, match: string): Promise<string[]> {
  const result = await d1
    .prepare('SELECT claim_id FROM claims_fts WHERE claims_fts MATCH ? LIMIT 50')
    .bind(match)
    .all<{ claim_id: string }>();
  return (result.results ?? []).map((row) => row.claim_id);
}

publicRoute.get('/search', async (c) => {
  const q = c.req.query('q') ?? '';
  const topic = c.req.query('topic');
  const match = sanitizeFtsQuery(q);
  const filters = publishedFilters({
    from: c.req.query('from'),
    person: c.req.query('person'),
    to: c.req.query('to'),
    type: c.req.query('type'),
  });
  const database = db(c.env.DB);
  const found = await database
    .select({ claim: schema.claims })
    .from(schema.claims)
    .innerJoin(schema.people, eq(schema.claims.personId, schema.people.id))
    .where(and(...filters))
    .limit(50);
  let rows = found.map((row) => row.claim);
  if (match) {
    const ids = new Set(await ftsClaimIds(c.env.DB, match));
    if (!ids.size) {
      return c.json({ claims: [], evidence: 'insufficient' });
    }
    rows = rows.filter((claim) => ids.has(claim.id));
  }
  if (topic) {
    const [topicRow] = await database
      .select()
      .from(schema.topics)
      .where(eq(schema.topics.slug, topic))
      .limit(1);
    if (!topicRow) {
      return c.json({ claims: [], evidence: 'insufficient' });
    }
    const linked = await database
      .select({ claimId: schema.claimTopics.claimId })
      .from(schema.claimTopics)
      .where(eq(schema.claimTopics.topicId, topicRow.id));
    const allow = new Set(linked.map((row) => row.claimId));
    rows = rows.filter((claim) => allow.has(claim.id));
  }
  if (!rows.length) {
    return c.json({ claims: [], evidence: 'insufficient' });
  }
  return c.json({ claims: rows });
});

publicRoute.get('/stats', async (c) => {
  const database = db(c.env.DB);
  const [people] = await database.select({ n: sql<number>`count(*)` }).from(schema.people);
  const [published] = await database
    .select({ n: sql<number>`count(*)` })
    .from(schema.claims)
    .where(eq(schema.claims.reviewStatus, 'published'));
  const [episodes] = await database.select({ n: sql<number>`count(*)` }).from(schema.episodes);
  return c.json({
    episodes: episodes?.n ?? 0,
    people: people?.n ?? 0,
    publishedClaims: published?.n ?? 0,
  });
});
