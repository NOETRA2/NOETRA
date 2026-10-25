"""Bounded local surface fairing; never substitutes a photograph for geometry."""
import numpy as np
import cv2 as cv
from scipy.sparse import coo_matrix,diags
from scipy.ndimage import distance_transform_edt,gaussian_filter
from geometry import require

def face_normals(vertices,faces):
    v=vertices[faces];n=np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0]);length=np.linalg.norm(n,axis=1)
    return n/np.maximum(length[:,None],1e-15),length

def adjacency(faces,count):
    edges=np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]);edges=np.unique(np.sort(edges,axis=1),axis=0)
    rows=np.concatenate([edges[:,0],edges[:,1]]);cols=np.concatenate([edges[:,1],edges[:,0]])
    A=coo_matrix((np.ones(len(rows)),(rows,cols)),shape=(count,count)).tocsr();degree=np.asarray(A.sum(axis=1)).ravel()
    return diags(1/np.maximum(degree,1))@A

def constrained_step(current,proposal,faces,initial_normals,areas):
    # A tiny invalid triangle must not stop fairing on the entire other side.
    # Limit only its incident vertices, then propagate until every face is valid.
    scale=np.ones(len(current));delta=proposal-current
    for attempt in range(32):
        trial=current+scale[:,None]*delta;normals,sizes=face_normals(trial,faces)
        invalid=((normals*initial_normals).sum(1)<=.05)|(sizes<=np.maximum(areas*.025,1e-14))
        if not invalid.any():return trial,{'limitedVertices':int((scale<1).sum()),'accepted':True,'attempts':attempt}
        indices=np.unique(faces[invalid]);scale[indices]=scale[indices]*.5 if attempt<12 else 0
    return current,{'limitedVertices':int((scale<1).sum()),'accepted':False,'attempts':32}

def repair(vertices,faces,pixels,depths,camera_rotation,focal,mask):
    vertices=np.asarray(vertices,float);faces=np.asarray(faces,int);require(np.isfinite(vertices).all(),'RECONSTRUCTION_SURFACE_NONFINITE')
    require(len(vertices)<=1_000_000 and faces.ndim==2 and faces.shape[1]==3,'RECONSTRUCTION_SURFACE_LIMIT')
    h,w=mask.shape;inside=np.asarray(mask,bool)
    outside_distance,nearest=distance_transform_edt(~inside,return_indices=True);inside_distance=distance_transform_edt(inside)
    ix=np.clip(np.rint(pixels[:,0]).astype(int),0,w-1);iy=np.clip(np.rint(pixels[:,1]).astype(int),0,h-1)
    distance=np.where(inside[iy,ix],inside_distance[iy,ix],-outside_distance[iy,ix])
    # Only the contour neighbourhood is eligible. It is fixed for the whole trial.
    eligible=(distance<16)&(distance>-20)&(depths>0)
    weight=np.clip((16-np.abs(distance))/8,0,1);weight[distance<0]=1;weight*=eligible
    A=adjacency(faces,len(vertices));initial_normals,areas=face_normals(vertices,faces)
    diagonal=float(np.linalg.norm(np.ptp(vertices,axis=0)));maximum=diagonal*.018
    current=vertices.copy();iterations=[]
    for iteration in range(24):
        # Locally anchored Laplacian proposal; distant interior coordinates stay exact.
        proposal=current+.35*weight[:,None]*(A@current-current)
        offsets=proposal-vertices;length=np.linalg.norm(offsets,axis=1)
        proposal=vertices+offsets*np.minimum(1,maximum/np.maximum(length,1e-15))[:,None]
        proposal[~eligible]=vertices[~eligible]
        # Backtrack each step to preserve triangle orientation and nonzero area.
        current,decision=constrained_step(current,proposal,faces,initial_normals,areas)
        iterations.append({'iteration':iteration,**decision})
        if not decision['accepted']:break
    # Contract protrusions towards a smooth image contour, only where source mask
    # establishes empty background. This is an attributed silhouette constraint.
    camera=np.asarray(camera_rotation,float);offset=(current-vertices)@camera
    uv=pixels+np.column_stack([offset[:,0],-offset[:,1]])*focal/depths[:,None]
    xx=np.clip(np.rint(uv[:,0]).astype(int),0,w-1);yy=np.clip(np.rint(uv[:,1]).astype(int),0,h-1)
    signed=gaussian_filter(inside_distance-outside_distance,.8)
    gy,gx=np.gradient(signed);norm=np.hypot(gx,gy)
    for iteration in range(16):
        offset=(current-vertices)@camera;depth=-((offset[:,2])-depths)
        uv=(pixels-np.array([w/2,h/2]))*depths[:,None]/np.maximum(depth[:,None],1e-8)+np.array([w/2,h/2])+np.column_stack([offset[:,0],-offset[:,1]])*focal/np.maximum(depth[:,None],1e-8)
        xx=np.clip(np.rint(uv[:,0]).astype(int),0,w-1);yy=np.clip(np.rint(uv[:,1]).astype(int),0,h-1)
        sd=signed[yy,xx];active=eligible&(sd<1.2)
        delta=np.zeros_like(current);magnitude=np.clip(1.2-sd,0,3)*active
        # Pixel flow gradient points into the observed foreground.
        dx=magnitude*gx[yy,xx]/np.maximum(norm[yy,xx],.1);dy=magnitude*gy[yy,xx]/np.maximum(norm[yy,xx],.1)
        delta=(np.column_stack([dx*depth/focal,-dy*depth/focal,np.zeros(len(dx))]))@camera.T
        # Smooth the flow over topology, suppressing alternating facet folds.
        for _ in range(3):delta=.55*delta+.45*(A@delta);delta[~eligible]=0
        proposal=current+delta;offsets=proposal-vertices;length=np.linalg.norm(offsets,axis=1)
        proposal=vertices+offsets*np.minimum(1,maximum/np.maximum(length,1e-15))[:,None]
        current,decision=constrained_step(current,proposal,faces,initial_normals,areas)
        iterations.append({'contourIteration':iteration,**decision})
        if not decision['accepted']:break
    before=np.linalg.norm(vertices-A@vertices,axis=1);after=np.linalg.norm(current-A@current,axis=1)
    changed=np.linalg.norm(current-vertices,axis=1)>1e-12;normals,sizes=face_normals(current,faces)
    require(np.array_equal(current[~eligible],vertices[~eligible]),'RECONSTRUCTION_PROTECTED_SURFACE_CHANGED')
    report={'eligibleVertices':int(eligible.sum()),'changedVertices':int(changed.sum()),'protectedVerticesUnchanged':int((~eligible).sum()),
        'maxDisplacementRelativeUnits':float(np.linalg.norm(current-vertices,axis=1).max()),'displacementLimit':maximum,
        'flippedFaces':int(((normals*initial_normals).sum(1)<=0).sum()),'minimumAreaRatio':float(np.min(sizes/np.maximum(areas,1e-15))),
        'localLaplacianResidualBefore':float(np.mean(before[eligible])),'localLaplacianResidualAfter':float(np.mean(after[eligible])),
        'scope':'Only a fixed 16px contour neighbourhood; smoothing is an inferred regularity prior, not recovered fine shape. Original topology retained.', 'iterations':iterations}
    return current,report
