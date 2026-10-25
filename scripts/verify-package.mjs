// Smoke-test the packed public artifact in a fresh installation, not this
// repository's workspace. No publication, global install or user config edits.
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';
import assert from 'node:assert/strict';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const destination=await mkdtemp(join(tmpdir(),'noetra-package-'));
const pkg=JSON.parse(await readFile(join(root,'package.json'),'utf8'));
function run(command,args,cwd,extra={}) {
  return new Promise((resolveRun,reject)=>{
    const p=spawn(command,args,{cwd,shell:false,windowsHide:true,env:{...process.env,...extra},stdio:['ignore','pipe','pipe']});
    let out='',err='';p.stdout.on('data',c=>out+=c);p.stderr.on('data',c=>err+=c);
    p.once('error',reject);p.once('exit',code=>code===0?resolveRun(out):reject(new Error(`${command} failed (${code}): ${err.slice(-2500)}`)));
  });
}
const npmCli=process.env.npm_execpath;
if(!npmCli)throw new Error('Run with npm run test:package so the current npm CLI is used without a shell.');
const npm=(args,cwd=root)=>run(process.execPath,[npmCli,...args],cwd);
await npm(['run','build']);
const packed=JSON.parse(await npm(['pack','--ignore-scripts','--json','--pack-destination',destination]));
const manifest=packed[0];
assert(manifest.files.some(f=>f.path==='dist/packages/logic/src/solver-worker.js'));
assert(manifest.files.some(f=>f.path==='dist/apps/demo/public/index.html'));
assert(manifest.files.some(f=>f.path==='server.json'));
assert(manifest.files.every(f=>!/(^|\/)(?:\.tools|\.noetra|__pycache__|\.env)(?:\/|$)|\.(?:safetensors|onnx|pth|sqlite|pyc)$/.test(f.path)));
const installed=join(destination,'installed');await mkdir(installed);
await npm(['install','--prefix',installed,'--ignore-scripts','--omit=dev','--no-audit','--no-fund',join(destination,manifest.filename)]);
const cli=join(installed,'node_modules',pkg.name,'dist/apps/cli/src/index.js');
const project=join(destination,'project');await mkdir(project);
const cliRun=args=>run(process.execPath,[cli,...args],project);
assert.equal(JSON.parse(await cliRun(['--version'])).version,pkg.version);
assert.equal(JSON.parse(await cliRun(['test'])).formalSolver,'passed');
// Test real safe registration against an isolated fixture, including preservation
// of an unrelated REA entry and exact rollback. Never use actual client settings.
const configDir=join(project,'.cursor');await mkdir(configDir);
const config=join(configDir,'mcp.json');
const original=JSON.stringify({mcpServers:{rea:{command:'keep-existing-rea'}},fixture:true});
await writeFile(config,original);
const preview=JSON.parse(await cliRun(['setup','--client','cursor']));assert.equal(preview.applied,false);
assert.equal(await readFile(config,'utf8'),original);
const applied=await cliRun(['setup','--client','cursor','--apply','--yes']);
// CLI emits multiple JSON objects; find only the final object without eval.
const receiptLine=applied.lastIndexOf('\n{');const receipt=JSON.parse(applied.slice(receiptLine+1));
assert.equal(JSON.parse(await readFile(config,'utf8')).mcpServers.rea.command,'keep-existing-rea');
await cliRun(['setup','--client','cursor','--rollback',receipt.receipt,'--yes']);
assert.equal(await readFile(config,'utf8'),original);
const space=JSON.parse(await readFile(join(root,'server.json'),'utf8'));
assert.equal(space.name,pkg.mcpName);assert.equal(space.version,pkg.version);
assert.equal(space.packages[0].identifier,pkg.name);assert.equal(space.packages[0].version,pkg.version);
assert(space.description.length<=100);
const result={ok:true,version:pkg.version,packedFiles:manifest.files.length,tarball:manifest.filename,tarballBytes:manifest.size,
  freshInstall:true,mcpAndSolver:true,setupPreview:true,otherServerPreserved:true,exactRollback:true,registryMetadataConsistent:true,published:false,artifacts:destination};
await writeFile(join(destination,'verification.json'),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result,null,2));
