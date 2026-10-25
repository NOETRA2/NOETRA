"""Fixed data-only prior completion: patches, bounded fairing, complete wheels,
ground/framing checks and real geometry renders. No supplied Python executes.
"""
import bpy,sys,json,math,hashlib,struct,bmesh
from collections import Counter
from pathlib import Path
import numpy as np
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
sys.path.insert(0,str(Path(__file__).parent))
from structural_math import coons,fit_camera_distance,wheel_roundness
from part_adapter import validate_scene,fingerprint
job=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text());out=Path(job['output']);spec=job['spec']
bpy.ops.wm.open_mainfile(filepath=job['source'],load_ui=False);bpy.context.preferences.filepaths.file_preview_type='NONE';bpy.context.preferences.filepaths.save_version=0
scene=bpy.context.scene;validate_scene(scene);before=fingerprint(scene)
collection=bpy.data.collections[spec['collection']];allowed=set();patch_reports=[];recess_reports=[]
for patch in spec['patches']:
    o=collection.objects[patch['object']];assert o.type=='MESH';allowed.add(o.name);n=patch.get('resolution',24)
    vertices=[coons(patch['curves'],i/n,j/n).tolist() for i in range(n+1) for j in range(n+1)]
    faces=[(i*(n+1)+j,(i+1)*(n+1)+j,(i+1)*(n+1)+j+1,i*(n+1)+j+1) for i in range(n) for j in range(n)]
    array=np.asarray(vertices);indices=np.asarray(faces);areas=np.linalg.norm(np.cross(array[indices[:,1]]-array[indices[:,0]],array[indices[:,3]]-array[indices[:,0]]),axis=1);assert np.min(areas)>1e-10
    mesh=bpy.data.meshes.new(o.name+' constrained patch');mesh.from_pydata(vertices,[],faces);mesh.update()
    for m in o.data.materials:mesh.materials.append(m)
    old=o.data;o.data=mesh
    for p in mesh.polygons:p.use_smooth=True
    if old.users==0:bpy.data.meshes.remove(old)
    o['shape_provenance']=patch['provenance'];o['construction']='Explicit boundary-constrained Coons surface, not measured hidden depth'
    patch_reports.append({'object':o.name,'vertices':len(vertices),'faces':len(faces),'provenance':patch['provenance']})
for item in spec.get('fairing',[]):
    o=collection.objects[item['object']];allowed.add(o.name);assert o.type=='MESH'
    if o.data.users>1:o.data=o.data.copy()
    p=np.array([v.co[:] for v in o.data.vertices]);base=p.copy();minimum=np.array(item['minimum']);maximum=np.array(item['maximum']);active=((p>minimum)&(p<maximum)).all(1)
    # End selection remains fixed, so a vertex cannot expand the editable region.
    edges=np.array([e.vertices[:] for e in o.data.edges]);degree=np.bincount(edges.ravel(),minlength=len(p));axis='XYZ'.index(item['axis'])
    for iteration in range(item['iterations']):
        total=np.zeros(len(p));np.add.at(total,edges[:,0],p[edges[:,1],axis]);np.add.at(total,edges[:,1],p[edges[:,0],axis])
        delta=(total/np.maximum(degree,1)-p[:,axis])*item['strength'];p[active,axis]+=delta[active]
        p[:,axis]=base[:,axis]+np.clip(p[:,axis]-base[:,axis],-item['maxDisplacement'],item['maxDisplacement'])
    for vertex,point in zip(o.data.vertices,p):vertex.co=point
    o.data.update();assert np.array_equal(p[~active],base[~active])
