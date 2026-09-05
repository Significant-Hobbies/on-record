--> The public Cache API cannot enumerate or wildcard-delete keys, and the
--> public routes take enough query-parameter combinations (search,
--> pagination, filters) that no fixed list of keys covers every cached
--> variant. Track a generation counter instead: every cached response's key
--> embeds it, so bumping it on publish makes every prior cache entry -
--> every route, every colo - unreachable at once, with no purge call
--> required. Old entries simply age out under their own max-age.
CREATE TABLE `public_cache_state` (
	`generation` integer DEFAULT 1 NOT NULL,
	`id` integer PRIMARY KEY NOT NULL
);
--> statement-breakpoint
INSERT INTO `public_cache_state` (`id`, `generation`) VALUES (1, 1);
