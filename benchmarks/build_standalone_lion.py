"""Independent host-authored Blender lion; no NOETRA imports or model calls.

Run with Blender --background --factory-startup --python this.py --
  --output DIRECTORY [--comparison-mesh EXISTING.glb]
The new mesh is finished and hash-frozen before the optional existing mesh is
opened for presentation. This is a procedural study, not an accuracy benchmark.
"""
import argparse, hashlib, json, math, random, sys
from pathlib import Path
import bpy
from mathutils import Vector

args=argparse.ArgumentParser()
args.add_argument('--output', required=True)
args.add_argument('--comparison-mesh')
opt=args.parse_args(sys.argv[sys.argv.index('--')+1:])
out=Path(opt.output).resolve();out.mkdir(parents=True,exist_ok=True)
rng=random.Random(8053)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
parts=[];body=[]

def ellipsoid(name,center,scale,skin=False):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=20,location=center)
    o=bpy.context.object;o.name=name;o.scale=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    parts.append(o)
    if skin:body.append(o)
    return o

def bone(name,a,b,radius,width=None,skin=True):
    a,b=Vector(a),Vector(b);mid=(a+b)/2
    o=ellipsoid(name,mid,(radius,width or radius,(b-a).length/2+radius),skin)
    o.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler()
    return o

def tube(name,points,radius):
    c=bpy.data.curves.new(name,'CURVE');c.dimensions='3D';c.resolution_u=12
    c.bevel_depth=radius;c.bevel_resolution=3
    spline=c.splines.new('BEZIER');spline.bezier_points.add(len(points)-1)
    for v,p in zip(spline.bezier_points,points):
        v.co=p;v.handle_left_type='AUTO';v.handle_right_type='AUTO'
    o=bpy.data.objects.new(name,c);scene.collection.objects.link(o)
    bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
    bpy.ops.object.convert(target='MESH');parts.append(o);return o

# Quadruped anatomy: x points toward the hindquarters, z is up.
ellipsoid('Ribcage',(-.08,0,.91),(.67,.275,.335),True)
ellipsoid('Abdomen',(.38,0,.90),(.40,.235,.255),True)
ellipsoid('Pelvis',(.63,0,.94),(.29,.265,.30),True)
ellipsoid('Shoulder girdle',(-.55,0,.96),(.27,.30,.38),True)
ellipsoid('Neck',(-.70,0,1.22),(.29,.26,.38),True)
for side in (-1,1):
    y=side*.215;offset=.045 if side==1 else 0
    bone('Scapular muscle',(-.53,y,1.04),(-.61,y,.66),.13,.125)
    bone('Front forearm',(-.61,y,.65),(-.64+offset,y,.20),.076,.072)
    bone('Front wrist',(-.64+offset,y,.21),(-.66+offset,y,.105),.063)
    ellipsoid('Front paw',(-.71+offset,y,.085),(.145,.108,.075),True)
    for k in range(4):ellipsoid('Front toe',(-.797+offset,y+(k-1.5)*.045,.061),(.062,.030,.045),True)
    # The rear leg follows hip -> forward stifle -> rear hock -> foot.
    bone('Thigh',(.60,y,.98),(.44,y,.56),.16,.13)
    bone('Rear shin',(.44,y,.57),(.76+offset,y,.30),.079,.07)
    bone('Rear ankle',(.76+offset,y,.30),(.69+offset,y,.13),.054)
    ellipsoid('Rear paw',(.61+offset,y,.075),(.14,.095,.068),True)
    for k in range(4):ellipsoid('Rear toe',(.52+offset,y+(k-1.5)*.04,.056),(.058,.027,.040),True)

ellipsoid('Cranium',(-.90,0,1.40),(.245,.225,.255),True)
ellipsoid('Forehead',(-1.04,0,1.45),(.18,.19,.16),True)
ellipsoid('Nasal bridge',(-1.145,0,1.32),(.21,.105,.105),True)
ellipsoid('Jaw',(-1.105,0,1.17),(.20,.15,.09),True)
for side in (-1,1):
    ellipsoid('Cheek',(-1.04,side*.153,1.28),(.15,.09,.115),True)
    ellipsoid('Muzzle pad',(-1.235,side*.073,1.225),(.12,.077,.076),True)
    brow=ellipsoid('Supraorbital ridge',(-1.095,side*.167,1.43),(.105,.06,.038),True)
    brow.rotation_euler.x=side*.16
    ear=ellipsoid('Ear',(-.79,side*.202,1.603),(.082,.065,.108),True)
    ear.rotation_euler.x=side*.25

