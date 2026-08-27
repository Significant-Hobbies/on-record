import { describe, expect, it } from 'vitest';
import { segmentIndexesAreValid, staleSegmentIds } from './admin-episodes';

describe('segment replacement', () => {
  it('rejects duplicate, negative, and fractional segment indexes', () => {
    expect(segmentIndexesAreValid([0, 1, 2])).toBe(true);
    expect(segmentIndexesAreValid([0, 1, 1])).toBe(false);
    expect(segmentIndexesAreValid([0, -1])).toBe(false);
    expect(segmentIndexesAreValid([0, 1.5])).toBe(false);
  });

  it('identifies rows left over from a shorter replacement transcript', () => {
    const existing = [
      { id: 'segment-0', idx: 0 },
      { id: 'segment-1', idx: 1 },
      { id: 'segment-2', idx: 2 },
    ];
    expect(staleSegmentIds(existing, new Set([0, 1]))).toEqual(['segment-2']);
  });
});
