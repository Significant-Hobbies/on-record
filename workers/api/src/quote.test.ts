import { describe, expect, it } from 'vitest';
import { findVerbatimAnchor, quoteIsValid } from './quote';

const segment =
  'I think software development is shifting toward supervising coding agents, not writing every line.';

describe('findVerbatimAnchor', () => {
  it('accepts a whitespace-normalized contiguous quote', () => {
    const quote = 'software   development is shifting toward supervising coding agents';
    const anchor = findVerbatimAnchor(segment, quote);
    expect(anchor).not.toBeNull();
    expect(segment.slice(anchor!.start, anchor!.end)).toContain('software development');
  });

  it('rejects paraphrases', () => {
    expect(
      quoteIsValid(segment, 'engineers will mostly babysit AI tools going forward forever')
    ).toBe(false);
  });

  it('rejects short quotes', () => {
    expect(findVerbatimAnchor(segment, 'I think software development')).toBeNull();
  });
});
