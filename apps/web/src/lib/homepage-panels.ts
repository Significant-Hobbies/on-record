import type { Person, RecommendationGroup, Source, Stats } from './api';
import { markDegraded } from './degraded';

type Row = Record<string, unknown>;
const ENTITY_SNAPSHOT_MAX_AGE_MS = 24 * 60 * 60 * 1000;

export function entitySnapshotFresh(capturedAt: string, now = Date.now()): boolean {
  const captureTime = Date.parse(capturedAt);
  const age = now - captureTime;
  return Number.isFinite(captureTime) && age >= 0 && age <= ENTITY_SNAPSHOT_MAX_AGE_MS;
}

function isRow(value: unknown): value is Row {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function isText(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}

function optionalText(value: unknown): boolean {
  return value === undefined || value === null || typeof value === 'string';
}

function optionalCount(value: unknown): boolean {
  return value === undefined || isCount(value);
}

function readList<T>(
  payload: unknown,
  key: string,
  maximum: number,
  valid: (row: Row) => boolean
): T[] {
  if (!(isRow(payload) && Array.isArray(payload[key]))) {
    throw new Error(`Invalid ${key} response`);
  }
  const rows = payload[key] as unknown[];
  if (rows.length > maximum || !rows.every((row) => isRow(row) && valid(row))) {
    throw new Error(`Invalid ${key} rows`);
  }
  return rows as T[];
}

export function homepageStats(payload: unknown): Stats {
  if (
    !(
      isRow(payload) &&
      isCount(payload.people) &&
      isCount(payload.episodes) &&
      isCount(payload.publishedClaims) &&
      ['catalogEpisodes', 'publishedReferences', 'transcriptEpisodes', 'trustedShows'].every(
        (key) => optionalCount(payload[key])
      )
    ) ||
    (payload.trustPolicy !== undefined &&
      !(
        isRow(payload.trustPolicy) &&
        isCount(payload.trustPolicy.withheldShows) &&
        isText(payload.trustPolicy.wording)
      ))
  ) {
    throw new Error('Invalid stats response');
  }
  return payload as Stats;
}

export function homepagePeople(payload: unknown): Person[] {
  return readList<Person>(
    payload,
    'people',
    8,
    (row) =>
      isText(row.id) &&
      isText(row.slug) &&
      isText(row.name) &&
      optionalText(row.title) &&
      optionalText(row.org) &&
      optionalCount(row.claimCount)
  );
}

export function homepageGroups(payload: unknown): RecommendationGroup[] {
  return readList<RecommendationGroup>(
    payload,
    'groups',
    8,
    (row) =>
      isText(row.kind) &&
      isText(row.name) &&
      isCount(row.peopleCount) &&
      isCount(row.occurrenceCount) &&
      isRow(row.roleCounts) &&
      Object.values(row.roleCounts).every(isCount) &&
      optionalCount(row.unverifiedSpeakerCount)
  );
}

export function homepageSources(payload: unknown): Source[] {
  return readList<Source>(
    payload,
    'sources',
    5,
    (row) =>
      isText(row.id) &&
      isText(row.title) &&
      row.status === 'published' &&
      optionalText(row.showName) &&
      optionalText(row.publishedAt) &&
      optionalCount(row.claimCount)
  );
}

export function homepagePanel<T>(
  result: PromiseSettledResult<unknown>,
  parse: (payload: unknown) => T,
  snapshot: T
): { value: T; snapshot: boolean } {
  if (result.status === 'fulfilled') {
    try {
      return { value: parse(result.value), snapshot: false };
    } catch {
      // A successful HTTP status is not enough to make malformed public data cacheable.
      markDegraded();
    }
  }
  return { value: snapshot, snapshot: true };
}
