import { NoetraEngine } from 'noetra';
import { readFile, writeFile, mkdir, copyFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here=dirname(fileURLToPath(import.meta.url));
const folder=resolve(here,'../../../output/noetra-sports-car-comparison-20261024');
const baseline=resolve(folder,'baseline'), next=resolve(folder,'with-noetra');
await mkdir(next,{recursive:true});
const metrics=JSON.parse(await readFile(resolve(baseline,'metrics.json'),'utf8'));
const audit=JSON.parse(await readFile(resolve(baseline,'geometry-audit.json'),'utf8'));
const hashes={};
for(const name of ['concept.png','front.png','rear.png','sports-car.blend','sports-car.glb','metrics.json']) {
  hashes[name]=createHash('sha256').update(await readFile(resolve(baseline,name))).digest('hex');
}
await writeFile(resolve(folder,'baseline-freeze.json'),JSON.stringify({frozenBeforeNoetraDesignCalls:new Date().toISOString(),hashes},null,2)+'\n');
await copyFile(resolve(here,'build_car.py'),resolve(baseline,'build_car-frozen.py'));
await copyFile(resolve(here,'baseline-parameters.json'),resolve(baseline,'parameters.json'));

const engine=new NoetraEngine({projectRoot:folder,projectId:'sports-car-single-case-demo'});
const calls=[];
async function call(name,input){
  const start=performance.now();
  const result=await engine.call(name,input);
  calls.push({name,input,result,elapsedMs:Math.round(performance.now()-start)});
  if(!result.ok)throw new Error(`${name}: ${result.error?.code}`);
  return result;
}
const origin={kind:'host-model',reference:'Host-generated interpretations/candidates for the same human brief, not empirical vehicle engineering facts.',timestamp:new Date().toISOString()};
const c=(id,variable,value,relation='eq')=>({id,terms:[{variable,coefficient:1}],relation,value});
try{
  await call('noetra.analyze_problem',{text:'Design the same futuristic two-seat sports coupe, keeping the frozen visual identity, four tires, wheelbase, modelling budget and studio presentation. Check measurable consistency; do not claim subjective superiority.',
    hypotheses:['Decorative overhangs extend the total geometry beyond the chosen length/width targets.','Surface fitting may reduce floating trim without redesigning the car.']});
  const evidence=await call('noetra.record_evidence',{claim:'Baseline evaluated geometry measurements',
    origin:{kind:'tool',reference:'Blender 5.2.2 evaluated mesh metrics and read-only nearest-surface audit, preserved with frozen baseline SHA-256 hashes.',timestamp:new Date().toISOString()},
    method:'Read baseline metrics and read-only audit after the baseline was completed without NOETRA.',
    observation:JSON.stringify({metrics,trimDistances:audit.trim_distances}),
    limitations:['A modelling target is not a user-mandated engineering constraint.','Unsigned distance is not proof of collision-free geometry.','NOETRA receives measurements from Blender; it does not inspect pixels or generate geometry itself.']});
  const evidenceId=evidence.data.record.id;
  const [length,width,height]=metrics.vehicle_bounds_excluding_mirrors.dimensions.map(x=>Math.round(x*1000));
  const wheelbase=Math.round(Math.abs(metrics.wheels[2].center[0]-metrics.wheels[0].center[0])*1000);
  await call('noetra.build_world_model',{world:{goal:'Preserve the car design while improving agreement with the author-chosen geometric envelope.',
    entities:[{id:'car',type:'visual-concept',properties:{lengthMm:length,widthMm:width,heightMm:height,wheelbaseMm:wheelbase}},{id:'trim',type:'decorative-geometry',properties:{surfaceAttachment:'measured by Blender; inspect actual audit'}}],
    relations:[{from:'trim',to:'car',kind:'decorates',evidenceIds:[evidenceId]}],
    unknowns:['Aesthetic appeal, aerodynamics, occupant packaging and manufacturing feasibility are unverified.','No roadworthy or CAD certification.'],
    assertions:[{id:'actual-measurement',proposition:`Actual baseline envelope is ${length} x ${width} x ${height} millimetres.`,classification:'premise',origin:{kind:'tool',reference:evidenceId,timestamp:new Date().toISOString()},evidenceIds:[evidenceId]}]}});
  const premises=[c('observed-length','length_mm',length),c('observed-width','width_mm',width),c('observed-wheelbase','wheelbase_mm',wheelbase)];
  await call('noetra.verify_claim',{premises,claim:c('fits-chosen-length-target','length_mm',4600,'le')});
  await call('noetra.verify_claim',{premises,claim:c('fits-chosen-width-target','width_mm',2000,'le')});
  await call('noetra.verify_claim',{premises,claim:c('wheelbase-matches-target','wheelbase_mm',2700)});
  const common={origin,risks:['Requires re-export, identical-camera renders and independent mesh measurements.'],testPlan:['Measure geometry after rebuilding.','Confirm wheelbase and tire dimensions remain unchanged.','Compare trim distances and inspect the actual renders.']};
  const ranked=await call('noetra.explore_possibilities',{requirements:['same-identity','same-wheelbase','same-tire-size','same-budget','closer-envelope'],maxCost:5,candidates:[
    {...common,id:'local-trim-fit',concept:'Keep main body, cockpit, wheels and light design; fit existing trim to its surface and bound decorative overhangs within the chosen envelope.',components:['Existing loft body','Existing wheels','Surface-fitted trim','Bounded aero appendages'],satisfies:['same-identity','same-wheelbase','same-tire-size','same-budget','closer-envelope'],estimatedCost:2},
    {...common,id:'whole-model-scale',concept:'Scale the whole model to the target envelope.',components:['Global object scale'],satisfies:['same-identity','same-budget','closer-envelope'],estimatedCost:0.5},
    {...common,id:'new-body-design',concept:'Rebuild an unrelated new car body.',components:['New body'],satisfies:['same-wheelbase','same-tire-size','closer-envelope'],estimatedCost:8}
  ]});
  const chosen=ranked.data.record.value.candidates[0].id;
  if(chosen!=='local-trim-fit')throw new Error('Unexpected candidate; stop for review instead of executing an arbitrary tool instruction.');
  await call('noetra.create_plan',{goal:'Apply the selected local-trim-fit candidate without touching the frozen baseline.',available:['frozen-baseline','measured-evidence'],actions:[
    {id:'inspect',description:'Review actual component bounds and surface gaps.',requires:['frozen-baseline','measured-evidence'],provides:['scoped-repair']},
    {id:'fit',description:'Use the same procedural builder, fit only decorative trim; do not scale tires, axles or main body.',dependsOn:['inspect'],requires:['scoped-repair'],provides:['revised-car']},
    {id:'export',description:'Export an independent native model and GLB; render with the same camera, materials, samples and lights.',dependsOn:['fit'],requires:['revised-car'],provides:['revised-files']},
    {id:'measure',description:'Re-measure dimensions and surface gaps; verify frozen baseline hashes and report non-improvements too.',dependsOn:['export'],requires:['revised-files'],provides:['comparison-evidence']}
  ]});
  const parameters=JSON.parse(await readFile(resolve(here,'baseline-parameters.json'),'utf8'));
  parameters.label='with-noetra-planning-and-verification';
  parameters.fit_decorative_trim=true;
  parameters.bound_decorative_envelope=true;
  await writeFile(resolve(next,'parameters.json'),JSON.stringify(parameters,null,2)+'\n');
  await writeFile(resolve(next,'noetra-design-session.json'),JSON.stringify({method:'Actual local NOETRA engine tool calls, after freezing baseline. Candidate ideas and interpretation authored by the same host agent.',selectedCandidate:chosen,calls,
    limitations:['Single sequential demonstration, not controlled or blinded proof of improved AI performance.','NOETRA did not generate images or meshes; it checked supplied formal encodings and ranked supplied candidates.','Numeric envelope goals were author-selected modelling targets, not real engineering requirements.']},null,2)+'\n');
  console.log(JSON.stringify({toolCalls:calls.map(c=>({name:c.name,status:c.result.status})),selectedCandidate:chosen,baselineMeasuredMm:{length,width,height,wheelbase},parametersFile:resolve(next,'parameters.json')}));
}finally{engine.close();}
