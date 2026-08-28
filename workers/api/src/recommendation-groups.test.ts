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
      },
    ]);
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
  it('normalizes Unicode, whitespace, and case without semantic aliasing', () => {
    expect(canonicalReferenceName('  Claude\u00a0Code ')).toBe('claude code');
    expect(canonicalReferenceName('Claude')).not.toBe(canonicalReferenceName('Claude Code'));
  });
});
