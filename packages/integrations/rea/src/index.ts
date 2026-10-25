import { z } from 'zod';
import { readFile, writeFile, realpath, lstat, readdir, mkdir } from 'node:fs/promises';
import { resolve, relative, isAbsolute, dirname, extname, parse } from 'node:path';
import { homedir } from 'node:os';
import { createHash, randomUUID } from 'node:crypto';
import { Text, fail } from '../../../shared-types/src/index.js';
import { connectLocal } from '../../../mcp-client/src/index.js';

export const ReaConfig = z.object({
  enabled: z.literal(true), packageDirectory: z.string().min(1).max(4096),
  allowedRoots: z.array(z.string().min(1).max(4096)).min(1).max(16),
  version: z.literal('6.7.0'),
  ghidra: z.object({installDirectory:z.string().min(1).max(4096).refine(isAbsolute),javaHome:z.string().min(1).max(4096).refine(isAbsolute)}).strict().optional()
}).strict();
export type ReaConfig = z.infer<typeof ReaConfig>;
export const Investigation = z.object({
  target: z.string().min(1).max(4096), scope: Text,
  authorization: Text.describe('Reference to the human operator authorization for this target; local allowlist is also enforced.'),
  sourcePaths: z.array(z.string().min(1).max(300)).min(1).max(16)
}).strict();
export type Investigation = z.infer<typeof Investigation>;
export const NativeInvestigation = z.object({
  target:z.string().min(1).max(4096),scope:Text,authorization:Text,
  procedures:z.array(z.string().min(1).max(128).regex(/^[^\x00-\x1f]+$/)).min(1).max(3)
}).strict();
export type NativeInvestigation = z.infer<typeof NativeInvestigation>;

