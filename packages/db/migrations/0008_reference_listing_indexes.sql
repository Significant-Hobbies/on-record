--> The public reference listing joins `claim_references` to claims, episodes,
--> shows, people, and the primary evidence row. Nothing indexed `role` on its
--> own, so SQLite had no cheap entry point and drove the join from a full scan
--> of `claim_evidence` — every published claim visited five times over to
--> return roughly a thousand references. Leading on `role` makes the six
--> actionable roles a short index range and puts the smallest table first.
CREATE INDEX `claim_references_role_claim_idx`
ON `claim_references` (`role`, `claim_id`);
--> statement-breakpoint
--> The evidence join wants one exact row per claim, not every evidence row for
--> that claim filtered afterwards. Carrying `role` in the index keeps
--> corroboration and contradiction rows out of the scan.
CREATE INDEX `claim_evidence_claim_role_idx`
ON `claim_evidence` (`claim_id`, `role`);
