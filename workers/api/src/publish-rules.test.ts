import { describe, expect, it } from 'vitest';
import { judgeClaim } from './publish-rules';

describe('judgeClaim', () => {
  it('publishes high confidence with a validated quote', () => {
    const decision = judgeClaim({
      extractionConfidence: 0.9,
      quoteValidated: true,
      speakerConfidence: 0.88,
      speakerRaw: 'andrej-karpathy',
    });
    expect(decision).toEqual({
      confidenceBand: 'high',
      publishReason: 'high_confidence',
      reviewStatus: 'published',
    });
  });

  it('holds medium confidence', () => {
    const decision = judgeClaim({
      extractionConfidence: 0.7,
      quoteValidated: true,
      speakerConfidence: 0.7,
      speakerRaw: 'sam-altman',
    });
    expect(decision.reviewStatus).toBe('held');
    expect(decision.confidenceBand).toBe('medium');
  });

  it('drafts unknown speakers even at high confidence', () => {
    const decision = judgeClaim({
      extractionConfidence: 0.99,
      quoteValidated: true,
      speakerConfidence: 0.99,
      speakerRaw: 'unknown',
    });
    expect(decision.reviewStatus).toBe('draft');
    expect(decision.publishReason).toBe('unknown_speaker');
  });

  it('drafts paraphrases that fail quote validation', () => {
    const decision = judgeClaim({
      extractionConfidence: 0.99,
      quoteValidated: false,
      speakerConfidence: 0.99,
      speakerRaw: 'andrej-karpathy',
    });
    expect(decision.publishReason).toBe('quote_not_verbatim');
    expect(decision.reviewStatus).toBe('draft');
  });
});
