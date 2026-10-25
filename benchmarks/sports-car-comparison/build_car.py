"""Original procedural car study. Run only in a NEW background Blender process.

The same modelling code and lighting are used for both workflow arms. Parameters
are supplied by the author, not inferred automatically from an image.
"""
import bpy
import bmesh
import math
import json
import sys
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import interpolate_bezier

args = sys.argv[sys.argv.index('--') + 1:]
config = json.loads(Path(args[0]).read_text(encoding='utf-8'))
output = Path(args[1]).resolve()
output.mkdir(parents=True, exist_ok=True)
if any((output / name).exists() for name in ['sports-car.blend', 'sports-car.glb', 'front.png']):
    raise RuntimeError('Use a new output folder; existing model/render files will not be overwritten.')

# This is a fresh --factory-startup --background process, not the user's UI scene.
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = config['render_samples']
scene.cycles.use_denoising = True
scene.render.threads_mode = 'FIXED'
scene.render.threads = 8
scene.render.resolution_x = config['render_width']
scene.render.resolution_y = config['render_height']
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.film_transparent = False
scene.view_settings.view_transform = 'AgX'
scene.view_settings.exposure = 0.6
scene.world = bpy.data.worlds.new('Neutral studio')
scene.world.use_nodes = True
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.10, 0.12, 0.15, 1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.32

car_collection = bpy.data.collections.new('SPORTS_CAR')
scene.collection.children.link(car_collection)
studio_collection = bpy.data.collections.new('PRESENTATION_STUDIO')
scene.collection.children.link(studio_collection)
root = bpy.data.objects.new('SportsCar_Root', None)
car_collection.objects.link(root)
root['workflow'] = config['label']
root['description'] = 'Original futuristic two-seat coupe concept; not an engineered or road-certified vehicle.'
root['seats'] = 2
model_objects = []

def move_collection(obj, collection):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    collection.objects.link(obj)

def register(obj, material, model=True):
    move_collection(obj, car_collection if model else studio_collection)
    if material is not None:
        obj.data.materials.append(material)
    if model:
        obj.parent = root
        model_objects.append(obj)
    return obj

