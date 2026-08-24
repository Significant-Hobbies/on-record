const FTS_OPERATORS = /["*:^(){}[\]-]/gu;
const FTS_WORDS = new Set(['and', 'or', 'not', 'near']);

export function sanitizeFtsQuery(raw: string): string | null {
  const cleaned = raw.replace(FTS_OPERATORS, ' ').replace(/\s+/gu, ' ').trim();
  if (!cleaned) {
    return null;
  }
  const tokens = cleaned
    .split(' ')
    .map((token) => token.replace(/[^a-zA-Z0-9_]+/gu, ''))
    .filter((token) => token.length >= 2 && !FTS_WORDS.has(token.toLowerCase()));
  if (!tokens.length) {
    return null;
  }
  return tokens.map((token) => `"${token}"`).join(' AND ');
}
