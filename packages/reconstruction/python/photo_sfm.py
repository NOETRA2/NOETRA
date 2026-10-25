"""Actual CPU COLMAP feature matching, camera recovery and sparse point clouds.

No synthetic viewpoints are substituted for supplied photographs, and sparse
landmarks are not represented as a verified closed object surface.
"""
from pathlib import Path
import json,time,contextlib,hashlib
import numpy as np
from PIL import Image
from geometry import require
from part_correction import save

def colmap_reconstruct(root,payload,config,helpers):
    scope,new_run,image_record=helpers
    require(len(payload['images'])>=3,'RECONSTRUCTION_COLMAP_NEEDS_MULTIPLE_VIEWS')
    require(not payload.get('foregroundMask'),'RECONSTRUCTION_COLMAP_MASK_UNSUPPORTED')
    run=new_run(root);pictures=run/'photos';pictures.mkdir();records=[];seen=set();started=time.monotonic()
    for i,path in enumerate(payload['images']):
        record,_=image_record(root,path,run,i)
        require(record['sha256'] not in seen,'RECONSTRUCTION_DUPLICATE_VIEW');seen.add(record['sha256'])
        require(record['metadata']['exifOrientation']==1,'RECONSTRUCTION_EXIF_ORIENTATION')
        with Image.open(record['preserved']) as image:
            # Feature-image scaling is explicit; byte-exact originals remain intact.
            image=image.convert('RGB');image.thumbnail((1600,1600));image.save(pictures/(str(i).zfill(3)+'.png'))
        records.append(record)
    try:
        import pycolmap as c,open3d as o3d
        database=run/'features.db';models=run/'colmap';models.mkdir()
        extraction=c.FeatureExtractionOptions();extraction.use_gpu=False;extraction.num_threads=2;extraction.max_image_size=1600;extraction.sift.max_num_features=6000
        matching=c.FeatureMatchingOptions();matching.use_gpu=False;matching.num_threads=2
        options=c.IncrementalPipelineOptions();options.num_threads=2;options.min_model_size=3;options.max_runtime_seconds=180
        with (run/'colmap-python-log.txt').open('w') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
            c.extract_features(database,pictures,reader_options=c.ImageReaderOptions(camera_model='SIMPLE_RADIAL'),extraction_options=extraction,device=c.Device.cpu)
            c.match_exhaustive(database,matching_options=matching,device=c.Device.cpu)
            reconstructions=c.incremental_mapping(database,pictures,models,options=options)
        require(bool(reconstructions),'RECONSTRUCTION_COLMAP_NO_REGISTERED_MODEL')
        best=max(reconstructions.values(),key=lambda r:(r.num_reg_images(),r.num_points3D()))
        require(best.num_reg_images()>=3 and best.num_points3D()>=30,'RECONSTRUCTION_COLMAP_INSUFFICIENT_COVERAGE')
        (run/'colmap-best').mkdir();best.write(run/'colmap-best');best.write_text(run/'colmap-best')
        points=list(best.points3D.values());vertices=np.array([p.xyz for p in points]);colors=np.array([p.color for p in points])/255.
        cloud=o3d.geometry.PointCloud(o3d.utility.Vector3dVector(vertices));cloud.colors=o3d.utility.Vector3dVector(colors)
        cloud.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamKNN(knn=min(20,len(vertices))))
        o3d.io.write_point_cloud(str(run/'sparse-cloud.ply'),cloud)
        np.savez_compressed(run/'sparse-geometry.npz',vertices=vertices,colors=colors,normals=np.asarray(cloud.normals))
        for record in records:require(hashlib.sha256(Path(record['source']).read_bytes()).hexdigest()==record['sha256'],'RECONSTRUCTION_SOURCE_CHANGED')
        report={'runId':run.name,'kind':'colmap-sparse-multiphoto','images':records,'backend':{'provider':'PyCOLMAP','version':c.__version__,'device':'cpu'},
            'registeredImages':best.num_reg_images(),'suppliedImages':len(records),'points3D':best.num_points3D(),'meanReprojectionErrorPx':float(best.compute_mean_reprojection_error()),
            'outputs':{'pointCloud':str(run/'sparse-cloud.ply'),'camerasAndTracks':str(run/'colmap-best')},'runtimeSeconds':time.monotonic()-started,
            'unknowns':['Scale is relative without measured dimensions.','Sparse landmarks do not establish a watertight detailed surface or hidden geometry.','Estimated point-cloud normals are not observed surface normals.'],
            'artifactDigests':{p.relative_to(run).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in run.rglob('*') if p.is_file() and (p.parent.name=='colmap-best' or p.suffix in ['.ply','.npz','.db'])}}
        save(run/'report.json',report);return {k:v for k,v in report.items() if k not in ['images','artifactDigests']}
    except Exception:
        import traceback
        (run/'failure-traceback.txt').write_text(traceback.format_exc(),encoding='utf8');raise
