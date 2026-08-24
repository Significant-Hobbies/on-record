CREATE TABLE `claim_references` (
  `id` text PRIMARY KEY NOT NULL,
  `claim_id` text NOT NULL,
  `kind` text NOT NULL,
  `name` text NOT NULL,
  `role` text NOT NULL,
  FOREIGN KEY (`claim_id`) REFERENCES `claims`(`id`)
);
--> statement-breakpoint
CREATE INDEX `claim_references_claim_idx` ON `claim_references` (`claim_id`);
--> statement-breakpoint
CREATE INDEX `claim_references_kind_role_idx` ON `claim_references` (`kind`, `role`);
--> statement-breakpoint
CREATE UNIQUE INDEX `claim_references_unique` ON `claim_references` (`claim_id`, `kind`, `role`, `name`);
