"""Geometry-based presentation checks shared by the fixed Blender adapters."""
import math
import numpy as np
from mathutils import Vector
import bpy
from structural_math import fit_camera_distance

def points_for(collection):
    dep=bpy.context.evaluated_depsgraph_get();points=[]
    for o in collection.all_objects:
        if o.type not in ['MESH','CURVE'] or o.hide_render:continue
        evaluated=o.evaluated_get(dep);mesh=evaluated.to_mesh();points.extend([tuple(evaluated.matrix_world@v.co) for v in mesh.vertices]);evaluated.to_mesh_clear()
    result=np.asarray(points,float)
    if len(result)==0 or not np.isfinite(result).all():raise ValueError('RECONSTRUCTION_FRAME_GEOMETRY')
    return result

def verify_presentation(scene,camera,points,floor=None,margin=.06):
    bpy.context.view_layer.update();R=np.array(camera.matrix_world.to_3x3());origin=np.array(camera.location)
    aspect=(scene.render.resolution_x*scene.render.pixel_aspect_x)/(scene.render.resolution_y*scene.render.pixel_aspect_y)
    retreat=max(0.,fit_camera_distance(points,R,origin,camera.data.angle_x,aspect,margin))
    if retreat>0:camera.location+=camera.matrix_world.to_3x3()@Vector((0,0,retreat*1.01+.001))
    floor_changed=False
    if floor is not None:
        low=float(np.asarray(points)[:,2].min());current=max((floor.matrix_world@Vector(c)).z for c in floor.bound_box);target=low-max(float(np.linalg.norm(np.ptp(points,axis=0)))*.0005,1e-5)
        if current>=low or current<low-np.linalg.norm(np.ptp(points,axis=0))*.01:
            floor.location.z+=target-current;floor_changed=True
    bpy.context.view_layer.update();q=(points-np.array(camera.location))@np.array(camera.matrix_world.to_3x3());depth=-q[:,2];tx=math.tan(camera.data.angle_x/2);ty=tx/aspect
    ndc=np.column_stack([.5+q[:,0]/(2*tx*depth),.5+q[:,1]/(2*ty*depth)])
    passed=bool((depth>0).all() and ndc.min()>=margin-.002 and ndc.max()<=1-margin+.002)
    if not passed:raise ValueError('RECONSTRUCTION_FRAME_CLIPPED')
    clearance=None if floor is None else float(points[:,2].min()-max((floor.matrix_world@Vector(c)).z for c in floor.bound_box))
    if clearance is not None and clearance<=0:raise ValueError('RECONSTRUCTION_GROUND_CLIPS_GEOMETRY')
    return {'allVerticesInFrame':passed,'margin':margin,'normalizedBounds':[ndc.min(0).tolist(),ndc.max(0).tolist()],
        'cameraRetreatRelativeUnits':retreat,'floorAdjusted':floor_changed,'groundClearance':clearance,'scope':'Presentation safety of actual geometry; does not fill missing geometry.'}
