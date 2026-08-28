import {
  ACTIONABLE_REFERENCE_ROLES,
  type ActionableReferenceRole,
  type ReferenceKind,
  isActionableReferenceRole,
} from './references';

type GroupableReference = {
  attributionStatus?: 'verified_speaker' | 'speaker_unverified';
  kind: ReferenceKind;
  name: string;
  personId: string | null;
  role: string;
};

export type RecommendationGroup = {
  kind: ReferenceKind;
  name: string;
  occurrenceCount: number;
  peopleCount: number;
  roleCounts: Record<ActionableReferenceRole, number>;
  unverifiedSpeakerCount: number;
};

const REFERENCE_ALIASES = new Map<string, string>([
  ['"how to measure anything"', 'how to measure anything'],
  ['15 commitments of conscious leadership', 'the 15 commitments of conscious leadership'],
  ['15 commitments to conscious leaders', 'the 15 commitments of conscious leadership'],
  ['business model canvas', 'business model generation'],
  ['creativity inc', 'creativity, inc.'],
  ["daniel kahneman's thinking, fast and slow", 'thinking, fast and slow'],
  ['darwin economy', 'the darwin economy'],
  ['design of everyday things', 'the design of everyday things'],
  ['demand side sales', 'demand-side sales 101'],
  ['five dysfunctions of a team', 'the five dysfunctions of a team'],
  ['finding intangibles', 'how to measure anything'],
  ['finding the value of intangibles in business', 'how to measure anything'],
  ['god saved texas', 'god save texas'],
  ['good strategy bad strategy', 'good strategy/bad strategy'],
  ['hard thing about hard things', 'the hard thing about hard things'],
  ['the high growth handbook', 'high growth handbook'],
  ['high-output management', 'high output management'],
  ['how brands grow 1', 'how brands grow'],
  [
    'how to listen so your kid will talk',
    'how to talk so your kids will listen & how to listen so your kid will talk',
  ],
  [
    'how to talk so your kids will listen',
    'how to talk so your kids will listen & how to listen so your kid will talk',
  ],
  ['in my antonia', 'my antonia'],
  ['in order, high output management', 'high output management'],
  ["innovator's dilemma", "the innovator's dilemma"],
  ['innovators dilemma', "the innovator's dilemma"],
  ['inspired: how to build products that people love', 'inspired'],
  ['leadership and self-deception', 'leadership and self deception'],
  ["mike shellenberger's san fransicko", 'san fransicko'],
  ["muriel's hooked", 'hooked'],
  ['name of the wind', 'the name of the wind'],
  ['origin of wealth', 'the origin of wealth'],
  ['play to win', 'playing to win'],
  [
    'range: why generalists triumph in a specialized world, by david epstein',
    'range: why generalists triumph in a specialized world',
  ],
  ['range', 'range: why generalists triumph in a specialized world'],
  ['simple path to wealth', 'the simple path to wealth'],
  ['skilling people', 'scaling people'],
  ['snowball', 'the snowball'],
  ['story of real life', 'story of your life'],
  ['supernatural meetings with the ancient teachers of mankind', 'visionary'],
  ['sherlock holmes', 'sherlock holmes stories'],
  ['switch', 'switch: how to change things when change is hard'],
  ['the crutch', 'the crux'],
  ['the design of everyday things', 'the design of everyday things'],
  ['the elements of thinking in systems', 'thinking in systems'],
  ['the flywheel from good to great', 'turning the flywheel'],
  ['the hard thing about hard things', 'the hard thing about hard things'],
  ['scarlet letter', 'the scarlet letter'],
  ['the timeless way of building', 'the timeless way of building'],
  ['the undoing projects', 'the undoing project'],
  ['the untethered soul', 'the untethered soul'],
  ['the shih ching', 'shih ching'],
  ['thinking slow and fast', 'thinking, fast and slow'],
  ['timeless way of building', 'the timeless way of building'],
  ['untethered soul', 'the untethered soul'],
  ['walt disney', 'walt disney: the triumph of the american imagination'],
  [
    'the triumph of the american imagination',
    'walt disney: the triumph of the american imagination',
  ],
  ['zen and the motorcycle maintenance', 'zen and the art of motorcycle maintenance'],
]);

