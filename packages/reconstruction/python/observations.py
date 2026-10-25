"""Attributed image observations. Estimation never upgrades provenance to truth."""
from pathlib import Path
import hashlib,re,json
import numpy as np
import cv2 as cv
from PIL import Image
from geometry import require

ID=re.compile(r'^[a-z][a-z0-9-]{0,63}$')

def _keys(value,required,optional=()):
    require(isinstance(value,dict) and set(required)<=set(value) and set(value)<=set(required)|set(optional),'RECONSTRUCTION_OBSERVATION_FIELDS')

def _text(value):
    require(isinstance(value,str) and 0<len(value)<=2000,'RECONSTRUCTION_OBSERVATION_ATTRIBUTION')

def _number(value,minimum=0,maximum=1e12):
    require(isinstance(value,(int,float)) and not isinstance(value,bool) and np.isfinite(value) and minimum<=value<=maximum,'RECONSTRUCTION_OBSERVATION_NUMBER')

def _array(value,shape):
    try:a=np.asarray(value,float)
    except (ValueError,TypeError):raise ValueError('RECONSTRUCTION_OBSERVATION_ARRAY')
    require(a.shape==shape and np.isfinite(a).all(),'RECONSTRUCTION_OBSERVATION_ARRAY');return a

def _identifier(value):
    require(isinstance(value,str) and ID.fullmatch(value),'RECONSTRUCTION_OBSERVATION_ID')

