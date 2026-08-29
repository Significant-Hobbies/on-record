import { and, asc, desc, eq, gte, inArray, like, lte, notInArray, or, sql } from 'drizzle-orm';
import type { SQL } from 'drizzle-orm';
import { Hono } from 'hono';
import { UNVERIFIED_SPEAKER_SLUG } from '../attribution';
import {
  type ClaimTranscriptContext,
  claimTranscriptContext,
  wantsTranscriptContext,
} from '../claim-context';
import { isClaimType } from '../claim-types';
import { db, schema } from '../db';
import type { Env } from '../env';
import { sanitizeFtsQuery } from '../fts';
import { canonicalReferenceName, groupRecommendationReferences } from '../recommendation-groups';
import {
  ACTIONABLE_REFERENCE_ROLES,
  isActionableReferenceRole,
  isReferenceKind,
  referenceAssertion,
  sanitizeReferences,
} from '../references';

export const publicRoute = new Hono<{ Bindings: Env }>();

export const WITHHELD_PUBLIC_SHOW_SLUGS = ['odd-lots', 'tbpn'] as const;

export function isTrustedPublicShowSlug(slug: string): boolean {
  return !WITHHELD_PUBLIC_SHOW_SLUGS.includes(slug as (typeof WITHHELD_PUBLIC_SHOW_SLUGS)[number]);
}

function trustedShowFilter(): SQL {
  return notInArray(schema.shows.slug, [...WITHHELD_PUBLIC_SHOW_SLUGS]);
}

export const publicClaimFields = {
  assertion: schema.claims.assertion,
  attributionStatus: schema.claims.attributionStatus,
  claimType: schema.claims.claimType,
  deepLinkUrl: sql<string | null>`(
    case when ${schema.episodes.transcriptKind} = 'youtube_captions' then (
      select ${schema.claimEvidence.deepLinkUrl}
      from ${schema.claimEvidence}
      where ${schema.claimEvidence.claimId} = ${schema.claims.id}
        and ${schema.claimEvidence.role} = 'primary'
      limit 1
    ) else null end
  )`,
  episodeId: schema.episodes.id,
  episodeTitle: schema.episodes.title,
  id: schema.claims.id,
  personId: sql<
    string | null
  >`case when ${schema.claims.attributionStatus} = 'verified_speaker' then ${schema.people.id} else null end`,
  personName: sql<
    string | null
  >`case when ${schema.claims.attributionStatus} = 'verified_speaker' then ${schema.people.name} else null end`,
  personOrg: sql<
    string | null
  >`case when ${schema.claims.attributionStatus} = 'verified_speaker' then ${schema.people.org} else null end`,
  personSlug: sql<
    string | null
  >`case when ${schema.claims.attributionStatus} = 'verified_speaker' then ${schema.people.slug} else null end`,
  personTitle: sql<
    string | null
  >`case when ${schema.claims.attributionStatus} = 'verified_speaker' then ${schema.people.title} else null end`,
  quote: schema.claims.quote,
  reviewStatus: schema.claims.reviewStatus,
  saidOn: schema.claims.saidOn,
  showName: schema.shows.name,
  showSlug: schema.shows.slug,
  sourceUrl: schema.episodes.sourceUrl,
  stance: schema.claims.stance,
  timestampS: sql<
    number | null
  >`case when ${schema.episodes.transcriptKind} = 'youtube_captions' then ${schema.claims.timestampS} else null end`,
  transcriptKind: schema.episodes.transcriptKind,
};

const publicSourceFields = {
  durationS: schema.episodes.durationS,
  id: schema.episodes.id,
  publishedAt: schema.episodes.publishedAt,
  showName: schema.shows.name,
  showSlug: schema.shows.slug,
  sourceUrl: schema.episodes.sourceUrl,
  status: schema.episodes.status,
  title: schema.episodes.title,
  transcriptKind: schema.episodes.transcriptKind,
};

async function publicClaims(d1: D1Database, filters: SQL[] = [], limit = 200) {
  return db(d1)
    .select(publicClaimFields)
    .from(schema.claims)
    .innerJoin(schema.people, eq(schema.claims.personId, schema.people.id))
    .innerJoin(schema.episodes, eq(schema.claims.episodeId, schema.episodes.id))
    .innerJoin(schema.shows, eq(schema.episodes.showId, schema.shows.id))
    .where(
      and(
        eq(schema.claims.reviewStatus, 'published'),
        eq(schema.people.status, 'active'),
        trustedShowFilter(),
        ...filters
      )
    )
    .orderBy(desc(schema.claims.saidOn), desc(schema.claims.createdAt))
    .limit(limit);
}

