import { describe, expect, it } from 'vitest';
import {
  assertionForClaim,
  type IncomingClaim,
  requiresEvidencedReference,
  transcriptHasPreciseTimestamps,
} from './admin-claims';

const baseClaim: IncomingClaim = {
  assertion: 'Open model development will continue through 2026.',
  claimType: 'prediction',
  extractionConfidence: 0.95,
  personId: 'person-1',
  pipelineVersion: 'claims-v1',
  promptVersion: 'extract-v3',
  quote: 'There will be more open model builders throughout 2026 than there were in 2025.',
  segmentId: 'segment-1',
  speakerConfidence: 0.95,
  speakerRaw: 'nathan-lambert',
};

describe('general claim persistence', () => {
  it('does not invent timestamps for coarse text transcripts', () => {
    expect(transcriptHasPreciseTimestamps('rss_text_coarse')).toBe(false);
    expect(transcriptHasPreciseTimestamps('publisher_html_coarse')).toBe(false);
    expect(transcriptHasPreciseTimestamps('publisher_html')).toBe(true);
    expect(transcriptHasPreciseTimestamps('publisher_json')).toBe(true);
  });

  it('allows an evidenced prediction without a named reference', () => {
    expect(requiresEvidencedReference(baseClaim, [])).toBe(false);
    expect(assertionForClaim(baseClaim, [])).toBe(baseClaim.assertion);
  });

  it('still rejects an extract-v3 recommendation without surviving reference evidence', () => {
    expect(requiresEvidencedReference({ ...baseClaim, claimType: 'recommendation' }, [])).toBe(
      true
    );
  });

  it('keeps deterministic reference assertions for recommendation rows', () => {
    const refs = [{ kind: 'book', name: 'The Beginning of Infinity', role: 'recommends' }] as const;
    expect(assertionForClaim({ ...baseClaim, claimType: 'recommendation' }, [...refs])).toBe(
      'Recommends The Beginning of Infinity.'
    );
  });
});
