import { describe, expect, it } from 'vitest';
import { sanitizeFtsQuery } from './fts';

describe('sanitizeFtsQuery', () => {
  it('strips FTS5 operators and AND-joins tokens', () => {
    expect(sanitizeFtsQuery('agents* AND "coding"')).toBe('"agents" AND "coding"');
  });

  it('returns null for operator-only input', () => {
    expect(sanitizeFtsQuery('***')).toBeNull();
    expect(sanitizeFtsQuery('   ')).toBeNull();
  });
});
