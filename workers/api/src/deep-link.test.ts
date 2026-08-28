import { describe, expect, it } from 'vitest';
import { youtubeDeepLink } from './deep-link';

describe('youtubeDeepLink', () => {
  it('links only timestamps produced by captions from the same YouTube video', () => {
    expect(youtubeDeepLink('video-1', 61.9, 'youtube_captions')).toBe(
      'https://www.youtube.com/watch?v=video-1&t=61s'
    );
  });

  it.each(['publisher_html', 'publisher_json', 'rss_vtt', 'whisper_local'])(
    'withholds a YouTube timestamp derived from %s',
    (transcriptKind) => {
      expect(youtubeDeepLink('video-1', 61, transcriptKind)).toBeNull();
    }
  );

  it('withholds a link when the video or timestamp is missing', () => {
    expect(youtubeDeepLink(null, 61, 'youtube_captions')).toBeNull();
    expect(youtubeDeepLink('video-1', null, 'youtube_captions')).toBeNull();
  });
});
