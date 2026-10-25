/** Explicit public-data fixture download, never called by the core/MCP worker. */
import { mkdir, writeFile, lstat } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
const destination=resolve(process.argv[2] ?? '');
if(!process.argv[2]) throw Error('Supply a new explicit fixture directory.');
try{await lstat(destination);throw Error('Refusing an existing fixture directory.');}catch(e){if(e.code!=='ENOENT')throw e;}
await mkdir(destination,{recursive:true});
const base='https://raw.githubusercontent.com/opencv/opencv/4.x/';
const names=[1,2,3,4,5,6,7,8,9,11,12,13,14].flatMap(n=>['left','right'].map(side=>`samples/data/${side}${String(n).padStart(2,'0')}.jpg`));
names.push('LICENSE');const results=[];
for(let at=0;at<names.length;at+=4)await Promise.all(names.slice(at,at+4).map(async name=>{
  const url=base+name;const response=await fetch(url,{signal:AbortSignal.timeout(30000),redirect:'error'});
  if(!response.ok)throw Error(`Official fixture fetch failed: ${name} ${response.status}`);
  const data=Buffer.from(await response.arrayBuffer());if(data.length>4*1024*1024)throw Error('Fixture size limit.');
  const filename=name.split('/').at(-1);await writeFile(resolve(destination,filename),data,{flag:'wx'});
  results.push({filename,url,bytes:data.length,sha256:createHash('sha256').update(data).digest('hex')});
}));
await writeFile(resolve(destination,'sources.json'),JSON.stringify({downloadedAt:new Date().toISOString(),source:'Official OpenCV stereo calibration sample photographs; originals preserved unchanged.',license:'See accompanying upstream LICENSE; fixture not bundled into NOETRA core.',files:results.sort((a,b)=>a.filename.localeCompare(b.filename))},null,2));
console.log(JSON.stringify({destination,files:results.length,bytes:results.reduce((sum,f)=>sum+f.bytes,0)}));
