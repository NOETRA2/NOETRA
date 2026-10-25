import { cp, mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const target=process.argv[2];
if(!target)throw new Error('Pass a new, dedicated output folder.');
const out=resolve(target);
await mkdir(out,{recursive:false});
for(const name of ['dist/apps','dist/packages','package.json','package-lock.json','LICENSE','THIRD_PARTY_NOTICES.md'])
  await cp(resolve(root,name),resolve(out,name),{recursive:true});
// Workspaces/dev tools/lifecycle hooks are only needed to build the source.
// Keep the lock's runtime dependencies intact; no source build occurs in Space.
const pkg=JSON.parse(await readFile(resolve(out,'package.json'),'utf8'));
delete pkg.workspaces;delete pkg.scripts;delete pkg.devDependencies;
await writeFile(resolve(out,'package.json'),JSON.stringify(pkg,null,2)+'\n');
await cp(resolve(root,'deploy/huggingface/Dockerfile'),resolve(out,'Dockerfile'));
await cp(resolve(root,'deploy/huggingface/README.md'),resolve(out,'README.md'));
console.log(JSON.stringify({prepared:true,published:false,directory:out,gpuRequired:false}));
