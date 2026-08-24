import { and, desc, eq, gte, inArray, lte, sql } from 'drizzle-orm';
import type { SQL } from 'drizzle-orm';
import { Hono } from 'hono';
import { isClaimType } from '../claim-types';
import { db, schema } from '../db';
import type { Env } from '../env';
import { sanitizeFtsQuery } from '../fts';
import { isReferenceKind, isReferenceRole } from '../references';

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
  const recommendations = await publishedReferences(c.env.DB, { personId: person.id });
  return c.json({ claims, person, recommendations });
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
  const references = await db(c.env.DB)
    .select()
    .from(schema.claimReferences)
    .where(eq(schema.claimReferences.claimId, claim.id));
  return c.json({ claim, evidence, references });
});

publicRoute.get('/sources', async (c) => {
  const database = db(c.env.DB);
  const published = await database
    .select({ episodeId: schema.claims.episodeId })
    .from(schema.claims)
    .where(eq(schema.claims.reviewStatus, 'published'));
  const ids = [
    ...new Set(
      published.map((row) => row.episodeId).filter((value): value is string => Boolean(value))
    ),
  ];
  if (!ids.length) {
    return c.json({ sources: [] });
  }
  const rows = await database
    .select()
    .from(schema.episodes)
    .where(inArray(schema.episodes.id, ids))
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

async function publishedReferences(
  d1: D1Database,
  filters: { personId?: string; kind?: string; role?: string }
) {
  const database = db(d1);
  const clauses: SQL[] = [eq(schema.claims.reviewStatus, 'published')];
  if (filters.personId) {
    clauses.push(eq(schema.claims.personId, filters.personId));
  }
  if (filters.kind && isReferenceKind(filters.kind)) {
    clauses.push(eq(schema.claimReferences.kind, filters.kind));
  }
  if (filters.role && isReferenceRole(filters.role)) {
    clauses.push(eq(schema.claimReferences.role, filters.role));
  }
  return database
    .select({
      assertion: schema.claims.assertion,
      claimId: schema.claims.id,
      kind: schema.claimReferences.kind,
      name: schema.claimReferences.name,
      personId: schema.claims.personId,
      quote: schema.claims.quote,
      role: schema.claimReferences.role,
      saidOn: schema.claims.saidOn,
      timestampS: schema.claims.timestampS,
    })
    .from(schema.claimReferences)
    .innerJoin(schema.claims, eq(schema.claimReferences.claimId, schema.claims.id))
    .where(and(...clauses))
    .orderBy(desc(schema.claims.saidOn))
    .limit(200);
}

publicRoute.get('/recommendations', async (c) => {
  const personSlug = c.req.query('person');
  let personId: string | undefined;
  if (personSlug) {
    const [person] = await db(c.env.DB)
      .select()
      .from(schema.people)
      .where(eq(schema.people.slug, personSlug))
      .limit(1);
    if (!person) {
      return c.json({ evidence: 'insufficient', recommendations: [] });
    }
    personId = person.id;
  }
  const recommendations = await publishedReferences(c.env.DB, {
    kind: c.req.query('kind'),
    personId,
    role: c.req.query('role'),
  });
  if (!recommendations.length) {
    return c.json({ evidence: 'insufficient', recommendations: [] });
  }
  return c.json({ recommendations });
});

publicRoute.get('/stats', async (c) => {
  const database = db(c.env.DB);
  const [people] = await database.select({ n: sql<number>`count(*)` }).from(schema.people);
  const [published] = await database
    .select({ n: sql<number>`count(*)` })
    .from(schema.claims)
    .where(eq(schema.claims.reviewStatus, 'published'));
  const [episodes] = await database
    .select({ n: sql<number>`count(distinct ${schema.claims.episodeId})` })
    .from(schema.claims)
    .where(eq(schema.claims.reviewStatus, 'published'));
  const [references] = await database
    .select({ n: sql<number>`count(*)` })
    .from(schema.claimReferences)
    .innerJoin(schema.claims, eq(schema.claimReferences.claimId, schema.claims.id))
    .where(eq(schema.claims.reviewStatus, 'published'));
  return c.json({
    episodes: episodes?.n ?? 0,
    people: people?.n ?? 0,
    publishedClaims: published?.n ?? 0,
    publishedReferences: references?.n ?? 0,
  });
});