publicRoute.get('/people', async (c) => {
  const database = db(c.env.DB);
  const limit = Math.min(Math.max(Number(c.req.query('limit') ?? 500) || 500, 1), 500);
  const offset = Math.max(Number(c.req.query('offset') ?? 0) || 0, 0);
  const q = c.req.query('q')?.trim();
  const filters: SQL[] = [
    eq(schema.people.status, 'active'),
    eq(schema.claims.reviewStatus, 'published'),
    eq(schema.claims.attributionStatus, 'verified_speaker'),
    trustedShowFilter(),
  ];
  if (q) {
    const match = `%${q}%`;
    const personMatch = or(
      like(schema.people.name, match),
      like(schema.people.title, match),
      like(schema.people.org, match)
    );
    if (personMatch) {
      filters.push(personMatch);
    }
  }
  const rows = await database
    .select({
      bio: schema.people.bio,
      claimCount: sql<number>`count(distinct ${schema.claims.id})`,
      id: schema.people.id,
      links: schema.people.links,
      name: schema.people.name,
      org: schema.people.org,
      slug: schema.people.slug,
      sourceCount: sql<number>`count(distinct ${schema.claims.episodeId})`,
      status: schema.people.status,
      title: schema.people.title,
    })
    .from(schema.people)
    .innerJoin(schema.claims, eq(schema.people.id, schema.claims.personId))
    .innerJoin(schema.episodes, eq(schema.claims.episodeId, schema.episodes.id))
    .innerJoin(schema.shows, eq(schema.episodes.showId, schema.shows.id))
    .where(and(...filters))
    .groupBy(schema.people.id)
    .orderBy(desc(sql`count(distinct ${schema.claims.id})`), schema.people.name)
    .limit(limit)
    .offset(offset);
  const [count] = await database
    .select({ total: sql<number>`count(distinct ${schema.people.id})` })
    .from(schema.people)
    .innerJoin(schema.claims, eq(schema.people.id, schema.claims.personId))
    .innerJoin(schema.episodes, eq(schema.claims.episodeId, schema.episodes.id))
    .innerJoin(schema.shows, eq(schema.episodes.showId, schema.shows.id))
    .where(and(...filters));
  return c.json({ people: rows, total: count?.total ?? rows.length });
});

publicRoute.get('/people/:slug', async (c) => {
  const slug = c.req.param('slug');
  if (slug === UNVERIFIED_SPEAKER_SLUG) {
    return c.json({ error: 'not_found' }, 404);
  }
  const [person] = await db(c.env.DB)
    .select()
    .from(schema.people)
    .where(eq(schema.people.slug, slug))
    .limit(1);
  if (!person || person.status !== 'active') {
    return c.json({ error: 'not_found' }, 404);
  }
  const claims = await publicClaims(c.env.DB, [eq(schema.claims.personId, person.id)], 500);
  if (!claims.length) {
    return c.json({ error: 'not_found' }, 404);
  }
  const recommendations = await publishedReferences(c.env.DB, { personId: person.id });
  return c.json({ claims, person, recommendations });
});

/**
 * Resolves the transcript window around an already-published claim.
 *
 * The claim has passed the published + trusted-show gate before this runs, so
 * the segment lookup only widens what is shown about a claim already public.
 * Every failure path returns null: missing data beats invented context.
 */
async function transcriptContextForClaim(
  env: Env,
  claim: { id: string; quote: string }
): Promise<ClaimTranscriptContext | null> {
  const [segment] = await db(env.DB)
    .select({ episodeId: schema.segments.episodeId, idx: schema.segments.idx })
    .from(schema.segments)
    .innerJoin(schema.claims, eq(schema.claims.segmentId, schema.segments.id))
    .where(eq(schema.claims.id, claim.id))
    .limit(1);
  if (!segment) {
    return null;
  }
  return await claimTranscriptContext(env.RAW, segment.episodeId, segment.idx, claim.quote);
}

