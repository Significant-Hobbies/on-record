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

const REFERENCE_ROLES = [
  'recommends',
  'uses',
  'likes',
  'owns',
  'built',
  'avoids',
  'mentions',
] as const;
export const ACTIONABLE_REFERENCE_ROLES = [
  'recommends',
  'uses',
  'likes',
  'owns',
  'built',
  'avoids',
] as const;

const REFERENCE_CLAUSE_BREAK =
  /(?:[.!?;]\s+|,\s*(?:and|but|while|whereas)\s+|\s+(?:but|whereas)\s+|\s+and\s+(?=(?:i|we|you|they|personally|currently|actually|still|use|used|recommend|avoid|built|created|made|read|love|like|prefer|own|bought)\b))/i;
const REFERENCE_GENERIC_NAME =
  /^(?:it|this|that|these|those|them|ai|artificial intelligence|machine learning|software|hardware|books?|apps?|applications?|games?|tools?|services?|papers?|courses?|devices?|accounts?|podcasts?|shows?|products?|platforms?|sources?|(?:a|an|the|this|that|some|any|my|your|our|their)\s+(?:app|application|book|game|tool|service|paper|course|device|hardware|account|podcast|show|product|software|platform))$/i;
const REFERENCE_DESCRIPTIVE_NAME =
  /^(?:his|her|their|my|your|our|a|an|the|this|that)\s+(?:(?:new|latest|recent|current|favorite|favourite)\s+)?(?:book|app|application|game|tool|service|paper|course|device|account|podcast|show|product|platform)\b/i;
const REFERENCE_OBJECT_PRONOUN = /\b(?:it|them|this|that|these|those)\b/i;
const REFERENCE_REPORTED_SPEECH =
  /\b(?:he|she|they|someone|a\s+woman|a\s+man|the\s+woman|the\s+man|my\s+friend)\s+(?:said|told|wrote|asked)\b/i;
const REFERENCE_WRAPPED_PERSON =
  /\b(?:conversation|interview|episode|talk|book|article|work)\s+(?:with|by|from)\b/i;
const REFERENCE_ADVERBS =
  '(?:(?:personally|currently|actually|still|always|mostly|usually|daily|now|highly|strongly|really|definitely|generally|originally)\\s+)*';
const REFERENCE_KIND_CONFLICTS: Partial<Record<ReferenceKind, RegExp>> = {
  app: /\b(?:book|novel|memoir|game|games|gaming|paper|course|device|hardware|chip|account)\b/i,
  book: /\b(?:game|app|application|software|tool|service|platform|device|hardware|paper|article|account|documentary|film|movie|video|channel|supplement|vitamin|multivitamin|drug|medication)\b|\b(?:online|training|video)\s+course\b|\bcourse\s+(?:called|named|on|about)\b/i,
  course: /\b(?:game|app|software|tool|service|device|hardware|paper|account)\b/i,
  hardware: /\b(?:book|novel|memoir|game|app|software|service|course|paper|account)\b/i,
  paper: /\b(?:game|app|software|tool|service|device|hardware|course|account)\b/i,
  person: /\b(?:book|novel|memoir|game|app|software|tool|service|device|course|paper|account)\b/i,
  service: /\b(?:book|novel|memoir|paper|course|device|hardware|chip|account)\b/i,
  tool: /\b(?:book|novel|memoir|paper|course|device|hardware|chip|account)\b/i,
};

export type ReferenceKind = (typeof REFERENCE_KINDS)[number];
type ReferenceRole = (typeof REFERENCE_ROLES)[number];
export type ActionableReferenceRole = (typeof ACTIONABLE_REFERENCE_ROLES)[number];

export type ClaimReference = {
  kind: ReferenceKind;
  name: string;
  role: ReferenceRole;
};

export function isReferenceKind(value: string): value is ReferenceKind {
  return (REFERENCE_KINDS as readonly string[]).includes(value);
}

function isReferenceRole(value: string): value is ReferenceRole {
  return (REFERENCE_ROLES as readonly string[]).includes(value);
}

export function isActionableReferenceRole(value: string): value is ActionableReferenceRole {
  return (ACTIONABLE_REFERENCE_ROLES as readonly string[]).includes(value);
}

