import { eq } from 'drizzle-orm';
import { Hono } from 'hono';
import { attributionStatusFor, type AttributionStatus } from '../attribution';
import { isClaimType } from '../claim-types';
import { bumpPublicCacheGeneration, db, markShowHasPublishedClaims, schema } from '../db';
import { youtubeDeepLink } from '../deep-link';
import type { Env } from '../env';
import { dedupeHash, newId } from '../ids';
import { judgeClaim } from '../publish-rules';
import { findVerbatimAnchor, normalizeWs } from '../quote';
import { getSegmentBodies, type SegmentBody } from '../segment-store';
import { speakerHintMatchesPerson } from '../speaker-hint';
import { timestampForOffset } from '../timestamp';
import { referenceAssertion, sanitizeReferences, type ClaimReference } from '../references';

export const adminClaimsRoute = new Hono<{ Bindings: Env }>();

export type IncomingClaim = {
  attributionStatus?: AttributionStatus;
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
  bookAnswer?: boolean;
};

type LlmRunInput = {
  model: string;
  promptVersion?: string;
  segmentId?: string;
  focus?: string;
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
  refs: ClaimReference[]
): Promise<void> {
  // Extraction is additive. A later model pass may identify another named
  // object in the same exact quote, but an empty or partial answer must not
  // erase previously validated evidence. Public reads re-sanitize every row,
  // so references rejected by a stronger validator no longer surface.
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

function referencesForClaim(incoming: IncomingClaim, body: SegmentBody): ClaimReference[] {
  const bookAnswerPrompt = incoming.promptVersion?.startsWith('extract-book-answers-') ?? false;
  return sanitizeReferences(
    incoming.references ?? [],
    incoming.quote,
    body.text,
    Boolean(incoming.bookAnswer && bookAnswerPrompt)
  );
}

function usesEvidencedReferencePrompt(promptVersion?: string): boolean {
  return (
    promptVersion === 'extract-v3' ||
    promptVersion === 'extract-v4' ||
    promptVersion === 'extract-recs-v5' ||
    promptVersion === 'extract-books-v1' ||
    promptVersion === 'extract-book-answers-v1' ||
    promptVersion === 'extract-book-answers-v2' ||
    promptVersion === 'extract-book-answers-v3' ||
    promptVersion === 'extract-book-answers-v4'
  );
}

export function transcriptHasPreciseTimestamps(kind: string | null): boolean {
  return Boolean(kind && kind !== 'none' && !kind.endsWith('_coarse'));
}

export function assertionForClaim(incoming: IncomingClaim, refs: ClaimReference[]): string {
  if (!usesEvidencedReferencePrompt(incoming.promptVersion) || refs.length === 0) {
    return incoming.assertion;
  }
  return refs.map((reference) => referenceAssertion(reference)).join(' ');
}

export function requiresEvidencedReference(
  incoming: IncomingClaim,
  refs: ClaimReference[]
): boolean {
  return (
    usesEvidencedReferencePrompt(incoming.promptVersion) &&
    incoming.claimType === 'recommendation' &&
    refs.length === 0
  );
}

function claimTimestamp(
  episode: typeof schema.episodes.$inferSelect,
  segment: typeof schema.segments.$inferSelect,
  body: SegmentBody,
  anchor: ReturnType<typeof findVerbatimAnchor>
): number | null {
  if (!transcriptHasPreciseTimestamps(episode.transcriptKind)) {
    return null;
  }
  return timestampForOffset(
    { cueMap: body.cueMap, endS: segment.endS, startS: segment.startS, text: body.text },
    anchor?.start ?? null
  );
}

function optionalClaimFields(
  incoming: IncomingClaim,
  decision: ReturnType<typeof judgeClaim>,
  anchor: ReturnType<typeof findVerbatimAnchor>,
  now: Date
) {
  return {
    model: incoming.model ?? null,
    pipelineVersion: incoming.pipelineVersion ?? 'claims-v1',
    promptVersion: incoming.promptVersion ?? null,
    publishedAt: decision.reviewStatus === 'published' ? now : null,
    quoteEndChar: anchor?.end ?? null,
    quoteStartChar: anchor?.start ?? null,
    stance: incoming.stance ?? null,
  };
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
  const attributionStatus = attributionStatusFor(incoming.speakerRaw, incoming.attributionStatus);
  const decision = judgeClaim({
    attributionStatus,
    extractionConfidence: incoming.extractionConfidence,
    quoteValidated: anchor !== null,
    speakerConfidence: incoming.speakerConfidence,
    speakerRaw: incoming.speakerRaw,
  });
  const refs = referencesForClaim(incoming, body);
  const hash = await dedupeHash(episode.id, incoming.personId, normalizeWs(incoming.quote));
  const [existing] = await database
    .select()
    .from(schema.claims)
    .where(eq(schema.claims.dedupeHash, hash))
    .limit(1);
  if (requiresEvidencedReference(incoming, refs)) {
    return { id: '', reason: 'no_evidenced_reference', reviewStatus: 'rejected' };
  }
  if (existing) {
    await persistReferences(database, existing.id, refs);
    return { id: existing.id, reason: 'duplicate', reviewStatus: existing.reviewStatus };
  }
  const assertion = assertionForClaim(incoming, refs);
  const id = newId();
  const timestampS = claimTimestamp(episode, segment, body, anchor);
  const now = new Date();
  await database.insert(schema.claims).values({
    ...optionalClaimFields(incoming, decision, anchor, now),
    assertion,
    attributionStatus,
    claimType: incoming.claimType as (typeof schema.claims.claimType.enumValues)[number],
    confidenceBand: decision.confidenceBand,
    createdAt: now,
    dedupeHash: hash,
    episodeId: episode.id,
    extractionConfidence: incoming.extractionConfidence,
    id,
    personId: incoming.personId,
    publishReason: decision.publishReason,
    quote: incoming.quote,
    reviewStatus: decision.reviewStatus,
    saidOn: episode.publishedAt,
    segmentId: segment.id,
    speakerConfidence: incoming.speakerConfidence,
    speakerRaw: incoming.speakerRaw,
    timestampS,
    version: 1,
  });
  await database.insert(schema.claimEvidence).values({
    claimId: id,
    deepLinkUrl: youtubeDeepLink(episode.youtubeVideoId, timestampS, episode.transcriptKind),
    episodeId: episode.id,
    id: newId(),
    quote: incoming.quote,
    role: 'primary',
    timestampS,
  });
  await persistTopics(database, id, incoming.topics ?? []);
  if (decision.reviewStatus === 'published') {
    await indexPublishedClaim(d1, id, assertion, incoming.quote);
  }
  await persistReferences(database, id, refs);
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
      focus: run.focus ?? null,
      id: newId(),
      latencyMs: run.latencyMs ?? null,
      model: run.model,
      promptVersion: run.promptVersion ?? null,
      reason: run.reason ?? null,
      requestJson: run.requestJson,
      responseJson: run.responseJson ?? null,
      segmentId: run.segmentId && segments.has(run.segmentId) ? run.segmentId : null,
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
  if (published > 0) {
    await markShowHasPublishedClaims(c.env.DB, episode.showId);
    await bumpPublicCacheGeneration(c.env.DB);
  }
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
    const timestampS = transcriptHasPreciseTimestamps(episode.transcriptKind)
      ? timestampForOffset(
          { cueMap: body.cueMap, endS: segment.endS, startS: segment.startS, text: body.text },
          anchor?.start ?? claim.quoteStartChar
        )
      : null;
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
      .set({
        deepLinkUrl: youtubeDeepLink(episode.youtubeVideoId, timestampS, episode.transcriptKind),
        timestampS,
      })
      .where(eq(schema.claimEvidence.claimId, claim.id));
  }
  return c.json({ claims: claims.length, moved });
});

