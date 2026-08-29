import { findVerbatimAnchor } from './quote';
import { getSegmentBodies } from './segment-store';

/**
 * Surrounding transcript context for a published claim.
 *
 * `text` is stored transcript text, never generated: the claim's own segment
 * plus at most one neighbouring segment on each side. `quoteStart`/`quoteEnd`
 * are character offsets into `text` marking the verbatim quote, so a reader can
 * see the excerpt inside what was actually said without the two ever being
 * confused for each other.
 */
export type ClaimTranscriptContext = {
  text: string;
  quoteStart: number;
  quoteEnd: number;
};

/** How many stored segments either side of the claim's own segment to include. */
const CONTEXT_SEGMENT_RADIUS = 1;

const SEGMENT_JOIN = '\n\n';

/** True only for an explicit opt-in, so the default receipt costs no R2 read. */
export function wantsTranscriptContext(value: string | undefined): boolean {
  return value === '1' || value === 'true';
}

function joinSegments(parts: string[]): string {
  return parts.filter((part) => part.length > 0).join(SEGMENT_JOIN);
}

/**
 * Builds the context window for one claim, or null when it cannot be proved.
 *
 * Returns null when the episode body is missing or unreadable, when the claim's
 * own segment is absent, or when the quote cannot be anchored in the stored
 * text. Context that does not demonstrably contain the published quote would be
 * confident misinformation, so no context is the correct answer.
 */
export async function claimTranscriptContext(
  bucket: R2Bucket,
  episodeId: string,
  idx: number,
  quote: string
): Promise<ClaimTranscriptContext | null> {
  const bodies = await getSegmentBodies(bucket, episodeId);
  const own = bodies.get(idx)?.text?.trim() ?? '';
  if (!own) {
    return null;
  }
  const anchor = findVerbatimAnchor(own, quote);
  if (!anchor) {
    return null;
  }
  const before = joinSegments(
    Array.from({ length: CONTEXT_SEGMENT_RADIUS }, (_, step) =>
      (bodies.get(idx - CONTEXT_SEGMENT_RADIUS + step)?.text ?? '').trim()
    )
  );
  const after = joinSegments(
    Array.from({ length: CONTEXT_SEGMENT_RADIUS }, (_, step) =>
      (bodies.get(idx + 1 + step)?.text ?? '').trim()
    )
  );
  const lead = before ? before + SEGMENT_JOIN : '';
  const tail = after ? SEGMENT_JOIN + after : '';
  return {
    quoteEnd: lead.length + anchor.end,
    quoteStart: lead.length + anchor.start,
    text: lead + own + tail,
  };
}
