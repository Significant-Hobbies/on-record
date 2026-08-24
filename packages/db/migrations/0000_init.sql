CREATE TABLE `people` (
  `id` text PRIMARY KEY NOT NULL,
  `slug` text NOT NULL,
  `name` text NOT NULL,
  `title` text,
  `org` text,
  `aliases` text,
  `bio` text,
  `links` text,
  `status` text NOT NULL DEFAULT 'active',
  `created_at` integer NOT NULL,
  `updated_at` integer NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `people_slug_idx` ON `people` (`slug`);
--> statement-breakpoint
CREATE TABLE `shows` (
  `id` text PRIMARY KEY NOT NULL,
  `slug` text NOT NULL,
  `name` text NOT NULL,
  `feed_url` text,
  `podcast_index_feed_id` integer,
  `youtube_channel_id` text,
  `host_person_ids` text,
  `active` integer NOT NULL DEFAULT 1,
  `created_at` integer NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `shows_slug_idx` ON `shows` (`slug`);
--> statement-breakpoint
CREATE TABLE `topics` (
  `id` text PRIMARY KEY NOT NULL,
  `slug` text NOT NULL,
  `name` text NOT NULL,
  `status` text NOT NULL DEFAULT 'approved'
);
--> statement-breakpoint
CREATE UNIQUE INDEX `topics_slug_idx` ON `topics` (`slug`);
--> statement-breakpoint
CREATE TABLE `episodes` (
  `id` text PRIMARY KEY NOT NULL,
  `show_id` text NOT NULL,
  `guid` text NOT NULL,
  `title` text NOT NULL,
  `description` text,
  `published_at` integer,
  `source_url` text,
  `audio_url` text,
  `youtube_video_id` text,
  `duration_s` integer,
  `transcript_kind` text,
  `raw_r2_key` text,
  `raw_hash` text,
  `status` text NOT NULL DEFAULT 'discovered',
  `status_detail` text,
  `pipeline_version` text,
  `created_at` integer NOT NULL,
  `updated_at` integer NOT NULL,
  FOREIGN KEY (`show_id`) REFERENCES `shows`(`id`)
);
--> statement-breakpoint
CREATE UNIQUE INDEX `episodes_guid_idx` ON `episodes` (`guid`);
--> statement-breakpoint
CREATE INDEX `episodes_show_status_idx` ON `episodes` (`show_id`, `status`);
--> statement-breakpoint
CREATE INDEX `episodes_published_idx` ON `episodes` (`published_at`);
--> statement-breakpoint
CREATE TABLE `episode_people` (
  `episode_id` text NOT NULL,
  `person_id` text NOT NULL,
  `role` text NOT NULL,
  `attribution_source` text NOT NULL,
  `confidence` real,
  PRIMARY KEY (`episode_id`, `person_id`),
  FOREIGN KEY (`episode_id`) REFERENCES `episodes`(`id`),
  FOREIGN KEY (`person_id`) REFERENCES `people`(`id`)
);
--> statement-breakpoint
CREATE TABLE `segments` (
  `id` text PRIMARY KEY NOT NULL,
  `episode_id` text NOT NULL,
  `idx` integer NOT NULL,
  `start_s` real NOT NULL,
  `end_s` real NOT NULL,
  `text` text NOT NULL,
  `speaker_hint` text,
  FOREIGN KEY (`episode_id`) REFERENCES `episodes`(`id`)
);
--> statement-breakpoint
CREATE UNIQUE INDEX `segments_episode_idx` ON `segments` (`episode_id`, `idx`);
--> statement-breakpoint
CREATE INDEX `segments_episode_id_idx` ON `segments` (`episode_id`);
--> statement-breakpoint
CREATE TABLE `claims` (
  `id` text PRIMARY KEY NOT NULL,
  `dedupe_hash` text NOT NULL,
  `person_id` text NOT NULL,
  `episode_id` text NOT NULL,
  `segment_id` text,
  `speaker_raw` text NOT NULL,
  `claim_type` text NOT NULL,
  `assertion` text NOT NULL,
  `stance` text,
  `quote` text NOT NULL,
  `quote_start_char` integer,
  `quote_end_char` integer,
  `timestamp_s` real,
  `said_on` integer,
  `extraction_confidence` real NOT NULL,
  `speaker_confidence` real NOT NULL,
  `confidence_band` text NOT NULL,
  `review_status` text NOT NULL DEFAULT 'draft',
  `publish_reason` text,
  `pipeline_version` text NOT NULL,
  `model` text,
  `prompt_version` text,
  `parent_claim_id` text,
  `version` integer NOT NULL DEFAULT 1,
  `created_at` integer NOT NULL,
  `published_at` integer,
  FOREIGN KEY (`person_id`) REFERENCES `people`(`id`),
  FOREIGN KEY (`episode_id`) REFERENCES `episodes`(`id`),
  FOREIGN KEY (`segment_id`) REFERENCES `segments`(`id`)
);
--> statement-breakpoint
CREATE UNIQUE INDEX `claims_dedupe_hash_idx` ON `claims` (`dedupe_hash`);
--> statement-breakpoint
CREATE INDEX `claims_person_status_idx` ON `claims` (`person_id`, `review_status`);
--> statement-breakpoint
CREATE INDEX `claims_episode_idx` ON `claims` (`episode_id`);
--> statement-breakpoint
CREATE INDEX `claims_parent_idx` ON `claims` (`parent_claim_id`);
--> statement-breakpoint
CREATE TABLE `claim_evidence` (
  `id` text PRIMARY KEY NOT NULL,
  `claim_id` text NOT NULL,
  `episode_id` text NOT NULL,
  `quote` text NOT NULL,
  `timestamp_s` real,
  `deep_link_url` text,
  `role` text NOT NULL,
  FOREIGN KEY (`claim_id`) REFERENCES `claims`(`id`),
  FOREIGN KEY (`episode_id`) REFERENCES `episodes`(`id`)
);
--> statement-breakpoint
CREATE INDEX `claim_evidence_claim_idx` ON `claim_evidence` (`claim_id`);
--> statement-breakpoint
CREATE TABLE `claim_topics` (
  `claim_id` text NOT NULL,
  `topic_id` text NOT NULL,
  PRIMARY KEY (`claim_id`, `topic_id`),
  FOREIGN KEY (`claim_id`) REFERENCES `claims`(`id`),
  FOREIGN KEY (`topic_id`) REFERENCES `topics`(`id`)
);
--> statement-breakpoint
CREATE TABLE `llm_runs` (
  `id` text PRIMARY KEY NOT NULL,
  `episode_id` text,
  `claim_id` text,
  `model` text NOT NULL,
  `prompt_version` text,
  `accepted` integer NOT NULL,
  `reason` text,
  `request_json` text NOT NULL,
  `response_json` text,
  `tokens_in` integer,
  `tokens_out` integer,
  `latency_ms` integer,
  `created_at` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `llm_runs_episode_idx` ON `llm_runs` (`episode_id`);
--> statement-breakpoint
CREATE INDEX `llm_runs_created_idx` ON `llm_runs` (`created_at`);
--> statement-breakpoint
CREATE TABLE `ingest_runs` (
  `id` text PRIMARY KEY NOT NULL,
  `stage` text NOT NULL,
  `show_slug` text,
  `days` integer,
  `started_at` integer NOT NULL,
  `finished_at` integer,
  `episodes_discovered` integer NOT NULL DEFAULT 0,
  `transcripts_found` integer NOT NULL DEFAULT 0,
  `claims_extracted` integer NOT NULL DEFAULT 0,
  `claims_published` integer NOT NULL DEFAULT 0,
  `claims_rejected_quote` integer NOT NULL DEFAULT 0,
  `claims_rejected_speaker` integer NOT NULL DEFAULT 0,
  `error` text
);
--> statement-breakpoint
CREATE INDEX `ingest_runs_started_idx` ON `ingest_runs` (`started_at`);
