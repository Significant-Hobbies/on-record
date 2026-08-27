import { describe, expect, it } from 'vitest';
import { speakerHintMatchesPerson } from './speaker-hint';

describe('speakerHintMatchesPerson', () => {
  it('accepts an absent hint', () => {
    expect(speakerHintMatchesPerson(null, 'person-uuid', 'lex-fridman')).toBe(true);
  });

  it('accepts both persisted person ids and pipeline slugs', () => {
    expect(speakerHintMatchesPerson('person-uuid', 'person-uuid', 'lex-fridman')).toBe(true);
    expect(speakerHintMatchesPerson('lex-fridman', 'person-uuid', 'lex-fridman')).toBe(true);
  });

  it('rejects a different speaker', () => {
    expect(speakerHintMatchesPerson('andrej-karpathy', 'person-uuid', 'lex-fridman')).toBe(false);
  });
});
