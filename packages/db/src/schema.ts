import {
  index,
  integer,
  primaryKey,
  real,
  sqliteTable,
  text,
  uniqueIndex,
} from 'drizzle-orm/sqlite-core';

export const people = sqliteTable(
  'people',
  {
    aliases: text('aliases', { mode: 'json' }).$type<string[]>(),
    bio: text('bio'),
    createdAt: integer('created_at', { mode: 'timestamp' })
      .notNull()
      .$defaultFn(() => new Date()),
    id: text('id').primaryKey(),
    links: text('links', { mode: 'json' }).$type<Record<string, string>>(),
    name: text('name').notNull(),
    org: text('org'),
    slug: text('slug').notNull(),
    status: text('status', { enum: ['active', 'hidden'] })
      .notNull()
      .default('active'),
    title: text('title'),
    updatedAt: integer('updated_at', { mode: 'timestamp' })
      .notNull()
      .$defaultFn(() => new Date()),
  },
  (t) => [uniqueIndex('people_slug_idx').on(t.slug)]
);

export const shows = sqliteTable(
  'shows',
  {
    active: integer('active', { mode: 'boolean' }).notNull().default(true),
    createdAt: integer('created_at', { mode: 'timestamp' })
      .notNull()
      .$defaultFn(() => new Date()),
    feedUrl: text('feed_url'),
    hasPublishedClaims: integer('has_published_claims', { mode: 'boolean' })
      .notNull()
      .default(false),
    hostPersonIds: text('host_person_ids', { mode: 'json' }).$type<string[]>(),
    id: text('id').primaryKey(),
    name: text('name').notNull(),
    podcastIndexFeedId: integer('podcast_index_feed_id'),
    slug: text('slug').notNull(),
    youtubeChannelId: text('youtube_channel_id'),
  },
  (t) => [uniqueIndex('shows_slug_idx').on(t.slug)]
);

export const topics = sqliteTable(
  'topics',
  {
    id: text('id').primaryKey(),
    name: text('name').notNull(),
    slug: text('slug').notNull(),
    status: text('status', { enum: ['proposed', 'approved'] })
      .notNull()
      .default('approved'),
  },
  (t) => [uniqueIndex('topics_slug_idx').on(t.slug)]
);

export const episodes = sqliteTable(
  'episodes',
  {
    audioUrl: text('audio_url'),
    createdAt: integer('created_at', { mode: 'timestamp' })
      .notNull()
      .$defaultFn(() => new Date()),
    description: text('description'),
    durationS: integer('duration_s'),
    guid: text('guid').notNull(),
    id: text('id').primaryKey(),
    pipelineVersion: text('pipeline_version'),
    publishedAt: integer('published_at', { mode: 'timestamp' }),
    rawHash: text('raw_hash'),
    rawR2Key: text('raw_r2_key'),
    showId: text('show_id')
      .notNull()
      .references(() => shows.id),
    sourceUrl: text('source_url'),
    status: text('status', {
      enum: [
        'discovered',
        'transcribed',
        'no_transcript',
        'segmented',
        'extracted',
        'published',
        'failed',
      ],
    })
      .notNull()
      .default('discovered'),
    statusDetail: text('status_detail'),
    title: text('title').notNull(),
    transcriptKind: text('transcript_kind', {
      enum: [
        'rss_vtt',
        'rss_srt',
        'rss_json',
        'rss_text',
        'rss_text_coarse',
        'rss_named_text',
        'publisher_html',
        'publisher_html_coarse',
        'publisher_json',
        'youtube_captions',
        'whisper_local',
        'none',
      ],
    }),
    updatedAt: integer('updated_at', { mode: 'timestamp' })
      .notNull()
      .$defaultFn(() => new Date()),
    youtubeVideoId: text('youtube_video_id'),
  },
  (t) => [
    uniqueIndex('episodes_guid_idx').on(t.guid),
    index('episodes_show_status_idx').on(t.showId, t.status),
    index('episodes_published_idx').on(t.publishedAt),
  ]
);

