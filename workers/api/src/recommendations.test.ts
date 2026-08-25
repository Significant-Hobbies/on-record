import { describe, expect, it } from 'vitest';
import { schema } from './db';
import { recommendationFields } from './routes/public';

describe('recommendation response', () => {
  it('includes the primary evidence deep link', () => {
    expect(recommendationFields.deepLinkUrl).toBe(schema.claimEvidence.deepLinkUrl);
  });
});
