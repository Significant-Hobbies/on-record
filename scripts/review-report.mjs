#!/usr/bin/env node

const base = process.env.API_BASE ?? 'http://127.0.0.1:8787';
const token = process.env.ADMIN_TOKEN;
if (!token) {
  throw new Error('ADMIN_TOKEN is required');
}

const response = await fetch(`${base}/admin/review-queue`, {
  headers: { Authorization: `Bearer ${token}` },
});
if (!response.ok) {
  throw new Error(`review-queue failed: ${response.status} ${await response.text()}`);
}
const payload = await response.json();
const rows = payload.claims ?? [];
process.stdout.write(`Held/draft claims: ${rows.length}\n`);
for (const row of rows) {
  process.stdout.write(
    `${row.reviewStatus}\t${row.confidenceBand}\t${row.personSlug ?? row.personId}\t${row.assertion}\n`
  );
}