def material(name, color, metallic=0, roughness=0.3, emission=None, strength=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Metallic'].default_value = metallic
    shader.inputs['Roughness'].default_value = roughness
    shader.inputs['Coat Weight'].default_value = 0.4 if metallic else 0.1
    if emission:
        shader.inputs['Emission Color'].default_value = (*emission, 1)
        shader.inputs['Emission Strength'].default_value = strength
    return mat

silver = material('Silver titanium paint', (0.47, 0.52, 0.59), 0.83, 0.22)
graphite = material('Graphite aero composite', (0.018, 0.022, 0.031), 0.48, 0.29)
glass = material('Dark cockpit glazing', (0.006, 0.014, 0.021), 0.48, 0.13)
rubber = material('Performance tire rubber', (0.010, 0.012, 0.015), 0.03, 0.56)
rim_mat = material('Brushed forged alloy', (0.20, 0.24, 0.29), 0.95, 0.25)
rim_edge = material('Polished rim edge', (0.58, 0.63, 0.70), 0.97, 0.16)
brake_mat = material('Brake rotor', (0.12, 0.14, 0.17), 0.85, 0.4)
cyan = material('Cyan LED signature', (0.02, 0.48, 0.62), 0.3, 0.2, (0.04, 0.8, 1.0), 4)
red = material('Rear LED signature', (0.6, 0.008, 0.015), 0.15, 0.2, (1, 0.005, 0.012), 3)
black = material('Intake and seam shadow', (0.003, 0.005, 0.007), 0.1, 0.43)
floor_mat = material('Charcoal studio floor', (0.025, 0.030, 0.041), 0.15, 0.32)

def smooth(obj):
    if obj.type == 'MESH':
        for poly in obj.data.polygons:
            poly.use_smooth = True

def mesh(name, vertices, faces, mat, model=True):
    data = bpy.data.meshes.new(name + '_Mesh')
    data.from_pydata(vertices, [], faces)
    data.update()
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(data)
    bm.free()
    obj = bpy.data.objects.new(name, data)
    (car_collection if model else studio_collection).objects.link(obj)
    if model:
        obj.parent = root
        model_objects.append(obj)
    obj.data.materials.append(mat)
    smooth(obj)
    return obj

def bevel(obj, width=0.015, segments=3):
    modifier = obj.modifiers.new('Small manufactured edge radii', 'BEVEL')
    modifier.width = width
    modifier.segments = segments
    return modifier

def box(name, location, dimensions, mat, radius=0.01, model=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    register(obj, mat, model)
    if radius:
        bevel(obj, radius)
    return obj

def curve(name, points, radius, mat, cyclic=False):
    data = bpy.data.curves.new(name + '_Curve', 'CURVE')
    data.dimensions = '3D'
    data.bevel_depth = radius
    data.bevel_resolution = 3
    path = data.splines.new('BEZIER')
    path.bezier_points.add(len(points)-1)
    for point, co in zip(path.bezier_points, points):
        point.co = co
        point.handle_left_type = 'AUTO'
        point.handle_right_type = 'AUTO'
    path.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, data)
    car_collection.objects.link(obj)
    obj.parent = root
    obj.data.materials.append(mat)
    model_objects.append(obj)
    return obj

def cylinder(name, location, radius, depth, mat, vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                     location=location, rotation=(math.pi/2, 0, 0))
    obj = bpy.context.object
    obj.name = name
    register(obj, mat)
    smooth(obj)
    bevel(obj, 0.004, 2)
    return obj

def torus_wheel(name, center, major, radial_minor, axial_minor, mat, count=96, cross=16):
    vertices, faces = [], []
    for i in range(count):
        theta = 2*math.pi*i/count
        for j in range(cross):
            phi = 2*math.pi*j/cross
            radius = major + radial_minor*math.cos(phi)
            vertices.append((center[0]+radius*math.cos(theta), center[1]+axial_minor*math.sin(phi), center[2]+radius*math.sin(theta)))
    for i in range(count):
        for j in range(cross):
            faces.append((i*cross+j, ((i+1)%count)*cross+j,
                          ((i+1)%count)*cross+(j+1)%cross, i*cross+(j+1)%cross))
    return mesh(name, vertices, faces, mat)

def linear(x, knots):
    for i in range(len(knots)-1):
        if knots[i][0] <= x <= knots[i+1][0]:
            a, b = knots[i], knots[i+1]
            t = (x-a[0])/(b[0]-a[0])
            t = t*t*(3-2*t)
            return a[1]*(1-t) + b[1]*t
    return knots[0][1] if x < knots[0][0] else knots[-1][1]

length = config['body_length']
half_width = config['body_half_width']
axle = config['axle_half_distance']
tire_r = config['tire_radius']
wheel_y = config['wheel_y']
arch_r = config['arch_radius']
sections, ring = config['body_sections'], config['body_ring_points']
width_knots = [(-2.30,0.77),(-2.10,0.91),(-1.35,0.997),(-0.65,0.91),(0.4,0.91),(1.35,1.0),(2.05,0.96),(2.3,0.88)]
height_knots = [(-2.3,0.42),(-1.7,0.57),(-0.8,0.62),(0.0,0.65),(0.9,0.65),(1.7,0.66),(2.3,0.59)]
verts, faces = [], []
for i in range(sections):
    x = (-length/2) + length*i/(sections-1)
    width = linear(x, width_knots)*half_width
    center_top = linear(x, height_knots)
    bulge = 0.25*(math.exp(-((x+axle)/0.43)**2) + math.exp(-((x-axle)/0.47)**2))
    for j in range(ring):
        theta = 2*math.pi*j/ring
        side = math.sin(theta)
        up = math.cos(theta)
        y = width*side
        if up >= 0:
            z = 0.43+(center_top-0.43)*up**0.72 + bulge*math.exp(-((abs(side)-0.83)/0.19)**2)
        else:
            z = 0.15+0.28*(1+up)**0.65
        verts.append((x,y,z))
for i in range(sections-1):
    for j in range(ring):
        faces.append((i*ring+j,(i+1)*ring+j,(i+1)*ring+(j+1)%ring,i*ring+(j+1)%ring))
faces.extend([tuple(reversed(range(ring))),tuple((sections-1)*ring+j for j in range(ring))])
body = mesh('Continuous sculpted body shell', verts, faces, silver)

# Four independent wheel-well cuts, not a cylinder through the entire chassis.
for x in [-axle, axle]:
    for sign in [-1,1]:
        bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=arch_r, depth=0.60,
            location=(x,sign*1.00,tire_r),rotation=(math.pi/2,0,0))
        cutter = bpy.context.object
        cutter.name = 'Temporary owned wheel-well cutter'
        bpy.context.view_layer.objects.active = body
        body.select_set(True)
        mod = body.modifiers.new('Wheel arch opening', 'BOOLEAN')
        mod.operation = 'DIFFERENCE'
        mod.solver = 'EXACT'
        mod.object = cutter
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cutter, do_unlink=True)
bevel(body,0.009,2)

