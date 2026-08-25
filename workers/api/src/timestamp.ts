import type { CueMap } from '@on-record/db';

export type TimestampSegment = {
  cueMap: CueMap | null;
  startS: number;
  endS: number;
  text: string;
};

function clamp(value: number, segment: TimestampSegment): number {
  const low = segment.startS;
  const high = Number.isFinite(segment.endS) && segment.endS > low ? segment.endS : value;
  return Math.round(Math.min(Math.max(value, Math.min(low, value)), high) * 100) / 100;
}

/**
 * When in the episode a quote was spoken, given where it starts in the
 * segment's text.
 *
 * Prefers the cue map recorded at segmentation time. Segments captured before
 * cue maps existed fall back to interpolating across the segment, which is
 * coarse but still far closer than pinning every claim to the segment start.
 */
export function timestampForOffset(segment: TimestampSegment, offset: number | null): number {
  if (offset === null || !Number.isFinite(offset) || offset < 0) {
    return segment.startS;
  }
  const map = segment.cueMap;
  if (map?.length) {
    let found: number | null = null;
    for (const [at, start] of map) {
      if (at > offset) {
        break;
      }
      found = start;
    }
    return found === null ? segment.startS : clamp(found, segment);
  }
  const span = segment.endS - segment.startS;
  const length = segment.text.length;
  if (span <= 0 || length <= 0) {
    return segment.startS;
  }
  const ratio = Math.min(1, offset / length);
  return clamp(segment.startS + ratio * span, segment);
}
