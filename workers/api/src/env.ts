export type Env = {
  DB: D1Database;
  RAW: R2Bucket;
  ADMIN_TOKEN?: string;
  ENVIRONMENT?: string;
  // Secret — set via `wrangler secret put`. Telemetry is a no-op when unset.
  APP_HEALTH_INGEST_KEY?: string;
};
