const fallback = 'http://127.0.0.1:8787';

export type RuntimeEnv = { PUBLIC_API_BASE?: string };

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
  runtimeEnv?: { PUBLIC_API_BASE?: string },
  options: { timeoutMs?: number } = {}
): Promise<T> {
  const response = await fetch(`${apiBase(runtimeEnv)}${path}`, {
    signal: options.timeoutMs ? AbortSignal.timeout(options.timeoutMs) : undefined,
  });
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
  saidOn?: string | null;
};

export type RecommendationGroup = {
  kind: string;
  name: string;
  occurrenceCount: number;
  peopleCount: number;
  roleCounts: Record<string, number>;
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
