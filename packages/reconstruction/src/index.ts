import { spawn } from 'node:child_process';
import { readFile, lstat, realpath } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { isAbsolute, resolve } from 'node:path';
import { fail, success } from '../../shared-types/src/index.js';
import type { Result } from '../../shared-types/src/index.js';
import { ReconstructionConfig, reconstructionSchemas } from './schemas.js';
import type { ReconstructionTool } from './schemas.js';
export { ReconstructionConfig, reconstructionSchemas, reconstructionDescriptions, isReconstructionTool } from './schemas.js';
export async function readReconstructionConfig(path?: string): Promise<ReconstructionConfig | undefined> {
  if (!path) return undefined;
  const info=await lstat(path);
  if (!info.isFile() || info.isSymbolicLink() || info.size>16384) fail('RECONSTRUCTION_CONFIG','Use a small, regular, explicitly selected JSON configuration.');
  return ReconstructionConfig.parse(JSON.parse(await readFile(path,'utf8')));
}
export class ReconstructionBridge {
  readonly enabled: boolean;
  private readonly config?: ReconstructionConfig;
  constructor(config: ReconstructionConfig | undefined, private readonly root: string) {
    this.config=config ? ReconstructionConfig.parse(config) : undefined;
    this.enabled=!!config;
  }
  async call(name: ReconstructionTool, raw: unknown, signal?: AbortSignal): Promise<Result> {
    if (!this.config) fail('RECONSTRUCTION_DISABLED','The optional local reconstruction module is not configured. No dependencies are installed or images uploaded automatically.');
    const payload=reconstructionSchemas[name].parse(raw);
    signal?.throwIfAborted();
    const config=this.config;
    const visionOperation=['noetra.reconstruction_backends','noetra.reconstruct_photos','noetra.reconstruct_calibrated_views','noetra.refine_learned_surface'].includes(name);
    if(visionOperation&&!config.vision)fail('RECONSTRUCTION_VISION_NOT_CONFIGURED','Select the local vision environment and verified model/source manifests.');
    const python=visionOperation?config.vision!.pythonExecutable:config.pythonExecutable;
    for (const exe of [python,...(config.blenderExecutable ? [config.blenderExecutable] : [])]) {
      if (!isAbsolute(exe)) fail('RECONSTRUCTION_RUNTIME','An explicitly configured absolute runtime executable is required.');
      try { if (!(await lstat(exe)).isFile()) fail('RECONSTRUCTION_RUNTIME','Configured reconstruction runtime is not a regular executable file.'); }
      catch { fail('RECONSTRUCTION_RUNTIME','The configured local reconstruction runtime is unavailable. No automatic installation was attempted.'); }
    }
    const worker=fileURLToPath(new URL('../python/worker.py',import.meta.url));
    const env: NodeJS.ProcessEnv={};
    for(const key of ['SystemRoot','WINDIR','TEMP','TMP','PATH','LOCALAPPDATA']) if(process.env[key]) env[key]=process.env[key];
    const request=JSON.stringify({projectRoot:await realpath(resolve(this.root)),operation:name.replace('noetra.',''),payload,config});
    const answer=await new Promise<Record<string,unknown>>((done,reject)=>{
      const child=spawn(python,['-I','-B',worker],{cwd:this.root,env,windowsHide:true,shell:false,stdio:['pipe','pipe','pipe']});
      let stdout='',stderr='',settled=false;
      const finish=(error?: Error,value?: Record<string,unknown>)=>{
        if(settled)return;settled=true;clearTimeout(timer);signal?.removeEventListener('abort',cancel);
        if(error)reject(error);else done(value!);
      };
      const stop=()=>{
        if(child.pid && process.platform==='win32') {
          // Only this owned worker and its generated Blender child are terminated.
          const killer=spawn('taskkill.exe',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,shell:false,stdio:'ignore'});
          killer.on('error',()=>child.kill());
        }else child.kill('SIGKILL');
      };
      const cancel=()=>{stop();finish(new Error('RECONSTRUCTION_CANCELLED'));};
      const timer=setTimeout(()=>{stop();finish(new Error('RECONSTRUCTION_TIMEOUT'));},['noetra.reconstruct_photos','noetra.refine_learned_surface'].includes(name)?1200000:['noetra.repair_photo_surface','noetra.complete_from_prior','noetra.colorize_reconstruction','noetra.paint_surface_material','noetra.refine_base_surface','noetra.paint_appearance_preview'].includes(name)?600000:name==='noetra.correct_parts' ? 360000 : 180000);
      signal?.addEventListener('abort',cancel,{once:true});
      child.on('error',()=>finish(new Error('RECONSTRUCTION_RUNTIME_UNAVAILABLE')));
      child.stdout.on('data',(chunk:Buffer)=>{stdout+=chunk.toString();if(Buffer.byteLength(stdout)>262144){stop();finish(new Error('RECONSTRUCTION_OUTPUT_LIMIT'));}});
      child.stderr.on('data',(chunk:Buffer)=>{stderr=(stderr+chunk.toString()).slice(-8192);});
      child.on('close',code=>{
        if(settled)return;
        try {
          const value=JSON.parse(stdout) as Record<string,unknown>;
          if(code!==0 || value.ok!==true) {finish(new Error(typeof value.error==='string' ? value.error : 'RECONSTRUCTION_FAILED'));return;}
          finish(undefined,value);
        }catch {finish(new Error(stderr.includes('ModuleNotFoundError') ? 'RECONSTRUCTION_DEPENDENCY_MISSING' : 'RECONSTRUCTION_FAILED'));}
      });
      child.stdin.on('error',()=>{});child.stdin.end(request);
      if(signal?.aborted)cancel();
    }).catch(error=>{signal?.throwIfAborted();fail('RECONSTRUCTION_FAILED',error instanceof Error && /^RECONSTRUCTION_[A-Z_]+$/.test(error.message) ? error.message : 'The local reconstruction operation failed; inspect the local report.');});
    return success(answer,'OBSERVED',['This records execution and attributed/conditional geometry measurements, not verified hidden shape or universal reconstruction capability.',visionOperation?'Only operator-configured verified local models are used; no cloud upload or automatic model download is enabled.':'External models and generic generated-code execution are not enabled by this operation.']);
  }
}
