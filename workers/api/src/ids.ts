export function newId(): string {
  return crypto.randomUUID();
}

export async function sha256Hex(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export async function dedupeHash(
  episodeId: string,
  personId: string,
  normalizedQuote: string
): Promise<string> {
  return sha256Hex(`${episodeId}|${personId}|${normalizedQuote}`);
}
