const CLAIM_TYPES = [
  'belief',
  'prediction',
  'recommendation',
  'evaluation',
  'observation',
  'preference',
  'commitment',
  'disagreement',
  'uncertainty',
] as const;

export type ClaimType = (typeof CLAIM_TYPES)[number];

export function isClaimType(value: string): value is ClaimType {
  return (CLAIM_TYPES as readonly string[]).includes(value);
}
