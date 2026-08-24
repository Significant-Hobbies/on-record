CREATE VIRTUAL TABLE `claims_fts` USING fts5(
  claim_id UNINDEXED,
  assertion,
  quote,
  tokenize = 'porter'
);