# Dark undertray and visible rocker aero.
box('Flat undertray',(0,0,0.155),(3.9,1.52,0.05),graphite,0.025)
for sign in [-1,1]:
    curve('Rocker aero blade '+str(sign),[(-1.0,sign*0.92,0.20),(-0.2,sign*0.98,0.18),(0.68,sign*1.005,0.22),(1.0,sign*0.97,0.29)],0.028,graphite)
    curve('Door seam '+str(sign),[(-0.72,sign*0.915,0.62),(-0.89,sign*0.93,0.36),(-0.55,sign*0.94,0.27),(0.55,sign*0.94,0.29),(0.83,sign*0.96,0.57)],0.0025,black)
    curve('Flush door handle '+str(sign),[(0.36,sign*0.935,0.62),(0.53,sign*0.943,0.63)],0.008,rim_mat)
    points=[(0.72,sign*0.963,0.40),(0.82,sign*0.972,0.65),(1.12,sign*0.982,0.60),(1.01,sign*0.993,0.32)]
    mesh('Rear quarter intake '+str(sign),points,[(0,1,2,3)],black)
    curve('Intake outer blade '+str(sign),[points[1],points[2],points[3]],0.012,silver)

# Wraparound dark cockpit; this is a closed concept canopy, not production glass.
cx=[-0.94,-0.73,-0.43,0.05,0.48,0.78,1.04]
cw=[0.42,0.61,0.61,0.59,0.55,0.44,0.15]
cz=[0.69,0.91,config['roof_height']-0.03,config['roof_height'],config['roof_height']-0.055,0.94,0.70]
cverts,cfaces=[],[]
steps=24
for x,w,z in zip(cx,cw,cz):
    for j in range(steps):
        theta=2*math.pi*j/steps
        y=w*math.sin(theta)
        zz=0.63+(z-0.63)*max(math.cos(theta),0)**0.62 if math.cos(theta)>=0 else 0.62
        cverts.append((x,y,zz))
for i in range(len(cx)-1):
    for j in range(steps):
        cfaces.append((i*steps+j,(i+1)*steps+j,(i+1)*steps+(j+1)%steps,i*steps+(j+1)%steps))
cfaces.extend([tuple(reversed(range(steps))),tuple((len(cx)-1)*steps+j for j in range(steps))])
canopy=mesh('Wraparound cockpit glazing',cverts,cfaces,glass)
sub=canopy.modifiers.new('Canopy surface continuity','SUBSURF')
sub.levels=2
sub.render_levels=2
for sign in [-1,1]:
    curve('Cockpit brightwork '+str(sign),[(-0.94,sign*0.42,0.70),(-0.75,sign*0.61,0.72),(-0.25,sign*0.61,0.72),(0.45,sign*0.56,0.71),(0.92,sign*0.32,0.71)],0.013,silver)
    curve('A pillar '+str(sign),[(-0.92,sign*0.43,0.70),(-0.65,sign*0.49,0.96),(-0.40,sign*0.47,1.105)],0.014,graphite)
    curve('Roof side rail '+str(sign),[(-0.40,sign*0.47,1.105),(0.05,sign*0.46,1.13),(0.45,sign*0.43,1.06),(0.82,sign*0.36,0.83)],0.017,silver)
    curve('Mirror stalk '+str(sign),[(-0.59,sign*0.62,0.78),(-0.52,sign*1.00,0.79),(-0.46,sign*1.08,0.82)],0.012,graphite)
    mirror=box('Mirror housing '+str(sign),(-0.43,sign*1.09,0.83),(0.24,0.13,0.075),silver,0.035)
    box('Mirror glass '+str(sign),(-0.365,sign*1.091,0.836),(0.018,0.103,0.05),glass,0.01)
    box('Seat back '+str(sign),(0.23,sign*0.265,0.77),(0.18,0.29,0.33),graphite,0.07)

