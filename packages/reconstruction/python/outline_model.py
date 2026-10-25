"""Guided silhouette-to-loft initial geometry; hidden parts remain hypotheses."""
import json,os,subprocess,hashlib
from pathlib import Path
import numpy as np
import cv2 as cv
from geometry import require,compare_masks
from part_correction import permission,save,render,measure

def geometry_from_outline(points,width,height,front_width,depth_ratio,sections):
    q=np.array(points,dtype=float)
    require(q.ndim==2 and q.shape[1]==2 and 3<=len(q)<=512 and np.isfinite(q).all(),'RECONSTRUCTION_OUTLINE_SHAPE')
    require((q[:,0]>=0).all() and (q[:,0]<width).all() and (q[:,1]>=0).all() and (q[:,1]<height).all(),'RECONSTRUCTION_POLYGON_OUTSIDE_IMAGE')
    require(abs(cv.contourArea(q.astype(np.float32)))>=4,'RECONSTRUCTION_POLYGON_AREA')
    require(sections[0]=={'t':0,'scaleX':1,'scaleZ':1} and sections[-1]['t']==1 and all(a['t']<b['t'] for a,b in zip(sections,sections[1:])),'RECONSTRUCTION_OUTLINE_SECTIONS')
    lo=q.min(axis=0);hi=q.max(axis=0);centre=(lo+hi)/2;factor=front_width/(hi[0]-lo[0]);h=(hi[1]-lo[1])*factor;depth=front_width*depth_ratio
    xz=np.c_[(q[:,0]-centre[0])*factor,(centre[1]-q[:,1])*factor+h/2]
    rings=[np.c_[xz[:,0]*s['scaleX'],np.full(len(q),s['t']*depth),(xz[:,1]-h/2)*s['scaleZ']+h/2].tolist() for s in sections]
    camera_x=(width/2-centre[0])*factor;camera_z=(centre[1]-height/2)*factor+h/2
    return {'rings':rings,'width':front_width,'height':h,'depth':depth,'cameraLocation':[camera_x,-depth-5,camera_z],
        'cameraTarget':[camera_x,0,camera_z],'orthoScale':factor*width,'imageWidth':width,'imageHeight':height}

