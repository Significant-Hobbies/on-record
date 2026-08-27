/**
 * Segment hints are roster slugs after speaker identification, while claims
 * store the corresponding database UUID. Accept either representation so a
 * correct attribution is not retracted merely because the layers use
 * different identifiers.
 */
export function speakerHintMatchesPerson(
  speakerHint: string | null | undefined,
  personId: string,
  personSlug: string | undefined
): boolean {
  return !speakerHint || speakerHint === personId || speakerHint === personSlug;
}
