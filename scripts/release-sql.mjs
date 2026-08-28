import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

export function invariant(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

export function createValidationDatabase(root) {
  const db = new DatabaseSync(':memory:');
  for (const migration of [
    '0000_init.sql',
    '0001_fts.sql',
    '0002_references.sql',
    '0003_segment_cue_map.sql',
    '0004_segments_to_r2.sql',
    '0005_claim_corrected_at.sql',
    '0006_llm_segment_attempts.sql',
  ]) {
    const sql = readFileSync(join(root, 'packages/db/migrations', migration), 'utf8');
    for (const statement of sql.split('--> statement-breakpoint')) {
      if (statement.trim()) {
        db.exec(statement);
      }
    }
  }
  return db;
}

function quoteIdentifier(value) {
  return `"${String(value).replaceAll('"', '""')}"`;
}

function sqlValue(value) {
  if (value === null || value === undefined) {
    return 'NULL';
  }
  if (typeof value === 'number') {
    invariant(Number.isFinite(value), `non-finite SQL number: ${value}`);
    return String(value);
  }
  if (typeof value === 'bigint') {
    return String(value);
  }
  if (value instanceof Uint8Array) {
    return `X'${Buffer.from(value).toString('hex')}'`;
  }
  return `'${String(value).replaceAll("'", "''")}'`;
}

export function rowsFor(db, table, where = '', params = []) {
  const suffix = where ? ` WHERE ${where}` : '';
  return db.prepare(`SELECT * FROM ${quoteIdentifier(table)}${suffix}`).all(...params);
}

function valuesForRows(table, rows, columns) {
  return rows.map((row) => {
    invariant(
      Object.keys(row).join('\0') === columns.join('\0'),
      `${table} rows have inconsistent columns`
    );
    return `  (${columns.map((column) => sqlValue(row[column])).join(', ')})`;
  });
}

function writeStatements(table, rows, suffix, chunkSize) {
  if (rows.length === 0) {
    return [];
  }
  const columns = Object.keys(rows[0]);
  const head = `INSERT INTO ${quoteIdentifier(table)} (${columns
    .map(quoteIdentifier)
    .join(', ')}) VALUES\n`;
  const statements = [];
  for (let offset = 0; offset < rows.length; offset += chunkSize) {
    const values = valuesForRows(table, rows.slice(offset, offset + chunkSize), columns);
    statements.push(`${head}${values.join(',\n')}${suffix(columns)};`);
  }
  return statements;
}

export function insertStatements(table, rows, chunkSize = 100) {
  return writeStatements(table, rows, () => '', chunkSize);
}

export function upsertStatements(table, rows, chunkSize = 50) {
  return writeStatements(
    table,
    rows,
    (columns) =>
      `\nON CONFLICT DO UPDATE SET ${columns
        .map((column) => `${quoteIdentifier(column)} = excluded.${quoteIdentifier(column)}`)
        .join(', ')}`,
    chunkSize
  );
}

export function stableReferenceId(row) {
  return createHash('sha256')
    .update(`${row.claim_id}\0${row.kind}\0${row.role}\0${row.name}`)
    .digest('hex')
    .slice(0, 32);
}
