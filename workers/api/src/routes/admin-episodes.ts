import { eq } from 'drizzle-orm';
import { Hono } from 'hono';
import type { CueMap } from '@on-record/db';
import { db, schema } from '../db';
import { getSegmentBodies, putSegmentBodies } from '../segment-store';
import type { Env } from '../env';
import { newId, sha256Hex } from '../ids';

export const adminEpisodesRoute = new Hono<{ Bindings: Env }>();

export function segmentIndexesAreValid(indexes: number[]): boolean {
  return (
    new Set(indexes).size === indexes.length &&
    indexes.every((index) => Number.isInteger(index) && index >= 0)
  );
}

export function staleSegmentIds(
  existing: Array<{ id: string; idx: number }>,
  incomingIndexes: ReadonlySet<number>
): string[] {
  return existing
    .filter((segment) => !incomingIndexes.has(segment.idx))
    .map((segment) => segment.id);
}

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
    attributionSource: 'show_config' | 'metadata_match' | 'publisher_transcript' | 'llm';
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
  // The extractor needs the words; they live in R2 now.
  const bodies = await getSegmentBodies(c.env.RAW, id);
  return c.json({
    episode,
    extractedSegmentIds,
    people,
    segments: segments
      .sort((a, b) => a.idx - b.idx)
      .map((row) => ({
        ...row,
        diarLabel: bodies.get(row.idx)?.diarLabel ?? null,
        text: bodies.get(row.idx)?.text ?? '',
      })),
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
  // Each stage overwrites rawR2Key, so callers that want an earlier artefact
  // (the discovery payload, the cue list) ask for it by key.
  const requested = c.req.query('key');
  if (requested && !requested.startsWith(`episodes/${id}/`)) {
    return c.json({ error: 'bad_key' }, 400);
  }
  const [episode] = await db(c.env.DB)
    .select()
    .from(schema.episodes)
    .where(eq(schema.episodes.id, id))
    .limit(1);
  const key = requested ?? episode?.rawR2Key;
  if (!key) {
    return c.json({ error: 'not_found' }, 404);
  }
  const object = await c.env.RAW.get(key);
  if (!object) {
    return c.json({ error: 'not_found' }, 404);
  }
  return c.json({ content: await object.text(), key });
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
      cueMap?: CueMap;
      diarLabel?: string;
    }>;
  };
  const database = db(c.env.DB);
  const incoming = body.segments ?? [];
  const incomingIndexes = new Set(incoming.map((segment) => segment.idx));
  if (!segmentIndexesAreValid(incoming.map((segment) => segment.idx))) {
    return c.json({ error: 'bad_segment_indexes' }, 400);
  }
  const [claimed] = await database
    .select({ id: schema.claims.id })
    .from(schema.claims)
    .where(eq(schema.claims.episodeId, id))
    .limit(1);
  if (claimed) {
    return c.json({ error: 'segments_have_claims' }, 409);
  }
  await putSegmentBodies(
    c.env.RAW,
    id,
    incoming.map((s) => ({
      cueMap: s.cueMap ?? null,
      diarLabel: s.diarLabel ?? null,
      idx: s.idx,
      text: s.text,
    }))
  );
  if (incoming.length) {
    const statements = incoming.map((segment) =>
      c.env.DB.prepare(
        `INSERT INTO segments
          (id, episode_id, idx, start_s, end_s, text, speaker_hint, cue_map)
         VALUES (?, ?, ?, ?, ?, '', ?, NULL)
         ON CONFLICT(episode_id, idx) DO UPDATE SET
           start_s = excluded.start_s,
           end_s = excluded.end_s,
           text = '',
           speaker_hint = excluded.speaker_hint,
           cue_map = NULL`
      ).bind(newId(), id, segment.idx, segment.startS, segment.endS, segment.speakerHint ?? null)
    );
    // D1 batch is one round trip and one ordered transaction. Chunking keeps
    // large transcripts below provider statement limits without returning to
    // the old one-request-per-segment path.
    for (let start = 0; start < statements.length; start += 100) {
      await c.env.DB.batch(statements.slice(start, start + 100));
    }
  }
  const existing = await database
    .select({ id: schema.segments.id, idx: schema.segments.idx })
    .from(schema.segments)
    .where(eq(schema.segments.episodeId, id));
  const stale = staleSegmentIds(existing, incomingIndexes);
  for (let start = 0; start < stale.length; start += 100) {
    await c.env.DB.batch(
      stale
        .slice(start, start + 100)
        .map((segmentId) =>
          c.env.DB.prepare('DELETE FROM segments WHERE id = ? AND episode_id = ?').bind(
            segmentId,
            id
          )
        )
    );
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

adminEpisodesRoute.post('/episodes/:id/people', async (c) => {
  const id = c.req.param('id');
  const body = (await c.req.json()) as {
    people?: Array<{
      personId: string;
      confidence: number;
      attributionSource?: 'show_config' | 'metadata_match' | 'publisher_transcript' | 'llm';
      role?: 'host' | 'guest';
    }>;
  };
  const database = db(c.env.DB);
  for (const person of body.people ?? []) {
    await database
      .insert(schema.episodePeople)
      .values({
        attributionSource: person.attributionSource ?? 'llm',
        confidence: person.confidence,
        episodeId: id,
        personId: person.personId,
        role: person.role ?? 'guest',
      })
      .onConflictDoUpdate({
        set: {
          attributionSource: person.attributionSource ?? 'llm',
          confidence: person.confidence,
          ...(person.role ? { role: person.role } : {}),
        },
        target: [schema.episodePeople.episodeId, schema.episodePeople.personId],
      });
  }
  return c.json({ updated: (body.people ?? []).length });
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
      // An empty string means "clear this", not "store an empty id" — a
      // wrong video link has to be removable.
      youtubeVideoId: body.youtubeVideoId === '' ? null : (body.youtubeVideoId ?? undefined),
    })
    .where(eq(schema.episodes.id, id));
  return c.json({ ok: true });
});
