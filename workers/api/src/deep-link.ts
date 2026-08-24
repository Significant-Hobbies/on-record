export function youtubeDeepLink(
  videoId: string | null | undefined,
  timestampS: number | null
): string | null {
  if (!videoId || timestampS === null || timestampS === undefined) {
    return null;
  }
  const seconds = Math.max(0, Math.floor(timestampS));
  return `https://www.youtube.com/watch?v=${videoId}&t=${seconds}s`;
}