# Narrow lights are real model geometry, not labels baked into a picture.
for sign in [-1,1]:
    curve('Front lamp recess '+str(sign),[(-2.265,sign*0.40,0.43),(-2.15,sign*0.70,0.50),(-1.99,sign*0.855,0.59)],0.026,black)
    curve('Cyan headlight '+str(sign),[(-2.278,sign*0.41,0.441),(-2.164,sign*0.70,0.511),(-2.003,sign*0.855,0.601)],0.008,cyan)
    box('Front side intake '+str(sign),(-2.21,sign*0.69,0.30),(0.18,0.27,0.19),black,0.025)
box('Central intake',(-2.307,0,0.29),(0.035,0.99,0.16),black,0.016)
curve('Front splitter',[(-2.27,-0.91,0.17),(-2.33,-0.69,0.14),(-2.34,0,0.13),(-2.33,0.69,0.14),(-2.27,0.91,0.17)],0.026,graphite)
curve('Rear LED bar',[(2.31,-0.81,0.56),(2.327,0,0.57),(2.31,0.81,0.56)],0.009,red)
box('Rear black fascia',(2.298,0,0.40),(0.05,1.65,0.19),graphite,0.025)
box('Rear diffuser',(2.17,0,0.20),(0.31,1.66,0.14),graphite,0.02)
for y in [-0.68,-0.41,-0.14,0.14,0.41,0.68]:
    box('Rear diffuser fin',(2.18,y,0.21),(0.36,0.018,0.18),black,0.005)
for sign in [-1,1]:
    for offset in [0,0.08,0.16]:
        curve('Rear deck vent '+str(sign)+' '+str(offset),[(1.49,sign*(0.33+offset),0.69),(1.9,sign*(0.34+offset),0.655)],0.011,black)

wheels=[]
for x in [-axle,axle]:
    for sign in [-1,1]:
        center=(x,sign*wheel_y,tire_r)
        tire=torus_wheel('Tire_'+('Front' if x<0 else 'Rear')+('_L' if sign<0 else '_R'),center,tire_r-0.065,0.065,config['tire_half_width'],rubber,
            config['wheel_segments'],config['wheel_cross_segments'])
        tire['component']='tire'
        tire['axle']='front' if x<0 else 'rear'
        wheels.append(tire)
        face_y=sign*(wheel_y+config['tire_half_width']-0.012)
        cylinder('Rim barrel',(x,sign*wheel_y,tire_r),0.267,0.22,graphite)
        cylinder('Brake rotor',(x,face_y-sign*0.035,tire_r),0.213,0.012,brake_mat)
        torus_wheel('Polished rim lip',(x,face_y,tire_r),0.251,0.010,0.010,rim_edge,96,8)
        cylinder('Axle hub',(x,face_y+sign*0.013,tire_r),0.058,0.024,rim_edge,48)
        for spoke in range(5):
            angle=2*math.pi*spoke/5+0.18
            polar=[(0.052,angle-0.20),(0.24,angle+0.04),(0.25,angle+0.16),(0.10,angle+0.30)]
            front=[(x+r*math.cos(a),face_y+sign*0.014,tire_r+r*math.sin(a)) for r,a in polar]
            back=[(px,py-sign*0.024,pz) for px,py,pz in front]
            mesh('Swept alloy spoke',front+back,[(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)],rim_mat)
        for hole in range(12):
            a=2*math.pi*hole/12
            cylinder('Rotor perforation',(x+0.173*math.cos(a),face_y-sign*0.026,tire_r+0.173*math.sin(a)),0.009,0.003,black,8)
        caliper=box('Cyan brake caliper',(x+0.155,face_y-sign*0.022,tire_r+0.045),(0.055,0.045,0.14),cyan,0.012)
        # Arch lip follows the actual opening rather than covering the tire.
        points=[(x+arch_r*math.cos(math.pi*i/18),sign*0.992,tire_r+arch_r*math.sin(math.pi*i/18)) for i in range(19)]
        curve('Wheel arch fine lip',points,0.009,silver)

