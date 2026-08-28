import {
  ACTIONABLE_REFERENCE_ROLES,
  type ActionableReferenceRole,
  type ReferenceKind,
  isActionableReferenceRole,
} from './references';

type GroupableReference = {
  kind: ReferenceKind;
  name: string;
  personId: string;
  role: string;
};

export type RecommendationGroup = {
  kind: ReferenceKind;
  name: string;
  occurrenceCount: number;
  peopleCount: number;
  roleCounts: Record<ActionableReferenceRole, number>;
};

export function canonicalReferenceName(name: string): string {
  return name.normalize('NFKC').replace(/\s+/g, ' ').trim().toLocaleLowerCase('en-US');
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
    }
  >();
  for (const row of rows) {
    if (!isActionableReferenceRole(row.role)) {
      continue;
    }
    const key = `${row.kind}\0${canonicalReferenceName(row.name)}`;
    const group = grouped.get(key) ?? {
      kind: row.kind,
      name: row.name,
      occurrences: 0,
      people: new Set<string>(),
      peopleByRole: new Map<ActionableReferenceRole, Set<string>>(),
    };
    group.occurrences += 1;
    group.people.add(row.personId);
    const rolePeople = group.peopleByRole.get(row.role) ?? new Set<string>();
    rolePeople.add(row.personId);
    group.peopleByRole.set(row.role, rolePeople);
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
    }))
    .sort(
      (left, right) =>
        right.peopleCount - left.peopleCount ||
        right.occurrenceCount - left.occurrenceCount ||
        left.name.localeCompare(right.name)
    );
}
