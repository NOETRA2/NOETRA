import { readFile, writeFile, mkdir, rename, lstat, unlink } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { homedir } from 'node:os';
import { fail } from '../../../packages/shared-types/src/index.js';

export type ClientName = 'cursor' | 'claude' | 'codex';
export function digest(value: string): string { return createHash('sha256').update(value).digest('hex'); }
export function clientPath(client: ClientName, root: string, scope: 'project' | 'user'): string {
  const base = scope === 'user' ? homedir() : root;
  if (client === 'cursor') return resolve(base, '.cursor', 'mcp.json');
  if (client === 'claude') return resolve(base, scope === 'user' ? '.claude.json' : '.mcp.json');
  return resolve(base, '.codex', 'config.toml');
}
export function configurationEntry(cli: string, project: string) {
  return { command: process.execPath, args: [cli, 'mcp', '--project', project] };
}
export async function detectClients(root: string) {
  const found: Array<{ client: ClientName; scope: string; config: string }> = [];
  for (const client of ['cursor', 'claude', 'codex'] as const) for (const scope of ['project', 'user'] as const) {
    const config = clientPath(client, root, scope);
    try { await lstat(config); found.push({ client, scope, config }); } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  }
  return found;
}
async function existing(path: string): Promise<string | null> {
  try {
    const stat = await lstat(path);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 2 * 1024 * 1024) fail('UNSAFE_CONFIG', 'Configuration must be a regular file at most 2 MiB.');
    return await readFile(path, 'utf8');
  } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return null; throw error; }
}
export interface SetupPlan { target: string; beforeHash: string | null; entry: ReturnType<typeof configurationEntry>; after: string }
export async function planJsonSetup(target: string, cli: string, project: string): Promise<SetupPlan> {
  const before = await existing(target);
  const config = before === null ? {} : JSON.parse(before) as Record<string, unknown>;
  if (!config || typeof config !== 'object' || Array.isArray(config)) fail('INVALID_CONFIG', 'Client configuration must be a JSON object.');
  const servers = config.mcpServers ?? {};
  if (!servers || typeof servers !== 'object' || Array.isArray(servers)) fail('INVALID_CONFIG', 'mcpServers must be an object.');
  const entries = servers as Record<string, unknown>;
  const entry = configurationEntry(cli, project);
  if (Object.hasOwn(entries, 'noetra') && JSON.stringify(entries.noetra) !== JSON.stringify(entry)) fail('CONFIG_CONFLICT', 'An existing NOETRA entry differs. Review it manually; it will not be overwritten.');
  return { target, beforeHash: before === null ? null : digest(before), entry,
    after: JSON.stringify({ ...config, mcpServers: { ...entries, noetra: entry } }, null, 2) + '\n' };
}
export async function applyJsonSetup(plan: SetupPlan): Promise<{ receipt: string; backup: string | null }> {
  const current = await existing(plan.target);
  if ((current === null ? null : digest(current)) !== plan.beforeHash) fail('CONFIG_CHANGED', 'Configuration changed after preview; generate a fresh plan.');
  await mkdir(dirname(plan.target), { recursive: true });
  const suffix = `noetra-${Date.now()}-${randomUUID()}`;
  const backup = current === null ? null : `${plan.target}.${suffix}.bak`;
  const receipt = `${plan.target}.${suffix}.receipt.json`;
  if (backup !== null) await writeFile(backup, current!, { flag: 'wx', mode: 0o600 });
  const temporary = `${plan.target}.${suffix}.tmp`;
  await writeFile(temporary, plan.after, { flag: 'wx', mode: 0o600 });
  const recheck = await existing(plan.target);
  if ((recheck === null ? null : digest(recheck)) !== plan.beforeHash) { await unlink(temporary); fail('CONFIG_CHANGED', 'Configuration changed during setup; no overwrite performed.'); }
  await writeFile(receipt, JSON.stringify({ target: plan.target, backup, beforeHash: plan.beforeHash, afterHash: digest(plan.after) }), { flag: 'wx', mode: 0o600 });
  await rename(temporary, plan.target);
  return { receipt, backup };
}
export async function rollbackJsonSetup(target: string, receiptPath: string): Promise<void> {
  const receipt = JSON.parse(await readFile(receiptPath, 'utf8')) as { target: string; backup: string | null; beforeHash: string | null; afterHash: string };
  if (resolve(receipt.target) !== resolve(target) || dirname(resolve(receiptPath)) !== dirname(resolve(target))) fail('INVALID_RECEIPT', 'Receipt does not match the selected client configuration.');
  const current = await existing(target);
  if (current === null || digest(current) !== receipt.afterHash) fail('ROLLBACK_CONFLICT', 'Client settings changed since setup; rollback refused to protect those changes.');
  if (receipt.backup === null) { await unlink(target); return; }
  if (dirname(resolve(receipt.backup)) !== dirname(resolve(target))) fail('INVALID_RECEIPT', 'Backup must be beside the selected configuration.');
  const before = await existing(receipt.backup);
  if (before === null || digest(before) !== receipt.beforeHash) fail('INVALID_BACKUP', 'Backup is missing or changed.');
  const temporary = `${target}.restore-${randomUUID()}.tmp`;
  await writeFile(temporary, before, { flag: 'wx', mode: 0o600 });
  await rename(temporary, target);
}
export function codexSnippet(cli: string, project: string): string {
  const entry = configurationEntry(cli, project);
  return `[mcp_servers.noetra]\ncommand = ${JSON.stringify(entry.command)}\nargs = ${JSON.stringify(entry.args)}\nstartup_timeout_sec = 20\ntool_timeout_sec = 90\n`;
}
