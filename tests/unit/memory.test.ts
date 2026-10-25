import { expect, test } from 'vitest';
import { Memory } from '../../packages/memory/src/index.js';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

test('SQLite persists across restarts, isolates projects and preserves old revisions', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'noetra-memory-')), path = join(dir, 'memory.sqlite');
  let memory = new Memory(path, 'project-a');
  const record = memory.put('world', { old: true });
  memory.put('world', { old: false }, { id: record.id, expectedRevision: 1 });
  expect(() => memory.put('world', {}, { id: record.id, expectedRevision: 1 })).toThrow();
  expect(() => memory.put('evidence', {}, { id: record.id })).toThrow();
  memory.close(); memory = new Memory(path, 'project-a');
  expect(memory.history(record.id)).toHaveLength(2); expect(memory.get(record.id)?.value).toEqual({ old: false });
  const other = new Memory(path, 'project-b'); expect(other.get(record.id)).toBeUndefined(); expect(other.export()).toEqual([]);
  expect(() => other.deleteProject('project-a')).toThrow(); expect(other.deleteProject('project-b')).toBe(0);
  expect(memory.deleteProject('project-a')).toBe(2); expect(memory.list()).toEqual([]);
  other.close(); memory.close();
});
test('expired latest record cannot resurrect an older revision after purge', () => {
  const memory = new Memory(':memory:', 'expiry');
  const first = memory.put('hypothesis', { outdated: true });
  memory.put('hypothesis', { newer: true }, { id: first.id, expiresAt: '2000-01-01T00:00:00.000Z' });
  expect(memory.get(first.id)).toBeUndefined(); memory.purgeExpired();
  expect(memory.get(first.id)).toBeUndefined(); expect(memory.history(first.id)).toEqual([]); memory.close();
});
test('SQL-like project/id text stays data, not executable SQL', () => {
  const memory = new Memory(':memory:', "';DROP TABLE records;--");
  const a = memory.put('evidence', { text: "'; DELETE FROM records;--" });
  expect(memory.get(a.id)?.value).toEqual({ text: "'; DELETE FROM records;--" }); memory.close();
});
