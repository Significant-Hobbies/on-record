import { eq } from 'drizzle-orm';
import { Hono } from 'hono';
import { db, schema } from '../db';
import type { Env } from '../env';
import { newId, sha256Hex } from '../ids';

export const adminEpisodesRoute = new Hono<{ Bindings: Env }>();

type EpisodeInput = {
  showId: string;
  guid: string;
  title: string;
  description?: string;
  publishedAt?: number;
  sourceUrl?: string;
  audioUrl?: string;
  youtubeVideoId?: string;
  durationS?: number;
  status?: typeof schema.episodes.$inferInsert.status;
  statusDetail?: string;
  pipelineVersion?: string;
  people?: Array<{
    personId: string;
    role: 'host' | 'guest';
    attributionSource: 'show_config' | 'metadata_match' | 'llm';
    confidence?: number;
  }>;
};

adminEpisodesRoute.get('/episodes/:id', async (c) => {
  const id = c.req.param('id');
  const database = db(c.env.DB);
  const [episode] = await database
    .select()
    .from(schema.episodes)
    .where(eq(schema.episodes.id, id))
    .limit(1);
  if (!episode) {
    return c.json({ error: 'not_found' }, 404);
  }
  const segments = await database
    .select()
    .from(schema.segments)
    .where(eq(schema.segments.episodeId, id));
  const people = await database
    .select()
    .from(schema.episodePeople)
    .where(eq(schema.episodePeople.episodeId, id));
  const claimed = await database
    .select({ segmentId: schema.claims.segmentId })
    .from(schema.claims)
    .where(eq(schema.claims.episodeId, id));
  const extractedSegmentIds = [
    ...new Set(
      claimed.map((row) => row.segmentId).filter((value): value is string => Boolean(value))
    ),
  ];
  return c.json({
    episode,
    extractedSegmentIds,
    people,
    segments: segments.sort((a, b) => a.idx - b.idx),
  });
});

adminEpisodesRoute.post('/episodes/upsert', async (c) => {
  const episode = (await c.req.json()) as EpisodeInput;
  if (!(episode.showId && episode.guid && episode.title)) {
    return c.json({ error: 'bad_payload' }, 400);
  }
  const database = db(c.env.DB);
  const [existing] = await database
    .select()
    .from(schema.episodes)
    .where(eq(schema.episodes.guid, episode.guid))
    .limit(1);
  const id = existing?.id ?? newId();
  const now = new Date();
  const values = {
    audioUrl: episode.audioUrl ?? null,
    description: episode.description ?? null,
    durationS: episode.durationS ?? null,
    guid: episode.guid,
    pipelineVersion: episode.pipelineVersion ?? existing?.pipelineVersion ?? null,
    publishedAt: episode.publishedAt ? new Date(episode.publishedAt) : null,
    showId: episode.showId,
    sourceUrl: episode.sourceUrl ?? null,
    status: episode.status ?? existing?.status ?? 'discovered',
    statusDetail: episode.statusDetail ?? null,
    title: episode.title,
    updatedAt: now,
    youtubeVideoId: episode.youtubeVideoId ?? null,
  };
  if (existing) {
    await database.update(schema.episodes).set(values).where(eq(schema.episodes.id, id));
  } else {
    await database.insert(schema.episodes).values({ createdAt: now, id, ...values });
  }
  for (const person of episode.people ?? []) {
    await database
      .insert(schema.episodePeople)
      .values({
        attributionSource: person.attributionSource,
        confidence: person.confidence ?? null,
        episodeId: id,
        personId: person.personId,
        role: person.role,
      })
      .onConflictDoUpdate({
        set: {
          attributionSource: person.attributionSource,
          confidence: person.confidence ?? null,
          role: person.role,
        },
        target: [schema.episodePeople.episodeId, schema.episodePeople.personId],
      });
  }
  return c.json({ id });
});

adminEpisodesRoute.get('/episodes/:id/raw', async (c) => {
  const id = c.req.param('id');
  const [episode] = await db(c.env.DB)
    .select()
    .from(schema.episodes)
    .where(eq(schema.episodes.id, id))
    .limit(1);
  if (!episode?.rawR2Key) {
    return c.json({ error: 'not_found' }, 404);
  }
  const object = await c.env.RAW.get(episode.rawR2Key);
  if (!object) {
    return c.json({ error: 'not_found' }, 404);
  }
  return c.json({ content: await object.text(), key: episode.rawR2Key });
});

adminEpisodesRoute.post('/episodes/:id/raw', async (c) => {
  const id = c.req.param('id');
  const body = (await c.req.json()) as { key: string; content: string; contentType?: string };
  if (!body.key || typeof body.content !== 'string') {
    return c.json({ error: 'bad_payload' }, 400);
  }
  const bytes = new TextEncoder().encode(body.content);
  await c.env.RAW.put(body.key, bytes, {
    httpMetadata: { contentType: body.contentType ?? 'application/json' },
  });
  const rawHash = await sha256Hex(body.content);
  await db(c.env.DB)
    .update(schema.episodes)
    .set({ rawHash, rawR2Key: body.key, updatedAt: new Date() })
    .where(eq(schema.episodes.id, id));
  return c.json({ key: body.key, rawHash });
});

adminEpisodesRoute.post('/episodes/:id/segments', async (c) => {
  const id = c.req.param('id');
  const body = (await c.req.json()) as {
    transcriptKind?: typeof schema.episodes.$inferInsert.transcriptKind;
    segments?: Array<{
      idx: number;
      startS: number;
      endS: number;
      text: string;
      speakerHint?: string;
    }>;
  };
  const database = db(c.env.DB);
  const existing = await database
    .select()
    .from(schema.segments)
    .where(eq(schema.segments.episodeId, id));
  const byIdx = new Map(existing.map((row) => [row.idx, row]));
  for (const segment of body.segments ?? []) {
    const match = byIdx.get(segment.idx);
    if (match) {
      await database
        .update(schema.segments)
        .set({
          endS: segment.endS,
          speakerHint: segment.speakerHint ?? null,
          startS: segment.startS,
          text: segment.text,
        })
        .where(eq(schema.segments.id, match.id));
    } else {
      await database.insert(schema.segments).values({
        endS: segment.endS,
        episodeId: id,
        id: newId(),
        idx: segment.idx,
        speakerHint: segment.speakerHint ?? null,
        startS: segment.startS,
        text: segment.text,
      });
    }
  }
  await database
    .update(schema.episodes)
    .set({
      status: 'segmented',
      transcriptKind: body.transcriptKind ?? undefined,
      updatedAt: new Date(),
    })
    .where(eq(schema.episodes.id, id));
  const stored = await database
    .select()
    .from(schema.segments)
    .where(eq(schema.segments.episodeId, id));
  return c.json({
    ids: stored.sort((a, b) => a.idx - b.idx).map((row) => row.id),
  });
});

adminEpisodesRoute.post('/episodes/:id/status', async (c) => {
  const id = c.req.param('id');
  const body = (await c.req.json()) as {
    status: typeof schema.episodes.$inferInsert.status;
    statusDetail?: string;
    transcriptKind?: typeof schema.episodes.$inferInsert.transcriptKind;
    youtubeVideoId?: string;
  };
  await db(c.env.DB)
    .update(schema.episodes)
    .set({
      status: body.status,
      statusDetail: body.statusDetail ?? null,
      transcriptKind: body.transcriptKind ?? undefined,
      updatedAt: new Date(),
      youtubeVideoId: body.youtubeVideoId ?? undefined,
    })
    .where(eq(schema.episodes.id, id));
  return c.json({ ok: true });
});