publicRoute.get('/claims/:id', async (c) => {
  const id = c.req.param('id');
  const [claim] = await publicClaims(c.env.DB, [eq(schema.claims.id, id)], 1);
  if (!claim) {
    return c.json({ error: 'not_found' }, 404);
  }
  const rawEvidence = await db(c.env.DB)
    .select()
    .from(schema.claimEvidence)
    .where(eq(schema.claimEvidence.claimId, claim.id));
  const evidence = rawEvidence.map((row) => ({
    ...row,
    deepLinkUrl: claim.transcriptKind === 'youtube_captions' ? row.deepLinkUrl : null,
    timestampS: claim.transcriptKind === 'youtube_captions' ? row.timestampS : null,
  }));
  const rawReferences = await db(c.env.DB)
    .select()
    .from(schema.claimReferences)
    .where(
      and(
        eq(schema.claimReferences.claimId, claim.id),
        inArray(schema.claimReferences.role, [...ACTIONABLE_REFERENCE_ROLES])
      )
    );
  const references = rawReferences.flatMap((reference) =>
    sanitizeReferences([reference], claim.quote)
  );
  if (!wantsTranscriptContext(c.req.query('context'))) {
    return c.json({ claim, evidence, references });
  }
  const context = await transcriptContextForClaim(c.env, claim);
  return c.json({ claim, context, evidence, references });
});

publicRoute.get('/sources', async (c) => {
  const database = db(c.env.DB);
  const limit = Math.min(Math.max(Number(c.req.query('limit') ?? 200) || 200, 1), 500);
  const offset = Math.max(Number(c.req.query('offset') ?? 0) || 0, 0);
  const q = c.req.query('q')?.trim();
  const show = c.req.query('show');
  const filters: SQL[] = [eq(schema.claims.reviewStatus, 'published'), trustedShowFilter()];
  if (q) {
    const match = `%${q}%`;
    const sourceMatch = or(like(schema.episodes.title, match), like(schema.shows.name, match));
    if (sourceMatch) {
      filters.push(sourceMatch);
    }
  }
  if (show) {
    filters.push(eq(schema.shows.slug, show));
  }
  const rows = await database
    .select({
      claimCount: sql<number>`count(distinct ${schema.claims.id})`,
      peopleCount: sql<number>`count(distinct case when ${schema.claims.attributionStatus} = 'verified_speaker' then ${schema.claims.personId} end)`,
      ...publicSourceFields,
    })
    .from(schema.episodes)
    .innerJoin(schema.shows, eq(schema.episodes.showId, schema.shows.id))
    .innerJoin(schema.claims, eq(schema.episodes.id, schema.claims.episodeId))
    .where(and(...filters))
    .groupBy(schema.episodes.id)
    .orderBy(desc(schema.episodes.publishedAt))
    .limit(limit)
    .offset(offset);
  const [count] = await database
    .select({ total: sql<number>`count(distinct ${schema.claims.episodeId})` })
    .from(schema.claims)
    .innerJoin(schema.episodes, eq(schema.claims.episodeId, schema.episodes.id))
    .innerJoin(schema.shows, eq(schema.episodes.showId, schema.shows.id))
    .where(and(...filters));
  const publishers = await database
    .selectDistinct({ name: schema.shows.name, slug: schema.shows.slug })
    .from(schema.shows)
    .innerJoin(schema.episodes, eq(schema.shows.id, schema.episodes.showId))
    .innerJoin(schema.claims, eq(schema.episodes.id, schema.claims.episodeId))
    .where(and(eq(schema.claims.reviewStatus, 'published'), trustedShowFilter()))
    .orderBy(schema.shows.name);
  return c.json({ publishers, sources: rows, total: count?.total ?? rows.length });
});

publicRoute.get('/sources/:id', async (c) => {
  const id = c.req.param('id');
  const [episode] = await db(c.env.DB)
    .select(publicSourceFields)
    .from(schema.episodes)
    .innerJoin(schema.shows, eq(schema.episodes.showId, schema.shows.id))
    .where(and(eq(schema.episodes.id, id), trustedShowFilter()))
    .limit(1);
  if (!episode) {
    return c.json({ error: 'not_found' }, 404);
  }
  const claims = await publicClaims(c.env.DB, [eq(schema.claims.episodeId, episode.id)], 500);
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
  const linkedClaimIds = db(c.env.DB)
    .select({ claimId: schema.claimTopics.claimId })
    .from(schema.claimTopics)
    .where(eq(schema.claimTopics.topicId, topic.id));
  const claims = await publicClaims(c.env.DB, [inArray(schema.claims.id, linkedClaimIds)], 200);
  return c.json({ claims, topic });
});

