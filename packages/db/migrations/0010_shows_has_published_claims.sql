--> GET /api/sources computed the publishers list by scanning every published
--> claim (joined through episodes) to find distinct shows, even though shows
--> holds 25 rows and the result only changes when a show's first claim is
--> published. Track that transition on the show row instead so the read
--> becomes a 25-row table scan.
ALTER TABLE `shows` ADD `has_published_claims` integer NOT NULL DEFAULT 0;
--> statement-breakpoint
UPDATE `shows` SET `has_published_claims` = 1 WHERE `id` IN (
  SELECT DISTINCT `episodes`.`show_id`
  FROM `claims`
  INNER JOIN `episodes` ON `episodes`.`id` = `claims`.`episode_id`
  WHERE `claims`.`review_status` = 'published'
);
