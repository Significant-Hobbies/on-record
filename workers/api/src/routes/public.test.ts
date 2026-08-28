import { describe, expect, it } from 'vitest';
import { isTrustedPublicShowSlug, WITHHELD_PUBLIC_SHOW_SLUGS } from './public';

describe('trusted public show boundary', () => {
  it('withholds shows whose diarized speakers remain unresolved', () => {
    expect(WITHHELD_PUBLIC_SHOW_SLUGS).toEqual(['odd-lots', 'tbpn']);
    expect(isTrustedPublicShowSlug('odd-lots')).toBe(false);
    expect(isTrustedPublicShowSlug('tbpn')).toBe(false);
  });

  it('keeps verified publisher-transcript shows public', () => {
    expect(isTrustedPublicShowSlug('lennys')).toBe(true);
    expect(isTrustedPublicShowSlug('lex-fridman')).toBe(true);
  });
});