export const episodePeople = sqliteTable(
  'episode_people',
  {
    attributionSource: text('attribution_source', {
      enum: ['show_config', 'metadata_match', 'publisher_transcript', 'llm'],
    }).notNull(),
    confidence: real('confidence'),
    episodeId: text('episode_id')
      .notNull()
      .references(() => episodes.id),
    personId: text('person_id')
      .notNull()
      .references(() => people.id),
    role: text('role', { enum: ['host', 'guest'] }).notNull(),
  },
  (t) => [primaryKey({ columns: [t.episodeId, t.personId] })]
);

/**
 * Sparse `[charOffset, startSeconds]` pairs mapping positions in a segment's
 * text back to the caption cue that was being spoken there. Sampled rather
 * than exhaustive: one entry roughly every 40 characters keeps the row small
 * while staying accurate to a second or two.
 */
export type CueMap = [number, number][];

export const segments = sqliteTable(
  'segments',
  {
    endS: real('end_s').notNull(),
    episodeId: text('episode_id')
      .notNull()
      .references(() => episodes.id),
    id: text('id').primaryKey(),
    idx: integer('idx').notNull(),
    speakerHint: text('speaker_hint'),
    startS: real('start_s').notNull(),
    /**
     * Always written empty. The words live in R2 — see `segment-store.ts`.
     * The column survives only because dropping it needs a table rebuild that
     * D1 refuses while claims reference this table.
     */
    text: text('text').notNull(),
  },
  (t) => [
    uniqueIndex('segments_episode_idx').on(t.episodeId, t.idx),
    index('segments_episode_id_idx').on(t.episodeId),
  ]
);

export const claims = sqliteTable(
  'claims',
  {
    assertion: text('assertion').notNull(),
    attributionStatus: text('attribution_status', {
      enum: ['verified_speaker', 'speaker_unverified'],
    })
      .notNull()
      .default('verified_speaker'),
    claimType: text('claim_type', {
      enum: [
        'belief',
        'prediction',
        'recommendation',
        'evaluation',
        'observation',
        'preference',
        'commitment',
        'disagreement',
        'uncertainty',
      ],
    }).notNull(),
    confidenceBand: text('confidence_band', { enum: ['low', 'medium', 'high'] }).notNull(),
    createdAt: integer('created_at', { mode: 'timestamp' })
      .notNull()
      .$defaultFn(() => new Date()),
    dedupeHash: text('dedupe_hash').notNull(),
    episodeId: text('episode_id')
      .notNull()
      .references(() => episodes.id),
    extractionConfidence: real('extraction_confidence').notNull(),
    id: text('id').primaryKey(),
    model: text('model'),
    parentClaimId: text('parent_claim_id'),
    personId: text('person_id')
      .notNull()
      .references(() => people.id),
    pipelineVersion: text('pipeline_version').notNull(),
    promptVersion: text('prompt_version'),
    correctedAt: integer('corrected_at', { mode: 'timestamp' }),
    publishedAt: integer('published_at', { mode: 'timestamp' }),
    publishReason: text('publish_reason'),
    quote: text('quote').notNull(),
    quoteEndChar: integer('quote_end_char'),
    quoteStartChar: integer('quote_start_char'),
    reviewStatus: text('review_status', {
      enum: ['draft', 'held', 'published', 'killed', 'corrected'],
    })
      .notNull()
      .default('draft'),
    saidOn: integer('said_on', { mode: 'timestamp' }),
    segmentId: text('segment_id').references(() => segments.id),
    speakerConfidence: real('speaker_confidence').notNull(),
    speakerRaw: text('speaker_raw').notNull(),
    stance: text('stance'),
    timestampS: real('timestamp_s'),
    version: integer('version').notNull().default(1),
  },
  (t) => [
    uniqueIndex('claims_dedupe_hash_idx').on(t.dedupeHash),
    index('claims_person_status_idx').on(t.personId, t.reviewStatus),
    index('claims_episode_idx').on(t.episodeId),
    index('claims_parent_idx').on(t.parentClaimId),
  ]
);