for item in spec.get('recesses',[]):
    target=collection.objects[item['object']];guide=collection.objects[item['guide']];allowed.add(target.name);assert target.type=='MESH' and guide.type=='MESH'
    direction=Vector(item['outward']);assert direction.length>.1;direction.normalize();inverse=target.matrix_world.inverted()
    points=[inverse@(guide.matrix_world@v.co+direction*distance) for v in guide.data.vertices for distance in [-item['depth'],item['clearance']]]
    mesh=bpy.data.meshes.new('Owned constrained recess');mesh.from_pydata(points,[],[]);mesh.update();bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.convex_hull(bm,input=list(bm.verts),use_existing_faces=False);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
    cutter=bpy.data.objects.new('Owned constrained recess',mesh);scene.collection.objects.link(cutter);cutter.matrix_world=target.matrix_world.copy()
    backup=target.data.copy();previous=len(target.data.polygons);bpy.ops.object.select_all(action='DESELECT');target.select_set(True);bpy.context.view_layer.objects.active=target
    modifier=target.modifiers.new('Declared exact guide recess','BOOLEAN');modifier.operation='DIFFERENCE';modifier.solver='EXACT';modifier.object=cutter
    bpy.ops.object.modifier_move_to_index(modifier=modifier.name,index=0)
    bpy.ops.object.modifier_apply(modifier=modifier.name);accepted=len(target.data.polygons)>previous*.8
    if not accepted:
        rejected=target.data;target.data=backup
        if rejected.users==0:bpy.data.meshes.remove(rejected)
    else:bpy.data.meshes.remove(backup)
    recess_reports.append({'object':target.name,'guide':guide.name,'accepted':accepted,'reason':'Bounded exact recess retained sufficient body geometry' if accepted else 'Rejected destructive Boolean result; original body checkpoint restored'})
    bpy.data.objects.remove(cutter,do_unlink=True);bpy.data.meshes.remove(mesh)
bpy.context.view_layer.update();after=fingerprint(scene);changed=[n for n,h in before['objects'].items() if after['objects'].get(n)!=h]
assert set(changed)<=allowed and set(before['objects'])==set(after['objects'])
assert before['world']==after['world'] and before['frame']==after['frame'] and before['active_camera']==after['active_camera']
def evaluated():
    dep=bpy.context.evaluated_depsgraph_get();points=[];triangles=0
    for o in collection.all_objects:
        if o.type not in ['MESH','CURVE'] or o.hide_render:continue
        e=o.evaluated_get(dep);m=e.to_mesh();m.calc_loop_triangles();triangles+=len(m.loop_triangles);points.extend([tuple(e.matrix_world@v.co) for v in m.vertices]);e.to_mesh_clear()
    a=np.asarray(points);assert len(a)>0 and np.isfinite(a).all();return a,triangles
