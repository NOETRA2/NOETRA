"""Local end-to-end orchestration. Source bytes/estimates/verified geometry stay distinct."""
from pathlib import Path
import os,json,time,subprocess,contextlib,importlib.metadata,hashlib,gc
import numpy as np
import cv2 as cv
from PIL import Image
from geometry import require,compare_masks,boundary
from part_correction import permission,save

def contour_flow(prediction,target):
    from scipy.spatial import cKDTree
    # A smooth local proposal, not a depth observation. Outside this 12px band
    # the 3D vertex positions are unchanged. Flow is bounded to 12 image pixels.
    py,px=np.where(boundary(prediction));ty,tx=np.where(boundary(target))
    require(len(px)>20 and len(tx)>20,'RECONSTRUCTION_CONTOUR_EMPTY')
    p=np.column_stack([px,py]);t=np.column_stack([tx,ty]);_,idx=cKDTree(t).query(p);flow=t[idx]-p
    norms=np.linalg.norm(flow,axis=1);flow=flow*np.minimum(1,12/np.maximum(norms,1))[:,None]
    yy,xx=np.indices(target.shape);d,nearest=cKDTree(p).query(np.column_stack([xx.ravel(),yy.ravel()]))
    weight=np.where(d<12,np.cos(np.minimum(d,12)/12*np.pi/2)**2,0)*.8
    return (flow[nearest]*weight[:,None]).reshape(*target.shape,2).astype(np.float32)

def fit_photo_outline(root,source,source_report,config,new_run):
    import shutil
    permission(config);require(source_report.get('kind')=='single-photo-learned-mesh','RECONSTRUCTION_PHOTO_RUN_REQUIRED')
    run=new_run(root);shutil.copyfile(source/'photo-base.blend',run/'photo-base.blend')
    for name in ['conditioning.png','conditioning-mask.png']:shutil.copyfile(source/name,run/name)
    target=cv.imread(str(run/'conditioning-mask.png'),0)>127
    predicted=cv.imread(str(source/(source_report['comparison']['chosen'].lower()+'-mask.png')),cv.IMREAD_UNCHANGED)[:,:,3]>127
    flow=contour_flow(predicted,target);np.save(run/'contour-flow.npy',flow,allow_pickle=False)
    blender(run,config,{'stage':'outline','output':str(run),'chosen':source_report['comparison']['chosen']},'outline')
    decision=compare(run);evidence=json.loads((run/'outline-evidence.json').read_text())
    accepted=decision['acceptedCandidate'] and evidence['cameraAndTopologyPreserved'] and evidence['cameraDepthMaxChange']<1e-6 and evidence['flippedFaces']==0
    save(run/'outline-decision.json',{'accepted':accepted,'comparison':decision,'evidence':evidence})
    if accepted:shutil.copyfile(run/'outline-candidate.blend',run/'photo-base.blend')
    blender(run,config,{'stage':'export','output':str(run),'chosen':source_report['comparison']['chosen'],
        'projection':{'source':source_report['images'][0]['preserved'],'mask':str(source/'foreground.png'),'sourceToConditioning':source_report['conditioning']['sourceToConditioning']}},'final')
    report={'runId':run.name,'kind':'photo-outline-and-projection','parentRun':source.name,'images':source_report['images'],'outlineAccepted':accepted,'comparison':decision,'evidence':evidence,
        'outputs':{'blend':str(run/'model.blend'),'glb':str(run/'model.glb'),'render':str(run/'final.png')},
        'unknowns':['Contour fitting uses an estimated foreground silhouette, not physical depth.','Source-image texture detail is projected appearance, not recovered wheel/headlight/panel geometry.','Unseen geometry remains a learned hypothesis.'],
        'artifactDigests':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in run.iterdir() if p.is_file() and p.suffix in ['.blend','.glb','.png','.json','.npy']}}
    save(run/'report.json',report);return {k:v for k,v in report.items() if k not in ['images','artifactDigests']}