# Fuse the skin primitives into a continuous sculpted body; eyes, nose and mane
# are true geometry rather than photographic planes or decals.
bpy.ops.object.select_all(action='DESELECT')
for o in body:o.select_set(True)
bpy.context.view_layer.objects.active=body[0];bpy.ops.object.join()
skin=bpy.context.object;skin.name='Independent lion - continuous skin'
parts=[skin]
remesh=skin.modifiers.new('Fused sculpt volume','REMESH');remesh.mode='VOXEL';remesh.voxel_size=.012
bpy.ops.object.modifier_apply(modifier=remesh.name)
smooth=skin.modifiers.new('Sculpt smoothing','SMOOTH');smooth.factor=.7;smooth.iterations=4
bpy.ops.object.modifier_apply(modifier=smooth.name)
for side in (-1,1):
    ellipsoid('Eyeball',(-1.139,side*.177,1.389),(.041,.035,.036))
    ellipsoid('Inset ear bowl',(-.828,side*.224,1.623),(.043,.037,.065))
    tube('Upper eyelid',[(-1.175,side*.182,1.393),(-1.145,side*.207,1.420),(-1.111,side*.191,1.403)],.009)
    tube('Mouth crease',[(-1.340,0,1.174),(-1.290,side*.075,1.159),(-1.205,side*.126,1.176),(-1.138,side*.134,1.195)],.006)
tube('Philtrum',[(-1.357,0,1.251),(-1.364,0,1.210),(-1.340,0,1.174)],.007)

# A closed hand-shaped triangular nose, not a painted black triangle.
verts=[(-1.365,-.078,1.279),(-1.365,.078,1.279),(-1.392,0,1.215),
       (-1.308,-.073,1.300),(-1.308,.073,1.300),(-1.325,0,1.222)]
faces=[(0,2,1),(3,4,5),(0,1,4,3),(1,2,5,4),(2,0,3,5)]
m=bpy.data.meshes.new('Nose anatomy');m.from_pydata(verts,[],faces);m.update()
nose=bpy.data.objects.new('Nose',m);scene.collection.objects.link(nose);parts.append(nose)
bevel=nose.modifiers.new('Nose softness','BEVEL');bevel.width=.014;bevel.segments=3
bpy.context.view_layer.objects.active=nose;bpy.ops.object.modifier_apply(modifier=bevel.name)

# Continuous corrugated mane shell. Tufts follow the neck surface; no image
# planes, no copied learned vertices, no quality-degrading alterations.
v=[];f=[];rings=48;around=144
for i in range(rings+1):
    t=math.pi*i/rings
    for j in range(around):
        p=2*math.pi*j/around
        wave=1+.035*math.sin(29*p+8*t)+.022*math.sin(47*p-11*t)
        # Front cap sits behind the independently sculpted face.
        x=-.63-.36*math.cos(t)+.018*math.sin(19*p+7*t)*math.sin(t)
        y=.345*math.sin(t)*math.cos(p)*wave
        z=1.13+.535*math.sin(t)*math.sin(p)*wave
        v.append((x,y,z))
for i in range(rings):
    for j in range(around):
        a=i*around+j;b=i*around+(j+1)%around
        f.append((a,b,b+around,a+around))
m=bpy.data.meshes.new('Corrugated mane mesh');m.from_pydata(v,[],f);m.update()
mane=bpy.data.objects.new('Sculpted mane',m);scene.collection.objects.link(mane);parts.append(mane)

# Individual curved solid locks give the mane a readable layered edge.
for i in range(130):
    t=rng.uniform(.45,2.45);p=rng.uniform(0,2*math.pi)
    pos=Vector((-.63-.36*math.cos(t),.35*math.sin(t)*math.cos(p),1.13+.54*math.sin(t)*math.sin(p)))
    normal=Vector((-.55*math.cos(t),math.sin(t)*math.cos(p),math.sin(t)*math.sin(p))).normalized()
    down=Vector((.08,0,-.1));length=rng.uniform(.035,.075)
    tangent=normal.cross(Vector((1,0,0)))
    if tangent.length<.1:tangent=Vector((0,1,0))
    tangent.normalize();bitangent=normal.cross(tangent).normalized();width=length*.32
    verts=[tuple(pos+tangent*math.cos(a)*width+bitangent*math.sin(a)*width) for a in [2*math.pi*k/6 for k in range(6)]]
    verts.append(tuple(pos+normal*length+down*length*3))
    faces=[tuple(range(5,-1,-1))]+[(k,(k+1)%6,6) for k in range(6)]
    m=bpy.data.meshes.new('Solid lock');m.from_pydata(verts,[],faces);m.update()
    o=bpy.data.objects.new('Mane lock',m);scene.collection.objects.link(o);parts.append(o)

