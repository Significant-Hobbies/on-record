import { markDegraded } from './degraded';

const fallback = import.meta.env.DEV
  ? 'http://127.0.0.1:8787'
  : 'https://api.podcasts.highsignal.app';

/**
 * The API worker, bound directly rather than reached over the public internet.
 *
 * Every server-rendered page fans out to the API, and issue #11 measured that
 * hop at ~69ms of the homepage's origin time: the web worker was making a real
 * HTTPS request back out to `api.podcasts.highsignal.app`, through DNS, TLS
 * and the edge, to reach a worker sitting in the same colo. A service binding
 * is a direct worker-to-worker call with none of that in between.
 *
 * The URL is deliberately left absolute. The API caches public responses with
 * `hono/cache`, which keys the Cache API entry on the request URL, so keeping
 * the same public URL through the binding keeps the exact same cache keys -
 * a binding call and an internet call share one cache, and neither invalidates
 * the other.
 */
export type ApiFetcher = { fetch: (input: string, init?: RequestInit) => Promise<Response> };

export type RuntimeEnv = {
  PUBLIC_API_BASE?: string;
  API?: ApiFetcher;
  APP_HEALTH_INGEST_KEY?: string;
};

export function apiBase(runtimeEnv?: RuntimeEnv): string {
  return (import.meta.env.PUBLIC_API_BASE || runtimeEnv?.PUBLIC_API_BASE || fallback).replace(
    /\/$/,
    ''
  );
}

export async function apiGet<T>(
  path: string,
  runtimeEnv?: RuntimeEnv,
  options: { timeoutMs?: number } = {}
): Promise<T> {
  const url = `${apiBase(runtimeEnv)}${path}`;
  const init = {
    signal: options.timeoutMs ? AbortSignal.timeout(options.timeoutMs) : undefined,
  };
  try {
    // Without an API binding, fall through to a normal fetch against the same URL.
    const response = runtimeEnv?.API
      ? await runtimeEnv.API.fetch(url, init)
      : await fetch(url, init);
    if (!response.ok) {
      throw new Error(`${path} failed: ${response.status}`);
    }
    return (await response.json()) as T;
  } catch (error) {
    markDegraded();
    throw error;
  }
}

export type Person = {
  id: string;
  slug: string;
  name: string;
  title?: string | null;
  org?: string | null;
  bio?: string | null;
  claimCount?: number;
  sourceCount?: number;
};

export type Claim = {
  attributionStatus?: 'verified_speaker' | 'speaker_unverified';
  id: string;
  assertion: string;
  claimType: string;
  quote: string;
  reviewStatus: string;
  timestampS?: number | null;
  saidOn?: string | null;
  stance?: string | null;
  personId?: string;
  personName?: string;
  personSlug?: string;
  personTitle?: string | null;
  personOrg?: string | null;
  episodeId?: string;
  episodeTitle?: string;
  showName?: string;
  showSlug?: string;
  sourceUrl?: string | null;
  deepLinkUrl?: string | null;
  transcriptKind?: string | null;
};

type HomepageEvidence = {
  status: 'ready' | 'empty' | 'unavailable';
  origin: 'recent' | 'search';
  heroClaim?: Claim;
  latestClaims: Claim[];
};

// Validate the public response, rather than treating a malformed success as an
// empty corpus. Quote/transcript validation remains the API's publication gate.
function homepageClaims(payload: unknown): Claim[] {
  const claims = (payload as { claims?: unknown } | null)?.claims;
  if (!Array.isArray(claims) || claims.length > 50) {
    throw new Error('Invalid claim response');
  }
  for (const claim of claims) {
    if (
      !(
        claim &&
        ['id', 'assertion', 'claimType', 'quote'].every(
          (key) => typeof claim[key] === 'string' && claim[key].trim().length > 0
        )
      ) ||
      claim.reviewStatus !== 'published' ||
      !['verified_speaker', 'speaker_unverified'].includes(claim.attributionStatus) ||
      ![
        'personName',
        'personSlug',
        'episodeId',
        'episodeTitle',
        'showName',
        'sourceUrl',
        'deepLinkUrl',
        'transcriptKind',
        'saidOn',
      ].every(
        (key) => claim[key] === null || claim[key] === undefined || typeof claim[key] === 'string'
      ) ||
      (claim.timestampS !== null &&
        claim.timestampS !== undefined &&
        (typeof claim.timestampS !== 'number' || !Number.isFinite(claim.timestampS)))
    ) {
      throw new Error('Invalid public claim');
    }
  }
  return claims;
}

export async function homepageEvidence(
  runtimeEnv?: RuntimeEnv,
  options: { timeoutMs?: number } = {}
): Promise<HomepageEvidence> {
  let claims: Claim[];
  let origin: HomepageEvidence['origin'] = 'recent';
  try {
    claims = homepageClaims(await apiGet<unknown>('/api/search', runtimeEnv, options));
  } catch {
    // Reuse the existing FTS route's bounded public corpus. This is a topical
    // sample, not a cached or necessarily recent stream; the page labels it.
    // Validation failures happen outside apiGet, so mark the render degraded here.
    markDegraded();
    origin = 'search';
    try {
      claims = homepageClaims(await apiGet<unknown>('/api/search?q=AI', runtimeEnv, options));
    } catch {
      return { status: 'unavailable', origin, latestClaims: [] };
    }
    if (!claims.length) {
      return { status: 'unavailable', origin, latestClaims: [] };
    }
  }
  const readsCleanly = (claim: Claim) => {
    const quote = claim.quote.trim();
    return (
      quote.length >= 80 &&
      quote.length <= 220 &&
      !/^(and|but|because|so|yeah|you know|i think)\b/i.test(quote)
    );
  };
  const heroClaim =
    claims.find((claim) => claim.transcriptKind === 'youtube_captions' && readsCleanly(claim)) ??
    claims.find(readsCleanly) ??
    claims.find((claim) => claim.deepLinkUrl || claim.sourceUrl) ??
    claims[0];
  const remaining = claims.filter((claim) => claim.id !== heroClaim?.id);
  return {
    status: claims.length ? 'ready' : 'empty',
    origin,
    heroClaim,
    latestClaims: [
      ...remaining.filter(readsCleanly),
      ...remaining.filter((claim) => !readsCleanly(claim)),
    ].slice(0, 4),
  };
}

export type Source = {
  id: string;
  title: string;
  status: string;
  publishedAt?: string | null;
  durationS?: number | null;
  transcriptKind?: string | null;
  sourceUrl?: string | null;
  showName?: string;
  showSlug?: string;
  claimCount?: number;
  peopleCount?: number;
};

export type Recommendation = {
  attributionStatus?: 'verified_speaker' | 'speaker_unverified';
  personId?: string;
  personName?: string;
  kind: string;
  role: string;
  name: string;
  assertion: string;
  claimId: string;
  deepLinkUrl?: string | null;
  episodeTitle?: string | null;
  quote: string;
  showName?: string | null;
  sourceUrl?: string | null;
  timestampS?: number | null;
  transcriptKind?: string | null;
  saidOn?: string | null;
};

export type RecommendationGroup = {
  kind: string;
  name: string;
  occurrenceCount: number;
  peopleCount: number;
  roleCounts: Record<string, number>;
  unverifiedSpeakerCount?: number;
};

export type Stats = {
  catalogEpisodes?: number;
  people: number;
  episodes: number;
  publishedClaims: number;
  publishedReferences?: number;
  transcriptEpisodes?: number;
  trustedShows?: number;
  trustPolicy?: {
    withheldShows: number;
    wording: string;
  };
};
