"""Immutable local material design job; trusted fixed Blender/xatlas workers only."""
from pathlib import Path
import os,json,hashlib,shutil,subprocess,time
from geometry import require
from part_correction import permission,save

def paint(root,source,source_report,payload,config,helpers):
    scope,new_run,image_record=helpers;executable=permission(config);vision=config.get('vision')
    require(vision and Path(vision['pythonExecutable']).is_absolute(),'RECONSTRUCTION_VISION_NOT_CONFIGURED')
    require('glb' in source_report.get('outputs',{}),'RECONSTRUCTION_COLOR_MODEL_REQUIRED')
    model=scope(root,source_report['outputs']['glb']);require(model.is_file() and model.suffix.lower()=='.glb' and model.stat().st_size<128*1024*1024,'RECONSTRUCTION_COLOR_MODEL_LIMIT')
    run=new_run(root);started=time.monotonic();digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    parent={'source':str(model),'preserved':str(run/'learned-mesh.glb'),'sha256':digest(model)};shutil.copyfile(model,parent['preserved']);images=[]
    for i,path in enumerate(payload['references']):
        record,_=image_record(root,path,run,i);images.append(record)
    from uv_cache import find_verified_cache
    cache=None if payload.get('refinement') else find_verified_cache(root,parent['sha256'],payload['design']['resolution'])
    save(run/'shape-export-job.json',{'output':str(run),'baseRefinement':payload.get('refinement'),'materialProfile':{'design':payload['design'],'images':images,'measuredPreview':payload.get('_measuredPreview'),'verifiedAtlasCache':cache,'pythonExecutable':vision['pythonExecutable']}})
    resources=run/'blender-runtime';resources.mkdir();temporary=run/'temporary';temporary.mkdir()
    process=subprocess.run([str(executable),'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(Path(__file__).with_name('learned_shape_blender.py')),'--',str(run/'shape-export-job.json')],cwd=str(run),env={**os.environ,'BLENDER_USER_RESOURCES':str(resources),'TEMP':str(temporary),'TMP':str(temporary)},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=400,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    (run/'material-log.txt').write_bytes(process.stdout[-262144:]);require(process.returncode==0,'RECONSTRUCTION_MATERIAL_PAINT_FAILED')
    evidence=json.loads((run/'material-verification.json').read_text());require(evidence['geometryExactlyUnchanged'],'RECONSTRUCTION_COLOR_GEOMETRY_CHANGED')
    require(digest(model)==parent['sha256'],'RECONSTRUCTION_PARENT_MODEL_CHANGED')
    for record in images:require(digest(record['source'])==record['sha256'],'RECONSTRUCTION_SOURCE_CHANGED')
    refinement=json.loads((run/'base-surface-verification.json').read_text()) if payload.get('refinement') else None
    report={'runId':run.name,'kind':'measured-appearance-preview' if payload.get('_measuredPreview') else 'refined-base-surface' if refinement else 'authored-surface-material','parentRun':source.name,'parentModel':parent,'images':images,'design':payload['design'],'material':evidence,'baseRefinement':refinement,'measuredPreview':payload.get('_measuredPreview'),
        'outputs':{'blend':str(run/'model.blend'),'glb':str(run/'model.glb'),'render':str(run/'three-quarter.png'),'baseColor':str(run/'base-color.png'),'roughness':str(run/'roughness.png'),'normal':str(run/'normal.png')},
        'views':json.loads((run/'shape-export-verification.json').read_text()),'runtimeSeconds':time.monotonic()-started,
        'unknowns':['Palette and region masks are authored design choices guided by the reference, not recovered intrinsic material.','Fine fur detail is a procedural shading pattern, not newly reconstructed strands or geometry.','Only declared base-surface masks are changed; anatomy remains approximate.' if refinement else 'All existing geometry is unchanged.'],
        'artifactDigests':{p.name:digest(p) for p in run.iterdir() if p.is_file() and p.suffix in ['.json','.npz','.png','.blend','.glb']}}
    save(run/'report.json',report);return {k:v for k,v in report.items() if k not in ['images','artifactDigests']}