const REFERENCE_DISPLAY_NAMES = new Map<string, string>([
  ['demand-side sales 101', 'Demand-Side Sales 101'],
  [
    'how to talk so your kids will listen & how to listen so your kid will talk',
    'How to Talk So Your Kids Will Listen & How to Listen So Your Kid Will Talk',
  ],
  ['san fransicko', 'San Fransicko'],
  ['shih ching', 'Shih Ching'],
  ['business model generation', 'Business Model Generation'],
  ['creativity, inc.', 'Creativity, Inc.'],
  ['good strategy/bad strategy', 'Good Strategy/Bad Strategy'],
  ['high growth handbook', 'High Growth Handbook'],
  ['high output management', 'High Output Management'],
  ['my antonia', 'My Antonia'],
  ['playing to win', 'Playing to Win'],
  [
    'range: why generalists triumph in a specialized world',
    'Range: Why Generalists Triumph in a Specialized World',
  ],
  ['scaling people', 'Scaling People'],
  ['story of your life', 'Story of Your Life'],
  ['the 15 commitments of conscious leadership', 'The 15 Commitments of Conscious Leadership'],
  ['the design of everyday things', 'The Design of Everyday Things'],
  ['the five dysfunctions of a team', 'The Five Dysfunctions of a Team'],
  ['the hard thing about hard things', 'The Hard Thing About Hard Things'],
  ["the innovator's dilemma", "The Innovator's Dilemma"],
  ['the name of the wind', 'The Name of the Wind'],
  ['the origin of wealth', 'The Origin of Wealth'],
  ['the scarlet letter', 'The Scarlet Letter'],
  ['the simple path to wealth', 'The Simple Path to Wealth'],
  ['the snowball', 'The Snowball'],
  ['the timeless way of building', 'The Timeless Way of Building'],
  ['the crux', 'The Crux'],
  ['the undoing project', 'The Undoing Project'],
  ['the untethered soul', 'The Untethered Soul'],
  ['thinking, fast and slow', 'Thinking, Fast and Slow'],
  ['thinking in systems', 'Thinking in Systems'],
  ['turning the flywheel', 'Turning the Flywheel'],
  ['visionary', 'Visionary'],
  [
    'walt disney: the triumph of the american imagination',
    'Walt Disney: The Triumph of the American Imagination',
  ],
  ['zen and the art of motorcycle maintenance', 'Zen and the Art of Motorcycle Maintenance'],
]);

export function canonicalReferenceName(name: string): string {
  const normalized = name.normalize('NFKC').replace(/\s+/g, ' ').trim().toLocaleLowerCase('en-US');
  return REFERENCE_ALIASES.get(normalized) ?? normalized;
}

export function groupRecommendationReferences(rows: GroupableReference[]): RecommendationGroup[] {
  const grouped = new Map<
    string,
    {
      kind: ReferenceKind;
      name: string;
      occurrences: number;
      people: Set<string>;
      peopleByRole: Map<ActionableReferenceRole, Set<string>>;
      unverifiedSpeakers: number;
    }
  >();
  for (const row of rows) {
    if (!isActionableReferenceRole(row.role)) {
      continue;
    }
    const key = `${row.kind}\0${canonicalReferenceName(row.name)}`;
    const group = grouped.get(key) ?? {
      kind: row.kind,
      name: REFERENCE_DISPLAY_NAMES.get(canonicalReferenceName(row.name)) ?? row.name,
      occurrences: 0,
      people: new Set<string>(),
      peopleByRole: new Map<ActionableReferenceRole, Set<string>>(),
      unverifiedSpeakers: 0,
    };
    group.occurrences += 1;
    if (row.attributionStatus === 'speaker_unverified') {
      group.unverifiedSpeakers += 1;
    } else if (row.personId) {
      group.people.add(row.personId);
      const rolePeople = group.peopleByRole.get(row.role) ?? new Set<string>();
      rolePeople.add(row.personId);
      group.peopleByRole.set(row.role, rolePeople);
    }
    grouped.set(key, group);
  }
  return [...grouped.values()]
    .map((group) => ({
      kind: group.kind,
      name: group.name,
      occurrenceCount: group.occurrences,
      peopleCount: group.people.size,
      roleCounts: Object.fromEntries(
        ACTIONABLE_REFERENCE_ROLES.map((role) => [role, group.peopleByRole.get(role)?.size ?? 0])
      ) as Record<ActionableReferenceRole, number>,
      unverifiedSpeakerCount: group.unverifiedSpeakers,
    }))
    .sort(
      (left, right) =>
        right.peopleCount - left.peopleCount ||
        right.occurrenceCount - left.occurrenceCount ||
        left.name.localeCompare(right.name)
    );
}
