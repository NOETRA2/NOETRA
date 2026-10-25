"""Explicit Blender integration tests, run in a fresh empty background process."""
import bpy,sys,math
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages'/'reconstruction'/'python'))
from part_adapter import apply_parameters,fingerprint
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add();a=bpy.context.object;a.name='a'
b=bpy.data.objects.new('b',a.data);bpy.context.scene.collection.objects.link(b)
original=[tuple(v.co) for v in b.data.vertices]
spec={'parts':[{'id':'part','objects':['a']}], 'parameters':[{'id':'offset','partId':'part','kind':'mesh_offset','axis':'Z','object':'a','indices':[0,1],'minimum':-.2,'maximum':.2}]}
apply_parameters(spec,{'offset':.1},{'a':a,'b':b})
assert [tuple(v.co) for v in b.data.vertices]==original,'Shared-data edit leaked into protected object'
assert abs(a.data.vertices[0].co.z-original[0][2]-.1)<1e-6
assert tuple(a.data.vertices[2].co)==original[2]
for kind in ['POLY','BEZIER']:
 d=bpy.data.curves.new('curve-'+kind,'CURVE');d.dimensions='3D';s=d.splines.new(kind)
 points=s.bezier_points if kind=='BEZIER' else s.points;points.add(2)
 for i,p in enumerate(points):p.co=(i,0,0) if kind=='BEZIER' else (i,0,0,1)
 o=bpy.data.objects.new('curve-'+kind,d);bpy.context.scene.collection.objects.link(o)
 spec={'parts':[{'id':'part','objects':[o.name]}], 'parameters':[{'id':'offset','partId':'part','kind':'curve_offset','axis':'Z','object':o.name,'indices':[1],'spline':0,'minimum':-.2,'maximum':.2}]}
 apply_parameters(spec,{'offset':.1},{o.name:o})
 assert abs(points[1].co.z-.1)<1e-6 and abs(points[0].co.z)<1e-6 and abs(points[2].co.z)<1e-6
parent=bpy.data.objects.new('parent',None);bpy.context.scene.collection.objects.link(parent);parent.rotation_euler.z=.7;a.parent=parent;bpy.context.view_layer.update()
prior=a.matrix_world.translation.copy();rotation=parent.rotation_euler.copy()
spec={'parts':[{'id':'part','objects':['a']}],'parameters':[{'id':'move','partId':'part','kind':'translate','axis':'X','minimum':-.2,'maximum':.2}]}
apply_parameters(spec,{'move':.1},{'a':a})
assert (a.matrix_world.translation-prior-Vector((.1,0,0))).length<1e-6
assert parent.rotation_euler==rotation
print('BLENDER_PART_CONTROLS_PASS shared-data mesh, poly/bezier controls, parented world translation',flush=True)