def build(root,payload,config,helpers):
    scope,new_run,image_record=helpers;blender=permission(config);run=new_run(root)
    record,_=image_record(root,payload['reference'],run,0);images=[record]
    require(record['metadata']['exifOrientation']==1 and record['width']*record['height']<=4_000_000,'RECONSTRUCTION_OUTLINE_IMAGE')
    expected=None
    if 'foregroundMask' in payload:
        mask_record,_=image_record(root,payload['foregroundMask'],run,1);images.append(mask_record)
        image=cv.imread(mask_record['preserved'],0)
        require(image.shape==(record['height'],record['width']) and set(np.unique(image)).issubset({0,255}),'RECONSTRUCTION_BINARY_MASK')
        contours,hierarchy=cv.findContours(image,cv.RETR_CCOMP,cv.CHAIN_APPROX_SIMPLE)
        require(len(contours)==1,'RECONSTRUCTION_OUTLINE_SINGLE_COMPONENT_NO_HOLES')
        q=contours[0];epsilon=.25
        while len(q)>512 and epsilon<=2:
            q=cv.approxPolyDP(contours[0],epsilon,True);epsilon+=.25
        points=q.reshape(-1,2).tolist();expected=image>0
    else:points=payload['outlinePx']
    geometry=geometry_from_outline(points,record['width'],record['height'],payload['frontWidthUnits'],payload['proposedDepthRatio'],payload['proposedSections'])
    if expected is None:
        expected=np.zeros((record['height'],record['width']),np.uint8);cv.fillPoly(expected,[np.rint(points).astype(np.int32)],255);expected=expected>0
    cv.imwrite(str(run/'observed-outline-mask.png'),expected.astype(np.uint8)*255)
    coordinates=' '.join(str(float(x))+','+str(float(y)) for x,y in points)
    (run/'observed-outline.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="'+str(record['width'])+'" height="'+str(record['height'])+'" viewBox="0 0 '+str(record['width'])+' '+str(record['height'])+'"><polygon points="'+coordinates+'" fill="none" stroke="black" stroke-width="1"/></svg>',encoding='utf8')
    save(run/'spatial.json',{'schemaVersion':1,'observedOutlinePx':points,'annotationProvenance':payload['provenance'],
        'frontBoundaryVertexMapping':list(range(len(points))),'geometry':geometry,'proposedSections':payload['proposedSections'],
        'scaleStatus':'Relative modelling units; caller-proposed width/depth, not a metric measurement.',
        'cameraAssumption':'front-orthographic; supplied explicitly, not recovered from the photograph',
        'unknownGeometry':['Front internal depth, parts, seams and relief','Side/back shapes and physical thickness','True camera perspective and physical scale']})
    job={'geometry':geometry,'output':str(run),'reference':record['preserved']};save(run/'outline-job.json',job)
    resources=scope(root,run/'blender-runtime',False);resources.mkdir()
    process=subprocess.run([str(blender),'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(Path(__file__).with_name('outline_adapter.py')),'--',str(run/'outline-job.json')],
        cwd=str(run),env={**os.environ,'BLENDER_USER_RESOURCES':str(resources)},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    (run/'construction-log.txt').write_bytes(process.stdout[-262144:]);require(process.returncode==0 and b'NOETRA_OUTLINE_BUILT' in process.stdout,'RECONSTRUCTION_OUTLINE_BUILD_FAILED')
    front={'id':'front','camera':'front','reference':record['preserved'],'width':record['width'],'height':record['height'],
        'annotations':[{'partId':'outline-object','polygon':points,'provenance':payload['provenance']}]}
    spec={'collection':'NOETRA_OUTLINE','parts':[{'id':'outline-object','objects':['Front_observed_outline','Sides_proposed','Rear_proposed']}],
        'parameters':[],'views':[front,{'id':'proposed-side','camera':'proposed-side','reference':record['preserved'],'width':record['width'],'height':record['height'],'annotations':[]}]}
    folder=render(root,run,spec,{},config,'initial',scope,beauty=True,export=True)
    values=measure(folder,spec)
    rendered=cv.imread(str(folder/'front-ids.png'),cv.IMREAD_UNCHANGED)[:,:,3]>127
    score=compare_masks(expected,rendered);accepted=score['silhouette_iou']>=.98 and score['boundary']['mean_px']<=1.5
    report={'runId':run.name,'kind':'front-outline-loft','images':images,'spatialSha256':hashlib.sha256((run/'spatial.json').read_bytes()).hexdigest(),
        'acceptedFrontSilhouette':bool(accepted),'frontMaskComparison':score,'partMeasurements':values,
        'outputs':{'blend':str(folder/'scene.blend'),'glb':str(folder/'scene.glb'),'drawing':str(run/'observed-outline.svg'),'proposedSideRender':str(folder/'proposed-side-beauty.png')},
        'unknowns':['This is an outline-constrained initial loft, not detailed car reconstruction.',
            'A supplied outline/mask is required; automatic general foreground segmentation is not configured.',
            'Front cap fill and every hidden surface are hypotheses. No missing-part identity is known from the silhouette.',
            'The front-orthographic assumption is unsuitable for an uncalibrated oblique/perspective car photo.',
            'Front overlap does not prove hidden shape; rejected silhouette fits remain review drafts.']}
    names=['source.blend','spatial.json','outline-job.json','construction-log.txt','observed-outline.svg','observed-outline-mask.png']+[p.relative_to(run).as_posix() for p in folder.iterdir() if p.is_file()]
    report['artifactDigests']={n:hashlib.sha256((run/n).read_bytes()).hexdigest() for n in names};save(run/'report.json',report)
    return {k:v for k,v in report.items() if k not in ['images','artifactDigests','partMeasurements']}