export function referenceAssertion(reference: ClaimReference): string {
  const labels: Record<ActionableReferenceRole, string> = {
    avoids: 'Avoids',
    built: 'Built',
    likes: 'Likes',
    owns: 'Owns',
    recommends: 'Recommends',
    uses: 'Mentions personal use of',
  };
  if (!isActionableReferenceRole(reference.role)) {
    return reference.name;
  }
  return `${labels[reference.role]} ${reference.name}.`;
}

function isStableReferenceName(name: string): boolean {
  const normalized = normalizeWs(name);
  if (REFERENCE_GENERIC_NAME.test(normalized) || REFERENCE_DESCRIPTIVE_NAME.test(normalized)) {
    return false;
  }
  if (!normalized.includes(' ')) {
    return true;
  }
  return /[A-Z]/.test(normalized) || /[./+#@]/.test(normalized);
}

type ReferenceMatch = {
  kind?: ReferenceKind;
  matching: string[];
  namePattern: string;
  role: ReferenceRole;
};

function activeReferenceObject(
  context: ReferenceMatch,
  verbs: string,
  clause: string,
  distance = 100
): boolean {
  const pattern = new RegExp(
    `\\b(?:i|we)\\s+${REFERENCE_ADVERBS}(?:${verbs})\\b(?<gap>.{0,${distance}}?)${context.namePattern}`,
    'i'
  );
  const match = pattern.exec(clause);
  if (!match) {
    return false;
  }
  const gap = match.groups?.['gap'] ?? '';
  return !(
    REFERENCE_OBJECT_PRONOUN.test(gap) ||
    REFERENCE_REPORTED_SPEECH.test(clause.slice(0, match.index)) ||
    (context.role === 'recommends' && /\b(?:about|regarding|concerning)\b/i.test(gap)) ||
    (context.kind === 'person' &&
      (REFERENCE_WRAPPED_PERSON.test(gap) || /\b(?:with|by|from)\b/i.test(gap)))
  );
}

function recommendationSupported(context: ReferenceMatch): boolean {
  const should = new RegExp(
    `\\b(?:you|people|everyone|founders|engineers|teams|we)\\s+(?:really\\s+)?should\\s+(?:read|try|use|watch|listen\\s+to|check\\s+out|follow)\\b.{0,80}?${context.namePattern}`,
    'i'
  );
  const relative = new RegExp(
    `${context.namePattern}.{0,60}?\\b(?:that|which)\\s+(?:i|we)\\s+${REFERENCE_ADVERBS}recommend(?:ed)?\\b`,
    'i'
  );
  const worth = new RegExp(
    `(?:\\bmust[- ](?:read|use|watch)\\b.{0,50}?${context.namePattern}|${context.namePattern}.{0,40}?\\bworth\\s+(?:reading|trying|using|watching|listening\\s+to)\\b)`,
    'i'
  );
  return context.matching.some(
    (clause) =>
      activeReferenceObject(context, 'recommend(?:ed)?', clause) ||
      should.test(clause) ||
      (context.kind !== 'person' && relative.test(clause)) ||
      worth.test(clause)
  );
}

function useSupported(context: ReferenceMatch): boolean {
  const verbs =
    'use|used|rely\\s+on|run|work\\s+with|read|am\\s+reading|are\\s+reading|have\\s+been\\s+using|have\\s+used|listen\\s+to|listened\\s+to|watch|watched|subscribe\\s+to|subscribed\\s+to|wear|drive|play';
  const fronted = new RegExp(
    `${context.namePattern}\\s*,\\s*(?:i|we)\\s+${REFERENCE_ADVERBS}(?:${verbs})\\b`,
    'i'
  );
  return context.matching.some(
    (clause) => activeReferenceObject(context, verbs, clause) || fronted.test(clause)
  );
}

function preferenceSupported(context: ReferenceMatch): boolean {
  const verbs = 'love|like|prefer|enjoy|adore|swear\\s+by';
  const fan = new RegExp(
    `\\b(?:i|we)(?:['’]m|\\s+am|['’]re|\\s+are)\\s+(?:a\\s+)?(?:(?:big|huge)\\s+)?fan\\s+of\\s+.{0,80}?${context.namePattern}`,
    'i'
  );
  const favorite = new RegExp(
    `(?:\\bmy\\s+favou?rite(?:\\s+\\w+){0,3}\\s+is\\s+${context.namePattern}|${context.namePattern}.{0,40}?\\bis\\s+my\\s+favou?rite\\b)`,
    'i'
  );
  const obsessed = new RegExp(
    `\\b(?:i|we)(?:['’]m|\\s+am|['’]re|\\s+are)\\s+obsessed\\s+with\\s+.{0,60}?${context.namePattern}`,
    'i'
  );
  return context.matching.some(
    (clause) =>
      activeReferenceObject(context, verbs, clause) ||
      fan.test(clause) ||
      favorite.test(clause) ||
      obsessed.test(clause)
  );
}

function referenceRoleSupported(
  name: string,
  role: ReferenceRole,
  claimQuote: string,
  kind?: ReferenceKind
): boolean {
  if (!isActionableReferenceRole(role)) {
    return false;
  }
  const needle = normalizeWs(name);
  if (REFERENCE_GENERIC_NAME.test(needle)) {
    return false;
  }
  const namePattern = needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
  const matching = normalizeWs(claimQuote)
    .split(REFERENCE_CLAUSE_BREAK)
    .filter((clause) => clause.toLowerCase().includes(needle.toLowerCase()));
  const context = { kind, matching, namePattern, role };
  if (role === 'recommends') {
    return recommendationSupported(context);
  }
  if (role === 'uses') {
    return useSupported(context);
  }
  if (role === 'likes') {
    return preferenceSupported(context);
  }
  if (role === 'owns') {
    const verbs = 'own|bought|purchased|have\\s+purchased|have\\s+bought';
    return matching.some((clause) => activeReferenceObject(context, verbs, clause));
  }
  if (role === 'built') {
    const verbs =
      'built|created|made|founded|developed|launched|wrote|authored|designed|shipped|started';
    return matching.some((clause) => activeReferenceObject(context, verbs, clause));
  }
  const verbs =
    "avoid|avoided|never\\s+use|stopped\\s+using|quit|uninstalled|stay\\s+away\\s+from|do\\s+not\\s+use|don['’]?t\\s+use|would\\s+not\\s+use|wouldn['’]?t\\s+use|cannot\\s+use|can['’]?t\\s+use";
  return matching.some((clause) => activeReferenceObject(context, verbs, clause));
}

function normalizedReferenceKind(
  name: string,
  kind: ReferenceKind,
  role: ReferenceRole,
  claimQuote: string
): ReferenceKind {
  // A direct person recommendation has already passed the stricter wrapper
  // checks above. Nearby words such as "book" describe the surrounding work,
  // not the recommended person's kind.
  if (kind === 'person' && role === 'recommends') {
    return kind;
  }
  const conflict = REFERENCE_KIND_CONFLICTS[kind];
  if (!conflict) {
    return kind;
  }
  const needle = normalizeWs(name).toLowerCase();
  const context = normalizeWs(claimQuote);
  const folded = context.toLowerCase();
  const namePattern = normalizeWs(name)
    .replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    .replace(/\s+/g, '\\s+');
  if (kind === 'book' && new RegExp(`\\bread\\s+in\\s+${namePattern}`, 'i').test(context)) {
    return 'other';
  }
  let at = folded.indexOf(needle);
  while (at >= 0) {
    const nearby = context.slice(Math.max(0, at - 160), at + needle.length + 160);
    if (conflict.test(nearby)) {
      return 'other';
    }
    at = folded.indexOf(needle, at + needle.length);
  }
  return kind;
}

export function sanitizeReferences(
  raw: unknown,
  claimQuote: string,
  kindContext = claimQuote
): ClaimReference[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const haystack = normalizeWs(claimQuote).toLowerCase();
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
    if (
      !(
        isReferenceKind(kind) &&
        isReferenceRole(role) &&
        name.length >= 2 &&
        isStableReferenceName(name)
      )
    ) {
      continue;
    }
    if (!haystack.includes(normalizeWs(name).toLowerCase())) {
      continue;
    }
    if (!referenceRoleSupported(name, role, claimQuote, kind)) {
      continue;
    }
    const normalizedKind = normalizedReferenceKind(name, kind, role, kindContext);
    const key = `${normalizedKind}|${role}|${name.toLowerCase()}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    out.push({ kind: normalizedKind, name, role });
  }
  return out;
}
