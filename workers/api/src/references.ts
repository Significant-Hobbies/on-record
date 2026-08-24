import { normalizeWs } from './quote';

const REFERENCE_KINDS = [
  'book',
  'app',
  'tool',
  'service',
  'paper',
  'course',
  'hardware',
  'person',
  'other',
] as const;

const REFERENCE_ROLES = ['recommends', 'uses', 'built', 'avoids', 'mentions'] as const;

export type ReferenceKind = (typeof REFERENCE_KINDS)[number];
export type ReferenceRole = (typeof REFERENCE_ROLES)[number];

export type ClaimReference = {
  kind: ReferenceKind;
  name: string;
  role: ReferenceRole;
};

export function isReferenceKind(value: string): value is ReferenceKind {
  return (REFERENCE_KINDS as readonly string[]).includes(value);
}

export function isReferenceRole(value: string): value is ReferenceRole {
  return (REFERENCE_ROLES as readonly string[]).includes(value);
}

export function sanitizeReferences(raw: unknown, segmentText: string): ClaimReference[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const haystack = normalizeWs(segmentText).toLowerCase();
  const out: ClaimReference[] = [];
  const seen = new Set<string>();
  for (const item of raw) {
    if (!item || typeof item !== 'object') {
      continue;
    }
    const record = item as Record<string, unknown>;
    const kindRaw = record['kind'];
    const roleRaw = record['role'];
    const nameRaw = record['name'];
    const kind = typeof kindRaw === 'string' ? kindRaw.trim().toLowerCase() : '';
    const role = typeof roleRaw === 'string' ? roleRaw.trim().toLowerCase() : '';
    const name = typeof nameRaw === 'string' ? nameRaw.trim() : '';
    if (!(isReferenceKind(kind) && isReferenceRole(role) && name.length >= 2)) {
      continue;
    }
    if (!haystack.includes(normalizeWs(name).toLowerCase())) {
      continue;
    }
    const key = `${kind}|${role}|${name.toLowerCase()}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    out.push({ kind, name, role });
  }
  return out;
}
