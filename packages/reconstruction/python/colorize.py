"""Immutable, data-only color operation on an existing local reconstruction."""
from pathlib import Path
import json,hashlib,shutil,os,subprocess
import numpy as np
from PIL import Image
from geometry import require
from part_correction import permission,save
from reference_colors import foreground,basis

def colorize(root,source,source_report,payload,config,helpers):
    scope,new_run,image_record=helpers;executable=permission(config)
    require(isinstance(source_report.get('outputs'),dict) and isinstance(source_report['outputs'].get('glb'),str),'RECONSTRUCTION_COLOR_MODEL_REQUIRED')
    model=scope(root,source_report['outputs']['glb']);require(model.suffix.lower()=='.glb' and model.stat().st_size<=128*1024*1024,'RECONSTRUCTION_COLOR_MODEL_LIMIT');run=new_run(root)
    parent={'source':str(model),'preserved':str(run/'learned-mesh.glb'),'sha256':hashlib.sha256(model.read_bytes()).hexdigest()}
    shutil.copyfile(model,parent['preserved']);images=[];views=[];pixels=0
    for i,view in enumerate(payload['views']):
        basis(view['direction'],view['up']);record,rgb=image_record(root,view['image'],run,i);images.append(record)
        pixels+=record['width']*record['height'];require(pixels<=24_000_000,'RECONSTRUCTION_COLOR_IMAGE_LIMIT')
        with Image.open(record['preserved']) as im:alpha=np.asarray(im.getchannel('A')) if 'A' in im.getbands() else None
        mask=foreground(rgb,alpha);require(mask.sum()>=100,'RECONSTRUCTION_COLOR_FOREGROUND')
        path=run/('color-reference-'+str(i)+'.npz');np.savez_compressed(path,rgb=rgb,mask=mask)
        views.append({k:view[k] for k in ['id','direction','up','weight','provenance']}|{'array':str(path),'controlPoints':view.get('controlPoints',[]),'region':view.get('region')})
    require(payload.get('mappingMode','multi-view')!='primary-view' or (len([v for v in views if not v.get('region')])==1),'RECONSTRUCTION_PRIMARY_COLOR_SINGLE_VIEW')
    profile={'views':views,'fallbackSRGB':payload['fallbackSRGB'],'provenance':payload['provenance'],'mappingMode':payload.get('mappingMode','multi-view'),'textureResolution':payload.get('textureResolution'),
        'diffusionPython':config.get('vision',{}).get('pythonExecutable',config['pythonExecutable']),'symmetryPlane':payload.get('symmetryPlane')}
    save(run/'shape-export-job.json',{'output':str(run),'referenceColorProfile':profile})
    resources=run/'blender-runtime';resources.mkdir()
    result=subprocess.run([str(executable),'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(Path(__file__).with_name('learned_shape_blender.py')),'--',str(run/'shape-export-job.json')],cwd=str(run),env={**os.environ,'BLENDER_USER_RESOURCES':str(resources)},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    (run/'color-export-log.txt').write_bytes(result.stdout[-262144:]);require(result.returncode==0,'RECONSTRUCTION_COLOR_EXPORT_FAILED')
    require(hashlib.sha256(model.read_bytes()).hexdigest()==parent['sha256'],'RECONSTRUCTION_PARENT_MODEL_CHANGED')
    for record in images:require(hashlib.sha256(Path(record['source']).read_bytes()).hexdigest()==record['sha256'],'RECONSTRUCTION_SOURCE_CHANGED')
    evidence=json.loads((run/'color-verification.json').read_text());require(evidence['geometryExactlyUnchanged'],'RECONSTRUCTION_COLOR_GEOMETRY_CHANGED')
    report={'runId':run.name,'kind':'reference-colored-reconstruction','parentRun':source.name,'parentModel':parent,'images':images,'color':evidence,'provenance':payload['provenance'],
        'outputs':{'blend':str(run/'model.blend'),'glb':str(run/'model.glb'),'render':str(run/'three-quarter.png')},
        'views':json.loads((run/'shape-export-verification.json').read_text()),
        'unknowns':['Approximate reference alignment; colors may spill across incorrectly matched regions.','Observed radiance is not intrinsic PBR; hidden colors use an explicit fallback.','Original mesh detail and imperfections remain unchanged.'],
        'artifactDigests':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in run.iterdir() if p.is_file() and p.suffix in ['.json','.png','.npz','.glb','.blend']}}
    save(run/'report.json',report);return {k:v for k,v in report.items() if k not in ['images','artifactDigests']}
