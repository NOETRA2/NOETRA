"""Opt-in local reconstruction worker. Fixed operations; no eval, providers or network."""
import sys,json,os,uuid,hashlib,time,shutil,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np
import cv2 as cv
from PIL import Image
from geometry import require,finite,triangulate_checked,plane_grid,grid_points,project,optimize_scales,compare_masks,symmetric_distance,exr_channels
cv.setNumThreads(2)
Image.MAX_IMAGE_PIXELS=24_000_000
ACTIVE_ROOT=None

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def scope(root,path,exists=True):
    p=Path(path)
    require(p.is_absolute(),'RECONSTRUCTION_ABSOLUTE_PATH')
    p=Path(os.path.abspath(p));require(p!=root and p.is_relative_to(root),'RECONSTRUCTION_OUTSIDE_PROJECT')
    q=p
    while q!=root:
        require(not q.is_symlink() and not (hasattr(q,'is_junction') and q.is_junction()),'RECONSTRUCTION_SYMLINK')
        q=q.parent
    if exists:require(p.exists() and p.resolve().is_relative_to(root),'RECONSTRUCTION_MISSING_FILE')
    return p
def dump(path,value):
    if ACTIVE_ROOT is not None:scope(ACTIVE_ROOT,path,False)
    path.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')
def new_run(root):
    base=scope(root,root/'.noetra'/'reconstruction',False)
    base.mkdir(parents=True,exist_ok=True)
    require(sum(p.is_dir() for p in base.iterdir())<64,'RECONSTRUCTION_RUN_LIMIT')
    run=scope(root,base/str(uuid.uuid4()),False);run.mkdir()
    return run
def load_run(root,identifier):
    require(str(uuid.UUID(identifier))==identifier,'RECONSTRUCTION_RUN_ID')
    run=scope(root,root/'.noetra'/'reconstruction'/identifier)
    report=read_json(run/'report.json')
    for record in report.get('images',[]):
        for key in ['source','preserved']:
            p=scope(root,record[key]);require(p.is_file() and digest(p)==record['sha256'],'RECONSTRUCTION_SOURCE_CHANGED')
    if report.get('prior'):
        for key in ['source','preserved']:
            p=scope(root,report['prior'][key]);require(digest(p)==report['prior']['sha256'],'RECONSTRUCTION_PRIOR_CHANGED')
    if report.get('sourceManifest'):
        for key in ['source','preserved']:
            p=scope(root,report['sourceManifest'][key]);require(digest(p)==report['sourceManifest']['sha256'],'RECONSTRUCTION_OBSERVATION_SOURCE_CHANGED')
    if report.get('parentModel'):
        for key in ['source','preserved']:
            p=scope(root,report['parentModel'][key]);require(digest(p)==report['parentModel']['sha256'],'RECONSTRUCTION_PARENT_MODEL_CHANGED')
    if report.get('sourceCheckpoint'):
        p=scope(root,report['sourceCheckpoint']['source']);require(digest(p)==report['sourceCheckpoint']['sha256'],'RECONSTRUCTION_SHAPE_CHECKPOINT_CHANGED')
    if report.get('spatialSha256'):
        p=scope(root,run/'spatial.json');require(digest(p)==report['spatialSha256'],'RECONSTRUCTION_SPATIAL_CHANGED')
    for filename,expected in report.get('artifactDigests',{}).items():
        p=scope(root,run/filename);require(p.is_file() and digest(p)==expected,'RECONSTRUCTION_ARTIFACT_CHANGED')
    return run,report
def read_json(path):
    if ACTIVE_ROOT is not None:scope(ACTIVE_ROOT,path)
    require(path.is_file() and path.stat().st_size<4_000_000,'RECONSTRUCTION_MANIFEST_LIMIT')
    return json.loads(path.read_text(encoding='utf-8'))
