import { test, expect } from 'vitest';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { NoetraEngine } from '../../packages/core/src/index.js';
import { ReconstructionConfig, reconstructionSchemas, readReconstructionConfig, isReconstructionTool } from '../../packages/reconstruction/src/index.js';

test('optional reconstruction is disabled by default and cannot install a runtime or upload an image',async()=>{
  const root=await mkdtemp(join(tmpdir(),'noetra-reconstruction-disabled-'));
  const engine=new NoetraEngine({projectRoot:root});
  try{
    expect(engine.reconstruction.enabled).toBe(false);
    const result=await engine.call('noetra.inspect_image_structure',{images:[join(root,'private.png')]});
    expect(result.ok).toBe(false);expect(result.error?.code).toBe('RECONSTRUCTION_DISABLED');
  }finally{engine.close();}
});
test('strict schemas reject caller-supplied permission, code, URLs and unbounded experiments',()=>{
  expect(()=>reconstructionSchemas['noetra.optimize_reconstruction'].parse({runId:'71837a28-6da6-40ec-b4ec-ab86c1f240a7',maxEvaluations:41})).toThrow();
  expect(()=>reconstructionSchemas['noetra.generate_3d_construction'].parse({runId:'71837a28-6da6-40ec-b4ec-ab86c1f240a7',code:'import os',allowBlenderExecution:true})).toThrow();
  expect(()=>ReconstructionConfig.parse({pythonExecutable:process.execPath,remoteEndpoint:'https://example.com'})).toThrow();
  expect(()=>reconstructionSchemas['noetra.reconstruct_multiview'].parse({pairs:[],initialScale:[0,10]})).toThrow();
});
test('reconstruction exposes twenty-three scoped operations, not proposed placeholder tools',()=>{
  expect(Object.keys(reconstructionSchemas)).toHaveLength(23);
  expect(isReconstructionTool('noetra.reconstruct_multiview')).toBe(true);
  expect(isReconstructionTool('noetra.segment_parts')).toBe(false);
  expect(isReconstructionTool('noetra.analyze_surface_geometry')).toBe(false);
  expect(isReconstructionTool('noetra.correct_parts')).toBe(true);
  expect(isReconstructionTool('noetra.build_outline_model')).toBe(true);
  expect(isReconstructionTool('noetra.reconstruct_calibrated_views')).toBe(true);
});

test('measured painting is an explicit preview and cannot claim verified automatic placement',()=>{
  const input={analysisRunId:'71837a28-6da6-40ec-b4ec-ab86c1f240a7',meshRunId:'71837a28-6da6-40ec-b4ec-ab86c1f240a7',layout:'/project/layout.json',mode:'unverified-preview'};
  expect(reconstructionSchemas['noetra.paint_appearance_preview'].parse(input).mode).toBe('unverified-preview');
  for(const extra of [{mode:'accepted'},{mode:'automatic'},{allowBlenderExecution:true},{code:'import os'},{palette:['#FF0000']}])
    expect(()=>reconstructionSchemas['noetra.paint_appearance_preview'].parse({...input,...extra})).toThrow();
});

test('automatic appearance analysis cannot accept custom palettes, meshes, masks or executable code',()=>{
  const input={images:['/project/reference.png']};
  expect(reconstructionSchemas['noetra.analyze_reference_appearance'].parse(input).colourFamilies).toBe(8);
  for(const extra of [{colours:['#AA6622']},{mesh:'/model.glb'},{parts:['eyes']},{code:'import os'},{colourFamilies:99}])
    expect(()=>reconstructionSchemas['noetra.analyze_reference_appearance'].parse({...input,...extra})).toThrow();
});

test('calibrated reconstruction accepts only a data manifest and cannot supply a source mesh or code',()=>{
  const input={manifest:'/project/views.json'};
  expect(reconstructionSchemas['noetra.reconstruct_calibrated_views'].parse(input)).toEqual(input);
  for(const extra of [{mesh:'/project/car.glb'},{code:'import os'},{allowBlenderExecution:true},{remoteEndpoint:'https://example.com'}])
    expect(()=>reconstructionSchemas['noetra.reconstruct_calibrated_views'].parse({...input,...extra})).toThrow();
});

