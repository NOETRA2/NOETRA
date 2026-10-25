"""Re-extract one fixed learned shape; no new conditioning or diffusion sampling."""
from pathlib import Path
import os,json,hashlib,subprocess,time
from geometry import require
from part_correction import permission,save

def refine(root,source,source_report,payload,config,helpers):
    scope,new_run=helpers;vision=config.get('vision')
    require(vision and vision.get('allowModelExecution') is True and vision.get('hunyuan'),'RECONSTRUCTION_MODEL_EXECUTION_NOT_APPROVED')
    require(payload['resolution']<=vision.get('maxResolution',192),'RECONSTRUCTION_RESOLUTION_LIMIT')
    cached=source_report.get('backend',{}).get('latentCheckpoint')
    require(isinstance(cached,dict) and isinstance(cached.get('path'),str) and isinstance(cached.get('sha256'),str),'RECONSTRUCTION_SHAPE_CHECKPOINT_REQUIRED')
    checkpoint=scope(root,cached['path']);require(hashlib.sha256(checkpoint.read_bytes()).hexdigest()==cached['sha256'],'RECONSTRUCTION_SHAPE_CHECKPOINT_CHANGED')
    executable=permission(config);run=new_run(root);started=time.monotonic()
    try:
        from providers.hunyuan_mini import extract_geometry
        try:mesh,provenance=extract_geometry(checkpoint,cached['sha256'],vision['hunyuan'],run,resolution=payload['resolution'])
        except Exception as error:
            if str(getattr(error,'code','')).startswith('RECONSTRUCTION_'):raise ValueError(error.code) from error
            raise
        save(run/'shape-export-job.json',{'output':str(run)});resources=run/'blender-runtime';resources.mkdir()
        process=subprocess.run([str(executable),'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(Path(__file__).with_name('learned_shape_blender.py')),'--',str(run/'shape-export-job.json')],cwd=str(run),env={**os.environ,'BLENDER_USER_RESOURCES':str(resources)},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        (run/'shape-export-log.txt').write_bytes(process.stdout[-262144:]);require(process.returncode==0,'RECONSTRUCTION_SHAPE_EXPORT_FAILED')
        require(hashlib.sha256(checkpoint.read_bytes()).hexdigest()==cached['sha256'],'RECONSTRUCTION_SHAPE_CHECKPOINT_CHANGED')
        report={'runId':run.name,'kind':'fixed-latent-surface-reextraction','parentRun':source.name,'images':source_report.get('images',[]),'backend':provenance,
            'sourceCheckpoint':{'source':str(checkpoint),'sha256':cached['sha256']},'newShapeSampled':False,
            'geometry':{'vertices':len(mesh.vertices),'triangles':len(mesh.faces),'watertight':bool(mesh.is_watertight)},
            'outputs':{'blend':str(run/'model.blend'),'glb':str(run/'model.glb'),'render':str(run/'three-quarter.png')},
            'views':json.loads((run/'shape-export-verification.json').read_text()),'runtimeSeconds':time.monotonic()-started,
            'visualQuality':{'status':'unreviewed','requirement':'Original shape quality remains unverified. Compare anatomical parts before accepting a candidate.'},
            'unknowns':['Higher extraction resolution can sharpen incorrect learned geometry.','No additional source evidence, learned resampling, color transfer or anatomical correction occurs.'],
            'artifactDigests':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in run.iterdir() if p.is_file() and p.suffix in ['.json','.png','.glb','.ply','.blend','.safetensors']}}
        save(run/'report.json',report);return {k:v for k,v in report.items() if k not in ['images','artifactDigests']}
    except Exception:
        import traceback
        (run/'failure-traceback.txt').write_text(traceback.format_exc());raise