def image_record(root,path,run,index):
    source=scope(root,path)
    require(source.is_file() and source.suffix.lower() in ['.png','.jpg','.jpeg'] and source.stat().st_size<=24*1024*1024,'RECONSTRUCTION_IMAGE_FORMAT')
    originals=run/'originals';originals.mkdir(exist_ok=True)
    saved=originals/(str(index)+source.suffix.lower())
    before=digest(source);shutil.copyfile(source,saved);require(digest(saved)==before and digest(source)==before,'RECONSTRUCTION_SOURCE_CHANGED')
    with Image.open(saved) as im:
        require(im.width*im.height<=24_000_000 and max(im.size)<=8192,'RECONSTRUCTION_IMAGE_LIMIT')
        require(getattr(im,'n_frames',1)==1,'RECONSTRUCTION_ANIMATION_UNSUPPORTED')
        rgb=np.asarray(im.convert('RGB')).copy()
        alpha=np.asarray(im.getchannel('A')).copy() if 'A' in im.getbands() else np.empty((0,),np.uint8)
        orientation=int(im.getexif().get(274,1))
        metadata={'format':im.format,'mode':im.mode,'size':list(im.size),'exifOrientation':orientation,'exifBytesPreservedInOriginal':bool(im.getexif())}
    grey=cv.cvtColor(rgb,cv.COLOR_RGB2GRAY)
    edges=cv.Canny(grey,70,150)
    gx=cv.Sobel(grey,cv.CV_32F,1,0);gy=cv.Sobel(grey,cv.CV_32F,0,1)
    np.savez_compressed(run/('image-'+str(index)+'.npz'),rgb=rgb,alpha=alpha,geometric_edges=edges,gradient_x=gx,gradient_y=gy)
    cv.imwrite(str(run/('edges-'+str(index)+'.png')),edges)
    small=cv.resize(grey,(16,16),interpolation=cv.INTER_AREA)
    return {'id':'image-'+str(index),'source':str(source),'preserved':str(saved),'sha256':before,'metadata':metadata,
      'width':rgb.shape[1],'height':rgb.shape[0],'rgbArray':str(run/('image-'+str(index)+'.npz')),
      'geometricEdges':str(run/('edges-'+str(index)+'.png')),'blurLaplacianVariance':float(cv.Laplacian(grey,cv.CV_64F).var()),
      'meanObservedRGB':rgb.mean(axis=(0,1)).tolist(),'meanLuminance':float(grey.mean()),
      'perceptualHash':np.packbits(small>np.median(small)).tobytes().hex(),
      'semanticSegmentation':None,'depthMeasurement':None,'intrinsicMaterial':None},rgb

def inspect(root,payload):
    run=new_run(root);images=[]
    for i,path in enumerate(payload['images']):
        record,_=image_record(root,path,run,i)
        record['exactDuplicateOf']=next((r['id'] for r in images if r['sha256']==record['sha256']),None)
        images.append(record)
    report={'runId':run.name,'kind':'image-structure','images':images,'semanticSegmentation':'not supplied; no general semantic model configured',
      'geometricSegmentation':'Canny/Sobel image structure; photometric edges are not proven physical creases',
      'lightingVariation':{'meanLuminanceRange':[min(i['meanLuminance'] for i in images),max(i['meanLuminance'] for i in images)]},
      'unknowns':['Object category and physical part boundaries','Dense measured depth and normals','Intrinsic roughness, metalness, lighting and metric scale']}
    dump(run/'report.json',report)
    return {'runId':run.name,'artifactDirectory':str(run),'images':images,'unknowns':report['unknowns']}

def corners(rgb,shape):
    grey=cv.cvtColor(rgb,cv.COLOR_RGB2GRAY)
    ok,pts=cv.findChessboardCorners(grey,tuple(shape),cv.CALIB_CB_ADAPTIVE_THRESH|cv.CALIB_CB_NORMALIZE_IMAGE)
    if ok:pts=cv.cornerSubPix(grey,pts,(7,7),(-1,-1),(cv.TERM_CRITERIA_EPS|cv.TERM_CRITERIA_MAX_ITER,40,.001))
    else:ok,pts=cv.findChessboardCornersSB(grey,tuple(shape),flags=cv.CALIB_CB_NORMALIZE_IMAGE)
    return pts.reshape(-1,2).astype(np.float32) if ok else None