test('reference colors remain attributed data and cannot supply executable code or permission',()=>{
  const input={runId:'71837a28-6da6-40ec-b4ec-ab86c1f240a7',views:[{id:'front',image:'/project/ref.png',direction:[-1,0,0],provenance:'Proposed front reference'}],provenance:'Approximate reference color transfer'};
  expect(reconstructionSchemas['noetra.colorize_reconstruction'].parse(input).views[0].up).toEqual([0,0,1]);
  for(const extra of [{code:'import os'},{allowBlenderExecution:true},{fallbackSRGB:[2,0,0]},{provenance:''}])
    expect(()=>reconstructionSchemas['noetra.colorize_reconstruction'].parse({...input,...extra})).toThrow();
  const mapped=reconstructionSchemas['noetra.colorize_reconstruction'].parse({...input,mappingMode:'primary-view',textureResolution:2048,
    views:[{...input.views[0],controlPoints:[{modelPixel:[2,3],referencePixel:[4,5]},{modelPixel:[10,3],referencePixel:[12,5]},{modelPixel:[2,10],referencePixel:[4,12]}]}]});
  expect(mapped.mappingMode).toBe('primary-view');expect(mapped.views[0].controlPoints).toHaveLength(3);
  expect(()=>reconstructionSchemas['noetra.colorize_reconstruction'].parse({...input,textureResolution:8192})).toThrow();
  expect(()=>reconstructionSchemas['noetra.colorize_reconstruction'].parse({...input,symmetryPlane:{normal:[0,1,0],offset:0,maxDistanceFraction:.9,provenance:'x'}})).toThrow();
});

test('surface refinement cannot accept replacement samples, unbounded grids or runtime permission',()=>{
  const input={runId:'71837a28-6da6-40ec-b4ec-ab86c1f240a7'};
  expect(reconstructionSchemas['noetra.refine_learned_surface'].parse(input).resolution).toBe(256);
  for(const extra of [{resolution:1024},{checkpoint:'/other'},{seed:77},{code:'import os'},{allowModelExecution:true}])
    expect(()=>reconstructionSchemas['noetra.refine_learned_surface'].parse({...input,...extra})).toThrow();
});

test('surface material painting requires bounded authored masks and cannot grant runtime access',()=>{
  const input={runId:'71837a28-6da6-40ec-b4ec-ab86c1f240a7',design:{baseSRGB:[.6,.3,.1],baseRoughness:.8,layers:[{id:'mane',region:{center:[0,0,0],radii:[1,1,1],provenance:'Artist mask'},colorSRGB:[.2,.1,.04],roughness:.9,provenance:'Artist color'}],provenance:'Reference-guided surface paint'}};
  expect(reconstructionSchemas['noetra.paint_surface_material'].parse(input).design.resolution).toBe(2048);
  for(const extra of [{code:'import os'},{allowBlenderExecution:true},{pythonExecutable:'/other'},{design:{...input.design,resolution:8192}},{design:{...input.design,layers:[]}},{design:{...input.design,referenceSurface:{referenceIndex:0}}}])
    expect(()=>reconstructionSchemas['noetra.paint_surface_material'].parse({...input,...extra})).toThrow();
  expect(()=>reconstructionSchemas['noetra.paint_surface_material'].parse({...input,design:{...input.design,layers:[{...input.design.layers[0],gradient:{axis:'Z',minimum:1,maximum:1,colorSRGB:[1,1,1]}}]}})).toThrow();
});

test('base surface refinement cannot add parts, inject code or exceed local displacement limits',()=>{
  const design={baseSRGB:[.6,.3,.1],baseRoughness:.8,layers:[{id:'coat',region:{center:[0,0,0],radii:[1,1,1],provenance:'Mask'},colorSRGB:[.6,.3,.1],roughness:.8,provenance:'Coat'}],provenance:'Surface paint'};
  const refinement={maximumDisplacement:.01,deformations:[{id:'nose',region:{center:[0,0,0],radii:[.1,.1,.1],provenance:'Nose'},direction:[0,0,1],distance:.005}],provenance:'Bounded existing vertices'};
  const input={runId:'71837a28-6da6-40ec-b4ec-ab86c1f240a7',references:['/project/lion.png'],design,refinement};
  expect(reconstructionSchemas['noetra.refine_base_surface'].parse(input).refinement.maximumDisplacement).toBe(.01);
  for(const extra of [{maximumDisplacement:1},{objects:['new-eye']},{code:'import os'},{deformations:[]}])
    expect(()=>reconstructionSchemas['noetra.refine_base_surface'].parse({...input,refinement:{...refinement,...extra}})).toThrow();
});


