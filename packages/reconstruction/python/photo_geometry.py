"""Real mesh cleanup, geometric image-space camera proposals and renderer checks."""
import math,json
from pathlib import Path
import numpy as np
import cv2 as cv
from scipy.optimize import differential_evolution
from geometry import require,boundary,symmetric_distance

def clean_mesh(mesh,output):
    import trimesh,open3d as o3d
    require(np.isfinite(mesh.vertices).all() and len(mesh.faces)>100,'RECONSTRUCTION_INVALID_LEARNED_MESH')
    before={'vertices':len(mesh.vertices),'faces':len(mesh.faces)}
    mesh=mesh.copy();mesh.process(validate=True)
    m=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(np.asarray(mesh.vertices,dtype=float)),o3d.utility.Vector3iVector(np.asarray(mesh.faces,dtype=np.int32)))
    if len(mesh.visual.vertex_colors)==len(mesh.vertices):m.vertex_colors=o3d.utility.Vector3dVector(np.asarray(mesh.visual.vertex_colors[:,:3],float)/255)
    m.remove_degenerate_triangles();m.remove_duplicated_triangles();m.remove_unreferenced_vertices();m.compute_vertex_normals()
    colors=np.asarray(m.vertex_colors);colors=(colors*255).clip(0,255).astype(np.uint8) if len(colors) else None
    result=trimesh.Trimesh(vertices=np.asarray(m.vertices),faces=np.asarray(m.triangles),vertex_normals=np.asarray(m.vertex_normals),vertex_colors=colors,process=False)
    require(np.isfinite(result.vertices).all() and len(result.faces)>100,'RECONSTRUCTION_MESH_CLEANUP_FAILED')
    result.export(output/'surface.glb');result.export(output/'surface.ply')
    proxy=m.simplify_quadric_decimation(8000) if len(m.triangles)>8000 else m
    np.savez_compressed(output/'mesh-geometry.npz',vertices=result.vertices,faces=result.faces,normals=result.vertex_normals,
        feature_edges=result.face_adjacency_edges[np.asarray(result.face_adjacency_angles)>.5])
    report={'before':before,'after':{'vertices':len(result.vertices),'faces':len(result.faces)},'watertight':bool(result.is_watertight),
        'surfaceAreaRelativeUnits':float(result.area),'smoothingApplied':False,'smallDisconnectedPartsDiscarded':False,
        'proxyFaces':len(proxy.triangles),'normalsStatus':'Computed from the learned mesh, not measured photograph normals'}
    return result,np.asarray(proxy.vertices),np.asarray(proxy.triangles),report

def camera(parameters,size=512):
    azimuth,elevation,distance,dy,dz=parameters;target=np.array([0.,dy,dz])
    position=target+distance*np.array([math.cos(elevation)*math.cos(azimuth),math.cos(elevation)*math.sin(azimuth),math.sin(elevation)])
    forward=(target-position)/distance;right=np.cross(forward,[0,0,1]);right/=np.linalg.norm(right);up=np.cross(right,forward)
    R=np.array([right,-up,forward]);f=.5*size/math.tan(math.radians(20))
    return {'position':position.tolist(),'target':target.tolist(),'fovDegrees':40.,'R':R.tolist(),'K':[[f,0,size/2],[0,f,size/2],[0,0,1]],'parameters':list(parameters),'scaleStatus':'Relative learned-model units'}

def silhouette(vertices,faces,parameters,size=128):
    c=camera(parameters,size);q=(vertices-np.array(c['position']))@np.array(c['R']).T
    if (q[:,2]<=.001).any():return np.zeros((size,size),np.uint8)
    pixels=q[:,:2]/q[:,2,None]*c['K'][0][0]+size/2
    polygons=np.rint(pixels[faces]).clip(-32760,32760).astype(np.int32);image=np.zeros((size,size),np.uint8)
    for p in polygons:cv.fillConvexPoly(image,p,255)
    return image

def propose_camera(vertices,faces,mask,output):
    mask=cv.resize(mask,(128,128),interpolation=cv.INTER_NEAREST)>127;reference_edge=boundary(mask)
    target_distance=cv.distanceTransform((~reference_edge).astype(np.uint8),cv.DIST_L2,cv.DIST_MASK_PRECISE)
    history=[]
    def objective(p):
        prediction=silhouette(vertices,faces,p,128)>0
        if not prediction.any():return 3.
        iou=float((prediction&mask).sum()/(prediction|mask).sum());edge=boundary(prediction)
        distance=float(target_distance[edge].mean())
        loss=1-iou+distance/128;history.append({'parameters':np.asarray(p).tolist(),'proxyMaskLoss':loss});return loss
    initial=[0.,0.,1.9,0.,0.];initial_loss=objective(initial)
    proposal=differential_evolution(objective,[(-.18,.18),(-.18,.18),(1.5,2.6),(-.12,.12),(-.12,.12)],
        maxiter=5,popsize=4,seed=17,polish=False,workers=1,x0=initial)
    candidate=proposal.x.tolist() if float(proposal.fun)<initial_loss else initial
    report={'initial':camera(initial),'candidate':camera(candidate),'proxyInitialLoss':initial_loss,'proxyCandidateLoss':float(proposal.fun),
        'history':history,'scope':'Bounded silhouette camera proposal on a decimated proxy; must be checked against actual full-mesh Blender renders. No metric camera recovery or hidden-shape validation.'}
    (output/'camera-proposal.json').write_text(json.dumps(report,indent=2));return report

def mitsuba_geometry_render(ply,pose,output):
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    scene=mi.load_dict({'type':'scene','integrator':{'type':'path','max_depth':3},
        'sensor':{'type':'perspective','fov':40,'fov_axis':'x','to_world':mi.ScalarTransform4f.look_at(origin=pose['position'],target=pose['target'],up=[0,0,1]),
            'sampler':{'type':'independent','sample_count':4},'film':{'type':'hdrfilm','width':256,'height':256,'pixel_format':'rgb'}},
        'surface':{'type':'ply','filename':str(ply),'bsdf':{'type':'roughconductor','material':'Al','alpha':.3}},
        'light':{'type':'constant','radiance':{'type':'rgb','value':[.6,.6,.6]}}})
    image=mi.render(scene);mi.util.write_bitmap(str(output/'mitsuba-geometry.png'),image)
    return {'provider':'Mitsuba','variant':mi.variant(),'render':str(output/'mitsuba-geometry.png'),
        'materialStatus':'Neutral aluminum hypothesis for geometric inspection, not recovered intrinsic paint/lighting'}
