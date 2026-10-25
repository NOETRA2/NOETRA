import { NoetraEngine } from 'noetra';
import { readFile, writeFile, copyFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const here=dirname(fileURLToPath(import.meta.url));
const folder=resolve(here,'../../../output/noetra-sports-car-comparison-20261024');
const load=async path=>JSON.parse(await readFile(resolve(folder,path),'utf8'));
const baseline=await load('baseline/metrics.json'), assisted=await load('with-noetra/metrics.json');
const oldAudit=await load('baseline/geometry-audit.json'), newAudit=await load('with-noetra/geometry-audit.json');
const freeze=await load('baseline-freeze.json');
for(const [file,digest]of Object.entries(freeze.hashes)){
  const actual=createHash('sha256').update(await readFile(resolve(folder,'baseline',file))).digest('hex');
  if(actual!==digest)throw new Error(`Frozen baseline changed: ${file}`);
}
const mm=x=>Math.round(x*1000);
const dimension=m=>m.vehicle_bounds_excluding_mirrors.dimensions.map(mm);
const wheelbase=m=>mm(Math.abs(m.wheels[2].center[0]-m.wheels[0].center[0]));
const gaps=a=>({maximumMm:Math.round(1000*Math.max(...a.trim_distances.map(t=>t.maximum_surface_distance_m))),
  averageOfPerPartMeansMm:Math.round(1000*a.trim_distances.reduce((s,t)=>s+t.mean_surface_distance_m,0)/a.trim_distances.length)});
if(JSON.stringify(baseline.render)!==JSON.stringify(assisted.render))throw new Error('Presentation settings differ.');
const wheelPlacementPreserved=baseline.wheels.every((wheel,i)=>wheel.center.every((value,axis)=>Math.abs(value-assisted.wheels[i].center[axis])<1e-6)&&Math.abs(wheel.radius-assisted.wheels[i].radius)<1e-6&&Math.abs(wheel.half_width-assisted.wheels[i].half_width)<1e-6);
if(!wheelPlacementPreserved)throw new Error('Tire geometry or placement changed.');
const summary={
  subject:'Original futuristic sports car, same frozen brief',
  baselineFrozenUnchanged:true,matchedBlenderPresentation:true,wheelPlacementPreserved,
  baseline:{dimensionsMm:dimension(baseline),wheelbaseMm:wheelbase(baseline),triangles:baseline.evaluated_triangles,objects:baseline.object_count,trimSurfaceDistance:gaps(oldAudit)},
  withNoetra:{dimensionsMm:dimension(assisted),wheelbaseMm:wheelbase(assisted),triangles:assisted.evaluated_triangles,objects:assisted.object_count,trimSurfaceDistance:gaps(newAudit)},
  targetDimensionsMm:[4600,2000,1160],
  observedImprovements:['Length is closer to the author-chosen envelope.','Width is closer to the author-chosen envelope.','Decorative cockpit/lamp geometry is nearer its supporting surfaces.'],
  observedNonImprovements:['Overall height is slightly further from the 1,160 mm target after raised roof trim is fitted to the canopy.','Strict 2,000 mm width is still missed by about 2 mm.','Surface fitting and envelope containment changed the front fascia appearance; visual preference remains mixed and subjective.'],
  limitations:['Single sequential demonstration, not a blind, seed-controlled or statistically valid causal benchmark.','Agent authored the candidates, formal encodings and Blender repairs. NOETRA did not independently invent the car, inspect pixels, generate meshes or operate Blender.','Baseline was not intentionally degraded. Both use the same 146 components, 92,034 triangle budget and Blender settings.','Concept PNGs are stochastic generated design images, not renders of the GLB mesh and not exact same-shape reconstructions.','This is a simplified visual 3D study, not CAD, manufacturing-ready geometry, physical simulation or a roadworthy vehicle.','Formal results refer to rounded millimetre measurements supplied by the host; they do not certify the measurement process.']
};
const engine=new NoetraEngine({projectRoot:folder,projectId:'sports-car-single-case-demo'});
const checks=[];
try{
  const evidence=await engine.call('noetra.record_evidence',{claim:'Post-build comparison measurements and limitations',origin:{kind:'tool',reference:'Actual Blender evaluated meshes, read-only surface audit and frozen baseline hash check.',timestamp:new Date().toISOString()},method:'Independent before/after numeric comparison; same camera/lighting/render settings.',observation:JSON.stringify(summary),limitations:summary.limitations});
  checks.push({name:'noetra.record_evidence',result:evidence});
  const [length,width]=summary.withNoetra.dimensionsMm;
  const c=(id,variable,relation,value)=>({id,terms:[{variable,coefficient:1}],relation,value});
  const premises=[c('measured-length','length_mm','eq',length),c('measured-width','width_mm','eq',width),c('measured-wheelbase','wheelbase_mm','eq',summary.withNoetra.wheelbaseMm)];
  for(const claim of [c('length-target','length_mm','le',4600),c('strict-width-target','width_mm','le',2000),c('wheelbase-target','wheelbase_mm','eq',2700)]){
    const result=await engine.call('noetra.verify_claim',{premises,claim});
    if(!result.ok)throw new Error(result.error?.code);
    checks.push({name:'noetra.verify_claim',claim,result});
  }
  await writeFile(resolve(folder,'comparison.json'),JSON.stringify({...summary,noetraFinalChecks:checks,glbRoundTrip:await load('glb-round-trip.json')},null,2)+'\n');
  const earlier=await load('with-noetra/noetra-design-session.json');
  const calls=[...earlier.calls,...checks];
  await writeFile(resolve(folder,'NOETRA-CALLS.json'),JSON.stringify({designWorkflowCalls:earlier.calls.length,postBuildCalls:checks.length,calls},null,2)+'\n');
  await copyFile(resolve(here,'BRIEF.md'),resolve(folder,'BRIEF.md'));
  await copyFile(resolve(here,'baseline-image-prompt.txt'),resolve(folder,'baseline/image-prompt.txt'));
  await copyFile(resolve(here,'noetra-image-prompt.txt'),resolve(folder,'with-noetra/image-prompt.txt'));
  await copyFile(resolve(here,'build_car.py'),resolve(folder,'with-noetra/build_car.py'));
  console.log(JSON.stringify({baseline:summary.baseline,withNoetra:summary.withNoetra,baselineFrozenUnchanged:true,noetraFinalChecks:checks.map(c=>({name:c.name,claim:c.claim?.id,status:c.result.status}))},null,2));
}finally{engine.close();}
