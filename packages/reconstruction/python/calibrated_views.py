"""Strict local manifest route for calibrated multiview visual-hull geometry."""
from pathlib import Path
import json,hashlib,time,shutil
import numpy as np
from PIL import Image
from geometry import require
from part_correction import save
from observations import _keys,_text,_identifier,checked_image,validate_camera
from visual_hull import fuse_silhouettes

def load_calibrated_views(root,manifest_path,scope):
    path=scope(root,manifest_path);require(path.suffix.lower()=='.json' and path.stat().st_size<=4_000_000,'RECONSTRUCTION_HULL_MANIFEST_LIMIT')
    original=path.read_bytes();manifest=json.loads(original.decode('utf8'))
    _keys(manifest,['schemaVersion','provenance','bounds','grid','views']);require(type(manifest['schemaVersion']) is int and manifest['schemaVersion']==1,'RECONSTRUCTION_HULL_MANIFEST_VERSION');_text(manifest['provenance'])
    require(type(manifest['grid']) is int and 16<=manifest['grid']<=192,'RECONSTRUCTION_HULL_GRID')
    _keys(manifest['bounds'],['minimum','maximum']);low=np.asarray(manifest['bounds']['minimum'],float);high=np.asarray(manifest['bounds']['maximum'],float)
    require(low.shape==high.shape==(3,) and np.isfinite([low,high]).all() and (high>low).all() and np.max(np.abs([low,high]))<=1e6,'RECONSTRUCTION_HULL_BOUNDS')
    require(isinstance(manifest['views'],list) and 3<=len(manifest['views'])<=16,'RECONSTRUCTION_HULL_VIEW_COUNT')
    views=[];ids=set();captures=set();actual_hashes=set();pixel_budget=0
    for record in manifest['views']:
        _keys(record,['id','image','mask','camera','origin']);_identifier(record['id']);require(record['id'] not in ids,'RECONSTRUCTION_HULL_DUPLICATE_VIEW');ids.add(record['id'])
        _keys(record['origin'],['kind','captureId','provenance'],['parentViewIds']);origin=record['origin'];require(origin['kind'] in ['actual_photo','reference_artwork','rendered'],'RECONSTRUCTION_HULL_ORIGIN');_text(origin['captureId']);_text(origin['provenance'])
        require(origin['captureId'] not in captures,'RECONSTRUCTION_HULL_DUPLICATE_VIEW');captures.add(origin['captureId'])
        if 'parentViewIds' in origin:
            require(isinstance(origin['parentViewIds'],list) and 1<=len(origin['parentViewIds'])<=16 and all(isinstance(p,str) and 0<len(p)<=160 for p in origin['parentViewIds']),'RECONSTRUCTION_HULL_LINEAGE')
        validate_camera(record['camera']);scope(root,record['image']['path']);rgb=checked_image(root,record['image']);h,w=rgb.shape[:2];pixel_budget+=h*w;require(pixel_budget<=64_000_000,'RECONSTRUCTION_HULL_PIXEL_LIMIT')
        mask_path=scope(root,record['mask']['path'])
        with Image.open(mask_path) as picture:require(picture.format=='PNG','RECONSTRUCTION_HULL_MASK_PNG')
        pixels=checked_image(root,record['mask']);require(pixels.shape[:2]==(h,w) and np.array_equal(pixels[:,:,0],pixels[:,:,1]) and np.array_equal(pixels[:,:,0],pixels[:,:,2]) and np.isin(pixels,[0,255]).all(),'RECONSTRUCTION_HULL_BINARY_MASK')
        mask=pixels[:,:,0]>127;require(mask.any(),'RECONSTRUCTION_HULL_MASK')
        if origin['kind']=='actual_photo':
            require(record['image']['sha256'] not in actual_hashes,'RECONSTRUCTION_HULL_DUPLICATE_VIEW');actual_hashes.add(record['image']['sha256'])
            require('parentViewIds' not in origin,'RECONSTRUCTION_HULL_LINEAGE')
        camera=record['camera'];views.append({'mask':mask,'K':camera['K'],'R':camera['R'],'t':camera['t']})
    return manifest,views,{'source':str(path),'sha256':hashlib.sha256(original).hexdigest()}

