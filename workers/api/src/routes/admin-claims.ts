import { eq } from 'drizzle-orm';
import { Hono } from 'hono';
import { isClaimType } from '../claim-types';
import { db, schema } from '../db';
import { youtubeDeepLink } from '../deep-link';
import type { Env } from '../env';
import { dedupeHash, newId } from '../ids';
import { judgeClaim } from '../publish-rules';
import { findVerbatimAnchor, normalizeWs } from '../quote';
import { getSegmentBodies, type SegmentBody } from '../segment-store';
import { timestampForOffset } from '../timestamp';
import { sanitizeReferences, type ClaimReference } from '../references';

export const adminClaimsRoute = new Hono<{ Bindings: Env }>();

type IncomingClaim = {
  personId: string;
  segmentId: string;
  speakerRaw: string;
  claimType: string;
  assertion: string;
  stance?: string;
  quote: string;
  extractionConfidence: number;
  speakerConfidence: number;
  topics?: string[];
  model?: string;
  promptVersion?: string;
  pipelineVersion?: string;
  references?: ClaimReference[];
};

type LlmRunInput = {
  model: string;
  promptVersion?: string;
  accepted: boolean;
  reason?: string;
  requestJson: unknown;
  responseJson?: unknown;
  tokensIn?: number;
  tokensOut?: number;
  latencyMs?: number;
};

type Database = ReturnType<typeof db>;

async function indexPublishedClaim(
  d1: D1Database,
  claimId: string,
  assertion: string,
  quote: string
): Promise<void> {
  await d1
    .prepare('INSERT INTO claims_fts (claim_id, assertion, quote) VALUES (?, ?, ?)')
    .bind(claimId, assertion, quote)
    .run();
}

async function topicIdForSlug(database: Database, slug: string): Promise<string | null> {
  const [topic] = await database
    .select()
    .from(schema.topics)
    .where(eq(schema.topics.slug, slug))
    .limit(1);
  return topic?.id ?? null;
}

async function loadEpisode(
  database: Database,
  bucket: R2Bucket,
  episodeId: string
): Promise<{
  episode: typeof schema.episodes.$inferSelect;
  segments: Map<string, typeof schema.segments.$inferSelect>;
  bodies: Map<number, SegmentBody>;
} | null> {
  const [episode] = await database
    .select()
    .from(schema.episodes)
    .where(eq(schema.episodes.id, episodeId))
    .limit(1);
  if (!episode) {
    return null;
  }
  const rows = await database
    .select()
    .from(schema.segments)
    .where(eq(schema.segments.episodeId, episodeId));
  // One object read for the whole batch, not one per claim.
  const bodies = await getSegmentBodies(bucket, episodeId);
  return { bodies, episode, segments: new Map(rows.map((row) => [row.id, row])) };
}

async function persistTopics(database: Database, claimId: string, slugs: string[]): Promise<void> {
  for (const slug of slugs) {
    const topicId = await topicIdForSlug(database, slug);
    if (!topicId) {
      continue;
    }
    await database.insert(schema.claimTopics).values({ claimId, topicId }).onConflictDoNothing();
  }
}

async function persistReferences(
  database: Database,
  claimId: string,
  incoming: IncomingClaim,
  segmentText: string
): Promise<void> {
  const refs = sanitizeReferences(incoming.references ?? [], segmentText);
  for (const ref of refs) {
    await database
      .insert(schema.claimReferences)
      .values({
        claimId,
        id: newId(),
        kind: ref.kind,
        name: ref.name,
        role: ref.role,
      })
      .onConflictDoNothing();
  }
}

async function persistOneClaim(
  database: Database,
  d1: D1Database,
  episode: typeof schema.episodes.$inferSelect,
  segment: typeof schema.segments.$inferSelect,
  body: SegmentBody,
  incoming: IncomingClaim
): Promise<{ id: string; reviewStatus: string; reason: string }> {
  // The guarantee is unchanged: the quote must appear in the stored source
  // text. That text is now read from R2 rather than carried in the row.
  const anchor = findVerbatimAnchor(body.text, incoming.quote);
  const decision = judgeClaim({
    extractionConfidence: incoming.extractionConfidence,
    quoteValidated: anchor !== null,
    speakerConfidence: incoming.speakerConfidence,
    speakerRaw: incoming.speakerRaw,
  });
  const hash = await dedupeHash(episode.id, incoming.personId, normalizeWs(incoming.quote));
  const [existing] = await database
    .select()
    .from(schema.claims)
    .where(eq(schema.claims.dedupeHash, hash))
    .limit(1);
  if (existing) {
    await persistReferences(database, existing.id, incoming, body.text);
    return { id: existing.id, reason: 'duplicate', reviewStatus: existing.reviewStatus };
  }
  const id = newId();
  const timestampS = timestampForOffset(
    { cueMap: body.cueMap, endS: segment.endS, startS: segment.startS, text: body.text },
    anchor?.start ?? null
  );
  const now = new Date();
  await database.insert(schema.claims).values({
    assertion: incoming.assertion,
    claimType: incoming.claimType as (typeof schema.claims.claimType.enumValues)[number],
    confidenceBand: decision.confidenceBand,
    createdAt: now,
    dedupeHash: hash,
    episodeId: episode.id,
    extractionConfidence: incoming.extractionConfidence,
    id,
    model: incoming.model ?? null,
    personId: incoming.personId,
    pipelineVersion: incoming.pipelineVersion ?? 'claims-v1',
    promptVersion: incoming.promptVersion ?? null,
    publishedAt: decision.reviewStatus === 'published' ? now : null,
    publishReason: decision.publishReason,
    quote: incoming.quote,
    quoteEndChar: anchor?.end ?? null,
    quoteStartChar: anchor?.start ?? null,
    reviewStatus: decision.reviewStatus,
    saidOn: episode.publishedAt,
    segmentId: segment.id,
    speakerConfidence: incoming.speakerConfidence,
    speakerRaw: incoming.speakerRaw,
    stance: incoming.stance ?? null,
    timestampS,
    version: 1,
  });
  await database.insert(schema.claimEvidence).values({
    claimId: id,
    deepLinkUrl: youtubeDeepLink(episode.youtubeVideoId, timestampS),
    episodeId: episode.id,
    id: newId(),
    quote: incoming.quote,
    role: 'primary',
    timestampS,
  });
  await persistTopics(database, id, incoming.topics ?? []);
  if (decision.reviewStatus === 'published') {
    await indexPublishedClaim(d1, id, incoming.assertion, incoming.quote);
  }
  await persistReferences(database, id, incoming, body.text);
  return { id, reason: decision.publishReason, reviewStatus: decision.reviewStatus };
}

