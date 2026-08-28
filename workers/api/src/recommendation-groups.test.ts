import { describe, expect, it } from 'vitest';
import { canonicalReferenceName, groupRecommendationReferences } from './recommendation-groups';

describe('groupRecommendationReferences', () => {
  it('counts one person once per item and role across repeated episodes', () => {
    const groups = groupRecommendationReferences([
      { kind: 'book', name: 'The Goal', personId: 'one', role: 'recommends' },
      { kind: 'book', name: '  the   goal ', personId: 'one', role: 'recommends' },
      { kind: 'book', name: 'THE GOAL', personId: 'two', role: 'uses' },
    ]);
    expect(groups).toEqual([
      {
        kind: 'book',
        name: 'The Goal',
        occurrenceCount: 3,
        peopleCount: 2,
        roleCounts: {
          avoids: 0,
          built: 0,
          likes: 0,
          owns: 0,
          recommends: 1,
          uses: 1,
        },
        unverifiedSpeakerCount: 0,
      },
    ]);
  });

  it('keeps unverified evidence without counting it as a distinct person', () => {
    const [group] = groupRecommendationReferences([
      {
        attributionStatus: 'speaker_unverified',
        kind: 'book',
        name: 'The Goal',
        personId: null,
        role: 'recommends',
      },
      {
        attributionStatus: 'verified_speaker',
        kind: 'book',
        name: 'The Goal',
        personId: 'one',
        role: 'recommends',
      },
    ]);
    expect(group.occurrenceCount).toBe(2);
    expect(group.peopleCount).toBe(1);
    expect(group.roleCounts.recommends).toBe(1);
    expect(group.unverifiedSpeakerCount).toBe(1);
  });

  it('does not count a missing verified person identifier', () => {
    const [group] = groupRecommendationReferences([
      {
        attributionStatus: 'verified_speaker',
        kind: 'app',
        name: 'Linear',
        personId: null,
        role: 'uses',
      },
    ]);
    expect(group.occurrenceCount).toBe(1);
    expect(group.peopleCount).toBe(0);
    expect(group.roleCounts.uses).toBe(0);
  });

  it('does not merge the same words across different kinds', () => {
    const groups = groupRecommendationReferences([
      { kind: 'app', name: 'Open', personId: 'one', role: 'uses' },
      { kind: 'book', name: 'Open', personId: 'two', role: 'uses' },
    ]);
    expect(groups).toHaveLength(2);
  });
});

describe('canonicalReferenceName', () => {
  it('normalizes Unicode, whitespace, case, and audited title aliases', () => {
    expect(canonicalReferenceName('  Claude\u00a0Code ')).toBe('claude code');
    expect(canonicalReferenceName('Claude')).not.toBe(canonicalReferenceName('Claude Code'));
    expect(canonicalReferenceName('Name of the Wind')).toBe('the name of the wind');
    expect(canonicalReferenceName('The Name of The Wind')).toBe('the name of the wind');
  });

  it('groups audited aliases under a canonical display title', () => {
    const [group] = groupRecommendationReferences([
      { kind: 'book', name: 'Name of the Wind', personId: 'one', role: 'likes' },
      { kind: 'book', name: 'The Name of The Wind', personId: 'two', role: 'uses' },
    ]);
    expect(group.name).toBe('The Name of the Wind');
    expect(group.occurrenceCount).toBe(2);
    expect(group.peopleCount).toBe(2);
  });

  it('merges audited punctuation, transcript, and subtitle variants', () => {
    const groups = groupRecommendationReferences([
      { kind: 'book', name: 'High-Output Management', personId: 'one', role: 'likes' },
      { kind: 'book', name: 'In Order, High Output Management', personId: 'two', role: 'uses' },
      { kind: 'book', name: 'High Output Management', personId: 'three', role: 'recommends' },
    ]);
    expect(groups).toEqual([
      expect.objectContaining({
        name: 'High Output Management',
        occurrenceCount: 3,
        peopleCount: 3,
      }),
    ]);
    expect(canonicalReferenceName('Skilling People')).toBe('scaling people');
    expect(canonicalReferenceName('Thinking Slow and Fast')).toBe('thinking, fast and slow');
  });
});
