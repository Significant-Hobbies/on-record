const fallback = 'http://127.0.0.1:8787';

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

export type RuntimeEnv = { PUBLIC_API_BASE?: string; API?: ApiFetcher };

export function runtimeEnvFromLocals(locals: {
  runtime?: { env?: RuntimeEnv };
}): RuntimeEnv | undefined {
  return locals.runtime?.env;
}

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
  // The binding only exists on the deployed worker; `astro dev` and any other
  // non-Workers runtime fall through to a normal fetch against the same URL.
  const response = runtimeEnv?.API ? await runtimeEnv.API.fetch(url, init) : await fetch(url, init);
  if (!response.ok) {
    throw new Error(`${path} failed: ${response.status}`);
  }
  return (await response.json()) as T;
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