def refine_appearance(root,source,source_report,config,new_run):
    import shutil
    permission(config);require(source_report.get('kind')=='single-photo-learned-mesh','RECONSTRUCTION_PHOTO_RUN_REQUIRED')
    run=new_run(root);shutil.copyfile(source/'photo-base.blend',run/'photo-base.blend')
    shutil.copyfile(source/'conditioning-mask.png',run/'conditioning-mask.png')
    picture=source_report['images'][0]
    blender(run,config,{'stage':'export','output':str(run),'chosen':source_report['comparison']['chosen'],
        'projection':{'source':picture['preserved'],'mask':str(source/'foreground.png'),'sourceToConditioning':source_report['conditioning']['sourceToConditioning']}},'appearance')
    evidence=json.loads((run/'appearance-evidence.json').read_text())
    report={'runId':run.name,'kind':'photo-projected-appearance','images':source_report['images'],'parentRun':source.name,
        'evidence':evidence,'outputs':{'blend':str(run/'model.blend'),'glb':str(run/'model.glb'),'render':str(run/'final.png')},
        'unknowns':['Texture projection preserves observed radiance on visible mesh faces; it does not recover headlight/spoke/panel geometry.',
            'Unobserved faces retain learned appearance; another view can reveal projection distortion.','Physical scale and hidden shape remain hypotheses.'],
        'artifactDigests':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in run.iterdir() if p.is_file() and p.suffix in ['.blend','.glb','.png','.json']}}
    save(run/'report.json',report);return {k:v for k,v in report.items() if k not in ['images','artifactDigests']}

def backends(config):
    names=['torch','torchvision','opencv-python-headless','trimesh','scikit-image','pycolmap','open3d','mitsuba','rembg','transformers','xatlas']
    versions={}
    for name in names:
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    vision=config.get('vision');return {'libraries':versions,'visionConfigured':bool(vision),'modelExecutionAllowed':bool(vision and vision.get('allowModelExecution')),
        'modelCachePresent':bool(vision and Path(vision['modelManifest']).is_file()),'modelHashesChecked':'Only on an explicitly authorized inference call',
        'singleView':'TripoSR learned geometry; unseen surfaces are hypotheses','multiView':'COLMAP CPU structure from motion; requires multiple overlapping photographs',
        'stagedShapeProvider':{'configured':bool(vision and vision.get('hunyuan')),'executionAllowed':bool(vision and vision.get('allowModelExecution')),
            'status':'Pinned Hunyuan3D-2mini source/assets and selected interpreter resources are checked on an explicit call; this metadata read does not verify inference.'},
        'remoteImageUpload':False}