async function unpublish(
  database: Database,
  d1: D1Database,
  claimId: string,
  reason: string
): Promise<void> {
  await database
    .update(schema.claims)
    .set({
      correctedAt: new Date(),
      publishedAt: null,
      publishReason: reason,
      reviewStatus: 'corrected',
    })
    .where(eq(schema.claims.id, claimId));
  // It must leave the search index too, or a retracted claim keeps surfacing.
  await d1.prepare('DELETE FROM claims_fts WHERE claim_id = ?').bind(claimId).run();
  await bumpPublicCacheGeneration(d1);
}

/**
 * Re-check every claim against the source as it stands now.
 *
 * Re-transcribing an episode rewrites its segments in place. Claims made
 * against the old text survive with quotes that may no longer appear anywhere
 * and speakers the new diarization disagrees with — 71 of 144 on the first
 * episode this happened to. Reprocessing must not leave the index asserting
 * two different people said the same sentence.
 */
adminClaimsRoute.post('/episodes/:id/reverify', async (c) => {
  const episodeId = c.req.param('id');
  const database = db(c.env.DB);
  const loaded = await loadEpisode(database, c.env.RAW, episodeId);
  if (!loaded) {
    return c.json({ error: 'episode_not_found' }, 404);
  }
  const { segments, bodies } = loaded;
  // Retracting is two writes a claim, so a long episode outruns the request
  // budget. Work a slice at a time and let the caller come back for more.
  const limit = Math.min(Number(c.req.query('limit') ?? 60) || 60, 200);
  const claims = await database
    .select()
    .from(schema.claims)
    .where(eq(schema.claims.episodeId, episodeId));
  const personSlugs = new Map(
    (
      await database.select({ id: schema.people.id, slug: schema.people.slug }).from(schema.people)
    ).map((person) => [person.id, person.slug])
  );
  let quoteGone = 0;
  let speakerChanged = 0;
  let kept = 0;
  for (const claim of claims) {
    if (claim.reviewStatus === 'corrected' || claim.reviewStatus === 'killed') {
      continue;
    }
    const segment = claim.segmentId ? segments.get(claim.segmentId) : undefined;
    const body = segment ? bodies.get(segment.idx) : undefined;
    if (!(segment && body && findVerbatimAnchor(body.text, claim.quote))) {
      quoteGone += 1;
      await unpublish(database, c.env.DB, claim.id, 'source_changed');
      continue;
    }
    if (
      !speakerHintMatchesPerson(
        segment.speakerHint,
        claim.personId,
        personSlugs.get(claim.personId)
      )
    ) {
      speakerChanged += 1;
      await unpublish(database, c.env.DB, claim.id, 'speaker_reattributed');
      continue;
    }
    kept += 1;
    if (quoteGone + speakerChanged >= limit) {
      return c.json({
        done: false,
        kept,
        quoteGone,
        speakerChanged,
        total: claims.length,
      });
    }
  }
  return c.json({ done: true, kept, quoteGone, speakerChanged, total: claims.length });
});
