"""Local mathematical geometry. No providers, networking, asset templates or model weights."""
import numpy as np
import cv2 as cv
import struct
from scipy.optimize import least_squares

def require(condition, code):
    if not condition: raise ValueError(code)

def exr_channels(path):
    """Bounded header inspection, including multipart EXR; not full pixel decoding."""
    with path.open('rb') as stream:data=stream.read(131072)
    require(len(data)>12 and data[:4]==b'\x76\x2f\x31\x01','RECONSTRUCTION_EXR_HEADER')
    multipart=bool(struct.unpack_from('<I',data,4)[0]&0x1000);offset=8;names=[];parts=0
    def text():
        nonlocal offset
        end=data.find(b'\0',offset)
        require(end>=offset and end-offset<=255,'RECONSTRUCTION_EXR_HEADER')
        value=data[offset:end].decode('ascii');offset=end+1;return value
    while offset<len(data) and data[offset]!=0:
        parts+=1;require(parts<=32,'RECONSTRUCTION_EXR_HEADER');attrs=0
        while offset<len(data) and data[offset]!=0:
            attrs+=1;require(attrs<=256,'RECONSTRUCTION_EXR_HEADER')
            name=text();kind=text();require(offset+4<=len(data),'RECONSTRUCTION_EXR_HEADER')
            size=struct.unpack_from('<I',data,offset)[0];offset+=4
            require(size<=131072 and offset+size<=len(data),'RECONSTRUCTION_EXR_HEADER')
            if name=='channels' and kind=='chlist':
                chunk=data[offset:offset+size];at=0
                while at<len(chunk) and chunk[at]!=0:
                    end=chunk.find(b'\0',at);require(end>=at and end+17<=len(chunk),'RECONSTRUCTION_EXR_HEADER')
                    names.append(chunk[at:end].decode('ascii'));at=end+17
            offset+=size
        require(offset<len(data),'RECONSTRUCTION_EXR_HEADER');offset+=1
        if not multipart:break
    return names

def finite(a):
    a=np.asarray(a,dtype=np.float64)
    require(np.isfinite(a).all(),'RECONSTRUCTION_NONFINITE')
    return a

def project(points,K,R=None,T=None):
    points=finite(points);K=finite(K)
    camera=points if R is None else (finite(R)@points.T).T+finite(T).reshape(1,3)
    require((camera[:,2]>1e-6).all(),'RECONSTRUCTION_BEHIND_CAMERA')
    q=(K@camera.T).T
    return q[:,:2]/q[:,2,None]

def triangulate_checked(left,right,K1,D1,K2,D2,R,T,max_error=3):
    left=finite(left).reshape(-1,2);right=finite(right).reshape(-1,2)
    require(len(left)==len(right) and len(left)>=8,'RECONSTRUCTION_CORRESPONDENCES')
    require(np.linalg.norm(T)>1e-5,'RECONSTRUCTION_ZERO_BASELINE')
    require(np.allclose(R.T@R,np.eye(3),atol=1e-4) and np.linalg.det(R)>0,'RECONSTRUCTION_CAMERA_ROTATION')
    a=cv.undistortPoints(left[:,None,:],K1,D1).reshape(-1,2)
    b=cv.undistortPoints(right[:,None,:],K2,D2).reshape(-1,2)
    h=cv.triangulatePoints(np.c_[np.eye(3),np.zeros(3)],np.c_[R,T],a.T,b.T)
    require((np.abs(h[3])>1e-9).all(),'RECONSTRUCTION_TRIANGULATION_DEGENERATE')
    xyz=(h[:3]/h[3]).T
    q=(R@xyz.T).T+T.reshape(1,3)
    rays1=xyz/np.linalg.norm(xyz,axis=1)[:,None]
    centre2=-R.T@T.reshape(3)
    rays2=xyz-centre2;rays2/=np.linalg.norm(rays2,axis=1)[:,None]
    angles=np.degrees(np.arccos(np.clip((rays1*rays2).sum(axis=1),-1,1)))
    def candidate_projection(points,K):
        pixels=(K@points.T).T;den=pixels[:,2,None]
        return np.divide(pixels[:,:2],den,out=np.full((len(points),2),np.nan),where=np.abs(den)>1e-9)
    errs=np.maximum(np.linalg.norm(candidate_projection(xyz,K1)-cv.undistortPoints(left[:,None,:],K1,D1,P=K1).reshape(-1,2),axis=1),
                    np.linalg.norm(candidate_projection(q,K2)-cv.undistortPoints(right[:,None,:],K2,D2,P=K2).reshape(-1,2),axis=1))
    valid=np.isfinite(xyz).all(axis=1)&(xyz[:,2]>0)&(q[:,2]>0)&(angles>.5)&(errs<=max_error)
    require(valid.sum()>=max(8,int(.9*len(xyz))),'RECONSTRUCTION_INCONSISTENT_MATCHES')
    return xyz,valid,errs,angles

