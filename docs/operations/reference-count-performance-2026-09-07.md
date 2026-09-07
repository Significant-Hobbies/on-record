# Published reference count: local qualification, 2026-09-07

Issue [#24](https://github.com/Significant-Hobbies/on-record/issues/24) describes
expensive cache-miss stats reads. The stats route now reads only eight fields
needed for quote validation and deduplication. It keeps the same six inner joins,
trusted-show/actionable-role/published gates, verified-speaker identity handling,
20,000-row window and total reference order. Count and display paths share the
sanitizer and dedupe helper. This is not a raw SQL row count or a cached counter.

Keeping the evidence join also preserves existing behavior when multiple primary
evidence rows consume the bounded window; an EXISTS rewrite would change that
window. No schema migration or production query was run.

## Reproducible checks

`workers/api/src/routes/public-reference-count.test.ts` uses Node's built-in
SQLite and the repository migrations. The small adversarial fixture covers
withheld shows, draft claims, unsupported quotes, mention-only roles, missing
primary evidence, same-segment duplicates, distinct verified people, unverified
speakers, missing segments, and the book-answer prompt exception. It checks the
actual `/stats` handler as well as full-list/count equality.

The large fixture contains 11,000 synthetic claims and two primary evidence rows
per claim. Both reads take the same first 20,000 raw rows and return 5,001 public
references. The lexical reference-id boundary cuts through one segment pair.
The test asserts parity and reduced payload, not a machine-dependent speed bar.

Run from the repository root on Node 22.16+:

```sh
REFERENCE_BENCH_OUTPUT=/tmp/on-record-reference-perf \
  pnpm --filter @on-record/api exec vitest run src/routes/public-reference-count.test.ts
```

This writes the synthetic fixture SQL, the exact two EXPLAIN statements and seven
local timing pairs. Timings cover the SQLite-backed Drizzle read, JSON encoding
for payload measurement, and JS sanitation/deduplication/display work; they are
not D1 network latency or full endpoint latency. The seven recorded pairs use
full then narrow reads after an initial warm pair.

| Measurement | Full display read | Narrow count read |
| --- | ---: | ---: |
| Median local harness time | 179.09 ms | 124.88 ms |
| Raw rows encoded as JSON | 11,335,773 bytes | 1,735,773 bytes |
| Public references | 5,001 | 5,001 |

This fixture therefore reduces harness time by 30.3% and encoded bytes by 84.7%.
Actual data shape, storage, CPU, cache and network behavior can differ.
[Raw samples and SQLite plans](evidence/reference-count-2026-09-07/receipt.json).

## Actual local D1 query plans

The same fixture and EXPLAIN statements were executed through Wrangler 4.85.0
with `d1 execute --local`, a temporary config naming only a fake local database,
and an isolated `/tmp` persistence directory. No repository provider config,
credentials, production D1 or R2 were used. Run each EXPLAIN statement separately:
Wrangler returns only the final result for a multi-statement EXPLAIN file, and
parallel Wrangler processes can lock the same local SQLite state.

Both [full](evidence/reference-count-2026-09-07/d1-full-plan.json) and
[narrow](evidence/reference-count-2026-09-07/d1-narrow-plan.json) plans enter via
`claim_references_role_claim_idx` with SEARCH, not an outer table SCAN. The narrow
read uses covering indexes for the people primary-key lookup and the primary
claim-evidence lookup. Both retain a temporary B-tree for ordering. Existing
indexes suffice for this bounded improvement; the sort/corpus-wide scan ceiling
has not been eliminated.

## Remaining qualification

`pnpm quality` passes: 122 TypeScript tests, 228 Python tests, formatting/lint,
all package typechecks and code-health gates. The focused route/SQLite suite
passes 20 tests. Only `@types/node` was added as a development dependency to
typecheck built-in SQLite; there is no new production dependency.

Issue #24 remains open for an authorized deployment, exact live cache-miss timing
and rows-read comparison, plus any further reduction justified by those results.
No live improvement, new ingestion or expansion is claimed. The project remains
inactive and its existing public corpus is untouched.
