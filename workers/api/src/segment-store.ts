import type { CueMap } from '@on-record/db';

/**
 * Segment text and cue maps live in R2, not D1.
 *
 * Nothing public ever reads them — they exist so a claim's quote can be
 * checked against its source and its timestamp resolved at write time. At
 * 2,600 episodes that is roughly 400MB of raw material no reader would ever
 * see, so D1 keeps only the anchor row the claim's foreign key points at.
 *
 * One object per episode, fetched once per batch rather than per claim.
 */
export type StoredSegment = {
  idx: number;
  text: string;
  cueMap: CueMap | null;
};

export type SegmentBody = { text: string; cueMap: CueMap | null };

function segmentsKey(episodeId: string): string {
  return `episodes/${episodeId}/segments.json`;
}

export async function putSegmentBodies(
  bucket: R2Bucket,
  episodeId: string,
  segments: StoredSegment[]
): Promise<void> {
  const byIdx: Record<string, SegmentBody> = {};
  for (const segment of segments) {
    byIdx[String(segment.idx)] = { cueMap: segment.cueMap ?? null, text: segment.text };
  }
  await bucket.put(segmentsKey(episodeId), JSON.stringify(byIdx), {
    httpMetadata: { contentType: 'application/json' },
  });
}

export async function getSegmentBodies(
  bucket: R2Bucket,
  episodeId: string
): Promise<Map<number, SegmentBody>> {
  const object = await bucket.get(segmentsKey(episodeId));
  if (!object) {
    return new Map();
  }
  let parsed: Record<string, SegmentBody>;
  try {
    parsed = JSON.parse(await object.text()) as Record<string, SegmentBody>;
  } catch {
    // A body we cannot read must not silently become "quote not found" —
    // an empty map makes every claim fail validation, which is the safe end.
    return new Map();
  }
  const out = new Map<number, SegmentBody>();
  for (const [idx, body] of Object.entries(parsed)) {
    out.set(Number(idx), { cueMap: body?.cueMap ?? null, text: String(body?.text ?? '') });
  }
  return out;
}
