export function youtubeDeepLink(
  videoId: string | null | undefined,
  timestampS: number | null,
  transcriptKind: string | null
): string | null {
  // Publisher and RSS transcript clocks can drift from a separately uploaded
  // YouTube edition because of ads, intros, or edits. Only caption timestamps
  // from the same YouTube video are safe to expose as deep links.
  if (
    transcriptKind !== 'youtube_captions' ||
    !videoId ||
    timestampS === null ||
    timestampS === undefined
  ) {
    return null;
  }
  const seconds = Math.max(0, Math.floor(timestampS));
  return `https://www.youtube.com/watch?v=${videoId}&t=${seconds}s`;
}