def reconstruct(root,payload):
    start=time.perf_counter();run=new_run(root);images=[];detected=[];size=None;hashes=set();shape=payload['pattern']
    require(payload['holdoutPair']<len(payload['pairs']),'RECONSTRUCTION_HOLDOUT')
    for pair_id,pair in enumerate(payload['pairs']):
        pts=[]
        for side in ['left','right']:
            record,rgb=image_record(root,pair[side],run,len(images))
            require(record['sha256'] not in hashes,'RECONSTRUCTION_DUPLICATE_FRAMES');hashes.add(record['sha256'])
            require(record['metadata']['exifOrientation']==1,'RECONSTRUCTION_ORIENTATION_UNSUPPORTED')
            current=(record['width'],record['height']);require(size is None or current==size,'RECONSTRUCTION_IMAGE_SIZE');size=current
            record['pair']=pair_id;record['side']=side;images.append(record)
            found=corners(rgb,shape);pts.append(found)
            annotation=rgb.copy()
            if found is not None:cv.drawChessboardCorners(annotation,tuple(shape),found[:,None,:],True)
            cv.imwrite(str(run/('annotated-'+str(len(images)-1)+'.png')),cv.cvtColor(annotation,cv.COLOR_RGB2BGR))
        if all(p is not None for p in pts):
            # Resolve the known rectangular target's 180-degree indexing ambiguity.
            if np.dot(pts[0][shape[0]-1]-pts[0][0],pts[1][shape[0]-1]-pts[1][0])<0:pts[1]=pts[1][::-1].copy()
            detected.append((pair_id,pts))
    training=[p for i,p in detected if i!=payload['holdoutPair']]
    holdouts=[p for i,p in detected if i==payload['holdoutPair']]
    require(len(training)>=6 and len(holdouts)==1,'RECONSTRUCTION_INSUFFICIENT_COVERAGE')
    unit=payload.get('squareSizeMetres',1.)
    require(unit>0,'RECONSTRUCTION_SCALE')
    obj=np.zeros((shape[0]*shape[1],3),np.float32);obj[:,:2]=np.mgrid[0:shape[0],0:shape[1]].T.reshape(-1,2)*unit
    board=[obj.copy() for _ in training]
    p1=[p[0][:,None,:] for p in training];p2=[p[1][:,None,:] for p in training]
    flags=cv.CALIB_FIX_K3
    rms1,K1,D1,_,_=cv.calibrateCamera(board,p1,size,None,None,flags=flags)
    rms2,K2,D2,_,_=cv.calibrateCamera(board,p2,size,None,None,flags=flags)
    rms,K1,D1,K2,D2,R,T,E,F=cv.stereoCalibrate(board,p1,p2,K1,D1,K2,D2,size,flags=cv.CALIB_FIX_INTRINSIC,
        criteria=(cv.TERM_CRITERIA_MAX_ITER|cv.TERM_CRITERIA_EPS,80,1e-7))
    require(np.isfinite(rms) and rms<3,'RECONSTRUCTION_CALIBRATION_ERROR')
    left,right=holdouts[0]
    xyz,valid,err,angles=triangulate_checked(left,right,K1,D1,K2,D2,R,T)
    require(valid.all(),'RECONSTRUCTION_GRID_OUTLIERS')
    surface=plane_grid(xyz,shape)
    require(surface['planarity_rms']<.20*np.mean(surface['steps']),'RECONSTRUCTION_NONPLANAR_TARGET')
    cameras=[];observed=[];hold=payload['holdoutPair']
    for index,(side,K,D,rot,trans,points) in enumerate([('left',K1,D1,np.eye(3),np.zeros((3,1)),left),('right',K2,D2,R,T,right)]):
        source=next(i for i in images if i['pair']==hold and i['side']==side)
        with np.load(source['rgbArray']) as stored:rgb=stored['rgb'].copy()
        und=cv.undistort(rgb,K,D,None,K)
        uv=cv.undistortPoints(points[:,None,:],K,D,P=K).reshape(-1,2)
        observed.append(uv)
        mask=np.zeros((size[1],size[0]),np.uint8);hull=cv.convexHull(uv.astype(np.float32)).astype(np.int32)
        cv.fillConvexPoly(mask,hull,255)
        labels=np.zeros(mask.shape,np.uint16);tiles=[]
        for row in range(shape[1]-1):
            for col in range(shape[0]-1):
                ids=[row*shape[0]+col,row*shape[0]+col+1,(row+1)*shape[0]+col+1,(row+1)*shape[0]+col]
                poly=uv[ids];identifier='tile-'+str(row)+'-'+str(col)
                cv.fillConvexPoly(labels,np.round(poly).astype(np.int32),len(tiles)+1)
                tiles.append({'id':identifier,'landmarks':ids,'boundary':poly.tolist(),'boundaryKind':'paint-pattern edge, not a physical ridge'})
        cv.imwrite(str(run/(side+'-reference.png')),cv.cvtColor(und,cv.COLOR_RGB2BGR))
        cv.imwrite(str(run/(side+'-mask.png')),mask)
        np.savez_compressed(run/(side+'-parts.npz'),semantic_grid_mask=mask,geometric_tile_labels=labels,observed_landmarks=uv)
        cameras.append({'id':side,'K':K.tolist(),'R':rot.tolist(),'T':trans.ravel().tolist(),'distortion':D.ravel().tolist(),
            'width':size[0],'height':size[1],'reference':str(run/(side+'-reference.png')),'mask':str(run/(side+'-mask.png')),
            'landmarks':uv.tolist(),'parts':tiles,'imageDomain':'undistorted, full original resolution, no crop'})
    np.savez_compressed(run/'triangulated-observations.npz',xyz=xyz,valid=valid,reprojection_error=err,triangulation_angle_degrees=angles)
    colours=[];left_image=cv.cvtColor(cv.imread(cameras[0]['reference']),cv.COLOR_BGR2RGB)
    for tile in cameras[0]['parts']:
        q=np.mean(np.asarray(tile['boundary']),axis=0).round().astype(int)
        patch=left_image[max(0,q[1]-2):q[1]+3,max(0,q[0]-2):q[0]+3]
        colours.append(np.median(patch.reshape(-1,3),axis=0).astype(float).tolist())
    spatial={'schemaVersion':1,'id':run.name,'objectType':'known calibration-grid sheet','surface':surface,'cameras':cameras,
      'parts':[{'id':t['id'],'landmarkIds':t['landmarks'],'observedRGB':c,'materialStatus':'view-specific observed RGB, not recovered intrinsic reflectance',
                'geometryKind':'open sheet; thickness unknown','sourceRegions':{v['id']:v['parts'][i]['boundary'] for v in cameras}} for i,(t,c) in enumerate(zip(cameras[0]['parts'],colours))],
      'initialScale':payload['initialScale'],'bestScale':payload['initialScale'],'revision':1,
      'scaleStatus':'caller-supplied metres; measurement authenticity not verified' if 'squareSizeMetres' in payload else 'relative checker-square units; not metric',
      'unknownGeometry':['Paper/board exterior beyond the detected inner grid','Thickness and back side','Non-planar deformation below observation accuracy'],
      'confidence':'No calibrated probability assigned; report residuals and coverage instead'}
    dump(run/'spatial.json',spatial);dump(run/'spatial-r1.json',spatial)
    # Conditional model-derived maps, never labelled measured photograph depth.
    normal=finite(surface['normal']);origin=finite(surface['centre'])
    for camera in cameras:
        rot=finite(camera['R']);trans=finite(camera['T']);K=finite(camera['K'])
        yy,xx=np.indices((camera['height'],camera['width']));rays=np.stack([xx,yy,np.ones_like(xx)],axis=-1)@np.linalg.inv(K).T
        nc=rot@normal;pc=rot@origin+trans;den=rays@nc
        depth=np.full(den.shape,np.nan,np.float32);support=cv.imread(camera['mask'],0)>0
        support &= np.abs(den)>1e-8
        depth[support]=(np.dot(nc,pc)/den[support]).astype(np.float32)
        normals=np.full((*den.shape,3),np.nan,np.float32);normals[support]=nc
        np.savez_compressed(run/(camera['id']+'-model-depth-normal.npz'),camera_z_depth=depth,normal_camera=normals,support=support)
    report={'runId':run.name,'kind':'planar-calibration-grid-proof','images':images,'calibrationTrainingPairs':len(training),'heldOutPair':hold,
      'spatialSha256':digest(run/'spatial.json'),
      'cameras':[{k:v for k,v in c.items() if k not in ['parts','landmarks']} for c in cameras],
      'calibration':{'left_rms_px':rms1,'right_rms_px':rms2,'stereo_rms_px':rms,'trainingJointRefinement':'OpenCV nonlinear calibration of intrinsics/target poses and stereo extrinsics; not general scene bundle adjustment'},
      'triangulation':{'points':len(xyz),'accepted':int(valid.sum()),'maximum_reprojection_error_px':float(err.max()),'minimum_parallax_degrees':float(angles.min()),'planarity_rms_relative_units':surface['planarity_rms']},
      'scaleStatus':spatial['scaleStatus'],'spatialModel':str(run/'spatial.json'),'geometryGroundTruthError':None,
      'denseDepthStatus':'Plane-model-derived map constrained by sparse stereo; not measured or learned dense depth',
      'semanticSegmentation':'Known grid detector and its observed inner-grid region; not general semantic segmentation',
      'geometricSegmentation':'Canny image edges plus observed grid-cell paint boundaries, not physical panel creases',
      'unknowns':spatial['unknownGeometry']+['Intrinsic materials and lighting','General car/organic reconstruction','General semantic segmentation, COLMAP, VGGT, MapAnything, Open3D and Mitsuba adapters are not implemented'],
      'runtime_seconds':time.perf_counter()-start,'optimization':None,'constructionPrepared':False}
    dump(run/'report.json',report)
    return {'runId':run.name,'artifactDirectory':str(run),'trainingPairs':len(training),'calibration':report['calibration'],'triangulation':report['triangulation'],'scaleStatus':report['scaleStatus'],'unknowns':report['unknowns']}