def blender(run,config,job,stage):
    executable=permission(config);path=run/(stage+'-blender-job.json');save(path,job)
    resources=run/'blender-runtime';resources.mkdir(exist_ok=True)
    process=subprocess.run([str(executable),'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(Path(__file__).with_name('photo_blender.py')),'--',str(path)],
        cwd=str(run),env={**os.environ,'BLENDER_USER_RESOURCES':str(resources)},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    (run/(stage+'-blender-log.txt')).write_bytes(process.stdout[-262144:]);require(process.returncode==0,'RECONSTRUCTION_PHOTO_BLENDER_FAILED')

def compare(run):
    target=cv.imread(str(run/'conditioning-mask.png'),0)>127;result={}
    for stage in ['initial','candidate']:
        image=cv.imread(str(run/(stage+'-mask.png')),cv.IMREAD_UNCHANGED);require(image is not None and image.shape==(*target.shape,4),'RECONSTRUCTION_RENDER_MISSING')
        mask=image[:,:,3]>127;values=compare_masks(target,mask);overlay=cv.imread(str(run/'conditioning.png'))
        overlay[boundary(target)]=(0,255,0);overlay[boundary(mask)]=(255,0,255);cv.imwrite(str(run/(stage+'-overlay.png')),overlay);result[stage]=values
    a,b=result['initial'],result['candidate'];accepted=b['silhouette_iou']>a['silhouette_iou']+.001 and b['boundary']['mean_px']<=a['boundary']['mean_px']
    return {'measurements':result,'acceptedCandidate':bool(accepted),'chosen':'Candidate' if accepted else 'Initial',
        'scope':'Actual Blender geometry renders versus the attributed estimated/supplied conditioning mask; no hidden-geometry truth or intrinsic-material measurement'}

def reconstruct_photos(root,payload,config,helpers):
    from filelock import FileLock,Timeout
    vision=config.get('vision')
    require(vision and vision.get('allowModelExecution') is True,'RECONSTRUCTION_MODEL_EXECUTION_NOT_APPROVED')
    # One heavy local job per configured model cache; OS lock is released on exit.
    try:
        with FileLock(str(Path(vision['sourceManifest']).parent/'inference.lock'),timeout=0):
            return reconstruct_locked(root,payload,config,helpers)
    except Timeout:raise ValueError('RECONSTRUCTION_BUSY')

def reconstruct_locked(root,payload,config,helpers):
    scope,new_run,image_record=helpers;vision=config.get('vision')
    require(vision and vision.get('allowModelExecution') is True,'RECONSTRUCTION_MODEL_EXECUTION_NOT_APPROVED');permission(config)
    if payload['backend']=='colmap':
        from photo_sfm import colmap_reconstruct
        return colmap_reconstruct(root,payload,config,helpers)
    if payload['backend']=='hunyuan-mini':
        from hunyuan_pipeline import reconstruct_hunyuan
        return reconstruct_hunyuan(root,payload,config,helpers)
    require(len(payload['images'])==1,'RECONSTRUCTION_TRIPOSR_SINGLE_VIEW_ONLY')
    run=new_run(root);record,rgb=image_record(root,payload['images'][0],run,0)
    require(record['metadata']['exifOrientation']==1 and record['width']*record['height']<=8_000_000,'RECONSTRUCTION_PHOTO_IMAGE_LIMIT')
    images=[record];supplied=None
    if payload.get('foregroundMask'):
        mask_record,_=image_record(root,payload['foregroundMask'],run,1);images.append(mask_record);supplied=mask_record['preserved']
    log=run/'vision-log.txt';started=time.monotonic()
    try:
        with log.open('w',encoding='utf8') as stream,contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
            from photo_provider import validate_models,foreground,triposr
            from photo_geometry import clean_mesh,propose_camera,mitsuba_geometry_render
            manifest=validate_models(vision)
            with Image.open(record['preserved']) as picture:conditioning,transform=foreground(picture,manifest,run,supplied)
            resolution=min(vision.get('maxResolution',192),{'preview':96,'standard':160,'high':192}[payload['quality']])
            mesh,prediction=triposr(conditioning,vision,manifest,run,resolution)
            mesh,vertices,faces,cleanup=clean_mesh(mesh,run);mask=cv.imread(str(run/'conditioning-mask.png'),0)
            proposal=propose_camera(vertices,faces,mask,run)
            renderer=mitsuba_geometry_render(run/'surface.ply',proposal['candidate'],run)
            del mesh,vertices,faces;gc.collect()
        blender(run,config,{'stage':'compare','output':str(run),'mesh':str(run/'surface.ply'),'reference':str(run/'conditioning.png'),'cameras':proposal},'compare')
        decision=compare(run);save(run/'camera-decision.json',decision)
        blender(run,config,{'stage':'export','output':str(run),'chosen':decision['chosen']},'final')
        for item in images:
            require(hashlib.sha256(Path(item['source']).read_bytes()).hexdigest()==item['sha256'],'RECONSTRUCTION_SOURCE_CHANGED')
        report={'runId':run.name,'kind':'single-photo-learned-mesh','images':images,'backend':prediction,'conditioning':transform,'cleanup':cleanup,'mitsuba':renderer,'comparison':decision,
            'outputs':{'blend':str(run/'model.blend'),'glb':str(run/'model.glb'),'render':str(run/'final.png')},'runtimeSeconds':time.monotonic()-started,
            'unknowns':['Learned hidden surfaces and scale are hypotheses, not exact recovered geometry.','Foreground segmentation may omit details; image boundaries are not automatically physical creases.',
                'Vertex appearance and studio PBR are estimates, not separated intrinsic materials/lighting.','Semantic panels/gaps and unseen interior detail are not automatically verified.'],
            'artifactDigests':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in run.iterdir() if p.is_file() and p.suffix in ['.blend','.glb','.ply','.png','.exr','.npz','.json']}}
        save(run/'report.json',report)
        return {k:v for k,v in report.items() if k not in ['images','artifactDigests']}
    except Exception:
        import traceback
        (run/'failure-traceback.txt').write_text(traceback.format_exc(),encoding='utf8')
        save(run/'failure.json',{'status':'failed','log':str(log),'originalImagePreserved':record['sha256'],'elapsedSeconds':time.monotonic()-started})
        raise
