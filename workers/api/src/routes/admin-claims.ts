import { eq } from 'drizzle-orm';
import { Hono } from 'hono';
import { isClaimType } from '../claim-types';
import { db, schema } from '../db';
import { youtubeDeepLink } from '../deep-link';
import type { Env } from '../env';
import { dedupeHash, newId } from '../ids';
import { judgeClaim } from '../publish-rules';
import { findVerbatimAnchor, normalizeWs } from '../quote';

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

async function persistOneClaim(
  database: Database,
  d1: D1Database,
  episode: typeof schema.episodes.$inferSelect,
  segment: typeof schema.segments.$inferSelect,
  incoming: IncomingClaim
): Promise<{ id: string; reviewStatus: string; reason: string }> {
  const anchor = findVerbatimAnchor(segment.text, incoming.quote);
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
    return { id: existing.id, reason: 'duplicate', reviewStatus: existing.reviewStatus };
  }
  const id = newId();
  const timestampS = segment.startS;
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
  for (const slug of incoming.topics ?? []) {
    const topicId = await topicIdForSlug(database, slug);
    if (!topicId) {
      continue;
    }
    await database
      .insert(schema.claimTopics)
      .values({ claimId: id, topicId })
      .onConflictDoNothing();
  }
  if (decision.reviewStatus === 'published') {
    await indexPublishedClaim(d1, id, incoming.assertion, incoming.quote);
  }
  return { id, reason: decision.publishReason, reviewStatus: decision.reviewStatus };
}

adminClaimsRoute.post('/episodes/:id/claims', async (c) => {
  const episodeId = c.req.param('id');
  const body = (await c.req.json()) as { claims?: IncomingClaim[]; llmRuns?: LlmRunInput[] };
  const database = db(c.env.DB);
  const [episode] = await database
    .select()
    .from(schema.episodes)
    .where(eq(schema.episodes.id, episodeId))
    .limit(1);
  if (!episode) {
    return c.json({ error: 'episode_not_found' }, 404);
  }
  const segmentRows = await database
    .select()
    .from(schema.segments)
    .where(eq(schema.segments.episodeId, episodeId));
  const segments = new Map(segmentRows.map((row) => [row.id, row]));
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
    const saved = await persistOneClaim(database, c.env.DB, episode, segment, incoming);
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
