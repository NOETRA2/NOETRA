"""Reusable saved-mesh repair and fixed-view verification orchestration."""
from pathlib import Path
import os,json,subprocess,hashlib,shutil
import numpy as np
import cv2 as cv
from PIL import Image,ImageDraw
from geometry import require
from part_correction import permission,save
from photo_pipeline import compare,blender
from surface_repair import repair

KINDS=['single-photo-learned-mesh','photo-outline-and-projection','photo-projected-appearance','photo-surface-repair']

def stage(run,config,job,name):
    executable=permission(config);path=run/(name+'-job.json');save(path,job)
    resources=run/'blender-runtime';resources.mkdir(exist_ok=True)
    process=subprocess.run([str(executable),'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(Path(__file__).with_name('photo_surface_blender.py')),'--',str(path)],
        cwd=str(run),env={**os.environ,'BLENDER_USER_RESOURCES':str(resources)},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=300 if name=='views' else 90,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    (run/(name+'-blender-log.txt')).write_bytes(process.stdout[-262144:]);require(process.returncode==0,'RECONSTRUCTION_SURFACE_BLENDER_FAILED')

def repair_surface(root,source,source_report,config,helpers):
    scope,new_run,load_run=helpers;permission(config);require(source_report.get('kind') in KINDS,'RECONSTRUCTION_PHOTO_RUN_REQUIRED')
    ancestor,observations=source,source_report;visited=set()
    while observations.get('kind')!='single-photo-learned-mesh':
        require(ancestor.name not in visited and len(visited)<8,'RECONSTRUCTION_PHOTO_LINEAGE');visited.add(ancestor.name)
        ancestor,observations=load_run(root,observations['parentRun'])
    model=scope(root,source_report['outputs']['blend']);run=new_run(root)
    for name in ['conditioning.png','conditioning-mask.png']:shutil.copyfile(ancestor/name,run/name)
    before_hash=hashlib.sha256(model.read_bytes()).hexdigest()
    stage(run,config,{'stage':'inspect','source':str(model),'output':str(run)},'inspect')
    data=np.load(run/'surface-input.npz',allow_pickle=False);mask=cv.imread(str(run/'conditioning-mask.png'),0)>127
    candidate,evidence=repair(data['vertices'],data['faces'],data['pixels'],data['depths'],data['cameraRotation'],float(data['focal']),mask)
    np.save(run/'candidate-vertices.npy',candidate,allow_pickle=False);save(run/'repair-proposal.json',evidence)
    stage(run,config,{'stage':'apply','source':str(model),'output':str(run)},'apply')
    decision=compare(run);scene=json.loads((run/'surface-scene-evidence.json').read_text())
    measurements=decision['measurements'];a,b=measurements['initial'],measurements['candidate']
    accepted=(evidence['flippedFaces']==0 and scene['cameraAndOtherObjectsUnchanged'] and scene['topologyUnchanged']
        and evidence['localLaplacianResidualAfter']<evidence['localLaplacianResidualBefore']*.95
        and b['silhouette_iou']>=a['silhouette_iou']-.003 and b['boundary']['mean_px']<=a['boundary']['mean_px']+.2)
    save(run/'repair-decision.json',{'accepted':bool(accepted),'measurements':measurements,'geometry':evidence,'scene':scene})
    shutil.copyfile(run/'surface-candidate.blend' if accepted else model,run/'photo-base.blend')
    # The accepted source scene camera is already fixed; its name is read from the
    # inspected model rather than assuming an arbitrary user-supplied camera.
    pose=json.loads((run/'surface-camera.json').read_text())
    blender(run,config,{'stage':'export','output':str(run),'cameraName':pose['name'],
        'projection':{'source':observations['images'][0]['preserved'],'mask':str(ancestor/'foreground.png'),'sourceToConditioning':observations['conditioning']['sourceToConditioning']}},'final')
    stage(run,config,{'stage':'views','source':str(run/'model.blend'),'output':str(run)},'views')
    names=['reference','front','left','rear','right','top','rear-three-quarter']
    sheet=Image.new('RGB',(1800,4*405),(16,18,20));draw=ImageDraw.Draw(sheet)
    for i,name in enumerate(names):
        with Image.open(run/(name+'.png')) as image:picture=image.convert('RGB');picture.thumbnail((900,375))
        x=(i%2)*900;y=(i//2)*405;sheet.paste(picture,(x,y+25));draw.text((x+15,y+7),name.replace('-',' ').title(),fill='white')
    sheet.save(run/'all-angles.jpg',quality=95)
    # Include neutral actual geometry so projected image detail is not confused
    # with physically reconstructed fine parts.
    clay=Image.new('RGB',(1600,3*525),(16,18,20));draw=ImageDraw.Draw(clay)
    for i,name in enumerate(names[1:]):
        with Image.open(run/(name+'-geometry.png')) as image:picture=image.convert('RGB')
        x=(i%2)*800;y=(i//2)*525;clay.paste(picture,(x,y+25));draw.text((x+15,y+7),name.replace('-',' ').title()+' — mesh',fill='white')
    clay.save(run/'geometry-angles.jpg',quality=95)
    require(hashlib.sha256(model.read_bytes()).hexdigest()==before_hash,'RECONSTRUCTION_SOURCE_CHANGED')
    report={'runId':run.name,'kind':'photo-surface-repair','parentRun':source.name,'images':observations['images'],'repairAccepted':bool(accepted),'measurements':measurements,'geometry':evidence,'scene':scene,
        'outputs':{'blend':str(run/'model.blend'),'glb':str(run/'model.glb'),'render':str(run/'final.png'),'angles':str(run/'all-angles.jpg'),'geometryAngles':str(run/'geometry-angles.jpg')},
        'views':[{'name':name,'image':str(run/(name+'.png'))} for name in names],
        'unknowns':['Unseen surfaces remain learned hypotheses; views are renders of one mesh, not extra source photographs.','Original image radiance is projected on visible faces; spokes/headlights/panel lines are not verified geometric parts.','Local smoothing is an estimated surface repair, not a physical scan.'],
        'artifactDigests':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in run.iterdir() if p.is_file() and p.suffix in ['.blend','.glb','.png','.jpg','.json','.npy','.npz']}}
    save(run/'report.json',report);return {k:v for k,v in report.items() if k not in ['images','artifactDigests']}
