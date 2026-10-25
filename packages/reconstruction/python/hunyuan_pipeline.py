"""Operator-configured isolated shape provider; source image and alpha stay local."""
from pathlib import Path
import os,sys,json,time,hashlib,subprocess
import numpy as np
from PIL import Image
from geometry import require
from part_correction import permission,save

def reconstruct_hunyuan(root,payload,config,helpers):
    scope,new_run,image_record=helpers;vision=config['vision'];options=vision.get('hunyuan')
    require(options is not None,'RECONSTRUCTION_HUNYUAN_NOT_CONFIGURED')
    require(len(payload['images'])==1,'RECONSTRUCTION_HUNYUAN_SINGLE_VIEW_ONLY')
    run=new_run(root);record,_=image_record(root,payload['images'][0],run,0);images=[record];started=time.monotonic()
    require(record['width']*record['height']<=8_000_000 and record['metadata']['exifOrientation']==1,'RECONSTRUCTION_PHOTO_IMAGE_LIMIT')
    supplied=None
    if payload.get('foregroundMask'):
        mask,_=image_record(root,payload['foregroundMask'],run,1);images.append(mask);supplied=mask['preserved']
    try:
        from photo_provider import digest
        from providers.hunyuan_mini import generate_geometry
        # Release ORT's native arena/DLL working set by ending the foreground
        # process before the large shape worker is started. gc alone is not enough.
        save(run/'foreground-job.json',{'output':str(run),'image':record['preserved'],'mask':supplied,'modelManifest':vision['modelManifest']})
        foreground_process=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).with_name('foreground_worker.py')),'--',str(run/'foreground-job.json')],cwd=str(run),env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        (run/'foreground-log.txt').write_bytes(foreground_process.stdout[-262144:]);require(foreground_process.returncode==0,'RECONSTRUCTION_FOREGROUND_FAILED')
        conditioning=json.loads((run/'foreground-provenance.json').read_text())
        with Image.open(run/'foreground-rgba.png') as picture:rgba=picture.copy()
        resolution=min(vision.get('maxResolution',192),{'preview':128,'standard':192,'high':256}[payload['quality']])
        try:mesh,provenance=generate_geometry(rgba,options,run,resolution=resolution)
        except Exception as error:
            if str(getattr(error,'code','')).startswith('RECONSTRUCTION_'):raise ValueError(error.code) from error
            raise
        require(len(mesh.faces)>100 and np.isfinite(mesh.vertices).all(),'RECONSTRUCTION_INVALID_LEARNED_MESH')
        resources=run/'blender-runtime';resources.mkdir(exist_ok=True);save(run/'shape-export-job.json',{'output':str(run)})
        executable=permission(config)
        process=subprocess.run([str(executable),'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(Path(__file__).with_name('learned_shape_blender.py')),'--',str(run/'shape-export-job.json')],cwd=str(run),env={**os.environ,'BLENDER_USER_RESOURCES':str(resources)},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        (run/'shape-export-log.txt').write_bytes(process.stdout[-262144:]);require(process.returncode==0,'RECONSTRUCTION_SHAPE_EXPORT_FAILED')
        for item in images:require(digest(item['source'])==item['sha256'],'RECONSTRUCTION_SOURCE_CHANGED')
        evidence=json.loads((run/'shape-export-verification.json').read_text())
        report={'runId':run.name,'kind':'hunyuan-single-photo-learned-mesh','images':images,'backend':provenance,'conditioning':conditioning,
            'geometry':{'vertices':len(mesh.vertices),'triangles':len(mesh.faces),'watertight':bool(mesh.is_watertight),'windingConsistent':bool(mesh.is_winding_consistent)},
            'visualQuality':{'status':'unreviewed','requirement':'Camera-aligned anatomy and part-shape review is required; execution, triangle count and watertightness do not establish fidelity.'},
            'outputs':{'blend':str(run/'model.blend'),'glb':str(run/'model.glb'),'render':str(run/'three-quarter.png')},'views':evidence,'runtimeSeconds':time.monotonic()-started,
            'unknowns':['One input image; hidden shape and scale are learned hypotheses.','Neutral material only; no texture projection, recovered PBR, semantic parts or exact surface-fidelity claim.','Inspection renders use proposed cameras; they are not calibrated source-photo validation.'],
            'artifactDigests':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in run.iterdir() if p.is_file() and p.suffix in ['.json','.png','.glb','.ply','.blend','.safetensors']}}
        save(run/'report.json',report);return {k:v for k,v in report.items() if k not in ['images','artifactDigests']}
    except Exception:
        import traceback
        (run/'failure-traceback.txt').write_text(traceback.format_exc(),encoding='utf8');save(run/'failure.json',{'status':'failed','sourceSha256':record['sha256'],'seconds':time.monotonic()-started});raise
