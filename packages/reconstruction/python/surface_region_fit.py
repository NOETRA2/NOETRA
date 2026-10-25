"""Provisional surface-aware refinement of the largest authored fibre region.

Uses normal-projected Laplacian roughness, not object names or a photo decal.
This fits a rough surface boundary; it does not establish anatomical identity.
"""
import copy
import numpy as np
from reference_colors import region_weights

def fit_fibre_region(points,faces,design):
    points=np.asarray(points,float);faces=np.asarray(faces,np.int32)
    candidates=[(i,np.prod(l['region']['radii'])) for i,l in enumerate(design['layers']) if l.get('verticalFiber',0)>=.5]
    if not candidates:return {},{'status':'no-attributed-fibre-region'}
    index=max(candidates,key=lambda pair:pair[1])[0];layer=design['layers'][index]
    edges=np.unique(np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
    rows=np.r_[edges[:,0],edges[:,1]];columns=np.r_[edges[:,1],edges[:,0]]
    degree=np.maximum(np.bincount(rows,minlength=len(points)),1)
    def neighbor_sum(values):
        if values.ndim==1:return np.bincount(rows,weights=values[columns],minlength=len(points))
        return np.column_stack([np.bincount(rows,weights=values[columns,i],minlength=len(points)) for i in range(values.shape[1])])
    edge_length=np.linalg.norm(points[edges[:,0]]-points[edges[:,1]],axis=1)
    scale=np.bincount(np.r_[edges[:,0],edges[:,1]],weights=np.r_[edge_length,edge_length],minlength=len(points))/degree
    normals=np.zeros_like(points);normal=np.cross(points[faces[:,1]]-points[faces[:,0]],points[faces[:,2]]-points[faces[:,0]])
    for i in range(3):np.add.at(normals,faces[:,i],normal)
    normals/=np.maximum(np.linalg.norm(normals,axis=1),1e-15)[:,None]
    mean=neighbor_sum(points)/degree[:,None]
    roughness=np.abs(np.sum((mean-points)*normals,axis=1))/np.maximum(scale,1e-15)
    roughness=neighbor_sum(roughness)/degree
    prior=region_weights(points,layer['region']);seed=roughness[prior>.8]
    if len(seed)<30:return {},{'status':'insufficient-surface-support','layer':layer['id']}
    low,high=np.percentile(seed,[15,60]);high=max(high,low+.005)
    gate=np.clip((roughness-low)/(high-low),0,1);gate=gate*gate*(3-2*gate)
    expanded=copy.deepcopy(layer['region']);expanded['radii']=(np.asarray(expanded['radii'])*1.55).tolist();expanded['feather']=.4
    support=region_weights(points,expanded)
    # Roughness locates a region's envelope, not pigment on each individual
    # triangle. Close small graph holes to avoid a mottled coat inside a mane.
    allowed=support>.05
    core=(gate>.22)&allowed
    for _ in range(12):core=(neighbor_sum(core.astype(float))>0)&allowed
    for _ in range(12):core=(neighbor_sum(core.astype(float))>=degree-.001)&allowed
    fitted=core.astype(float)
    for _ in range(10):fitted=(.3*fitted+.7*neighbor_sum(fitted)/degree)*support
    fitted=np.clip(fitted*1.25,0,1)
    return {layer['id']:fitted},{'status':'provisional-geometric-fit','layer':layer['id'],'roughnessThresholds':[float(low),float(high)],
      'extendedVertices':int(((prior<.01)&(fitted>.2)).sum()),'affectedVertices':int((fitted>.01).sum()),
      'geometryChanged':False,'semanticIdentityVerified':False,'method':'Normalized normal-projected Laplacian, authored bounded support, graph-closed envelope and smoothed material weights.'}
