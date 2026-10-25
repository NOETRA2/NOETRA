"""Fixed front-outline loft builder. Side/depth/rear are declared hypotheses."""
import bpy,bmesh,sys,json,math,uuid
from pathlib import Path
from mathutils import Vector
job=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf8'))
out=Path(job['output']);data=job['geometry']
assert out.is_dir() and not (out/'source.blend').exists()
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.context.preferences.filepaths.file_preview_type='NONE'
scene=bpy.context.scene;scene.unit_settings.system='NONE'
collection=bpy.data.collections.new('NOETRA_OUTLINE');scene.collection.children.link(collection)
material=bpy.data.materials.new('Estimated neutral surface');material.diffuse_color=(.25,.32,.38,1);material.use_nodes=True
p=material.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(.25,.32,.38,1);p.inputs['Metallic'].default_value=.45;p.inputs['Roughness'].default_value=.3
def mesh(name,vertices,faces,status):
 d=bpy.data.meshes.new(name+'_mesh');d.from_pydata(vertices,[],faces);d.update();bm=bmesh.new();bm.from_mesh(d)
 bmesh.ops.triangulate(bm,faces=[f for f in bm.faces if len(f.verts)>4]);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(d);bm.free()
 o=bpy.data.objects.new(name,d);collection.objects.link(o);d.materials.append(material)
 o['persistent_id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'noetra-outline/'+name));o['evidence_status']=status
 return o
rings=data['rings'];n=len(rings[0]);count=len(rings)
mesh('Front_observed_outline',rings[0],[tuple(reversed(range(n)))],'Boundary observed; planar front fill is a hypothesis, not measured surface depth.')
v=[p for ring in rings for p in ring]
faces=[(r*n+i,r*n+(i+1)%n,(r+1)*n+(i+1)%n,(r+1)*n+i) for r in range(count-1) for i in range(n)]
sides=mesh('Sides_proposed',v,faces,'HYPOTHESIS: proposed cross-sections and depth. No side photograph supplied.')
for f in sides.data.polygons:f.use_smooth=True
mesh('Rear_proposed',rings[-1],[tuple(range(n))],'HYPOTHESIS: inferred rear cap, not observed.')
world=bpy.data.worlds.new('Outline studio');scene.world=world;world.color=(.15,.15,.15)
for name,loc,power in [('key',(-3,-4,5),700),('rim',(3,3,4),900)]:
 d=bpy.data.lights.new(name,'AREA');d.energy=power;d.shape='DISK';d.size=4;o=bpy.data.objects.new(name,d);scene.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((0,data['depth']/2,data['height']/2))-o.location).to_track_quat('-Z','Y').to_euler()
for name,loc,target,scale in [('front',data['cameraLocation'],data['cameraTarget'],data['orthoScale']),
 ('proposed-side',(data['width']*2,-data['depth']*2,data['height']*1.7),(0,data['depth']/2,data['height']/2),max(data['width'],data['height'],data['depth'])*1.8)]:
 d=bpy.data.cameras.new(name);d.type='ORTHO';d.ortho_scale=scale;o=bpy.data.objects.new(name,d);scene.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
scene.camera=bpy.data.objects['front'];scene.render.resolution_x=data['imageWidth'];scene.render.resolution_y=data['imageHeight'];scene.render.resolution_percentage=100
reference=bpy.data.images.load(job['reference']);reference.use_fake_user=True;reference.pack()
bpy.ops.wm.save_as_mainfile(filepath=str(out/'source.blend'),compress=True)
print('NOETRA_OUTLINE_BUILT',flush=True)
