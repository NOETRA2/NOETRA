import { expect, test } from 'vitest';
import { mkdtemp, readFile, writeFile, access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { planJsonSetup, applyJsonSetup, rollbackJsonSetup, codexSnippet } from '../../apps/cli/src/setup.js';

test('setup previews without writing, preserves other servers and backs up exact bytes', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'noetra-setup-')), path = join(dir, 'mcp.json');
  const previous = JSON.stringify({ mcpServers: { rea: { command: 'keep-existing-rea' } }, other: { option: true } });
  await writeFile(path, previous);
  const plan = await planJsonSetup(path, '/noetra/cli.js', '/project');
  expect(await readFile(path, 'utf8')).toBe(previous);
  const receipt = await applyJsonSetup(plan);
  expect(JSON.parse(await readFile(path, 'utf8')).mcpServers.rea.command).toBe('keep-existing-rea');
  expect(await readFile(receipt.backup!, 'utf8')).toBe(previous);
  await rollbackJsonSetup(path, receipt.receipt); expect(await readFile(path, 'utf8')).toBe(previous);
});
test('setup refuses existing conflicting NOETRA entries and intervening changes', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'noetra-setup-')), path = join(dir, 'mcp.json');
  await writeFile(path, JSON.stringify({ mcpServers: { noetra: { command: 'different' } } }));
  await expect(planJsonSetup(path, '/noetra/cli.js', '/project')).rejects.toThrow();
  await writeFile(path, '{}'); const plan = await planJsonSetup(path, '/noetra/cli.js', '/project');
  await writeFile(path, '{"newSetting":true}'); await expect(applyJsonSetup(plan)).rejects.toThrow();
  expect(await readFile(path, 'utf8')).toBe('{"newSetting":true}');
});
test('rollback refuses to overwrite settings changed after install', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'noetra-setup-')), path = join(dir, 'mcp.json');
  const plan = await planJsonSetup(path, '/noetra/cli.js', '/project'), receipt = await applyJsonSetup(plan);
  await writeFile(path, '{"changed":true}'); await expect(rollbackJsonSetup(path, receipt.receipt)).rejects.toThrow();
});
test('new-file rollback removes only the generated configuration; Codex is preview-only', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'noetra-setup-')), path = join(dir, 'mcp.json');
  const receipt = await applyJsonSetup(await planJsonSetup(path, '/noetra/cli.js', '/project'));
  await rollbackJsonSetup(path, receipt.receipt); await expect(access(path)).rejects.toThrow();
  expect(codexSnippet('C:\\NOETRA\\cli.js', 'C:\\my project')).toContain('[mcp_servers.noetra]');
});