function publishedFilters(query: {
  person?: string;
  type?: string;
  from?: string;
  to?: string;
}): SQL[] {
  const filters: SQL[] = [];
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
  if (match) {
    const ids = await ftsClaimIds(c.env.DB, match);
    if (!ids.length) {
      return c.json({ claims: [], evidence: 'insufficient' });
    }
    filters.push(inArray(schema.claims.id, ids));
  }
  if (topic) {
    const database = db(c.env.DB);
    const [topicRow] = await database
      .select()
      .from(schema.topics)
      .where(eq(schema.topics.slug, topic))
      .limit(1);
    if (!topicRow) {
      return c.json({ claims: [], evidence: 'insufficient' });
    }
    const linked = database
      .select({ claimId: schema.claimTopics.claimId })
      .from(schema.claimTopics)
      .where(eq(schema.claimTopics.topicId, topicRow.id));
    filters.push(inArray(schema.claims.id, linked));
  }
  const rows = await publicClaims(c.env.DB, filters, 50);
  if (!rows.length) {
    return c.json({ claims: [], evidence: 'insufficient' });
  }
  return c.json({ claims: rows });
});

export const recommendationFields = {
  assertion: schema.claims.assertion,
  attributionStatus: schema.claims.attributionStatus,
  claimId: schema.claims.id,
  deepLinkUrl: sql<
    string | null
  >`case when ${schema.episodes.transcriptKind} = 'youtube_captions' then ${schema.claimEvidence.deepLinkUrl} else null end`,
  episodeTitle: schema.episodes.title,
  kind: schema.claimReferences.kind,
  name: schema.claimReferences.name,
  personId: sql<
    string | null
  >`case when ${schema.claims.attributionStatus} = 'verified_speaker' then ${schema.claims.personId} else null end`,
  personName: sql<
    string | null
  >`case when ${schema.claims.attributionStatus} = 'verified_speaker' then ${schema.people.name} else null end`,
  quote: schema.claims.quote,
  role: schema.claimReferences.role,
  saidOn: schema.claims.saidOn,
  promptVersion: schema.claims.promptVersion,
  segmentId: schema.claims.segmentId,
  showName: schema.shows.name,
  sourceUrl: schema.episodes.sourceUrl,
  timestampS: sql<
    number | null
  >`case when ${schema.episodes.transcriptKind} = 'youtube_captions' then ${schema.claims.timestampS} else null end`,
  transcriptKind: schema.episodes.transcriptKind,
};

async function publishedReferences(
  d1: D1Database,
  filters: { personId?: string; kind?: string; name?: string; role?: string },
  limit = 200
) {
  const database = db(d1);
  const clauses: SQL[] = [
    eq(schema.claims.reviewStatus, 'published'),
    inArray(schema.claimReferences.role, [...ACTIONABLE_REFERENCE_ROLES]),
    trustedShowFilter(),
  ];
  if (filters.personId) {
    clauses.push(eq(schema.claims.personId, filters.personId));
  }
  if (filters.kind && !isReferenceKind(filters.kind)) {
    return [];
  }
  if (filters.role && !isActionableReferenceRole(filters.role)) {
    return [];
  }
  const rows = await database
    .select(recommendationFields)
    .from(schema.claimReferences)
    .innerJoin(schema.claims, eq(schema.claimReferences.claimId, schema.claims.id))
    .innerJoin(schema.episodes, eq(schema.claims.episodeId, schema.episodes.id))
    .innerJoin(schema.shows, eq(schema.episodes.showId, schema.shows.id))
    .innerJoin(schema.people, eq(schema.claims.personId, schema.people.id))
    .innerJoin(
      schema.claimEvidence,
      and(
        eq(schema.claimEvidence.claimId, schema.claims.id),
        eq(schema.claimEvidence.role, 'primary')
      )
    )
    .where(and(...clauses))
    .orderBy(desc(schema.claims.saidOn), asc(schema.claims.createdAt));
  const seen = new Set<string>();
  return rows
    .flatMap((row) => {
      const [reference] = sanitizeReferences(
        [{ kind: row.kind, name: row.name, role: row.role }],
        row.quote,
        row.quote,
        row.promptVersion?.startsWith('extract-book-answers-') ?? false
      );
      if (!reference) {
        return [];
      }
      if (filters.kind && reference.kind !== filters.kind) {
        return [];
      }
      if (filters.role && reference.role !== filters.role) {
        return [];
      }
      if (
        filters.name &&
        canonicalReferenceName(reference.name) !== canonicalReferenceName(filters.name)
      ) {
        return [];
      }
      const key = `${row.segmentId ?? row.claimId}|${row.personId}|${reference.kind}|${reference.role}|${canonicalReferenceName(reference.name)}`;
      if (seen.has(key)) {
        return [];
      }
      seen.add(key);
      const { promptVersion: _promptVersion, segmentId: _segmentId, ...publicRow } = row;
      return [{ ...publicRow, ...reference, assertion: referenceAssertion(reference) }];
    })
    .slice(0, limit);
}