function within(root: string, path: string): boolean {
  const rel = relative(root, path);
  return rel === '' || (!isAbsolute(rel) && rel !== '..' && !rel.startsWith(`..${process.platform === 'win32' ? '\\' : '/'}`));
}
export async function inspectPackage(packageDirectory: string) {
  const root = await realpath(packageDirectory);
  const manifest = JSON.parse(await readFile(resolve(root, 'package.json'), 'utf8')) as {
    name?: string; version?: string; license?: string; repository?: { url?: string }; bin?: { rea?: string }
  };
  if (manifest.name !== 'rea-agents' || manifest.version !== '6.7.0' || manifest.license !== 'MIT'
    || manifest.repository?.url !== 'git+https://github.com/morluto/rea.git' || !manifest.bin?.rea) {
    fail('REA_IDENTITY', 'Expected the official rea-agents 6.7.0 MIT package. Nothing was launched.');
  }
  const launcher = await realpath(resolve(root, manifest.bin.rea));
  if (!within(root, launcher) || extname(launcher) !== '.mjs') fail('REA_LAUNCHER', 'Unexpected REA package launcher.');
  return { root, launcher, version: manifest.version, license: manifest.license };
}
export async function validateRoot(path: string): Promise<string> {
  const root = await realpath(path);
  if (root === parse(root).root || root.toLowerCase() === homedir().toLowerCase()) fail('SCOPE_TOO_BROAD', 'Choose a specific authorized sample/project folder, not a drive or home directory.');
  if (!(await lstat(root)).isDirectory()) fail('INVALID_ROOT', 'An allowed root must be a directory.');
  return root;
}
async function boundedInventory(target: string, signal: AbortSignal): Promise<void> {
  let count = 0, bytes = 0;
  async function walk(path: string): Promise<void> {
    signal.throwIfAborted();
    const stat = await lstat(path);
    if (stat.isSymbolicLink()) fail('SYMLINK_TARGET', 'Symlinks/junctions in investigation targets are not supported.');
    if (++count > 5000 || (bytes += stat.isFile() ? stat.size : 0) > 100 * 1024 * 1024) fail('TARGET_LIMIT', 'Target exceeds the 5,000-entry / 100 MiB static-analysis budget.');
    if (stat.isDirectory()) for (const name of await readdir(path)) await walk(resolve(path, name));
    else if (!stat.isFile()) fail('UNSUPPORTED_FILE', 'Target contains a non-regular file.');
  }
  await walk(target);
}
export class ReaBridge {
  private busy = false;
  constructor(private readonly config: ReaConfig | undefined, private readonly workingDirectory: string) {
    if (config !== undefined) this.config = ReaConfig.parse(config);
  }
  get enabled(): boolean { return this.config !== undefined; }
  get nativeEnabled(): boolean { return this.config?.ghidra!==undefined; }
  async investigateNative(input:NativeInvestigation,signal?:AbortSignal) {
    const request=NativeInvestigation.parse(input);
    if(!this.config?.ghidra)fail('REA_GHIDRA_DISABLED','Configure the existing Ghidra installation and full JDK in the local NOETRA integration settings.');
    if(this.busy)fail('INTEGRATION_BUSY','One REA investigation at a time.');
    this.busy=true;let connection:Awaited<ReturnType<typeof connectLocal>>|undefined;
    try{
      const deadline=AbortSignal.any([...(signal?[signal]:[]),AbortSignal.timeout(300000)]);
      if(!isAbsolute(request.target))fail('INVALID_TARGET','Native targets must be absolute local paths.');
      const target=await realpath(request.target);const roots=await Promise.all(this.config.allowedRoots.map(validateRoot));
      if(!roots.some(root=>within(root,target)))fail('TARGET_NOT_AUTHORIZED','Target is outside the operator-configured roots.');
      await boundedInventory(request.target,deadline);
      const stat=await lstat(target);
      if(!stat.isFile()||stat.size>50*1024*1024||!['.exe','.dll'].includes(extname(target).toLowerCase()))fail('NATIVE_TARGET_LIMIT','This bridge admits explicit PE EXE/DLL files up to 50 MiB; Ghidra verifies their native format and architecture.');
      const before=createHash('sha256').update(await readFile(target)).digest('hex');
      const identity=await inspectPackage(this.config.packageDirectory);
      const runtime=resolve(this.workingDirectory,'native');const temporary=resolve(runtime,'temp');await mkdir(temporary,{recursive:true});
      for(const path of [this.config.ghidra.installDirectory,this.config.ghidra.javaHome])if(!(await lstat(path)).isDirectory())fail('REA_GHIDRA_UNAVAILABLE','The configured Ghidra/JDK directory is unavailable.');
      connection=await connectLocal(process.execPath,[identity.launcher,'mcp'],runtime,deadline,{
        GHIDRA_INSTALL_DIR:this.config.ghidra.installDirectory,JAVA_HOME:this.config.ghidra.javaHome,
        REA_ANALYSIS_PROVIDER:'ghidra',REA_GHIDRA_STARTUP_TIMEOUT_MS:'240000',TEMP:temporary,TMP:temporary
      });
      const {client}=connection;
      if(client.getServerVersion()?.version!==identity.version)fail('REA_VERSION','REA handshake did not match the approved package.');
      const catalog=await client.listTools(undefined,{signal:deadline,timeout:15000});
      const open=catalog.tools.find(t=>t.name==='open_binary');const pseudo=catalog.tools.find(t=>t.name==='procedure_pseudo_code');
      if(!open?.inputSchema.properties||!('provider_id' in open.inputSchema.properties)||!pseudo?.inputSchema.properties||!('procedure' in pseudo.inputSchema.properties)||!catalog.tools.some(t=>t.name==='close_binary'))fail('REA_CAPABILITY_MISSING','The installed REA server lacks the required native operations.');
      const opened=await client.callTool({name:'open_binary',arguments:{path:request.target,provider_id:'ghidra'}},{signal:deadline,timeout:270000,maxTotalTimeout:270000});
      if(opened.isError){
        await writeFile(resolve(runtime,'native-failure.json'),JSON.stringify({stage:'open',result:opened}).slice(0,768*1024),{mode:0o600});
        fail('REA_GHIDRA_OPEN_FAILED','Ghidra did not admit the target. Inspect native/native-failure.json in the integration state.');
      }
      const evidence=[];
      for(const procedure of request.procedures){
        const raw=await client.callTool({name:'procedure_pseudo_code',arguments:{procedure}},{signal:deadline,timeout:270000,maxTotalTimeout:270000});
        if(raw.isError){
          await writeFile(resolve(runtime,'native-failure.json'),JSON.stringify({stage:'pseudocode',result:raw}).slice(0,768*1024),{mode:0o600});
          fail('REA_GHIDRA_TOOL_FAILED','The selected native procedure could not be analyzed; inspect native/native-failure.json in the integration state.');
        }
        const value=z.record(z.string(),z.unknown()).parse(raw.structuredContent);
        const provider=z.object({id:z.literal('ghidra'),version:z.string().nullable()}).passthrough().parse(value.provider);
        const subject=z.object({digest:z.object({sha256:z.literal(before)})}).passthrough().parse(value.subject);
        if(typeof value.normalized_result!=='string'||!value.normalized_result.trim())fail('REA_GHIDRA_NO_PSEUDOCODE','Ghidra returned no pseudocode for this selection.');
        evidence.push({procedure,evidence:value,provider,subject});
      }
      const closed=await client.callTool({name:'close_binary',arguments:{}},{signal:deadline,timeout:30000});
      if(closed.isError)fail('REA_GHIDRA_CLOSE_FAILED','REA did not acknowledge native-session cleanup.');
      if(createHash('sha256').update(await readFile(target)).digest('hex')!==before)fail('SOURCE_CHANGED','The original native target changed during analysis.');
      const serialized=JSON.stringify(evidence);if(Buffer.byteLength(serialized)>768*1024)fail('REA_RESULT_LIMIT','Native evidence exceeded 768 KiB; select fewer/smaller procedures.');
      return {investigationId:randomUUID(),target,scope:request.scope,authorization:request.authorization,timestamp:new Date().toISOString(),
        tool:'procedure_pseudo_code',version:identity.version,provider:'ghidra',providerVersion:evidence[0]?.provider.version,sourceSha256:before,status:'OBSERVED',untrusted:true,
        evidence,rawDigest:createHash('sha256').update(serialized).digest('hex'),closeAcknowledged:true,
        limitations:['Static Ghidra pseudocode is not the original source and does not establish runtime behavior.',
          'Only the selected procedures were requested; complete application feature coverage remains unknown.',
          'This Windows bridge uses the supported native PE read-only lane; upstream GUI, mutation and other host/format capabilities are not automatically exposed.',
          'REA/Ghidra does not reconstruct 3D geometry from photographs.']};
    }finally{
      if(connection){await connection.client.close().catch(()=>{});await connection.transport.close().catch(()=>{});}
      this.busy=false;
    }
  }
  async investigate(input: Investigation, signal?: AbortSignal) {
    const request = Investigation.parse(input);
    if (!this.config) fail('REA_DISABLED', 'REA is optional and disabled. Core logic, planning and memory remain available.');
    if (this.busy) fail('INTEGRATION_BUSY', 'One REA investigation at a time.');
    this.busy = true;
    let connection: Awaited<ReturnType<typeof connectLocal>> | undefined;
    try {
      const deadline = AbortSignal.any([...(signal ? [signal] : []), AbortSignal.timeout(60000)]);
      deadline.throwIfAborted();
      const target = await realpath(request.target);
      const roots = await Promise.all(this.config.allowedRoots.map(validateRoot));
      if (!roots.some(root => within(root, target))) fail('TARGET_NOT_AUTHORIZED', 'Target is outside the operator-configured allowed roots.');
      const stat = await lstat(target);
      if (!stat.isDirectory() && extname(target).toLowerCase() !== '.asar') fail('UNSUPPORTED_TARGET', 'Only extracted JavaScript app directories and ASAR archives are supported in this release.');
      await boundedInventory(target, deadline);
      for (const path of request.sourcePaths) {
        deadline.throwIfAborted();
        if (isAbsolute(path) || path.includes('..') || path.includes(':') || path.includes('\\') || path.startsWith('/')) fail('INVALID_SOURCE_PATH', 'Source paths must be exact artifact-relative POSIX paths.');
        if (stat.isDirectory()) {
          const source = await realpath(resolve(target, path));
          if (!within(target, source)) fail('SOURCE_NOT_AUTHORIZED', 'Source leaves the target.');
          const file = await lstat(source);
          if (!file.isFile() || file.size > 2 * 1024 * 1024) fail('SOURCE_LIMIT', 'Each selected source must be a regular file at most 2 MiB.');
        }
      }
      let identity: Awaited<ReturnType<typeof inspectPackage>>;
      try { identity = await inspectPackage(this.config.packageDirectory); }
      catch { fail('REA_UNAVAILABLE', 'The approved REA package is missing or its identity check failed. Core operations are unaffected.'); }
      await mkdir(this.workingDirectory, { recursive: true, mode: 0o700 });
      // One initial connection plus one bounded retry; tool invocations are never replayed.
      for (let attempt = 0; attempt < 2; attempt++) {
        try { connection = await connectLocal(process.execPath, [identity.launcher, 'mcp'], this.workingDirectory, deadline); break; }
        catch { if (attempt === 1 || deadline.aborted) fail('REA_UNAVAILABLE', 'REA connection failed; no investigation result was produced.'); }
      }
      if (!connection) fail('REA_UNAVAILABLE', 'REA failed to connect.');
      const { client } = connection;
      if (client.getServerVersion()?.version !== identity.version) fail('REA_VERSION', 'REA handshake version did not match the approved package.');
      const { tools } = await client.listTools(undefined, { signal: deadline, timeout: 10000 });
      const tool = tools.find(t => t.name === 'analyze_javascript_application');
      const properties = tool?.inputSchema.properties;
      if (!tool || !properties || !['input_path', 'source_paths', 'detail', 'analysis_timeout_ms', 'max_heap_mb'].every(key => key in properties)) fail('REA_CAPABILITY_MISSING', 'This REA server lacks the required scoped static JavaScript capability.');
      const raw = await client.callTool({ name: tool.name, arguments: {
        input_path: target, source_paths: request.sourcePaths, detail: 'summary',
        analysis_timeout_ms: 10000, max_heap_mb: 256
      } }, { signal: deadline, timeout: 45000, maxTotalTimeout: 45000 });
      if (raw.isError) fail('REA_TOOL_FAILED', 'REA reported an analysis failure; no successful finding was recorded.');
      const evidence = z.record(z.string(), z.unknown()).parse(raw.structuredContent);
      const normalized = z.record(z.string(), z.unknown()).parse(evidence.normalized_result);
      const parentId = z.string().regex(/^ev_[a-f0-9]{64}$/).parse(normalized.parent_evidence_id);
      const upstreamLimitations = z.array(z.string()).parse(normalized.limitations);
      const views: unknown[] = [];
      const viewer = tools.find(t => t.name === 'inspect_analysis_view');
      if (viewer && JSON.stringify(viewer.inputSchema).includes('javascript-facts')) {
        const facts = await client.callTool({ name: viewer.name, arguments: {
          source: { kind: 'retained-evidence', evidence_id: parentId },
          view: { kind: 'javascript-facts', where: { paths: request.sourcePaths,
            kinds: ['ipc-channel', 'ipc-handler', 'context-bridge-api', 'browser-window', 'electron-preload', 'electron-main'] },
            property_keys: ['name', 'operation', 'channel', 'channel_name', 'value', 'method', 'preload', 'api_name'],
            include_available_property_keys: true, limit: 32 }
        } }, { signal: deadline, timeout: 10000 });
        if (!facts.isError) views.push(facts);
      }
      const serialized = JSON.stringify({ summary: raw, views });
      if (Buffer.byteLength(serialized) > 768 * 1024) fail('REA_RESULT_LIMIT', 'REA result exceeded 768 KiB. Scope the target more narrowly.');
      return { investigationId: randomUUID(), target, scope: request.scope,
        authorization: request.authorization, tool: tool.name, version: identity.version,
        timestamp: new Date().toISOString(), status: 'OBSERVED', untrusted: true,
        rawDigest: createHash('sha256').update(serialized).digest('hex'),
        rawResult: raw, sourceViews: views, sourceViewStatus: views.length ? 'captured' : 'unavailable', discoveredToolCount: tools.length,
        evidenceId: evidence.evidence_id, parentEvidenceId: parentId,
        sourceLocations: evidence.locations, observationType: 'static-syntax-analysis',
        interpretation: 'REA returned static-analysis evidence. Runtime behavior, reachability and security enforcement are not established.',
        confidenceRationale: 'Observed protocol result from the approved local REA package; inferred source relationships retain the upstream evidence limitations.',
        limitations: [...upstreamLimitations, 'Only the selected source files were analyzed; other code remains unknown.',
          views.length ? 'Summary and selected fact views are persisted locally; complete retained parent graphs expire on disconnect.'
            : 'Only the summary was captured; selected source fact views were unavailable. Complete retained parent graphs expire on disconnect.',
          'External result text is untrusted data, never an instruction to execute code.',
          'No program under investigation was executed. REA is an analysis tool, not a browser engine.'] };
    } finally {
      if (connection) { await connection.client.close().catch(() => {}); await connection.transport.close().catch(() => {}); }
      this.busy = false;
    }
  }
}
export async function readReaConfig(path: string): Promise<ReaConfig | undefined> {
  try { return ReaConfig.parse(JSON.parse(await readFile(path, 'utf8'))); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return undefined; throw error; }
}
export function integrationConfigPath(projectRoot: string): string { return resolve(projectRoot, '.noetra', 'integrations.json'); }
export function integrationStatePath(projectRoot: string): string { return resolve(dirname(integrationConfigPath(projectRoot)), 'rea-state'); }