def prepare_construction(run,report):
    require(report['kind']=='planar-calibration-grid-proof','RECONSTRUCTION_RUN_KIND')
    template=Path(__file__).with_name('blender_adapter.py')
    target=run/'construction.py';shutil.copyfile(template,target)
    report['constructionPrepared']=True;report['constructionSha256']=digest(template)
    dump(run/'report.json',report)
    return {'runId':run.name,'script':str(target),'scriptSha256':report['constructionSha256'],'spatialModel':str(run/'spatial.json'),'executed':False}

def compare_render(run,spatial,stage,scales):
    points=grid_points(spatial['surface'],scales);results={}
    for camera in spatial['cameras']:
        image=cv.imread(str(run/(stage+'-'+camera['id']+'.png')),cv.IMREAD_UNCHANGED)
        require(image is not None and image.ndim==3 and image.shape[2]==4,'RECONSTRUCTION_RENDER_MISSING')
        pass_file=run/(stage+'-'+camera['id']+'-passes.exr')
        require(pass_file.is_file(),'RECONSTRUCTION_RENDER_PASSES_MISSING')
        channels=exr_channels(pass_file)
        require(any('.Depth.' in c for c in channels) and any('.Normal.' in c for c in channels),'RECONSTRUCTION_RENDER_PASSES_MISSING')
        reference=cv.imread(camera['reference']);mask=cv.imread(camera['mask'],0)>0
        require(image.shape[:2]==reference.shape[:2],'RECONSTRUCTION_IMAGE_SIZE')
        rendered_mask=image[:,:,3]>127;values=compare_masks(mask,rendered_mask)
        prediction=project(points,finite(camera['K']),finite(camera['R']),finite(camera['T']))
        observed=finite(camera['landmarks']);distances=np.linalg.norm(prediction-observed,axis=1)
        region=mask&rendered_mask
        a=cv.Canny(cv.cvtColor(reference,cv.COLOR_BGR2GRAY),70,150)>0
        b=cv.Canny(cv.cvtColor(image[:,:,:3],cv.COLOR_BGR2GRAY),70,150)>0
        a &= mask;b &= rendered_mask
        edge=symmetric_distance(a,b)
        values.update({'landmark_rmse_px':float(np.sqrt(np.mean(distances**2))),'maximum_landmark_error_px':float(distances.max()),
            'renderedDepthNormalPasses':str(pass_file),'referenceDepthNormalError':None,
            'exrChannels':channels,
            'apparent_edge_distance':edge,'observed_RGB_mae':float(np.abs(image[:,:,:3][region].astype(float)-reference[region]).mean()) if region.any() else None,
            'colourScope':'View-specific display RGB, not intrinsic PBR material recovery',
            'parts':[{'id':part['id'],'boundary_landmark_rmse_px':float(np.sqrt(np.mean(distances[part['landmarkIds']]**2)))} for part in spatial['parts']]})
        overlay=reference.copy();ref_boundary=cv.morphologyEx(mask.astype(np.uint8),cv.MORPH_GRADIENT,np.ones((3,3),np.uint8))>0
        gen_boundary=cv.morphologyEx(rendered_mask.astype(np.uint8),cv.MORPH_GRADIENT,np.ones((3,3),np.uint8))>0
        overlay[ref_boundary]=(0,255,0);overlay[gen_boundary]=(255,0,255)
        cv.imwrite(str(run/(stage+'-'+camera['id']+'-overlay.png')),overlay)
        values['overlay']=str(run/(stage+'-'+camera['id']+'-overlay.png'));results[camera['id']]=values
    return results

