#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import { readdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, extname, join, resolve } from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const productionPaths = ['packages/db/src', 'workers/api/src', 'python/ingest/src', 'scripts'];
const baselines = {
  complexity: { maxCcn: 20, maxLength: 120, maxParams: 8, violations: 0 },
  duplication: { clones: 0, duplicatedLines: 0, percentage: 0 },
  suppressions: 0,
  unused: {
    dependencies: 0,
    devDependencies: 0,
    exports: 0,
    files: 0,
    types: 0,
    unlisted: 0,
    unresolved: 0,
  },
};

function output(message) {
  process.stdout.write(`${message}\n`);
}

function run(command, args, allowFailure = false) {
  const result = spawnSync(command, args, {
    cwd: root,
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0 && !allowFailure) {
    process.stdout.write(result.stdout ?? '');
    process.stderr.write(result.stderr ?? '');
    throw new Error(`${command} exited with status ${result.status}`);
  }
  return result;
}

function parseJson(result, label) {
  try {
    return JSON.parse(result.stdout);
  } catch (error) {
    throw new Error(`${label} did not return JSON`, { cause: error });
  }
}

function regress(label, observed, baseline) {
  const failures = Object.entries(baseline).filter(([key, max]) => observed[key] > max);
  if (failures.length) {
    throw new Error(
      failures.map(([key, max]) => `${label} ${key}: ${observed[key]} > ${max}`).join('\n')
    );
  }
}

function unused() {
  const result = run('pnpm', ['exec', 'knip', '--reporter', 'json'], true);
  const data = parseJson(result, 'knip');
  const observed = {
    dependencies: (data.issues ?? []).reduce(
      (sum, issue) => sum + (issue.dependencies?.length ?? 0),
      0
    ),
    devDependencies: (data.issues ?? []).reduce(
      (sum, issue) => sum + (issue.devDependencies?.length ?? 0),
      0
    ),
    exports: (data.issues ?? []).reduce((sum, issue) => sum + (issue.exports?.length ?? 0), 0),
    files: (data.files ?? []).length,
    types: (data.issues ?? []).reduce((sum, issue) => sum + (issue.types?.length ?? 0), 0),
    unlisted: (data.issues ?? []).reduce((sum, issue) => sum + (issue.unlisted?.length ?? 0), 0),
    unresolved: (data.issues ?? []).reduce(
      (sum, issue) => sum + (issue.unresolved?.length ?? 0),
      0
    ),
  };
  output(`Unused: ${JSON.stringify(observed)}`);
  regress('Unused', observed, baselines.unused);
}

function complexity() {
  const result = run('uv', [
    'run',
    '--project',
    'python/ingest',
    '--no-sync',
    'lizard',
    ...productionPaths,
    '-x',
    '**/*.test.*',
    '--csv',
  ]);
  const rows = result.stdout
    .trim()
    .split('\n')
    .map((line) => line.match(/^(\d+),(\d+),(\d+),(\d+),(\d+),/u))
    .filter(Boolean)
    .map((match) => match.slice(1).map(Number));
  const observed = {
    maxCcn: Math.max(0, ...rows.map((row) => row[1])),
    maxLength: Math.max(0, ...rows.map((row) => row[4])),
    maxParams: Math.max(0, ...rows.map((row) => row[3])),
    violations: rows.filter((row) => row[1] > 20 || row[4] > 100 || row[3] > 7).length,
  };
  output(`Complexity: ${JSON.stringify(observed)}`);
  regress('Complexity', observed, baselines.complexity);
}

function duplication() {
  const outputDirectory = join(tmpdir(), `on-record-jscpd-${process.pid}`);
  run('pnpm', [
    'exec',
    'jscpd',
    ...productionPaths,
    '--format',
    'javascript,typescript,python',
    '--min-lines',
    '8',
    '--min-tokens',
    '60',
    '--mode',
    'strict',
    '--ignore',
    '**/*.test.*,**/*.spec.*,**/node_modules/**,**/coverage/**',
    '--reporters',
    'json',
    '--output',
    outputDirectory,
    '--silent',
    '--no-tips',
  ]);
  const report = JSON.parse(readFileSync(join(outputDirectory, 'jscpd-report.json'), 'utf8'));
  const observed = {
    clones: report.statistics.total.clones,
    duplicatedLines: report.statistics.total.duplicatedLines,
    percentage: report.statistics.total.percentage,
  };
  output(`Duplication: ${JSON.stringify(observed)}`);
  regress('Duplication', observed, baselines.duplication);
}

function cycles() {
  const result = run('pnpm', ['exec', 'knip', '--cycles', '--no-config-hints']);
  output(result.stdout.trim() || 'Cycles: none');
}

function suppressions() {
  const skip = new Set(['.git', 'node_modules', '.wrangler', 'coverage', 'dist', '.venv']);
  const files = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (skip.has(entry.name)) {
        continue;
      }
      const full = join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
        continue;
      }
      if (entry.name === 'check-code-health.mjs') {
        continue;
      }
      if (['.ts', '.js', '.mjs', '.py'].includes(extname(entry.name))) {
        files.push(full);
      }
    }
  };
  walk(root);
  let count = 0;
  const markers = [
    'biome-ignore',
    'knip-ignore',
    '@ts-ignore',
    '@ts-expect-error',
    'noqa',
    'type: ignore',
  ];
  for (const file of files) {
    const text = readFileSync(file, 'utf8');
    for (const marker of markers) {
      if (text.includes(marker)) {
        count += text.split(marker).length - 1;
      }
    }
  }
  output(`Suppressions: ${count}`);
  if (count > baselines.suppressions) {
    throw new Error(`Suppressions ${count} > ${baselines.suppressions}`);
  }
}

function hygiene() {
  const forbidden = ['.env', '.dev.vars'];
  const found = forbidden.filter((name) => {
    try {
      readFileSync(join(root, name));
      return true;
    } catch {
      return false;
    }
  });
  if (found.length) {
    throw new Error(`Tracked secret files present: ${found.join(', ')}`);
  }
  output('Hygiene: ok');
}

const commands = {
  complexity,
  cycles,
  duplication,
  hygiene,
  suppressions,
  unused,
};

const name = process.argv[2];
if (!(name && name in commands)) {
  throw new Error(`Unknown check: ${name}. Expected ${Object.keys(commands).join(', ')}`);
}
commands[name]();