def checked_image(root,record):
    """Recheck project-scoped source bytes before decoding a bounded image."""
    _keys(record,['path','sha256']);require(isinstance(record['path'],str) and 0<len(record['path'])<=4096,'RECONSTRUCTION_OBSERVATION_PATH')
    root=Path(root).resolve();path=Path(record['path']);path=path if path.is_absolute() else root/path
    path=path.resolve();require(path.is_relative_to(root) and path.is_file(),'RECONSTRUCTION_OBSERVATION_PATH')
    require(path.stat().st_size<=32_000_000,'RECONSTRUCTION_OBSERVATION_IMAGE_LIMIT')
    require(isinstance(record['sha256'],str) and re.fullmatch('[0-9a-f]{64}',record['sha256']),'RECONSTRUCTION_OBSERVATION_HASH')
    require(hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256'],'RECONSTRUCTION_OBSERVATION_SOURCE_CHANGED')
    with Image.open(path) as image:
        require(image.format in ['PNG','JPEG'] and image.width*image.height<=8_000_000,'RECONSTRUCTION_OBSERVATION_IMAGE_LIMIT')
        require(image.getexif().get(274,1)==1,'RECONSTRUCTION_OBSERVATION_EXIF_ORIENTATION')
        image.load();return np.asarray(image.convert('RGB')).copy()

def validate_camera(camera):
    _keys(camera,['convention','K','R','t','uncertaintyPx','provenance'])
    require(camera['convention']=='opencv-world-to-camera-x-right-y-down-z-forward','RECONSTRUCTION_CAMERA_CONVENTION')
    K=_array(camera['K'],(3,3));R=_array(camera['R'],(3,3));_array(camera['t'],(3,))
    require(K[0,0]>0 and K[1,1]>0 and np.allclose(K[2],[0,0,1]) and abs(K[1,0])<1e-8,'RECONSTRUCTION_CAMERA_INTRINSICS')
    require(np.allclose(R@R.T,np.eye(3),atol=1e-6) and abs(np.linalg.det(R)-1)<1e-6,'RECONSTRUCTION_CAMERA_ROTATION')
    _number(camera['uncertaintyPx'],0,8192);_text(camera['provenance'])

def fit_observed_ellipse(mask=None,keypoints=None,image_size=None):
    """Estimate an image ellipse; reject incomplete support as a full-wheel constraint.

    Keypoints must sample the outer boundary, not arbitrary spoke/center points.
    A fitted 2D ellipse alone cannot establish a physical circle or camera pose.
    """
    require((mask is None)!=(keypoints is None),'RECONSTRUCTION_ELLIPSE_INPUT')
    clipped=False;binary=None
    if mask is not None:
        binary=np.asarray(mask)
        require(binary.ndim==2 and min(binary.shape)>=3 and binary.size<=8_000_000 and np.isfinite(binary).all() and np.isin(binary,[0,1,255]).all(),'RECONSTRUCTION_ELLIPSE_MASK')
        binary=binary.astype(bool);h,w=binary.shape
        clipped=bool(binary[0].any() or binary[-1].any() or binary[:,0].any() or binary[:,-1].any())
        contours,_=cv.findContours(binary.astype(np.uint8),cv.RETR_EXTERNAL,cv.CHAIN_APPROX_NONE)
        require(len(contours)==1 and len(contours[0])>=12,'RECONSTRUCTION_ELLIPSE_COMPONENTS')
        points=contours[0][:,0].astype(float)
    else:
        require(image_size is not None and len(image_size)==2,'RECONSTRUCTION_ELLIPSE_IMAGE_SIZE')
        w,h=image_size;require(type(w) is int and type(h) is int,'RECONSTRUCTION_ELLIPSE_IMAGE_SIZE');_number(w,1,8192);_number(h,1,8192)
        require(w*h<=8_000_000,'RECONSTRUCTION_ELLIPSE_IMAGE_SIZE')
        points=np.asarray(keypoints,float)
        require(points.ndim==2 and points.shape[1]==2 and 12<=len(points)<=4096 and np.isfinite(points).all(),'RECONSTRUCTION_ELLIPSE_POINTS')
        require(((points>=0)&(points<np.array([w,h]))).all(),'RECONSTRUCTION_ELLIPSE_POINTS')
        clipped=bool((points<=.5).any() or (points>=np.array([w-1,h-1])-.5).any())
    (cx,cy),(diameter_x,diameter_y),angle=cv.fitEllipse(points.astype(np.float32))
    axes=np.array([diameter_x,diameter_y],float)/2
    require(np.isfinite([cx,cy,*axes,angle]).all() and axes.min()>1 and axes.max()<max(w,h)*4,'RECONSTRUCTION_ELLIPSE_DEGENERATE')
    radians=np.deg2rad(angle);rotation=np.array([[np.cos(radians),-np.sin(radians)],[np.sin(radians),np.cos(radians)]])
    q=(points-[cx,cy])@rotation/axes;radii=np.linalg.norm(q,axis=1);error=np.abs(radii-1)
    angles=np.mod(np.arctan2(q[:,1],q[:,0]),2*np.pi);support=error<.06
    bins=np.unique(np.floor(angles[support]/(2*np.pi)*36).astype(int));coverage=len(bins)/36
    sampled=np.sort(angles[support]);gap=float(np.rad2deg(np.diff(np.r_[sampled,sampled[0]+2*np.pi]).max())) if len(sampled) else 360.
    ellipse_mask=np.zeros((h,w),np.uint8);cv.ellipse(ellipse_mask,((cx,cy),(diameter_x,diameter_y),angle),1,-1)
    iou=None if binary is None else float((binary&(ellipse_mask>0)).sum()/max(1,(binary|(ellipse_mask>0)).sum()))
    # Sparse attributed boundary keypoints need coverage, not dense adjacent samples.
    enough=(coverage>=.83 if binary is not None else float(support.mean())>=.9) and gap<=35
    complete=bool(not clipped and enough and np.quantile(error,.95)<.08 and (iou is None or iou>=.92))
    return {'centerPx':[float(cx),float(cy)],'semiAxesPx':axes.tolist(),'angleDegrees':float(angle),
        'boundaryRadialErrorP95':float(np.quantile(error,.95)),'angularCoverage':coverage,'maximumSupportedGapDegrees':gap,
        'maskEllipseIoU':iou,'touchesImageBorder':clipped,'completeBoundarySupported':complete,
        'scope':'Image-space ellipse fitted to attributed boundary evidence; not proof of physical circularity or recovered hidden geometry.'}

def validate_observation_set(root,spec,expected_sha256=None):
    """Validate and load a bounded ObservationSet; source origin remains attributed.

    Returns dictionaries containing masks/points for numerical matching. Generated
    and rendered hypotheses may be inspected, but never independent validation.
    """
    _keys(spec,['schemaVersion','parts','views','scale','provenance']);require(type(spec['schemaVersion']) is int and spec['schemaVersion']==1,'RECONSTRUCTION_OBSERVATION_VERSION')
    try:encoded=json.dumps(spec,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    except (ValueError,TypeError,RecursionError):raise ValueError('RECONSTRUCTION_OBSERVATION_FIELDS')
    require(len(encoded)<=4_000_000,'RECONSTRUCTION_OBSERVATION_SET_LIMIT');identity=hashlib.sha256(encoded).hexdigest()
    require(expected_sha256 is None or identity==expected_sha256,'RECONSTRUCTION_OBSERVATION_SET_CHANGED')
    _text(spec['provenance']);_keys(spec['scale'],['status','units','uncertainty','provenance'],['unitsPerMeter'])
    scale=spec['scale'];require(scale['status'] in ['relative','measured'],'RECONSTRUCTION_SCALE_STATUS');_text(scale['units']);_text(scale['provenance']);_number(scale['uncertainty'])
    require(('unitsPerMeter' in scale)==(scale['status']=='measured'),'RECONSTRUCTION_SCALE_MEASUREMENT')
    if 'unitsPerMeter' in scale:_number(scale['unitsPerMeter'],1e-12)
    require(isinstance(spec['parts'],list) and 1<=len(spec['parts'])<=64,'RECONSTRUCTION_OBSERVATION_PART_LIMIT')
    parts={};objects=set()
    for part in spec['parts']:
        _keys(part,['id','label','objects','locked','provenance']);_identifier(part['id']);_text(part['label']);_text(part['provenance'])
        require(type(part['locked']) is bool and isinstance(part['objects'],list) and 1<=len(part['objects'])<=128,'RECONSTRUCTION_OBSERVATION_PART')
        require(part['id'] not in parts,'RECONSTRUCTION_OBSERVATION_DUPLICATE_ID')
        for name in part['objects']:
            _text(name);require(name not in objects,'RECONSTRUCTION_OBSERVATION_OBJECT_OVERLAP');objects.add(name)
        parts[part['id']]=part
    require(isinstance(spec['views'],list) and 1<=len(spec['views'])<=16,'RECONSTRUCTION_OBSERVATION_VIEW_LIMIT')
    views={};validation_hashes=set();validation_captures=set();mask_pixels=0;image_pixels=0
    for view in spec['views']:
        _keys(view,['id','image','origin','role','camera','observations']);_identifier(view['id']);require(view['id'] not in views,'RECONSTRUCTION_OBSERVATION_DUPLICATE_ID')
        _keys(view['origin'],['kind','captureId','provenance'],['parentViewIds'])
        origin=view['origin'];require(origin['kind'] in ['actual_photo','reference_artwork','generated','rendered'],'RECONSTRUCTION_OBSERVATION_ORIGIN');_text(origin['captureId']);_text(origin['provenance'])
        require(view['role'] in ['fit','heldout','inspection'],'RECONSTRUCTION_OBSERVATION_ROLE')
        require(origin['kind'] in ['actual_photo','reference_artwork'] or view['role']=='inspection','RECONSTRUCTION_HYPOTHESIS_VALIDATION')
        require(origin['kind']=='actual_photo' or view['role']!='heldout','RECONSTRUCTION_INDEPENDENT_PHOTO_REQUIRED')
        if origin['kind'] in ['generated','rendered'] or 'parentViewIds' in origin:
            require(isinstance(origin.get('parentViewIds'),list) and 1<=len(origin['parentViewIds'])<=16,'RECONSTRUCTION_OBSERVATION_LINEAGE')
            require(all(isinstance(parent,str) for parent in origin['parentViewIds']),'RECONSTRUCTION_OBSERVATION_LINEAGE')
        if origin['kind']=='actual_photo':require('parentViewIds' not in origin,'RECONSTRUCTION_OBSERVATION_LINEAGE')
        rgb=checked_image(root,view['image']);h,w=rgb.shape[:2];image_pixels+=h*w
        require(image_pixels<=64_000_000,'RECONSTRUCTION_OBSERVATION_IMAGE_LIMIT');validate_camera(view['camera'])
        if view['role']!='inspection':
            require(view['image']['sha256'] not in validation_hashes and origin['captureId'] not in validation_captures,'RECONSTRUCTION_DUPLICATE_VALIDATION_VIEW')
            validation_hashes.add(view['image']['sha256']);validation_captures.add(origin['captureId'])
        require(isinstance(view['observations'],list) and 1<=len(view['observations'])<=64,'RECONSTRUCTION_OBSERVATION_COUNT')
        observations={};assigned=np.zeros((h,w),bool)
        for observation in view['observations']:
            _keys(observation,['partId','provenance','uncertaintyPx'],['mask','keypoints','ellipseBoundary','requireCompleteEllipse'])
            pid=observation['partId'];require(pid in parts and pid not in observations,'RECONSTRUCTION_OBSERVATION_PART');_text(observation['provenance']);_number(observation['uncertaintyPx'],0,8192)
            require(any(k in observation for k in ['mask','keypoints','ellipseBoundary']),'RECONSTRUCTION_OBSERVATION_EMPTY')
            loaded={**observation}
            if 'mask' in observation:
                mask_pixels+=h*w;require(mask_pixels<=32_000_000,'RECONSTRUCTION_OBSERVATION_MASK_LIMIT')
                pixels=checked_image(root,observation['mask']);require(pixels.shape[:2]==(h,w),'RECONSTRUCTION_OBSERVATION_MASK_SIZE')
                require(np.array_equal(pixels[:,:,0],pixels[:,:,1]) and np.array_equal(pixels[:,:,0],pixels[:,:,2]) and np.isin(pixels,[0,255]).all(),'RECONSTRUCTION_OBSERVATION_BINARY_MASK')
                loaded['maskArray']=pixels[:,:,0]>127;require(loaded['maskArray'].any(),'RECONSTRUCTION_OBSERVATION_EMPTY_MASK')
                require(not (assigned&loaded['maskArray']).any(),'RECONSTRUCTION_OBSERVATION_MASK_OVERLAP');assigned|=loaded['maskArray']
            if 'keypoints' in observation:
                points=observation['keypoints'];require(isinstance(points,dict) and 1<=len(points)<=256,'RECONSTRUCTION_OBSERVATION_KEYPOINTS')
                for name,point in points.items():
                    _identifier(name);p=_array(point,(2,));require(((p>=0)&(p<np.array([w,h]))).all(),'RECONSTRUCTION_OBSERVATION_KEYPOINTS')
            if 'ellipseBoundary' in observation:
                loaded['ellipse']=fit_observed_ellipse(keypoints=observation['ellipseBoundary'],image_size=(w,h))
                if 'maskArray' in loaded:
                    # Boundary keypoints cannot silently upgrade a cut-off mask
                    # to complete evidence. Preserve both independent checks.
                    loaded['maskEllipse']=fit_observed_ellipse(mask=loaded['maskArray'])
                    loaded['ellipse']['completeBoundarySupported']&=loaded['maskEllipse']['completeBoundarySupported']
            elif observation.get('requireCompleteEllipse'):
                require('maskArray' in loaded,'RECONSTRUCTION_ELLIPSE_INPUT');loaded['ellipse']=fit_observed_ellipse(mask=loaded['maskArray'])
            if 'requireCompleteEllipse' in observation:
                require(type(observation['requireCompleteEllipse']) is bool,'RECONSTRUCTION_OBSERVATION_FIELDS')
                if observation['requireCompleteEllipse']:require(loaded['ellipse']['completeBoundarySupported'],'RECONSTRUCTION_WHEEL_BOUNDARY_INCOMPLETE')
            observations[pid]=loaded
        views[view['id']]={**view,'size':[w,h],'parts':observations,'independentValidation':origin['kind']=='actual_photo' and view['role']=='heldout'}
    for view in views.values():
        if view['origin']['kind']!='actual_photo':
            require(all(pid in views and pid!=view['id'] for pid in view['origin'].get('parentViewIds',[])),'RECONSTRUCTION_OBSERVATION_LINEAGE')
    def visit(identifier,ancestors):
        require(identifier not in ancestors,'RECONSTRUCTION_OBSERVATION_LINEAGE')
        for parent in views[identifier]['origin'].get('parentViewIds',[]):visit(parent,ancestors|{identifier})
    for identifier in views:visit(identifier,set())
    return {'schemaVersion':1,'sha256':identity,'parts':parts,'views':views,'scale':scale,'provenance':spec['provenance'],
        'scope':'Origins and annotations are attributed claims; hashes establish byte identity, not authenticity. No measured 3D depth or automatic semantics.'}