test('photo inference cannot grant itself execution permission, download models or inject code',()=>{
  const input={images:['/project/photo.png'],backend:'triposr'};
  expect(reconstructionSchemas['noetra.reconstruct_photos'].parse(input).quality).toBe('standard');
  for(const extra of [{allowModelExecution:true},{sourceDirectory:'/other'},{code:'print(1)'},{remoteEndpoint:'https://example.com'}])
    expect(()=>reconstructionSchemas['noetra.reconstruct_photos'].parse({...input,...extra})).toThrow();
  expect(()=>reconstructionSchemas['noetra.reconstruct_photos'].parse({...input,images:Array(17).fill('/project/photo.png')})).toThrow();
  const config=ReconstructionConfig.parse({pythonExecutable:process.execPath,vision:{pythonExecutable:process.execPath,sourceDirectory:'/source',modelManifest:'/models.json',sourceManifest:'/source.json'}});
  expect(config.vision?.allowModelExecution).toBe(false);
  expect(reconstructionSchemas['noetra.reconstruct_photos'].parse({...input,backend:'hunyuan-mini'}).backend).toBe('hunyuan-mini');
  expect(()=>reconstructionSchemas['noetra.reconstruct_photos'].parse({...input,backend:'hunyuan-mini',hunyuan:{pythonExecutable:'/untrusted'}})).toThrow();
  expect(()=>ReconstructionConfig.parse({pythonExecutable:process.execPath,vision:{...config.vision,hunyuan:{sourceDirectory:'/source',assetDirectory:'/assets',pythonExecutable:process.execPath,device:'auto'}}})).toThrow();
});

test('saved-surface repair cannot change cameras, accept external scenes or take executable inputs',()=>{
  const input={runId:'71837a28-6da6-40ec-b4ec-ab86c1f240a7'};
  expect(reconstructionSchemas['noetra.repair_photo_surface'].parse(input)).toEqual(input);
  for(const extra of [{blend:'C:/outside/private.blend'},{code:'bpy.ops.wm.quit_blender()'},{allowBlenderExecution:true},{camera:'other'}])
    expect(()=>reconstructionSchemas['noetra.repair_photo_surface'].parse({...input,...extra})).toThrow();
});

test('structural completion requires explicit prior provenance and rejects executable or unbounded edits',()=>{
  const spec={blend:'/project/prior.blend',collection:'Model',reference:'/project/reference.png',floor:'Floor',wheels:['Tyre'],referenceTarget:[0,0,1],patches:[],provenance:'Explicit authored prior; hidden geometry is proposed.'};
  expect(reconstructionSchemas['noetra.complete_from_prior'].parse(spec).groundClearance).toBe(.003);
  for(const extra of [{code:'import os'},{provenance:''},{allowBlenderExecution:true},{patches:[{object:'Hood',resolution:10000,curves:{}}]}])
    expect(()=>reconstructionSchemas['noetra.complete_from_prior'].parse({...spec,...extra})).toThrow();
});

test('outline initial model requires an attributed outline and explicit camera assumption',()=>{
  const input={reference:'/project/image.png',outlinePx:[[1,1],[20,1],[20,20]],provenance:'User drawing',cameraAssumption:'front-orthographic'};
  expect(reconstructionSchemas['noetra.build_outline_model'].parse(input).proposedDepthRatio).toBe(.75);
  expect(()=>reconstructionSchemas['noetra.build_outline_model'].parse({...input,cameraAssumption:'arbitrary photo'})).toThrow();
  expect(()=>reconstructionSchemas['noetra.build_outline_model'].parse({...input,foregroundMask:'/project/mask.png'})).toThrow();
  expect(()=>reconstructionSchemas['noetra.build_outline_model'].parse({...input,outlinePx:undefined})).toThrow();
});

test('part correction accepts data controls only, rejects code and uncontrolled budgets',()=>{
  expect(()=>reconstructionSchemas['noetra.correct_parts'].parse({runId:'71837a28-6da6-40ec-b4ec-ab86c1f240a7',maxCandidates:7})).toThrow();
  expect(()=>reconstructionSchemas['noetra.prepare_part_correction'].parse({blend:'x',collection:'x',parts:[],parameters:[],views:[],code:'bpy.ops.wm.quit_blender()'})).toThrow();
  expect(()=>reconstructionSchemas['noetra.inspect_part_correction'].parse({runId:'../other-run'})).toThrow();
});
test('operator config has execution off unless explicitly enabled and unknown fields fail',async()=>{
  const root=await mkdtemp(join(tmpdir(),'noetra-reconstruction-config-'));
  const path=join(root,'config.json');await writeFile(path,JSON.stringify({pythonExecutable:process.execPath}));
  expect((await readReconstructionConfig(path))?.allowBlenderExecution).toBe(false);
  expect(await readReconstructionConfig()).toBeUndefined();
  await writeFile(path,'x'.repeat(16385));await expect(readReconstructionConfig(path)).rejects.toThrow();
});
test('missing configured runtime fails closed without falling back to another executable',async()=>{
  const root=await mkdtemp(join(tmpdir(),'noetra-reconstruction-missing-'));
  const engine=new NoetraEngine({projectRoot:root,reconstruction:{pythonExecutable:resolve(root,'not-installed-python.exe'),allowBlenderExecution:false}});
  try{
    const result=await engine.call('noetra.inspect_image_structure',{images:[join(root,'image.png')]});
    expect(result.ok).toBe(false);expect(result.error?.code).toBe('RECONSTRUCTION_RUNTIME');
  }finally{engine.close();}
});
