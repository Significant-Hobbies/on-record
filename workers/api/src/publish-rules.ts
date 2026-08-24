type ConfidenceBand = 'low' | 'medium' | 'high';
type ReviewStatus = 'draft' | 'held' | 'published';

export type PublishInput = {
  speakerRaw: string;
  extractionConfidence: number;
  speakerConfidence: number;
  quoteValidated: boolean;
};

export type PublishDecision = {
  confidenceBand: ConfidenceBand;
  reviewStatus: ReviewStatus;
  publishReason: string;
};

function isUnknownSpeaker(speakerRaw: string): boolean {
  return speakerRaw.trim().toLowerCase() === 'unknown';
}

export function judgeClaim(input: PublishInput): PublishDecision {
  if (!input.quoteValidated) {
    return {
      confidenceBand: 'low',
      publishReason: 'quote_not_verbatim',
      reviewStatus: 'draft',
    };
  }
  if (isUnknownSpeaker(input.speakerRaw)) {
    return {
      confidenceBand: 'low',
      publishReason: 'unknown_speaker',
      reviewStatus: 'draft',
    };
  }
  const extraction = input.extractionConfidence;
  const speaker = input.speakerConfidence;
  if (extraction >= 0.85 && speaker >= 0.85) {
    return {
      confidenceBand: 'high',
      publishReason: 'high_confidence',
      reviewStatus: 'published',
    };
  }
  if (extraction >= 0.65 && speaker >= 0.65) {
    return {
      confidenceBand: 'medium',
      publishReason: 'medium_confidence',
      reviewStatus: 'held',
    };
  }
  return {
    confidenceBand: 'low',
    publishReason: 'low_confidence',
    reviewStatus: 'draft',
  };
}