def plane_grid(points,shape):
    cols,rows=shape;points=finite(points).reshape(rows,cols,3)
    dx=np.median(np.diff(points,axis=1).reshape(-1,3),axis=0)
    dy=np.median(np.diff(points,axis=0).reshape(-1,3),axis=0)
    require(np.linalg.norm(dx)>1e-6 and np.linalg.norm(dy)>1e-6,'RECONSTRUCTION_DEGENERATE_SURFACE')
    ux=dx/np.linalg.norm(dx);uy=dy-np.dot(dy,ux)*ux;uy/=np.linalg.norm(uy)
    normal=np.cross(ux,uy);centre=np.median(points.reshape(-1,3),axis=0)
    x,y=np.meshgrid(np.arange(cols)-(cols-1)/2,np.arange(rows)-(rows-1)/2)
    offsets=np.c_[x.ravel(),y.ravel()]
    sx=np.median(np.linalg.norm(np.diff(points,axis=1),axis=2))
    sy=np.median(np.linalg.norm(np.diff(points,axis=0),axis=2))
    return {'centre':centre.tolist(),'axes':[ux.tolist(),uy.tolist()],'normal':normal.tolist(),
            'steps':[float(sx),float(sy)],'offsets':offsets.tolist(),'shape':list(shape),
            'planarity_rms':float(np.sqrt(np.mean(((points.reshape(-1,3)-centre)@normal)**2)))}

def grid_points(surface,scales):
    scales=finite(scales);require(scales.shape==(2,) and ((scales>=.5)&(scales<=1.5)).all(),'RECONSTRUCTION_PARAMETER_BOUNDS')
    offsets=finite(surface['offsets'])*finite(surface['steps'])*scales
    return finite(surface['centre'])+offsets@finite(surface['axes'])

def optimize_scales(surface,initial,K,observations,max_evaluations):
    require(4<=max_evaluations<=40,'RECONSTRUCTION_BUDGET')
    observations=finite(observations);calls=[]
    def residual(scales):
        error=(project(grid_points(surface,scales),K)-observations).ravel()
        calls.append({'scales':scales.tolist(),'landmark_rmse_px':float(np.sqrt(np.mean(error**2)))})
        return error
    result=least_squares(residual,finite(initial),bounds=([.5,.5],[1.5,1.5]),loss='soft_l1',f_scale=1,
                         jac='2-point',max_nfev=max_evaluations,ftol=1e-8,xtol=1e-8,gtol=1e-8)
    return result.x.tolist(),calls,{'success':bool(result.success),'nfev':int(result.nfev),'finite_difference_calls':len(calls)}

def boundary(mask):
    return cv.morphologyEx(mask.astype(np.uint8),cv.MORPH_GRADIENT,np.ones((3,3),np.uint8))>0

def symmetric_distance(a,b):
    if not a.any() or not b.any():return None
    da=cv.distanceTransform((~a).astype(np.uint8),cv.DIST_L2,cv.DIST_MASK_PRECISE)
    db=cv.distanceTransform((~b).astype(np.uint8),cv.DIST_L2,cv.DIST_MASK_PRECISE)
    samples=np.r_[db[a],da[b]]
    return {'mean_px':float(samples.mean()),'p95_px':float(np.percentile(samples,95))}

def compare_masks(a,b):
    a=np.asarray(a)>0;b=np.asarray(b)>0
    require(a.shape==b.shape,'RECONSTRUCTION_IMAGE_SIZE')
    require(a.any() and b.any(),'RECONSTRUCTION_EMPTY_MASK')
    union=np.logical_or(a,b).sum()
    return {'silhouette_iou':float(np.logical_and(a,b).sum()/union),'boundary':symmetric_distance(boundary(a),boundary(b))}

def bezier_patch(control,u,v):
    """Bicubic controlled patch point/normal/curvature; geometry, never brightness."""
    c=finite(control);require(c.shape==(4,4,3),'RECONSTRUCTION_PATCH_SHAPE')
    require(0<=u<=1 and 0<=v<=1,'RECONSTRUCTION_PATCH_DOMAIN')
    def basis(t):return np.array([(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3])
    def first(t):return np.array([-3*(1-t)**2,3*(1-t)*(1-3*t),3*t*(2-3*t),3*t*t])
    def second(t):return np.array([6*(1-t),18*t-12,6-18*t,6*t])
    def evaluate(a,b):return np.einsum('i,j,ijk->k',a,b,c)
    a,b=basis(u),basis(v);du,dv=evaluate(first(u),b),evaluate(a,first(v))
    normal=np.cross(du,dv);length=np.linalg.norm(normal);require(length>1e-10,'RECONSTRUCTION_PATCH_DEGENERATE');normal/=length
    E,F,G=np.dot(du,du),np.dot(du,dv),np.dot(dv,dv)
    e,f,g=np.dot(normal,evaluate(second(u),b)),np.dot(normal,evaluate(first(u),first(v))),np.dot(normal,evaluate(a,second(v)))
    denom=E*G-F*F;require(denom>1e-12,'RECONSTRUCTION_PATCH_DEGENERATE')
    return {'point':evaluate(a,b).tolist(),'normal':normal.tolist(),'gaussian_curvature':float((e*g-f*f)/denom),'mean_curvature':float((E*g-2*F*f+G*e)/(2*denom))}