points,triangles=evaluated();floor=scene.objects[spec['floor']];assert floor.name not in collection.all_objects;ground=float(points[:,2].min()-spec.get('groundClearance',.003));floor_top=max((floor.matrix_world@Vector(c)).z for c in floor.bound_box);floor.location.z+=ground-floor_top;bpy.context.view_layer.update()
wheels=[]
for name in spec['wheels']:
    o=collection.objects[name];record=wheel_roundness([tuple(o.matrix_world@v.co) for v in o.data.vertices],spec.get('wheelAxis',1));record['object']=name
    counts=Counter(tuple(sorted(edge)) for p in o.data.polygons for edge in p.edge_keys);record['closedSurface']=all(c==2 for c in counts.values())
    assert record['completeCircle'] and record['closedSurface'] and record['minimumZ']>ground;wheels.append(record)
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=12;scene.cycles.use_denoising=True;scene.render.threads_mode='FIXED';scene.render.threads=4
scene.render.resolution_x=1600;scene.render.resolution_y=900;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.film_transparent=False
scene.view_settings.view_transform='AgX';scene.view_settings.exposure=-.6;scene.view_layers[0].use_pass_z=False;scene.view_layers[0].use_pass_normal=False
original=scene.camera;center=Vector(((points.min(0)+points.max(0))/2).tolist());center.z=float(points[:,2].min()+np.ptp(points[:,2])*.48)
front=Vector(spec.get('forward',[-1,0,0]));side=Vector((0,-1,0));poses=[('reference',None),('front',front+Vector((0,0,.16))),('left',side+Vector((0,0,.10))),('rear',-front+Vector((0,0,.20))),('right',-side+Vector((0,0,.10))),('top',Vector((0,0,1))),('rear-three-quarter',(-front+side+Vector((0,0,.52))).normalized())];frames=[]
for name,direction in poses:
    d=original.data.copy();camera=bpy.data.objects.new('Verified view '+name,d);scene.collection.objects.link(camera);d.lens=65;d.sensor_fit='HORIZONTAL';d.shift_x=0;d.shift_y=0
    target=center.copy()
    if direction is None:
        camera.matrix_world=original.matrix_world.copy();d.lens=original.data.lens;target=Vector(spec.get('referenceTarget',center))
    else:camera.location=target+direction.normalized()*12;camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    bpy.context.view_layer.update()
    distance=fit_camera_distance(points,np.array(camera.matrix_world.to_3x3()),target,d.angle_x,1600/900,.075)
    # Reference composition may change slightly to guarantee full tyre clearance.
    camera.location=target+camera.matrix_world.to_3x3()@Vector((0,0,distance*1.01));scene.camera=camera;bpy.context.view_layer.update()
    q=(points-np.array(camera.location))@np.array(camera.matrix_world.to_3x3());depth=-q[:,2];tx=math.tan(d.angle_x/2);ty=tx/(1600/900)
    coords=np.column_stack([.5+q[:,0]/(2*tx*depth),.5+q[:,1]/(2*ty*depth),depth]);bounds=[coords[:,:2].min(0).tolist(),coords[:,:2].max(0).tolist()]
    assert (coords[:,2]>0).all() and coords[:,:2].min()>.055 and coords[:,:2].max()<.945
    frames.append({'name':name,'boundsNormalized':bounds,'allVerticesInFrame':True,'wheelGroundClearance':min(w['minimumZ']-ground for w in wheels),'camera':[list(r) for r in camera.matrix_world]})
    if name=='reference':
        # Save the clean structured hypothesis with a safe default camera.
        root=collection.objects.get('SportsCar_Root')
        if root:root['workflow']='NOETRA explicit geometric-prior completion; photo-guided, unseen shape proposed, not automatically recovered'
        bpy.ops.object.select_all(action='DESELECT')
        for o in collection.all_objects:o.select_set(True)
        bpy.context.view_layer.objects.active=next(o for o in collection.all_objects if o.type=='MESH')
        bpy.ops.export_scene.gltf(filepath=str(out/'model.glb'),export_format='GLB',use_selection=True,export_apply=True,export_animations=False,export_extras=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(out/'model.blend'),compress=True)
    scene.render.filepath=str(out/(name+'.png'));bpy.ops.render.render(write_still=True)
    if name in ['front','left','rear','right']:
        neutral=bpy.data.materials.get('Structure inspection')
        if not neutral:
            neutral=bpy.data.materials.new('Structure inspection');neutral.use_nodes=True;p=neutral.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(.28,.3,.33,1);p.inputs['Roughness'].default_value=.5
        scene.view_layers[0].material_override=neutral;scene.render.resolution_x=1000;scene.render.resolution_y=563;scene.render.filepath=str(out/(name+'-geometry.png'));bpy.ops.render.render(write_still=True);scene.view_layers[0].material_override=None;scene.render.resolution_x=1600;scene.render.resolution_y=900
    scene.camera=original
    if name!='reference':bpy.data.objects.remove(camera,do_unlink=True)
report={'kind':'explicit-structural-prior-completion','triangles':triangles,'objects':len(collection.all_objects),'changedObjects':changed,'protectedObjectsUnchanged':True,'patches':patch_reports,'recessProposals':recess_reports,'wheels':wheels,'groundZ':ground,'framing':frames,
    'appearance':'Real geometry/materials from an explicit authored prior; original photograph is not projected onto this model.',
    'limits':['Single-view hidden shape and scale remain hypotheses.','This route requires an explicit prior and authored boundary constraints; not automatic semantic reconstruction.','Separate visual parts are not a watertight engineering solid.']}
(out/'structure-verification.json').write_text(json.dumps(report,indent=2));print('NOETRA_STRUCTURAL_COMPLETION_RENDERED')
