#!/usr/bin/env node
import { parseArgs } from 'node:util';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdir, writeFile, lstat, realpath, copyFile, constants } from 'node:fs/promises';
import { createInterface } from 'node:readline/promises';
import { serveStdio, StdioServerTransport } from '@modelcontextprotocol/server/stdio';
import { NoetraEngine } from '../../../packages/core/src/index.js';
import { createServer } from '../../../packages/mcp-server/src/index.js';
import { readReaConfig, integrationConfigPath, inspectPackage, validateRoot } from '../../../packages/integrations/rea/src/index.js';
import { VERSION, fail, NoetraError, supportedNode } from '../../../packages/shared-types/src/index.js';
import { applyJsonSetup, clientPath, codexSnippet, detectClients, planJsonSetup, rollbackJsonSetup } from './setup.js';
import type { ClientName } from './setup.js';
import { selfTest } from './self-test.js';
import { readReconstructionConfig } from '../../../packages/reconstruction/src/index.js';

const cliPath = fileURLToPath(import.meta.url);
const parsed = parseArgs({ allowPositionals: true, strict: true, options: {
  project: { type: 'string' }, client: { type: 'string' }, scope: { type: 'string' },
  apply: { type: 'boolean', default: false }, yes: { type: 'boolean', default: false },
  rollback: { type: 'string' }, package: { type: 'string' }, 'allow-root': { type: 'string', multiple: true },
  version: { type: 'boolean' }, help: { type: 'boolean' }, 'reconstruction-config': { type: 'string' },
  'ghidra-dir':{type:'string'},'java-home':{type:'string'}
} });
const command = parsed.positionals[0] ?? 'help';
const flags = parsed.values;
function output(value: unknown): void { process.stdout.write(JSON.stringify(value, null, 2) + '\n'); }

