--> Zero-result extraction is still work. Record the segment and extraction
--> focus so a checkpointed corpus run does not spend on it again unless the
--> prompt version changes or the operator explicitly forces a retry.
ALTER TABLE `llm_runs` ADD `segment_id` text REFERENCES segments(id);
--> statement-breakpoint
ALTER TABLE `llm_runs` ADD `focus` text;
--> statement-breakpoint
CREATE INDEX `llm_runs_segment_prompt_focus_idx`
ON `llm_runs` (`segment_id`, `prompt_version`, `focus`);
