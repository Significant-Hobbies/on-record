import { existsSync, readFileSync, statSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';

const manifestArg = process.argv.indexOf('--manifest');
const manifestPath = resolve(
  manifestArg >= 0
    ? process.argv[manifestArg + 1]
    : 'workers/api/.wrangler/releases/2026-08-27-reviewed-v9/r2-uploads.json'
);
const apply = process.argv.includes('--apply');
const uploads = JSON.parse(readFileSync(manifestPath, 'utf8'));
const startArg = process.argv.indexOf('--start');
const startIndex = startArg >= 0 ? Number(process.argv[startArg + 1]) : 0;

if (!Array.isArray(uploads) || uploads.length === 0) {
  throw new Error(`No R2 uploads found in ${manifestPath}`);
}
if (!Number.isInteger(startIndex) || startIndex < 0 || startIndex >= uploads.length) {
  throw new Error(`--start must be an index from 0 to ${uploads.length - 1}`);
}

for (const upload of uploads) {
  if (!(upload?.file && upload?.key && Number.isInteger(upload?.size))) {
    throw new Error('Every R2 upload must include file, key, and integer size');
  }
  if (!existsSync(upload.file) || statSync(upload.file).size !== upload.size) {
    throw new Error(`R2 source file is missing or changed: ${upload.file}`);
  }
}

if (!apply) {
  console.log(JSON.stringify({ apply: false, objects: uploads.length, status: 'validated' }));
  process.exit(0);
}

function uploadObject(upload) {
  return new Promise((resolveUpload, rejectUpload) => {
    const child = spawn(
      'pnpm',
      [
        '--filter',
        '@on-record/api',
        'exec',
        'wrangler',
        'r2',
        'object',
        'put',
        `on-record-raw/${upload.key}`,
        '--remote',
        '--file',
        upload.file,
        '--content-type',
        'application/json',
        '--config',
        'wrangler.jsonc',
        '--force',
      ],
      { cwd: process.cwd(), stdio: ['ignore', 'ignore', 'pipe'] }
    );
    let stderr = '';
    child.stderr.on('data', (chunk) => {
      stderr += chunk;
    });
    child.on('error', rejectUpload);
    child.on('exit', (code) => {
      if (code === 0) {
        resolveUpload();
      } else {
        rejectUpload(new Error(`Upload failed for ${upload.key}: ${stderr.trim()}`));
      }
    });
  });
}

async function uploadObjectWithRetry(upload, maxAttempts = 3) {
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      await uploadObject(upload);
      return;
    } catch (error) {
      if (attempt === maxAttempts) {
        throw error;
      }
      console.warn(`Retrying ${upload.key} after failed attempt ${attempt}/${maxAttempts}`);
      await new Promise((resolveRetry) => setTimeout(resolveRetry, attempt * 500));
    }
  }
}

let completed = startIndex;
const queue = uploads.slice(startIndex);
const workers = Array.from({ length: Math.min(4, queue.length) }, async () => {
  while (queue.length > 0) {
    const upload = queue.shift();
    await uploadObjectWithRetry(upload);
    completed += 1;
    if (completed % 10 === 0 || completed === uploads.length) {
      console.log(`Uploaded ${completed}/${uploads.length} reviewed R2 objects`);
    }
  }
});

await Promise.all(workers);
console.log(
  JSON.stringify({
    apply: true,
    objects: uploads.length - startIndex,
    startIndex,
    status: 'uploaded',
  })
);
