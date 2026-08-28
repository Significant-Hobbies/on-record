import { describe, expect, it } from 'vitest';
import { segmentIndexesAreValid, speakerRepairRejection, staleSegmentIds } from './admin-episodes';

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

describe('speaker repairs', () => {
  const repair = { diarLabel: 'SPEAKER_01', speakerHint: 'guest-one' };
  const segment = { id: 'segment-1', speakerHint: 'unknown' };
  const roster = new Set(['guest-one']);

  it('accepts only an unknown, unclaimed segment with matching stored evidence', () => {
    expect(speakerRepairRejection(repair, segment, 'SPEAKER_01', roster, new Set())).toBeNull();
  });

  it('rejects drift in the label, roster, existing identity, or claim state', () => {
    expect(speakerRepairRejection(repair, segment, 'SPEAKER_02', roster, new Set())).toBe(
      'diar_label_mismatch'
    );
    expect(speakerRepairRejection(repair, segment, 'SPEAKER_01', new Set(), new Set())).toBe(
      'speaker_not_in_episode'
    );
    expect(
      speakerRepairRejection(
        repair,
        { id: 'segment-1', speakerHint: 'somebody-else' },
        'SPEAKER_01',
        roster,
        new Set()
      )
    ).toBe('speaker_already_known');
    expect(
      speakerRepairRejection(repair, segment, 'SPEAKER_01', roster, new Set(['segment-1']))
    ).toBe('segment_has_claims');
  });
});
