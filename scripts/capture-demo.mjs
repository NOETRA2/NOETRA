// Capture actual core output for a reproducible walkthrough. No generated
// values are substituted for engine results, and no user data is read.
import { runDemo } from '../dist/apps/demo/src/engine.js';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
const directory=process.argv[2];
if(!directory)throw new Error('Pass an output directory.');
const out=resolve(directory);await mkdir(out,{recursive:true});
const requests=[{example:'logic',lowerBound:2,claimBound:1},{example:'logic',lowerBound:2,claimBound:5},
  {example:'planning',testsPassed:false},{example:'planning',testsPassed:true},{example:'evidence'}];
const runs=[];
for(const request of requests)runs.push({request,response:await runDemo(request)});
if(runs.some(r=>!r.response.result.ok))throw new Error('A live example failed. Do not create a success walkthrough.');
await writeFile(resolve(out,'results.json'),JSON.stringify({format:'Actual NOETRA engine responses; not browser screenshots',runs},null,2)+'\n');
console.log(JSON.stringify({captured:runs.length,statuses:runs.map(r=>r.response.result.status)}));
