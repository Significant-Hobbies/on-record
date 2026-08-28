export const UNVERIFIED_SPEAKER_SLUG = 'speaker-unverified';

export type AttributionStatus = 'verified_speaker' | 'speaker_unverified';

export function attributionStatusFor(
  speakerRaw: string,
  explicit?: AttributionStatus
): AttributionStatus {
  if (explicit) {
    return explicit;
  }
  return speakerRaw === UNVERIFIED_SPEAKER_SLUG ? 'speaker_unverified' : 'verified_speaker';
}