adminClaimsRoute.post('/episodes/:id/claims', async (c) => {
  const episodeId = c.req.param('id');
  const body = (await c.req.json()) as { claims?: IncomingClaim[]; llmRuns?: LlmRunInput[] };
  const database = db(c.env.DB);
  const loaded = await loadEpisode(database, c.env.RAW, episodeId);
  if (!loaded) {
    return c.json({ error: 'episode_not_found' }, 404);
  }
  const { episode, segments, bodies } = loaded;
  const results = [];
  let rejectedQuote = 0;
  let rejectedSpeaker = 0;
  let published = 0;
  for (const incoming of body.claims ?? []) {
    if (!isClaimType(incoming.claimType)) {
      results.push({ error: 'bad_claim_type' });
      continue;
    }
    const segment = segments.get(incoming.segmentId);
    if (!segment) {
      results.push({ error: 'segment_not_found' });
      continue;
    }
    const body_ = bodies.get(segment.idx);
    if (!body_) {
      results.push({ error: 'segment_body_missing' });
      continue;
    }
    const saved = await persistOneClaim(database, c.env.DB, episode, segment, body_, incoming);
    if (saved.reason === 'quote_not_verbatim') {
      rejectedQuote += 1;
    }
    if (saved.reason === 'unknown_speaker') {
      rejectedSpeaker += 1;
    }
    if (saved.reviewStatus === 'published') {
      published += 1;
    }
    results.push(saved);
  }
  for (const run of body.llmRuns ?? []) {
    await database.insert(schema.llmRuns).values({
      accepted: run.accepted,
      createdAt: new Date(),
      episodeId,
      id: newId(),
      latencyMs: run.latencyMs ?? null,
      model: run.model,
      promptVersion: run.promptVersion ?? null,
      reason: run.reason ?? null,
      requestJson: run.requestJson,
      responseJson: run.responseJson ?? null,
      tokensIn: run.tokensIn ?? null,
      tokensOut: run.tokensOut ?? null,
    });
  }
  await database
    .update(schema.episodes)
    .set({
      status: published > 0 ? 'published' : 'extracted',
      updatedAt: new Date(),
    })
    .where(eq(schema.episodes.id, episodeId));
  return c.json({ published, rejectedQuote, rejectedSpeaker, results });
});

adminClaimsRoute.post('/episodes/:id/retime', async (c) => {
  const episodeId = c.req.param('id');
  const database = db(c.env.DB);
  const loaded = await loadEpisode(database, c.env.RAW, episodeId);
  if (!loaded) {
    return c.json({ error: 'episode_not_found' }, 404);
  }
  const { episode, segments, bodies } = loaded;
  const claims = await database
    .select()
    .from(schema.claims)
    .where(eq(schema.claims.episodeId, episodeId));
  let moved = 0;
  for (const claim of claims) {
    const segment = claim.segmentId ? segments.get(claim.segmentId) : undefined;
    if (!segment) {
      continue;
    }
    const body = bodies.get(segment.idx);
    if (!body) {
      continue;
    }
    const anchor = findVerbatimAnchor(body.text, claim.quote);
    const timestampS = timestampForOffset(
      { cueMap: body.cueMap, endS: segment.endS, startS: segment.startS, text: body.text },
      anchor?.start ?? claim.quoteStartChar
    );
    if (timestampS === claim.timestampS) {
      continue;
    }
    moved += 1;
    await database
      .update(schema.claims)
      .set({
        quoteEndChar: anchor?.end ?? claim.quoteEndChar,
        quoteStartChar: anchor?.start ?? claim.quoteStartChar,
        timestampS,
      })
      .where(eq(schema.claims.id, claim.id));
    await database
      .update(schema.claimEvidence)
      .set({ deepLinkUrl: youtubeDeepLink(episode.youtubeVideoId, timestampS), timestampS })
      .where(eq(schema.claimEvidence.claimId, claim.id));
  }
  return c.json({ claims: claims.length, moved });
});
