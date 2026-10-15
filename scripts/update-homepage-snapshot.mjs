import { writeFile } from 'node:fs/promises';

const apiOrigin = 'https://api.podcasts.highsignal.app';
const endpoints = {
  stats: '/api/stats',
  people: '/api/people?limit=8',
  groups: '/api/recommendation-groups?limit=8',
  sources: '/api/sources?limit=5',
};

async function publicJson(path) {
  const response = await fetch(`${apiOrigin}${path}`, { signal: AbortSignal.timeout(10_000) });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json();
}

function count(value, field) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error(`Invalid ${field}`);
  }
  return value;
}

function text(value, field) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`Invalid ${field}`);
  }
  return value;
}

function optionalText(value, field) {
  if (value !== null && value !== undefined && typeof value !== 'string') {
    throw new Error(`Invalid ${field}`);
  }
  return value ?? null;
}

function roles(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Invalid group roleCounts');
  }
  return Object.fromEntries(
    Object.entries(value).map(([role, amount]) => [role, count(amount, role)])
  );
}

function rows(payload, key, maximum) {
  const entries = payload?.[key];
  if (!Array.isArray(entries) || entries.length > maximum) {
    throw new Error(`Invalid ${key} list`);
  }
  return entries;
}

const [rawStats, rawPeople, rawGroups, rawSources] = await Promise.all(
  Object.values(endpoints).map(publicJson)
);
const stats = {
  catalogEpisodes: count(rawStats.catalogEpisodes, 'catalogEpisodes'),
  episodes: count(rawStats.episodes, 'episodes'),
  people: count(rawStats.people, 'people'),
  publishedClaims: count(rawStats.publishedClaims, 'publishedClaims'),
  publishedReferences: count(rawStats.publishedReferences, 'publishedReferences'),
  transcriptEpisodes: count(rawStats.transcriptEpisodes, 'transcriptEpisodes'),
  trustedShows: count(rawStats.trustedShows, 'trustedShows'),
  trustPolicy: {
    withheldShows: count(rawStats.trustPolicy?.withheldShows, 'withheldShows'),
    wording: text(rawStats.trustPolicy?.wording, 'trustPolicy wording'),
  },
};
const people = rows(rawPeople, 'people', 8).map((person) => ({
  id: text(person.id, 'person id'),
  slug: text(person.slug, 'person slug'),
  name: text(person.name, 'person name'),
  title: optionalText(person.title, 'person title'),
  org: optionalText(person.org, 'person org'),
  claimCount: count(person.claimCount, 'person claimCount'),
}));
const groups = rows(rawGroups, 'groups', 8).map((group) => ({
  kind: text(group.kind, 'group kind'),
  name: text(group.name, 'group name'),
  occurrenceCount: count(group.occurrenceCount, 'group occurrenceCount'),
  peopleCount: count(group.peopleCount, 'group peopleCount'),
  roleCounts: roles(group.roleCounts),
}));
const sources = rows(rawSources, 'sources', 5).map((source) => {
  if (source.status !== 'published') {
    throw new Error(`Unpublished source ${source.id}`);
  }
  return {
    id: text(source.id, 'source id'),
    title: text(source.title, 'source title'),
    publishedAt: optionalText(source.publishedAt, 'source publishedAt'),
    showName: optionalText(source.showName, 'source showName'),
    claimCount: count(source.claimCount, 'source claimCount'),
    status: 'published',
  };
});
const snapshot = {
  capturedAt: new Date().toISOString(),
  provenance: { apiOrigin, endpoints },
  stats,
  people,
  groups,
  sources,
};
const target = new URL('../apps/web/src/data/homepage-snapshot.json', import.meta.url);
await writeFile(target, `${JSON.stringify(snapshot, null, 2)}\n`);
process.stdout.write(`Updated ${target.pathname} from public API endpoints\n`);
