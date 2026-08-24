import { describe, expect, it } from 'vitest';
import { sanitizeReferences } from './references';

const segment =
  'I still recommend The Sovereign Individual, and personally I use Cursor every day.';

describe('sanitizeReferences', () => {
  it('keeps names that appear in the segment', () => {
    const refs = sanitizeReferences(
      [
        { kind: 'book', name: 'The Sovereign Individual', role: 'recommends' },
        { kind: 'app', name: 'Cursor', role: 'uses' },
      ],
      segment
    );
    expect(refs).toHaveLength(2);
  });

  it('drops hallucinated titles', () => {
    const refs = sanitizeReferences(
      [{ kind: 'book', name: 'Invented Title', role: 'recommends' }],
      segment
    );
    expect(refs).toEqual([]);
  });
});