tube('Tail',[(.83,0,1.0),(1.03,.025,.90),(1.15,.045,.61),(1.32,.08,.43),(1.43,.10,.46)],.030)
tuft=ellipsoid('Tail tuft',(1.46,.10,.46),(.105,.062,.064));tuft.rotation_euler.y=-.25

material=bpy.data.materials.new('Shared neutral clay');material.use_nodes=True
shader=material.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(.32,.32,.32,1)
shader.inputs['Roughness'].default_value=.72
for o in parts:
    o.data.materials.clear();o.data.materials.append(material)
    for p in o.data.polygons:p.use_smooth=True

# Freeze and export independent geometry BEFORE loading the optional comparison.
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=skin
mesh_path=out/'lion-without-noetra.glb'
bpy.ops.export_scene.gltf(filepath=str(mesh_path),export_format='GLB',use_selection=True,export_yup=True)
frozen=hashlib.sha256(mesh_path.read_bytes()).hexdigest()
scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.device='CPU'
scene.render.threads_mode='FIXED';scene.render.threads=3
scene.render.resolution_x=1100;scene.render.resolution_y=800;scene.render.resolution_percentage=100
scene.world=bpy.data.worlds.new('Studio world');scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.12,.12,.12,1)
scene.world.node_tree.nodes['Background'].inputs[1].default_value=.5
scene.view_settings.view_transform='AgX'
bpy.ops.object.camera_add(location=(-4,-6,3));camera=bpy.context.object;camera.name='Shared studio camera';camera.data.type='ORTHO';scene.camera=camera
for name,location,power,size in [('Key',(-3,-4,5),550,4),('Fill',(-1,4,3),350,3),('Rim',(3,1,4),600,3)]:
    bpy.ops.object.light_add(type='AREA',location=location);light=bpy.context.object;light.name=name;light.data.energy=power;light.data.shape='DISK';light.data.size=size
    light.rotation_euler=(Vector((0,0,.8))-light.location).to_track_quat('-Z','Y').to_euler()

views={'side':Vector((0,-1,.12)), 'three-quarter':Vector((-1,-1.6,.35))}
report={'baselineMethod':'Host-authored procedural Blender mesh, built from primitives and remeshed; no NOETRA modules or learned shape model',
        'baselineMeshSha256':frozen,'seed':8053,'accuracyPercent':None,
        'limitations':['Different construction methods, not a controlled accuracy or model-quality comparison.','Procedural lion is an approximation, not exact reconstruction.','Independent baseline finished before existing comparison mesh was loaded.'],
        'meshes':{}}

def present(objects,arm):
    bpy.context.view_layer.update()
    points=[o.matrix_world@Vector(c) for o in objects for c in o.bound_box]
    lo=Vector([min(p[k] for p in points) for k in range(3)]);hi=Vector([max(p[k] for p in points) for k in range(3)])
    center=(lo+hi)/2;height=hi.z-lo.z
    # Normalize only presentation size/grounding, preserving original proportions.
    for o in objects:
        o.location=(o.location-Vector((center.x,center.y,lo.z)))/height
        o.scale/=height
    bpy.context.view_layer.update();target=Vector((0,0,.52));camera.data.ortho_scale=2.18
    for view,direction in views.items():
        camera.location=target+direction.normalized()*5
        camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
        scene.render.filepath=str(out/(arm+'-'+view+'.png'));bpy.ops.render.render(write_still=True)
    report['meshes'][arm]={'objects':len(objects),'vertices':sum(len(o.data.vertices) for o in objects),
                         'triangles':sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in objects)}

present(parts,'without-noetra')
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(out/'lion-without-noetra.blend'),compress=True)
if opt.comparison_mesh:
    for o in parts:o.hide_render=True;o.hide_set(True)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.import_scene.gltf(filepath=str(Path(opt.comparison_mesh).resolve()))
    comparison=[o for o in bpy.context.selected_objects if o.type=='MESH']
    for o in comparison:
        o.data.materials.clear();o.data.materials.append(material)
        for p in o.data.polygons:p.use_smooth=True
    present(comparison,'with-noetra')
    report['comparisonMeshSha256']=hashlib.sha256(Path(opt.comparison_mesh).read_bytes()).hexdigest()
assert hashlib.sha256(mesh_path.read_bytes()).hexdigest()==frozen
assert not any(n=='noetra' or n.startswith('noetra.') for n in sys.modules)
report['noetraImported']=False
(out/'evidence.json').write_text(json.dumps(report,indent=2))
print('INDEPENDENT_LION_COMPLETE',json.dumps(report))