def optimize(root,run,report,payload,config):
    require(config.get('allowBlenderExecution') is True,'RECONSTRUCTION_EXECUTION_NOT_APPROVED')
    blender=Path(config.get('blenderExecutable',''))
    require(blender.is_absolute() and blender.is_file(),'RECONSTRUCTION_BLENDER_UNAVAILABLE')
    require(report.get('constructionPrepared') is True,'RECONSTRUCTION_CONSTRUCTION_REQUIRED')
    spatial=read_json(run/'spatial.json');require(spatial['revision']==1,'RECONSTRUCTION_ALREADY_OPTIMIZED')
    template=Path(__file__).with_name('blender_adapter.py')
    require(digest(template)==report['constructionSha256'] and digest(run/'construction.py')==report['constructionSha256'],'RECONSTRUCTION_SCRIPT_CHANGED')
    for filename in ['before.blend','candidate.blend','before-left.png','candidate-left.png']:
        require(not (run/filename).exists(),'RECONSTRUCTION_EXISTING_EXPERIMENT')
    left=spatial['cameras'][0];initial=spatial['initialScale']
    proposal,calls,solver=optimize_scales(spatial['surface'],initial,finite(left['K']),finite(left['landmarks']),payload['maxEvaluations'])
    hypothesis={'mismatch':'Inner-grid scale causes projected boundary/landmark mismatch','parameters':['scale_x','scale_y'],
      'affectedParts':[p['id'] for p in spatial['parts']],'prediction':'Optimizing the left-view landmark residual may reduce mask and landmark errors in the right view; this is a hypothesis until rendered.',
      'constraintBounds':[.5,1.5],'initial':initial,'proposal':proposal,'checkpoint':str(run/'spatial-r1.json'),
      'trainingObservations':'Held-out stereo-pair left image, not the camera-calibration training pairs',
      'validationObservations':'Right image excluded from scale-optimizer objective; used earlier for stereo triangulation/plane pose, so this is not a wholly independent data split',
      'finiteDifferenceSearch':solver,'searchHistory':calls}
    dump(run/'experiment-prediction.json',hypothesis)
    job={**spatial,'candidateScale':proposal};dump(run/'spatial-render-job.json',job)
    start=time.perf_counter()
    resources=scope(root,run/'blender-runtime',False);resources.mkdir()
    blender_env={**os.environ,'BLENDER_USER_RESOURCES':str(resources)}
    process=subprocess.run([str(blender),'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(template),'--',str(run/'spatial-render-job.json'),str(run)],
        cwd=str(run),env=blender_env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=110,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    (run/'blender-log.txt').write_bytes(process.stdout[-262144:])
    require(process.returncode==0 and b'NOETRA_CONSTRUCTION_RENDER_COMPLETE' in process.stdout,'RECONSTRUCTION_BLENDER_FAILED')
    before=compare_render(run,spatial,'before',initial);after=compare_render(run,spatial,'candidate',proposal)
    # Never accept merely because an optimizer returned success or the script ran.
    accepted=all(after[v]['silhouette_iou']>=before[v]['silhouette_iou']-.001 and
                 after[v]['landmark_rmse_px']<before[v]['landmark_rmse_px'] and
                 after[v]['boundary']['mean_px']<=before[v]['boundary']['mean_px'] for v in ['left','right'])
    improvement=after['right']['silhouette_iou']-before['right']['silhouette_iou']
    accepted=accepted and improvement>.002
    chosen='candidate' if accepted else 'before'
    for extension in ['blend','glb']:shutil.copyfile(run/(chosen+'.'+extension),run/('best.'+extension))
    spatial['bestScale']=proposal if accepted else initial;spatial['revision']=2
    dump(run/'spatial-r2.json',spatial);dump(run/'spatial.json',spatial)
    report['spatialSha256']=digest(run/'spatial.json')
    report['optimization']={'accepted':bool(accepted),'best':chosen,'before':before,'candidate':after,'right_view_iou_improvement':improvement,
      'history':str(run/'experiment-prediction.json'),'render_seconds':time.perf_counter()-start,
      'geometryTruth':'No independent physical 3D ground truth for these photographs; only observed grid-image alignment is measured',
      'output':{'blend':str(run/'best.blend'),'glb':str(run/'best.glb')}}
    immutable=['spatial-r1.json','spatial-r2.json','experiment-prediction.json','spatial-render-job.json','construction.py',
               'before.blend','before.glb','candidate.blend','candidate.glb','best.blend','best.glb']
    immutable += [stage+'-'+view+suffix for stage in ['before','candidate'] for view in ['left','right'] for suffix in ['.png','-passes.exr']]
    report['artifactDigests']={name:digest(run/name) for name in immutable}
    dump(run/'report.json',report)
    return {'runId':run.name,'accepted':bool(accepted),'best':chosen,'before':{v:{k:x for k,x in before[v].items() if k!='parts'} for v in before},
      'candidate':{v:{k:x for k,x in after[v].items() if k!='parts'} for v in after},'outputs':report['optimization']['output'],'report':str(run/'report.json')}

def main(request):
    global ACTIVE_ROOT
    raw=Path(request['projectRoot']);require(raw.is_absolute() and raw.is_dir() and not raw.is_symlink(),'RECONSTRUCTION_PROJECT')
    root=raw.resolve();require(root!=Path(root.anchor) and root!=Path.home(),'RECONSTRUCTION_BROAD_SCOPE')
    ACTIVE_ROOT=root
    operation=request['operation'];payload=request['payload'];config=request['config']
    if operation=='inspect_image_structure':return inspect(root,payload)
    if operation=='analyze_reference_appearance':
        from appearance_analysis import analyze
        return analyze(root,payload,(new_run,image_record))
    if operation=='reconstruct_calibrated_views':
        from calibrated_views import reconstruct_from_views
        return reconstruct_from_views(root,payload,config,(scope,new_run,image_record))
    if operation=='reconstruct_multiview':return reconstruct(root,payload)
    if operation=='prepare_part_correction':
        from part_correction import prepare
        return prepare(root,payload,config,(scope,new_run,image_record))
    if operation=='build_outline_model':
        from outline_model import build
        return build(root,payload,config,(scope,new_run,image_record))
    if operation=='complete_from_prior':
        from structural_completion import complete
        return complete(root,payload,config,(scope,new_run,image_record))
    if operation in ['reconstruction_backends','reconstruct_photos']:
        from photo_pipeline import backends,reconstruct_photos
        if operation=='reconstruction_backends':return backends(config)
        return reconstruct_photos(root,payload,config,(scope,new_run,image_record))
    if operation=='paint_appearance_preview':
        from measured_paint import preview
        return preview(root,payload,config,(scope,new_run,image_record,load_run,read_json))
    run,report=load_run(root,payload['runId'])
    if operation in ['paint_surface_material','refine_base_surface']:
        from material_paint import paint
        return paint(root,run,report,payload,config,(scope,new_run,image_record))
    if operation=='refine_learned_surface':
        from learned_refinement import refine
        return refine(root,run,report,payload,config,(scope,new_run))
    if operation=='colorize_reconstruction':
        from colorize import colorize
        return colorize(root,run,report,payload,config,(scope,new_run,image_record))
    if operation=='repair_photo_surface':
        from photo_surface import repair_surface
        return repair_surface(root,run,report,config,(scope,new_run,load_run))
    if operation=='refine_photo_appearance':
        from photo_pipeline import refine_appearance
        return refine_appearance(root,run,report,config,new_run)
    if operation=='fit_photo_outline':
        from photo_pipeline import fit_photo_outline
        return fit_photo_outline(root,run,report,config,new_run)
    if operation in ['correct_parts','inspect_part_correction']:
        from part_correction import correct,inspect as inspect_parts
        if operation=='correct_parts':return correct(root,run,report,payload,config,scope)
        return inspect_parts(root,run,report,scope)
    if operation=='generate_3d_construction':return prepare_construction(run,report)
    if operation=='optimize_reconstruction':return optimize(root,run,report,payload,config)
    if operation=='compare_reference_render':
        require(report.get('optimization') is not None,'RECONSTRUCTION_NOT_RENDERED')
        spatial=read_json(run/'spatial.json');prediction=read_json(run/'experiment-prediction.json')
        return {'runId':run.name,'before':compare_render(run,spatial,'before',spatial['initialScale']),
                'candidate':compare_render(run,spatial,'candidate',prediction['proposal']),'acceptedBest':report['optimization']['best']}
    if operation=='export_reconstruction_report':
        compact={k:v for k,v in report.items() if k not in ['images','optimization','artifactDigests']}
        compact['sourceImages']=[{'id':r['id'],'sha256':r['sha256'],'width':r['width'],'height':r['height']} for r in report['images']]
        compact['optimization']=None if not report.get('optimization') else {k:v for k,v in report['optimization'].items() if k not in ['before','candidate']}
        compact['artifacts']=[{'name':p.name,'bytes':p.stat().st_size} for p in sorted(run.iterdir()) if p.is_file()]
        return compact
    raise ValueError('RECONSTRUCTION_UNKNOWN_OPERATION')

if __name__=='__main__':
    # Native libraries may write C/C++ diagnostics directly to descriptor 1.
    # Reserve the original pipe solely for our JSON envelope, including on error.
    protocol_fd=os.dup(1);os.dup2(2,1)
    def reply(value):os.write(protocol_fd,(json.dumps(value,allow_nan=False)+'\n').encode('utf8'))
    try:
        raw=sys.stdin.buffer.read(262145);require(len(raw)<=262144,'RECONSTRUCTION_INPUT_LIMIT')
        started=time.perf_counter();request=json.loads(raw);answer=main(request)
        answer['worker_seconds']=time.perf_counter()-started
        try:
            import psutil
            memory=psutil.Process().memory_info()
            answer['memory']={'worker_peak_bytes':getattr(memory,'peak_wset',None),'worker_rss_bytes':memory.rss,'includesBlenderChild':False,'source':'optional installed psutil; no dependency auto-install'}
        except ImportError:answer['memory']={'status':'unavailable; optional psutil not installed'}
        reply({'ok':True,**answer})
    except Exception as error:
        # Do not echo image metadata, secrets, source strings or arbitrary exceptions.
        code=str(error) if isinstance(error,ValueError) and str(error).startswith('RECONSTRUCTION_') else 'RECONSTRUCTION_WORKER_FAILED'
        reply({'ok':False,'error':code});sys.exit(1)
    finally:os.close(protocol_fd)
