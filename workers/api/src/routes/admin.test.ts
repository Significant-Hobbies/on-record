import { describe, expect, it } from 'vitest';
import { reviewStatusIsIndexed } from './admin';

describe('manual review search indexing', () => {
  it('indexes only claims that remain published', () => {
    expect(reviewStatusIsIndexed('published')).toBe(true);
    expect(reviewStatusIsIndexed('held')).toBe(false);
    expect(reviewStatusIsIndexed('killed')).toBe(false);
    expect(reviewStatusIsIndexed('corrected')).toBe(false);
  });
});
