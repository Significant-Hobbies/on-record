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
  /^(?:it|this|that|these|those|him|his|her|them|ai|artificial intelligence|machine learning|ai note[- ]taking|software|hardware|books?|apps?|applications?|games?|tools?|services?|papers?|courses?|devices?|accounts?|podcasts?|shows?|products?|platforms?|sources?|(?:a|an|the|this|that|some|any|my|your|our|their)\s+(?:app|application|book|game|tool|service|paper|course|device|hardware|account|podcast|show|product|software|platform))$/i;
const REFERENCE_DESCRIPTIVE_NAME =
  /^(?:his|her|their|my|your|our|a|an|the|this|that)\s+(?:(?:new|latest|recent|current|favorite|favourite)\s+)?(?:book|app|application|game|tool|service|paper|course|device|account|podcast|show|series|channel|product|platform)\b/i;
const REFERENCE_NON_TITLE_BOOK_NAME =
  /(?:['’]s\s+(?:new\s+)?book|\bbooks|\bbook\s+reviews)$|^(?:the\s+)?(?:first|second|last)\s+(?:third|half|part|chapter|section)$|^(?:the\s+)?(?:front|back)(?:\s+inside)?\s+cover\s+of\s+(?:this|the)\s+book$|['’]s\s+(?:auto)?biography$|['’]s\s+encyclopedia$/i;
const REFERENCE_AUDITED_NON_TITLE_BOOK_NAMES = new Set([
  "amazon's management science",
  'andrew roberts latest book on winston churchill',
  "cialdini's persuasion book",
  'elon musk book',
  "kim scott's writing",
  'over my shoulder',
  "rick reuben's creativity book",
  'shakespearean comedies',
  'shawn theron',
  'the design sprint',
  'the economic history of chicago',
  'the how to book',
  'what is it in the first place',
]);
const REFERENCE_OBJECT_PRONOUN = /\b(?:it|them|this|that|these|those)\b/i;
const REFERENCE_REPORTED_SPEECH =
  /\b(?:he|she|they|someone|a\s+woman|a\s+man|the\s+woman|the\s+man|my\s+friend)\s+(?:said|told|wrote|asked)\b/i;
const REFERENCE_WRAPPED_PERSON =
  /\b(?:conversation|interview|episode|talk|book|article|work|series|channel|podcast|show)\s+(?:with|by|from)\b/i;
const REFERENCE_ADVERBS =
  '(?:(?:personally|currently|actually|still|always|mostly|usually|daily|now|highly|strongly|really|definitely|generally|originally)\\s+)*';
const REFERENCE_KIND_CONFLICTS: Partial<Record<ReferenceKind, RegExp>> = {
  app: /\b(?:book|novel|memoir|game|games|gaming|paper|course|device|hardware|chip|account)\b/i,
  book: /\b(?:game|app|application|software|tool|service|platform|device|hardware|paper|article|account|documentary|films?|movies?|songs?|albums?|magazines?|newsletters?|website|blog|talk|video|channel|supplement|vitamin|multivitamin|drug|medication)\b|\b(?:online|training|video)\s+course\b|\bcourse\s+(?:called|named|on|about)\b/i,
  course: /\b(?:game|app|software|tool|service|device|hardware|paper|account)\b/i,
  hardware: /\b(?:book|novel|memoir|game|app|software|service|course|paper|account)\b/i,
  paper: /\b(?:game|app|software|tool|service|device|hardware|course|account)\b/i,
  person: /\b(?:book|novel|memoir|game|app|software|tool|service|device|course|paper|account)\b/i,
  service: /\b(?:book|novel|memoir|paper|course|device|hardware|chip|account)\b/i,
  tool: /\b(?:book|novel|memoir|paper|course|device|hardware|chip|account)\b/i,
};
const REFERENCE_KIND_OVERRIDES = new Map<string, ReferenceKind>([
  ['antigravity', 'app'],
  ['blade runner', 'other'],
  ['claude', 'app'],
  ['coda', 'app'],
  ['creative destruction', 'book'],
  ['demand-side sales 101', 'book'],
  ['design sprint by google', 'other'],
  ['devin', 'app'],
  ['don giovanni', 'other'],
  ['embrace the adventure', 'other'],
  ['figjam', 'app'],
  ['forbes', 'other'],
  ['founders podcast', 'other'],
  ['gong', 'app'],
  ['goose', 'tool'],
  ['gta 4', 'other'],
  ['hey jude', 'other'],
  ['marginal revolution', 'other'],
  ['michael lewis', 'person'],
  ['miro', 'app'],
  ['mystery', 'app'],
  ['new york times', 'other'],
  ['nintendo power', 'other'],
  ['notebooklm', 'app'],
  ['nvidia', 'other'],
  ['orb', 'service'],
  ['pando', 'app'],
  ['persona', 'other'],
  ['pessimist archive', 'other'],
  ['quantum country', 'other'],
  ['red dead 1', 'other'],
  ['reinhold niebuhr', 'person'],
  ['rescuetime', 'app'],
  ['roald dahl', 'person'],
  ['scaling devtools', 'other'],
  ['silent all these years', 'other'],
  ['ted chiang', 'person'],
  ['the princess bride', 'other'],
  ['the peel', 'other'],
  ['thomas mann', 'person'],
  ['twitter', 'app'],
  ['ulm fit', 'paper'],
  ['v0', 'app'],
  ['vercel', 'service'],
  ['virgil', 'person'],
  ['wikipedia', 'other'],
  ['zoom', 'app'],
]);

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
    return /[A-Z0-9./+#@]/.test(normalized);
  }
  const firstToken = normalized.split(' ', 1)[0] ?? '';
  if (/^[a-z]+$/.test(firstToken)) {
    return false;
  }
  return /[A-Z]/.test(normalized) || /[./+#@]/.test(normalized);
}

type ReferenceMatch = {
  full: string;
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
    `\\b(?:i|we)(?:\\s+|['’](?:m|re|ve)\\s+)${REFERENCE_ADVERBS}(?:${verbs})\\b(?<gap>.{0,${distance}}?)${context.namePattern}`,
    'i'
  );
  const match = pattern.exec(clause);
  if (!match) {
    return false;
  }
  const gap = match.groups?.['gap'] ?? '';
  return !(
    REFERENCE_OBJECT_PRONOUN.test(gap) ||
    (context.kind === 'book' && /\b(?:book|biography)\s+(?:about|on)\b/i.test(gap)) ||
    /\b(?:said|told|wrote|asked)\b/i.test(gap) ||
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
  const deictic = new RegExp(
    `${context.namePattern}.{0,100}?\\b(?:i|we)(?:\\s+|['’](?:m|re|ve)\\s+)${REFERENCE_ADVERBS}recommend(?:ed)?\\s+(?:it|that|this)\\b`,
    'i'
  );
  const myRecommendations = new RegExp(
    `\\bmy\\s+recommendations?\\b.{0,180}?${context.namePattern}`,
    'i'
  );
  return (
    deictic.test(context.full) ||
    myRecommendations.test(context.full) ||
    context.matching.some(
      (clause) =>
        activeReferenceObject(context, 'recommend(?:ed)?', clause) ||
        should.test(clause) ||
        (context.kind !== 'person' && relative.test(clause)) ||
        worth.test(clause)
    )
  );
}

function useSupported(context: ReferenceMatch): boolean {
  const verbs =
    'use|used|using|rely\\s+on|run|work\\s+with|read|reread|reading|finished\\s+reading|started\\s+reading|am\\s+reading|are\\s+reading|have\\s+read|have\\s+been\\s+reading|have\\s+been\\s+using|have\\s+used|listen\\s+to|listened\\s+to|watch|watched|subscribe\\s+to|subscribed\\s+to|wear|drive|play';
  const fronted = new RegExp(
    `${context.namePattern}\\s*,\\s*(?:i|we)\\s+${REFERENCE_ADVERBS}(?:${verbs})\\b`,
    'i'
  );
  const titleFirst = new RegExp(
    `${context.namePattern}.{0,100}?\\b(?:i|we)(?:\\s+|['’](?:m|re|ve)\\s+)${REFERENCE_ADVERBS}(?:${verbs})\\b`,
    'i'
  );
  return context.matching.some(
    (clause) =>
      activeReferenceObject(context, verbs, clause) ||
      fronted.test(clause) ||
      titleFirst.test(clause)
  );
}

function preferenceSupported(context: ReferenceMatch): boolean {
  const verbs =
    'love|loved|like|liked|prefer|preferred|enjoy|enjoyed|adore|adored|swear\\s+by|do\\s+(?:love|like|prefer|enjoy|adore)';
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
  const describedBook = new RegExp(
    `\\b(?:book|novel|memoir|biography)\\b.{0,60}?\\b(?:i|we)(?:\\s+|['’](?:m|re|ve)\\s+)${REFERENCE_ADVERBS}(?:love|loved|like|liked|prefer|preferred|enjoy|enjoyed|adore|adored)\\b.{0,80}?${context.namePattern}`,
    'i'
  );
  const positiveBook = new RegExp(
    `(?:${context.namePattern}.{0,100}?\\b(?:best|great|excellent|incredible|fantastic|extraordinary|exceptionally\\s+good|wonderful)\\b.{0,40}?\\bbook\\b|\\b(?:best|great|excellent|incredible|fantastic|extraordinary|exceptionally\\s+good|wonderful)\\b.{0,40}?\\bbook\\b.{0,100}?${context.namePattern})`,
    'i'
  );
  const titleThenApproval = new RegExp(
    `${context.namePattern}.{0,100}?\\b(?:i|we)\\s+(?:thought|think)\\s+(?:it|that|this)\\s+(?:is|was)\\s+(?:great|excellent|incredible|fantastic|extraordinary|wonderful)\\b`,
    'i'
  );
  return context.matching.some(
    (clause) =>
      activeReferenceObject(context, verbs, clause) ||
      fan.test(clause) ||
      favorite.test(clause) ||
      obsessed.test(clause) ||
      describedBook.test(clause) ||
      positiveBook.test(clause) ||
      titleThenApproval.test(clause)
  );
}

function referenceRoleSupported(
  name: string,
  role: ReferenceRole,
  claimQuote: string,
  kind?: ReferenceKind,
  allowBookAnswer = false
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
  const context = { full: normalizeWs(claimQuote), kind, matching, namePattern, role };
  if (role === 'recommends') {
    if (allowBookAnswer && kind === 'book') {
      return true;
    }
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
  claimQuote: string,
  allowBookAnswer = false
): ReferenceKind {
  const override = REFERENCE_KIND_OVERRIDES.get(normalizeWs(name).toLowerCase());
  if (override) {
    return override;
  }
  if (kind === 'book' && allowBookAnswer) {
    return kind;
  }
  const context = normalizeWs(claimQuote);
  const namePattern = normalizeWs(name)
    .replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    .replace(/\s+/g, '\\s+');
  const mediaWrapper = new RegExp(
    `\\b(?:channel|podcast|show|series|episode)(?:\\s+(?:called|named|of))?\\s*,?\\s*${namePattern}\\b`,
    'i'
  );
  if (kind !== 'other' && mediaWrapper.test(context)) {
    return 'other';
  }
  // A direct person recommendation has already passed the stricter wrapper
  // checks above. Nearby words such as "book" describe the surrounding work,
  // not the recommended person's kind.
  if (kind === 'person' && role === 'recommends') {
    return kind;
  }
  return kindAfterConflictCheck(name, kind, context, namePattern);
}

function kindAfterConflictCheck(
  name: string,
  kind: ReferenceKind,
  context: string,
  namePattern: string
): ReferenceKind {
  const conflict = REFERENCE_KIND_CONFLICTS[kind];
  if (!conflict) {
    return kind;
  }
  const needle = normalizeWs(name).toLowerCase();
  const folded = context.toLowerCase();
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
  kindContext = claimQuote,
  allowBookAnswer = false
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
        isStableReferenceName(name) &&
        !(
          kind === 'book' &&
          (REFERENCE_NON_TITLE_BOOK_NAME.test(normalizeWs(name)) ||
            REFERENCE_AUDITED_NON_TITLE_BOOK_NAMES.has(normalizeWs(name).toLowerCase()))
        )
      )
    ) {
      continue;
    }
    if (!haystack.includes(normalizeWs(name).toLowerCase())) {
      continue;
    }
    if (!referenceRoleSupported(name, role, claimQuote, kind, allowBookAnswer)) {
      continue;
    }
    const normalizedKind = normalizedReferenceKind(name, kind, role, kindContext, allowBookAnswer);
    const key = `${role}|${name.toLowerCase()}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    out.push({ kind: normalizedKind, name, role });
  }
  return out;
}