def reconstruct_from_views(root,payload,config,helpers):
    """payload={'manifest':path}; helpers=(scope,new_run,image_record).

    This route reads images, masks and calibration only. In particular it accepts
    no source mesh path and never opens a source BLEND/GLB/PLY to reconstruct.
    """
    _keys(payload,['manifest']);scope,new_run,image_record=helpers;started=time.monotonic()
    manifest,views,source=load_calibrated_views(root,payload['manifest'],scope)
    run=new_run(root);shutil.copyfile(source['source'],run/'manifest.json')
    require(hashlib.sha256((run/'manifest.json').read_bytes()).hexdigest()==source['sha256'],'RECONSTRUCTION_OBSERVATION_SOURCE_CHANGED')
    source={**source,'preserved':str(run/'manifest.json')};images=[]
    for i,view in enumerate(manifest['views']):
        for kind in ['image','mask']:
            record,_=image_record(root,view[kind]['path'],run,i*2+(kind=='mask'))
            require(record['sha256']==view[kind]['sha256'],'RECONSTRUCTION_OBSERVATION_SOURCE_CHANGED');images.append(record)
    try:
        mesh,geometry=fuse_silhouettes(views,manifest['bounds'],manifest['grid']);mesh.export(run/'mesh.ply');mesh.export(run/'mesh.glb')
        rendered=None
        if config.get('allowBlenderExecution') is True:
            from calibrated_export import render_calibrated_hull
            rendered=render_calibrated_hull(run,manifest,config)
        # Recheck source files after extraction as well as before preserving them.
        require(hashlib.sha256(Path(source['source']).read_bytes()).hexdigest()==source['sha256'],'RECONSTRUCTION_OBSERVATION_SOURCE_CHANGED')
        for view in manifest['views']:
            for kind in ['image','mask']:
                path=scope(root,view[kind]['path']);require(hashlib.sha256(path.read_bytes()).hexdigest()==view[kind]['sha256'],'RECONSTRUCTION_OBSERVATION_SOURCE_CHANGED')
        kinds={view['origin']['kind'] for view in manifest['views']};derived='rendered' in kinds
        scope_label='derived-render-silhouette-hull; no independent physical validation' if derived else ('reference-artwork-silhouette-hull; hidden geometry unvalidated' if 'reference_artwork' in kinds else 'calibrated-photo-silhouette-hull; hidden concavities unvalidated')
        report={'runId':run.name,'kind':'calibrated-multiview-visual-hull','sourceManifest':source,'images':images,
            'views':[{'id':v['id'],'origin':v['origin'],'imageSha256':v['image']['sha256'],'maskSha256':v['mask']['sha256'],'camera':v['camera']} for v in manifest['views']],
            'geometry':geometry,'validationScope':scope_label,'sourceMeshRead':False,'derivedViewCount':sum(v['origin']['kind']=='rendered' for v in manifest['views']),
            'outputs':{'ply':str(run/'mesh.ply'),'glb':str(run/'mesh.glb')},'runtimeSeconds':time.monotonic()-started,
            'unknowns':geometry['unknowns']+(['Rendered views transfer constraints from the producer hypothesis; reconstructing them does not validate that producer against the original reference.'] if derived else []),
            'artifactDigests':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in run.iterdir() if p.is_file() and p.suffix in ['.json','.ply','.glb','.blend','.png','.jpg','.jpeg']}}
        if rendered is not None:
            report['renderVerification']=rendered
            if isinstance(rendered,dict):report['outputs'].update(rendered.get('outputs',{}))
        save(run/'report.json',report);return {k:v for k,v in report.items() if k not in ['images','artifactDigests']}
    except Exception as error:
        save(run/'failure.json',{'kind':'calibrated-multiview-visual-hull','status':'failed','reason':str(error),'sourceMeshRead':False});raise