# NOETRA-assisted arm only: execute the host-reviewed local repair plan, not
# arbitrary text/code returned by a model or tool. Original baseline is frozen.
repair_log=[]
if config.get('fit_decorative_trim'):
    bpy.context.view_layer.update()
    deps=bpy.context.evaluated_depsgraph_get()
    surfaces={}
    for target in [body,canopy]:
        evaluated=target.evaluated_get(deps)
        data=evaluated.to_mesh()
        surfaces[target.name]=BVHTree.FromPolygons([evaluated.matrix_world@v.co for v in data.vertices],
            [list(p.vertices) for p in data.polygons])
        evaluated.to_mesh_clear()
    for obj in model_objects:
        if obj.type!='CURVE':
            continue
        target=canopy.name if obj.name.startswith(('A pillar','Roof side rail','Cockpit brightwork')) else body.name if obj.name.startswith(('Cyan headlight','Front lamp recess')) else None
        if not target:
            continue
        old=obj.data
        points=[]
        for spline in old.splines:
            if spline.type!='BEZIER':
                continue
            knots=spline.bezier_points
            for i in range(len(knots)-1):
                segment=interpolate_bezier(knots[i].co,knots[i].handle_right,knots[i+1].handle_left,knots[i+1].co,13)
                points.extend(segment if not points else segment[1:])
        attached=[]
        offset=0.029 if obj.name.startswith('Cyan headlight') else 0.005
        for point in points:
            hit=surfaces[target].find_nearest(obj.matrix_world@point)
            if hit[0] is None:
                raise RuntimeError('Surface fitting failed; do not fabricate an attached trim result.')
            attached.append(obj.matrix_world.inverted()@(hit[0]+hit[1]*offset))
        replacement=bpy.data.curves.new(old.name+'_SurfaceFitted','CURVE')
        replacement.dimensions='3D'
        replacement.bevel_depth=old.bevel_depth
        replacement.bevel_resolution=old.bevel_resolution
        poly=replacement.splines.new('POLY')
        poly.points.add(len(attached)-1)
        for point,co in zip(poly.points,attached):
            point.co=(*co,1)
        for mat in old.materials:
            replacement.materials.append(mat)
        obj.data=replacement
        repair_log.append({'object':obj.name,'repair':'project sampled existing trim centerline onto its actual evaluated target surface','target':target})

if config.get('bound_decorative_envelope'):
    exempt=('Tire_','Rim barrel','Brake rotor','Polished rim lip','Swept alloy spoke','Rotor perforation','Cyan brake caliper','Mirror','Seat','Continuous sculpted body shell','Wraparound cockpit glazing')
    for obj in model_objects:
        if obj.type not in {'MESH','CURVE'} or obj.name.startswith(exempt):
            continue
        for axis,limit in [(0,length/2-0.001),(1,half_width-0.001)]:
            bpy.context.view_layer.update()
            evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            data=evaluated.to_mesh()
            coordinates=[(evaluated.matrix_world@v.co)[axis] for v in data.vertices]
            lo,hi=min(coordinates),max(coordinates)
            evaluated.to_mesh_clear()
            low=max(lo,-limit)
            high=min(hi,limit)
            if lo< -limit or hi>limit:
                if high<=low:
                    # Entire thin fascia lies beyond the body plane: translate it inward.
                    delta=(-limit-lo) if hi< -limit else (limit-hi)
                    obj.location[axis]+=delta
                else:
                    factor=(high-low)/(hi-lo)
                    # World-axis affine fitting; all eligible decorative objects have no rotation.
                    old_location=obj.location[axis]
                    obj.scale[axis]*=factor
                    obj.location[axis]=factor*old_location + low-factor*lo
                repair_log.append({'object':obj.name,'repair':'bound decorative extent only','axis':axis,'before':[lo,hi],'target_limit':limit})

