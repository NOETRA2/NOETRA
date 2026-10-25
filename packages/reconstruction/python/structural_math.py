"""Deterministic shape primitives and framing constraints for explicit priors."""
import numpy as np

def cubic(points,t):
    p=np.asarray(points,float);t=np.asarray(t,float)
    if p.shape!=(4,3) or not np.isfinite(p).all():raise ValueError('RECONSTRUCTION_PATCH_CONTROL')
    b=np.stack([(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3],axis=-1)
    return b@p

def coons(curves,u,v):
    left,right,bottom,top=[np.asarray(curves[k],float) for k in ['left','right','bottom','top']]
    for a,b in [(left[0],bottom[0]),(left[3],top[0]),(right[0],bottom[3]),(right[3],top[3])]:
        if np.linalg.norm(a-b)>1e-6:raise ValueError('RECONSTRUCTION_PATCH_OPEN_CORNERS')
    bl,br,tl,tr=bottom[0],bottom[3],top[0],top[3]
    return (1-u)*cubic(left,v)+u*cubic(right,v)+(1-v)*cubic(bottom,u)+v*cubic(top,u)-((1-u)*(1-v)*bl+u*(1-v)*br+(1-u)*v*tl+u*v*tr)

def fit_camera_distance(points,camera_rotation,target,fov_x,aspect,margin=.08):
    # Camera looks along local -Z. Solve all near/far perspective inequalities,
    # including actual wheel geometry; do not frame only the upper body.
    q=(np.asarray(points,float)-np.asarray(target,float))@np.asarray(camera_rotation,float)
    tx=np.tan(fov_x/2)*(1-2*margin);ty=tx/aspect
    return float(max(np.max(q[:,2]+np.abs(q[:,0])/tx),np.max(q[:,2]+np.abs(q[:,1])/ty),np.max(q[:,2])+.01))

def wheel_roundness(points,axis=1):
    p=np.asarray(points,float);other=[i for i in range(3) if i!=axis];center=(p.min(0)+p.max(0))/2
    q=p[:,other]-center[other];r=np.linalg.norm(q,axis=1);outer=r>r.max()*.995
    angles=np.unique(np.round(np.mod(np.arctan2(q[outer,1],q[outer,0]),2*np.pi),7));gaps=np.diff(np.r_[angles,angles[0]+2*np.pi])
    return {'center':center.tolist(),'outerRadius':float(r[outer].mean()),'radiusStd':float(r[outer].std()),'outerAngularSamples':len(angles),
        'maximumAngularGapDegrees':float(np.rad2deg(gaps.max())),'minimumZ':float(p[:,2].min()),'completeCircle':bool(len(angles)>=48 and np.rad2deg(gaps.max())<8 and r[outer].std()<r.max()*.005)}
