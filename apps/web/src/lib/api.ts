const fallback = 'http://127.0.0.1:8787';

export function apiBase(runtimeEnv?: { PUBLIC_API_BASE?: string }): string {
  return runtimeEnv?.PUBLIC_API_BASE || import.meta.env.PUBLIC_API_BASE || fallback;
}

export async function apiGet<T>(
  path: string,
  runtimeEnv?: { PUBLIC_API_BASE?: string }
): Promise<T> {
  const response = await fetch(`${apiBase(runtimeEnv)}${path}`);
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
};

export type Claim = {
  id: string;
  assertion: string;
  claimType: string;
  quote: string;
  reviewStatus: string;
  timestampS?: number | null;
  saidOn?: string | null;
};

export type Recommendation = {
  kind: string;
  role: string;
  name: string;
  assertion: string;
  claimId: string;
  quote: string;
};

export type Stats = {
  people: number;
  episodes: number;
  publishedClaims: number;
  publishedReferences?: number;
};