# Shared studio and presentation settings.
box('Studio floor',(0,0,-0.055),(200,200,0.10),floor_mat,0,False)
def aim(obj, target):
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
def light(name, location, power, size, size_y=None):
    data=bpy.data.lights.new(name,'AREA')
    data.energy=power
    data.shape='RECTANGLE'
    data.size=size
    data.size_y=size_y or size
    obj=bpy.data.objects.new(name,data)
    studio_collection.objects.link(obj)
    obj.location=location
    aim(obj,(0,0,0.4))
    return obj
light('Overhead softbox',(-1,-1,5.2),1500,5.0,3.0)
light('Long side reflection',(0,4,3.0),1400,5.5,1.4)
light('Front key',(-5,-4,2.8),1100,4.0,2.5)
light('Rear rim',(4,-1,3.4),1200,3.4,2)
camera_data=bpy.data.cameras.new('Common comparison camera')
camera=bpy.data.objects.new('Common comparison camera',camera_data)
studio_collection.objects.link(camera)
camera.location=(-6.8,-5.8,2.65)
camera_data.lens=56
aim(camera,(0,0,0.55))
scene.camera=camera

bpy.context.view_layer.update()
depsgraph=bpy.context.evaluated_depsgraph_get()
bounds=[]
measured_wheels=[]
triangles=0
for obj in model_objects:
    if obj.type not in {'MESH','CURVE'}:
        continue
    evaluated=obj.evaluated_get(depsgraph)
    computed=evaluated.to_mesh()
    computed.calc_loop_triangles()
    triangles+=len(computed.loop_triangles)
    if obj in wheels:
        points=[tuple(evaluated.matrix_world@v.co) for v in computed.vertices]
        low=[min(p[i] for p in points) for i in range(3)]
        high=[max(p[i] for p in points) for i in range(3)]
        measured_wheels.append({'name':obj.name,'center':[(low[i]+high[i])/2 for i in range(3)],'radius':(high[2]-low[2])/2,'half_width':(high[1]-low[1])/2,'ground_minimum':low[2]})
    if not obj.name.startswith('Mirror'):
        bounds.extend(tuple(evaluated.matrix_world@v.co) for v in computed.vertices)
    evaluated.to_mesh_clear()
mins=[min(p[i] for p in bounds) for i in range(3)]
maxs=[max(p[i] for p in bounds) for i in range(3)]
metrics={
    'workflow':config['label'],'blender_version':bpy.app.version_string,
    'object_count':len(model_objects),'evaluated_triangles':triangles,
    'vehicle_bounds_excluding_mirrors':{'minimum':mins,'maximum':maxs,'dimensions':[maxs[i]-mins[i] for i in range(3)]},
    'wheel_count':len(wheels),'wheels':measured_wheels,
    'design_parameters':config,
    'local_repairs':repair_log,
    'render':{'engine':'CYCLES','device':'CPU','samples':config['render_samples'],'resolution':[config['render_width'],config['render_height']],'camera_position':list(camera.location),'camera_lens_mm':camera.data.lens},
    'limitations':['Procedural visual concept, not CAD or validated vehicle engineering.','Dark cockpit is simplified; no mechanical drivetrain or functional suspension.','Some meshes intentionally intersect as a multi-part visual asset; not a single watertight manufacturing solid.','Concept image and procedural mesh are distinct outputs, not exact image-to-3D reconstruction.']
}
(output/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')

# Export only car objects. The editable .blend also keeps the presentation studio.
bpy.ops.object.select_all(action='DESELECT')
root.select_set(True)
for obj in model_objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active=root
bpy.ops.export_scene.gltf(filepath=str(output/'sports-car.glb'),export_format='GLB',use_selection=True,export_apply=True,export_animations=False,export_extras=True)
scene.render.filepath=str(output/'front.png')
bpy.ops.wm.save_as_mainfile(filepath=str(output/'sports-car.blend'))
bpy.ops.render.render(write_still=True)
camera.location=(6.8,5.8,2.65)
aim(camera,(0,0,0.55))
scene.render.filepath=str(output/'rear.png')
bpy.ops.render.render(write_still=True)
print('NOETRA_CAR_BUILD_COMPLETE '+json.dumps({'output':str(output),'triangles':triangles,'objects':len(model_objects)}))