async function run(): Promise<void> {
  if (flags.version) { output({ name: 'NOETRA', version: VERSION }); return; }
  if (command === 'help' || flags.help) {
    process.stdout.write(`NOETRA ${VERSION} — standalone cognitive engine\n\nCommands:\n  setup [--client cursor|claude|codex] [--scope project|user]\n        [--apply --yes] [--rollback RECEIPT --yes]\n  doctor [--project PATH]\n  mcp [--project PATH]\n  integrations [rea --package DIRECTORY --allow-root DIRECTORY --apply --yes]\n  test\n\nNo other Nexa apps, global packages or model weights are installed.\nSetup previews changes by default. REA is optional. Codex registration is a manual snippet in this alpha.\n`); return;
  }
  if (!supportedNode()) fail('UNSUPPORTED_NODE', 'Use Node.js 24.11+ (24.x) or Node.js 26+.');
  const project = await realpath(resolve(flags.project ?? process.cwd()));
  if (!(await lstat(project)).isDirectory()) fail('INVALID_PROJECT', 'Project path must be an existing directory.');
  if (command === 'doctor') {
    const rea = await readReaConfig(integrationConfigPath(project));
    let reaIdentity: unknown = { enabled: false };
    if (rea) {
      try { const identity = await inspectPackage(rea.packageDirectory); reaIdentity = { enabled: true, version: identity.version, license: identity.license, allowedRootCount: rea.allowedRoots.length, liveConnection: 'not probed; use authorized investigation' }; }
      catch { reaIdentity = { enabled: true, available: false, reason: 'Package identity/path check failed.' }; }
    }
    output({ name: 'NOETRA', version: VERSION, node: process.version, nodeSupported: supportedNode(),
      project, clients: await detectClients(project), rea: reaIdentity, telemetry: false,
      independentPackage: true, otherNexaAppsRequired: false, defaultModelProvider: 'none',
      sqlite: 'Node built-in; checked by noetra test', limits: { concurrentRequests: 2, solverWallMs: 10000, reaWallMs: 60000 },
      limitations: ['Alpha release; no AI-host UI connection verified by this command.', 'No automatic installers for optional REA/Python/browser/native-analysis dependencies.'] });
    return;
  }
  if (command === 'mcp') {
    const rea = await readReaConfig(integrationConfigPath(project));
    const reconstruction=await readReconstructionConfig(flags['reconstruction-config'] ? resolve(flags['reconstruction-config']) : undefined);
    const engine = new NoetraEngine({ projectRoot: project, rea, reconstruction });
    const transport = new StdioServerTransport(process.stdin, process.stdout, { maxBufferSize: 512 * 1024 });
    const handle = serveStdio(() => createServer(engine), { transport, onerror: () => { process.stderr.write('NOETRA_PROTOCOL_ERROR\n'); } });
    const shutdown = async (): Promise<void> => {
      await handle.close();
      // Cancellation signals unwind in-flight integration/solver work before memory is closed.
      for (let attempt = 0; attempt < 100; attempt++) {
        try { engine.close(); return; } catch (error) {
          if (!(error instanceof NoetraError) || error.code !== 'ENGINE_BUSY') throw error;
          await new Promise<void>(resolveWait => setTimeout(resolveWait, 25));
        }
      }
    };
    process.stdin.once('end', () => { void shutdown(); });
    process.once('SIGINT', () => { void shutdown(); });
    process.once('SIGTERM', () => { void shutdown(); });
    return;
  }
  if (command === 'test') { output(await selfTest(cliPath)); return; }
  if (command === 'setup') {
    let client = flags.client;
    if (!client && process.stdin.isTTY) {
      output({ detectedConfigurations: await detectClients(project), choices: ['cursor', 'claude', 'codex'] });
      const prompt = createInterface({ input: process.stdin, output: process.stdout });
      try { client = (await prompt.question('Choose client (cursor/claude/codex): ')).trim(); } finally { prompt.close(); }
    }
    if (!client) { output({ detectedConfigurations: await detectClients(project), next: 'Run setup --client cursor|claude|codex. No settings changed.' }); return; }
    if (!['cursor', 'claude', 'codex'].includes(client)) fail('INVALID_CLIENT', 'Choose cursor, claude or codex.');
    const scope = flags.scope ?? 'project';
    if (scope !== 'project' && scope !== 'user') fail('INVALID_SCOPE', 'Choose project or user scope.');
    const target = clientPath(client as ClientName, project, scope);
    if (client === 'codex') {
      if (flags.apply || flags.rollback) fail('MANUAL_CODEX_SETUP', 'Automatic Codex TOML editing is not supported in this alpha; review the emitted snippet manually.');
      output({ target, snippet: codexSnippet(cliPath, project), applied: false,
        instruction: 'Review and add this new server table only if no NOETRA entry already exists, then reconnect your agent. Existing REA settings must stay unchanged.' }); return;
    }
    if (flags.rollback) {
      if (!flags.yes) fail('CONFIRMATION_REQUIRED', 'Rollback requires --yes. It will refuse if settings changed since setup.');
      await rollbackJsonSetup(target, resolve(flags.rollback)); output({ rolledBack: true, target }); return;
    }
    const plan = await planJsonSetup(target, cliPath, project);
    output({ target, entry: plan.entry, existingConfigurationDigest: plan.beforeHash, action: 'Add only mcpServers.noetra; preserve other entries.', applied: false });
    if (!flags.apply) return;
    if (!flags.yes) fail('CONFIRMATION_REQUIRED', 'Review the setup preview, then explicitly rerun with --apply --yes.');
    output({ connectionCheck: await selfTest(cliPath) });
    output({ applied: true, ...(await applyJsonSetup(plan)), next: 'Reconnect/restart your AI host. This verifies the protocol, not the host UI connection.' }); return;
  }
  if (command === 'integrations') {
    const path = integrationConfigPath(project);
    if (parsed.positionals[1] !== 'rea') {
      const existing=await readReaConfig(path);
      output({ rea: existing ? 'configured; integrated lazy connection' : 'not configured',
        ghidra:existing?.ghidra?'configured native provider':'not configured',
        reconstruction:'Available through the separately selected local reconstruction config',
        note: 'No optional integrations are downloaded automatically. Reuse a reviewed official rea-agents 6.7.0 installation.' }); return;
    }
    if (!flags.package || !flags['allow-root']?.length) fail('CONFIG_REQUIRED', 'Specify --package (official installed package folder) and at least one --allow-root.');
    const identity = await inspectPackage(resolve(flags.package));
    const previous=await readReaConfig(path);
    if(!!flags['ghidra-dir']!==!!flags['java-home'])fail('CONFIG_REQUIRED','Supply both --ghidra-dir and --java-home.');
    const ghidra=flags['ghidra-dir']?{
      installDirectory:await realpath(resolve(flags['ghidra-dir'])),javaHome:await realpath(resolve(flags['java-home']!))
    }:previous?.ghidra;
    if(ghidra){
      for(const folder of [ghidra.installDirectory,ghidra.javaHome])if(!(await lstat(folder)).isDirectory())fail('CONFIG_REQUIRED','Ghidra and Java must select existing directories.');
    }
    const config = { enabled: true, packageDirectory: identity.root, allowedRoots: await Promise.all(flags['allow-root'].map(validateRoot)), version: identity.version,...(ghidra?{ghidra}:{}) };
    output({ path, planned: config, applied: false, note: 'Reuses the approved existing installation. No download, global registration or target execution.' });
    if (!flags.apply) return;
    if (!flags.yes) fail('CONFIRMATION_REQUIRED', 'Enabling integration requires --apply --yes.');
    await mkdir(dirname(path), { recursive: true, mode: 0o700 });
    try { await lstat(path); await copyFile(path, `${path}.${Date.now()}.bak`, constants.COPYFILE_EXCL); } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
    await writeFile(path, JSON.stringify(config, null, 2) + '\n', { mode: 0o600 }); output({ applied: true, path }); return;
  }
  fail('UNKNOWN_COMMAND', 'Unknown command. Run noetra help.');
}
void run().catch(error => {
  process.stderr.write(JSON.stringify({ ok: false, code: error instanceof NoetraError ? error.code : 'COMMAND_FAILED',
    message: error instanceof NoetraError ? error.message : 'Command failed; check local paths, permissions and configuration.' }) + '\n');
  process.exitCode = 1;
});
