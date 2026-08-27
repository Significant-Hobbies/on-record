import { describe, expect, it } from 'vitest';
import { schema } from './db';
import { recommendationFields } from './routes/public';

describe('recommendation response', () => {
  it('includes the complete source receipt', () => {
    expect(recommendationFields.deepLinkUrl).toBe(schema.claimEvidence.deepLinkUrl);
    expect(recommendationFields.episodeTitle).toBe(schema.episodes.title);
    expect(recommendationFields.showName).toBe(schema.shows.name);
    expect(recommendationFields.sourceUrl).toBe(schema.episodes.sourceUrl);
  });
});
