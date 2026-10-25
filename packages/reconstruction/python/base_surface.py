"""Small connected-base deformations with protected vertices and topology checks."""
import numpy as np,json,hashlib
from pathlib import Path
from reference_colors import region_weights

def bounded_deform(points,faces,spec):
    original=np.asarray(points,float);triangles=np.asarray(faces,np.int32)
    delta=np.zeros_like(original);mask=np.zeros(len(original),bool);records=[]
    for control in spec['deformations']:
        direction=np.asarray(control['direction'],float);length=np.linalg.norm(direction)
        if length<1e-8:raise ValueError('BASE_SURFACE_DIRECTION')
        weights=region_weights(original,control['region']);mask|=weights>0
        delta+=weights[:,None]*direction/length*control['distance']
        records.append({'id':control['id'],'affectedVertices':int((weights>0).sum())})
    magnitude=np.linalg.norm(delta,axis=1)
    delta*=np.minimum(1,spec['maximumDisplacement']/np.maximum(magnitude,1e-15))[:,None]
    old=np.cross(original[triangles[:,1]]-original[triangles[:,0]],original[triangles[:,2]]-original[triangles[:,0]])
    old_lengths=np.linalg.norm(old,axis=1);valid=old_lengths>1e-14
    for factor in [1,.5,.25,.125,.0625]:
        candidate=original+delta*factor
        normal=np.cross(candidate[triangles[:,1]]-candidate[triangles[:,0]],candidate[triangles[:,2]]-candidate[triangles[:,0]])
        lengths=np.linalg.norm(normal,axis=1)
        cos=np.sum(old*normal,axis=1)/np.maximum(old_lengths*lengths,1e-30)
        if (lengths[valid]>1e-14).all() and (cos[valid]>.1).all():break
    else:raise ValueError('BASE_SURFACE_FACE_REVERSAL')
    assert np.array_equal(original[~mask],candidate[~mask])
    return candidate,{'changedVertices':int((np.linalg.norm(candidate-original,axis=1)>0).sum()),'protectedVertices':int((~mask).sum()),
      'protectedVerticesExactlyUnchanged':True,'topologyUnchanged':True,'addedObjects':0,'acceptedStepFactor':factor,
      'maximumActualDisplacement':float(np.linalg.norm(candidate-original,axis=1).max()),'minimumFaceNormalCosine':float(cos[valid].min()),'controls':records}

def refine_base(objects,out,spec):
    assert len(objects)==1,'One connected base object required'
    o=objects[0];assert all(len(p.vertices)==3 for p in o.data.polygons)
    points=np.asarray([tuple(o.matrix_world@v.co) for v in o.data.vertices]);faces=np.asarray([list(p.vertices) for p in o.data.polygons],np.int32)
    updated,qa=bounded_deform(points,faces,spec);inverse=o.matrix_world.inverted()
    from mathutils import Vector
    for index in np.flatnonzero(np.any(points!=updated,axis=1)):o.data.vertices[int(index)].co=inverse@Vector(updated[index])
    o.data.update()
    actual=np.asarray([tuple(o.matrix_world@v.co) for v in o.data.vertices]);unchanged=np.all(points==updated,axis=1)
    assert np.array_equal(points[unchanged],actual[unchanged])
    assert np.array_equal(faces,np.asarray([list(p.vertices) for p in o.data.polygons],np.int32))
    qa.update(originalVertices=len(points),originalTriangles=len(faces),provenance=spec['provenance'],
      scope='Authored local depth corrections in the existing base; no added pieces and no automatic anatomical inference.')
    (Path(out)/'base-surface-verification.json').write_text(json.dumps(qa,indent=2));return qa