export const claimEvidence = sqliteTable(
  'claim_evidence',
  {
    claimId: text('claim_id')
      .notNull()
      .references(() => claims.id),
    deepLinkUrl: text('deep_link_url'),
    episodeId: text('episode_id')
      .notNull()
      .references(() => episodes.id),
    id: text('id').primaryKey(),
    quote: text('quote').notNull(),
    role: text('role', {
      enum: ['primary', 'corroboration', 'contradiction'],
    }).notNull(),
    timestampS: real('timestamp_s'),
  },
  (t) => [
    index('claim_evidence_claim_idx').on(t.claimId),
    index('claim_evidence_claim_role_idx').on(t.claimId, t.role),
  ]
);

export const claimTopics = sqliteTable(
  'claim_topics',
  {
    claimId: text('claim_id')
      .notNull()
      .references(() => claims.id),
    topicId: text('topic_id')
      .notNull()
      .references(() => topics.id),
  },
  (t) => [primaryKey({ columns: [t.claimId, t.topicId] })]
);

export const claimReferences = sqliteTable(
  'claim_references',
  {
    claimId: text('claim_id')
      .notNull()
      .references(() => claims.id),
    id: text('id').primaryKey(),
    kind: text('kind', {
      enum: ['book', 'app', 'tool', 'service', 'paper', 'course', 'hardware', 'person', 'other'],
    }).notNull(),
    name: text('name').notNull(),
    role: text('role', {
      enum: ['recommends', 'uses', 'likes', 'owns', 'built', 'avoids', 'mentions'],
    }).notNull(),
  },
  (t) => [
    index('claim_references_claim_idx').on(t.claimId),
    index('claim_references_kind_role_idx').on(t.kind, t.role),
    index('claim_references_role_claim_idx').on(t.role, t.claimId),
    uniqueIndex('claim_references_unique').on(t.claimId, t.kind, t.role, t.name),
  ]
);

export const llmRuns = sqliteTable(
  'llm_runs',
  {
    accepted: integer('accepted', { mode: 'boolean' }).notNull(),
    claimId: text('claim_id'),
    createdAt: integer('created_at', { mode: 'timestamp' })
      .notNull()
      .$defaultFn(() => new Date()),
    episodeId: text('episode_id'),
    focus: text('focus'),
    id: text('id').primaryKey(),
    latencyMs: integer('latency_ms'),
    model: text('model').notNull(),
    promptVersion: text('prompt_version'),
    reason: text('reason'),
    requestJson: text('request_json', { mode: 'json' }).notNull(),
    responseJson: text('response_json', { mode: 'json' }),
    segmentId: text('segment_id').references(() => segments.id),
    tokensIn: integer('tokens_in'),
    tokensOut: integer('tokens_out'),
  },
  (t) => [
    index('llm_runs_episode_idx').on(t.episodeId),
    index('llm_runs_created_idx').on(t.createdAt),
    index('llm_runs_segment_prompt_focus_idx').on(t.segmentId, t.promptVersion, t.focus),
  ]
);

export const ingestRuns = sqliteTable(
  'ingest_runs',
  {
    claimsExtracted: integer('claims_extracted').notNull().default(0),
    claimsPublished: integer('claims_published').notNull().default(0),
    claimsRejectedQuote: integer('claims_rejected_quote').notNull().default(0),
    claimsRejectedSpeaker: integer('claims_rejected_speaker').notNull().default(0),
    days: integer('days'),
    episodesDiscovered: integer('episodes_discovered').notNull().default(0),
    error: text('error'),
    finishedAt: integer('finished_at', { mode: 'timestamp' }),
    id: text('id').primaryKey(),
    showSlug: text('show_slug'),
    stage: text('stage').notNull(),
    startedAt: integer('started_at', { mode: 'timestamp' }).notNull(),
    transcriptsFound: integer('transcripts_found').notNull().default(0),
  },
  (t) => [index('ingest_runs_started_idx').on(t.startedAt)]
);

// The Cache API cannot enumerate or wildcard-delete keys, and the public
// routes take enough query-parameter combinations (search, pagination,
// filters) that no fixed list of keys covers every cached variant. A single
// row here tracks a generation counter instead: every cached response's key
// embeds it, so bumping it on publish makes every prior cache entry - every
// route, every colo - unreachable at once, with no purge call required.
export const publicCacheState = sqliteTable('public_cache_state', {
  generation: integer('generation').notNull().default(1),
  id: integer('id').primaryKey(),
});
