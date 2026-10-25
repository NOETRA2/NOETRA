"""Calibrated silhouette intersection. No source mesh, learned prior or texture."""
import time
import numpy as np
import cv2 as cv
from geometry import require

def fuse_silhouettes(views,bounds,grid=96):
    """Intersect foreground cones on a bounded sample grid and extract triangles.

    Each view contains binary mask, K, R, t in OpenCV world-to-camera convention.
    Samples outside a view or behind its camera are empty, never extrapolated.
    A hull touching the supplied bounds is rejected as incompletely constrained.
    """
    require(isinstance(views,list) and 3<=len(views)<=16,'RECONSTRUCTION_HULL_VIEW_COUNT')
    require(type(grid) is int and 16<=grid<=192,'RECONSTRUCTION_HULL_GRID')
    require(isinstance(bounds,dict) and set(bounds)=={'minimum','maximum'},'RECONSTRUCTION_HULL_BOUNDS')
    low=np.asarray(bounds['minimum'],float);high=np.asarray(bounds['maximum'],float)
    require(low.shape==high.shape==(3,) and np.isfinite([low,high]).all() and (high>low).all() and np.max(np.abs([low,high]))<=1e6,'RECONSTRUCTION_HULL_BOUNDS')
    prepared=[];centers=[]
    for view in views:
        require(isinstance(view,dict) and set(view)=={'mask','K','R','t'},'RECONSTRUCTION_HULL_VIEW_FIELDS')
        mask=np.asarray(view['mask']);K=np.asarray(view['K'],float);R=np.asarray(view['R'],float);t=np.asarray(view['t'],float)
        require(mask.ndim==2 and min(mask.shape)>=3 and mask.size<=8_000_000 and np.isfinite(mask).all() and np.isin(mask,[0,1,255]).all() and mask.any(),'RECONSTRUCTION_HULL_MASK')
        require(K.shape==R.shape==(3,3) and t.shape==(3,) and np.isfinite(K).all() and np.isfinite(R).all() and np.isfinite(t).all(),'RECONSTRUCTION_HULL_CAMERA')
        require(K[0,0]>0 and K[1,1]>0 and np.allclose(K[2],[0,0,1]) and abs(K[1,0])<1e-8 and np.allclose(R@R.T,np.eye(3),atol=1e-6) and abs(np.linalg.det(R)-1)<1e-6,'RECONSTRUCTION_HULL_CAMERA')
        # Signed Euclidean pixel distance to the half-pixel foreground boundary.
        # Padding makes image edges explicit constraints, including all-white masks.
        binary=np.pad(mask.astype(np.uint8)>0,1).astype(np.uint8)
        inner=cv.distanceTransform(binary,cv.DIST_L2,cv.DIST_MASK_PRECISE)
        outer=cv.distanceTransform(1-binary,cv.DIST_L2,cv.DIST_MASK_PRECISE)
        signed=inner-outer;signed-=np.sign(signed)*.5
        prepared.append((signed[1:-1,1:-1],K,R,t));centers.append(-R.T@t)
    scale=float(np.linalg.norm(high-low));distinct=[]
    for center in centers:
        if all(np.linalg.norm(center-other)>scale*1e-6 for other in distinct):distinct.append(center)
    require(len(distinct)>=3,'RECONSTRUCTION_HULL_CAMERA_BASELINE')
    started=time.monotonic();count=grid**3;flat=np.empty(count,dtype=np.float32);spacing=(high-low)/(grid-1)
    # At most 131k XYZ positions are materialized at a time, even for a 192^3 grid.
    for start in range(0,count,131072):
        indices=np.arange(start,min(start+131072,count));coordinates=np.column_stack(np.unravel_index(indices,(grid,grid,grid)))
        points=low+coordinates*spacing;field=np.full(len(points),scale,dtype=np.float32)
        for signed,K,R,t in prepared:
            camera=points@R.T+t;z=camera[:,2];positive=z>max(scale*1e-10,1e-12)
            uvw=camera@K.T;uv=uvw[:,:2]/np.maximum(z[:,None],1e-12)
            h,w=signed.shape
            valid=positive&(uv[:,0]>=0)&(uv[:,0]<=w-1)&(uv[:,1]>=0)&(uv[:,1]<=h-1)
            cone=np.full(len(points),-scale,dtype=np.float32)
            # Bilinear image distance preserves subvoxel crossing positions. The
            # depth/focal factor expresses cone residuals in approximate world
            # units before intersection, without averaging away sharp constraints.
            sample=uv[valid];x=np.floor(sample[:,0]).astype(int);y=np.floor(sample[:,1]).astype(int)
            dx=sample[:,0]-x;dy=sample[:,1]-y;x1=np.minimum(x+1,w-1);y1=np.minimum(y+1,h-1)
            pixel_distance=(1-dx)*(1-dy)*signed[y,x]+dx*(1-dy)*signed[y,x1]+(1-dx)*dy*signed[y1,x]+dx*dy*signed[y1,x1]
            cone[valid]=pixel_distance*z[valid]/np.sqrt(K[0,0]*K[1,1]);np.minimum(field,cone,out=field)
        flat[start:start+len(indices)]=field
    distance_field=flat.reshape((grid,grid,grid));occupied=distance_field>0;require(occupied.any(),'RECONSTRUCTION_HULL_EMPTY')
    touches=bool(occupied[0].any() or occupied[-1].any() or occupied[:,0].any() or occupied[:,-1].any() or occupied[:,:,0].any() or occupied[:,:,-1].any())
    require(not touches,'RECONSTRUCTION_HULL_OPEN_BOUNDS')
    from skimage.measure import marching_cubes
    import trimesh
    vertices,faces,_,_=marching_cubes(distance_field,level=0.,spacing=tuple(spacing),allow_degenerate=False)
    mesh=trimesh.Trimesh(vertices=vertices+low,faces=faces,process=True,validate=True);mesh.fix_normals(multibody=True)
    require(mesh.is_watertight and mesh.is_winding_consistent and np.isfinite(mesh.vertices).all() and len(mesh.faces)>0,'RECONSTRUCTION_HULL_NOT_CLOSED')
    report={'grid':grid,'sampleCount':count,'occupiedSamples':int(occupied.sum()),'spacing':spacing.tolist(),'bounds':bounds,
        'vertices':len(mesh.vertices),'triangles':len(mesh.faces),'watertight':bool(mesh.is_watertight),'windingConsistent':bool(mesh.is_winding_consistent),
        'boundaryOccupied':False,'seconds':time.monotonic()-started,'sourceMeshRead':False,
        'method':'Minimum of bilinearly sampled signed 2D silhouette distance cones, depth/focal world normalization, float zero-isosurface marching cubes; actual triangle geometry, no post-smoothing.',
        'distanceField':'Positive interior; exact min intersection, approximate signed distance in world units; preserves cone corners without averaging.',
        'unknowns':['Silhouettes constrain the visual hull only; concavities and internal geometry invisible in every outline are unrecoverable.',
            'Voxel sampling bounds detail and introduces discretization error; watertightness does not establish geometric fidelity.',
            'Camera calibration, foreground attribution and scale are supplied assumptions; no intrinsic materials or texture are recovered.']}
    return mesh,report