async function personIdForSlug(d1: D1Database, slug?: string): Promise<string | undefined | null> {
  if (!slug) {
    return;
  }
  const [person] = await db(d1)
    .select({ id: schema.people.id })
    .from(schema.people)
    .where(eq(schema.people.slug, slug))
    .limit(1);
  return person?.id ?? null;
}

publicRoute.get('/recommendations', async (c) => {
  const personSlug = c.req.query('person');
  const personId = await personIdForSlug(c.env.DB, personSlug);
  if (personId === null) {
    return c.json({ evidence: 'insufficient', recommendations: [] });
  }
  const recommendations = await publishedReferences(c.env.DB, {
    kind: c.req.query('kind'),
    name: c.req.query('name'),
    personId,
    role: c.req.query('role'),
  });
  if (!recommendations.length) {
    return c.json({ evidence: 'insufficient', recommendations: [] });
  }
  return c.json({ recommendations });
});

publicRoute.get('/recommendation-groups', async (c) => {
  const recommendations = await publishedReferences(
    c.env.DB,
    { kind: c.req.query('kind'), role: c.req.query('role') },
    Number.MAX_SAFE_INTEGER
  );
  const q = c.req.query('q')?.trim().toLocaleLowerCase('en-US');
  const groups = groupRecommendationReferences(recommendations).filter(
    (group) => !q || group.name.toLocaleLowerCase('en-US').includes(q)
  );
  if (!groups.length) {
    return c.json({ evidence: 'insufficient', groups: [], total: 0 });
  }
  const limit = Math.min(Math.max(Number(c.req.query('limit') ?? 200) || 200, 1), 500);
  const offset = Math.max(Number(c.req.query('offset') ?? 0) || 0, 0);
  return c.json({ groups: groups.slice(offset, offset + limit), total: groups.length });
});

publicRoute.get('/stats', async (c) => {
  const database = db(c.env.DB);
  const [counts] = await database
    .select({
      episodes: sql<number>`count(distinct ${schema.claims.episodeId})`,
      people: sql<number>`count(distinct case when ${schema.claims.attributionStatus} = 'verified_speaker' then ${schema.claims.personId} end)`,
      publishedClaims: sql<number>`count(*)`,
    })
    .from(schema.claims)
    .innerJoin(schema.episodes, eq(schema.claims.episodeId, schema.episodes.id))
    .innerJoin(schema.shows, eq(schema.episodes.showId, schema.shows.id))
    .where(and(eq(schema.claims.reviewStatus, 'published'), trustedShowFilter()));
  const [catalog] = await database
    .select({
      catalogEpisodes: sql<number>`count(distinct ${schema.episodes.id})`,
      trustedShows: sql<number>`count(distinct ${schema.shows.id})`,
    })
    .from(schema.episodes)
    .innerJoin(schema.shows, eq(schema.episodes.showId, schema.shows.id))
    .where(and(eq(schema.shows.active, true), trustedShowFilter()));
  const [transcripts] = await database
    .select({ transcriptEpisodes: sql<number>`count(distinct ${schema.segments.episodeId})` })
    .from(schema.segments)
    .innerJoin(schema.episodes, eq(schema.segments.episodeId, schema.episodes.id))
    .innerJoin(schema.shows, eq(schema.episodes.showId, schema.shows.id))
    .where(trustedShowFilter());
  const references = await publishedReferences(c.env.DB, {}, Number.MAX_SAFE_INTEGER);
  return c.json({
    catalogEpisodes: catalog?.catalogEpisodes ?? 0,
    episodes: counts?.episodes ?? 0,
    people: counts?.people ?? 0,
    publishedClaims: counts?.publishedClaims ?? 0,
    publishedReferences: references.length,
    transcriptEpisodes: transcripts?.transcriptEpisodes ?? 0,
    trustedShows: catalog?.trustedShows ?? 0,
    trustPolicy: {
      withheldShows: WITHHELD_PUBLIC_SHOW_SLUGS.length,
      wording:
        'Two shows with unsafe diarization are withheld; unverified speakers inside trusted shows are labeled and excluded from people counts.',
    },
  });
});
