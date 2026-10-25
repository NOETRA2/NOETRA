"""Fixed actual-mesh Blender adapter: compare cameras, then export accepted geometry."""
import bpy,sys,json,math,uuid,hashlib,struct
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras.object_utils import world_to_camera_view
sys.path.insert(0,str(Path(__file__).parent))
from blender_framing import points_for,verify_presentation
job=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf8'));out=Path(job['output'])
bpy.context.preferences.filepaths.file_preview_type='NONE';bpy.context.preferences.filepaths.save_version=0
def aim(o,target):o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
def material(name,color,metal=0,rough=.4):
 m=bpy.data.materials.new(name);m.use_nodes=True;p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough;return m
def camera(name,pose):
 d=bpy.data.cameras.new(name);d.sensor_fit='HORIZONTAL';d.sensor_width=36;d.lens=36/(2*math.tan(math.radians(pose['fovDegrees']/2)))
 o=bpy.data.objects.new(name,d);bpy.context.scene.collection.objects.link(o);o.location=pose['position'];aim(o,pose['target']);return o

def geometry_digest(objects):
 h=hashlib.sha256()
 for o in sorted(objects,key=lambda o:o.name):
  for v in o.data.vertices:h.update(struct.pack('<3d',*(o.matrix_world@v.co)))
  for p in o.data.polygons:
   h.update(struct.pack('<I',len(p.vertices)))
   for index in p.vertices:h.update(struct.pack('<I',index))
 return h.hexdigest()

def project_appearance(scene,projection):
 objects=list(bpy.data.collections['RECONSTRUCTED_MODEL'].all_objects);before=geometry_digest(objects);camera_before=list(scene.camera.matrix_world)
 source=bpy.data.images.load(projection['source']);source.pack();source.use_fake_user=True
 foreground=bpy.data.images.load(projection['mask']);foreground.colorspace_settings.name='Non-Color';foreground.pack()
 mask=bpy.data.images.load(str(out/'conditioning-mask.png'));pixels=list(mask.pixels);W,H=mask.size
 from mathutils import Matrix
 transform=Matrix(projection['sourceToConditioning']).inverted();count=total=0
 for o in objects:
  for p in o.data.polygons:p.material_index=0
  while len(o.data.materials)>1:o.data.materials.pop(index=len(o.data.materials)-1)
  while o.data.uv_layers:o.data.uv_layers.remove(o.data.uv_layers[-1])
  vertices=[o.matrix_world@v.co for v in o.data.vertices];tree=BVHTree.FromPolygons(vertices,[list(p.vertices) for p in o.data.polygons],all_triangles=True)
  uv=o.data.uv_layers.new(name='ObservedPhotoProjection');m=bpy.data.materials.new('Observed photo radiance — view dependent');m.use_nodes=True
  t=m.node_tree;t.nodes.clear();texture=t.nodes.new('ShaderNodeTexImage');texture.image=source;texture.extension='CLIP'
  alpha=t.nodes.new('ShaderNodeTexImage');alpha.image=foreground;alpha.extension='CLIP';mix=t.nodes.new('ShaderNodeMixRGB');t.links.new(alpha.outputs['Color'],mix.inputs[0]);mix.inputs[1].default_value=(.35,.35,.35,1);t.links.new(texture.outputs['Color'],mix.inputs[2])
  if o.data.color_attributes:
   vertex=t.nodes.new('ShaderNodeVertexColor');vertex.layer_name=o.data.color_attributes[0].name;t.links.new(vertex.outputs['Color'],mix.inputs[1])
  emission=t.nodes.new('ShaderNodeEmission');surface=t.nodes.new('ShaderNodeOutputMaterial');t.links.new(mix.outputs['Color'],emission.inputs['Color']);t.links.new(emission.outputs[0],surface.inputs[0])
  m['appearance_status']='Unlit observed radiance; not intrinsic PBR or recovered fine geometry';o.data.materials.append(m);slot=len(o.data.materials)-1
  for p in o.data.polygons:
   total+=1;center=sum((vertices[i] for i in p.vertices),Vector())/len(p.vertices);visible=False
   # A triangle may straddle an occlusion edge: its centroid alone is insufficient.
   samples=[center]+[vertices[i]*.8+center*.2 for i in p.vertices]
   for sample in samples:
    direction=sample-scene.camera.location;distance=direction.length;co=world_to_camera_view(scene,scene.camera,sample)
    x=int(co.x*W);y=int(co.y*H)
    if not (0<=x<W and 0<=y<H) or pixels[4*(y*W+x)]<.5:continue
    hit=tree.ray_cast(scene.camera.location,direction.normalized(),distance+.01)
    if hit[0] is not None and (hit[2]==p.index or abs(hit[3]-distance)<.0003):visible=True;break
   if not visible:continue
   p.material_index=slot;count+=1
   for li in p.loop_indices:
    coord=world_to_camera_view(scene,scene.camera,vertices[o.data.loops[li].vertex_index]);original=transform@Vector((coord.x*512,(1-coord.y)*512,1))
    uv.data[li].uv=((original.x+.5)/source.size[0],1-(original.y+.5)/source.size[1])
 after=geometry_digest(objects);assert before==after and list(scene.camera.matrix_world)==camera_before
 evidence={'geometrySha256Before':before,'geometrySha256After':after,'geometryAndCameraUnchanged':True,'projectedFaces':count,'totalFaces':total,
  'appearance':'Original observed radiance on visibility-tested triangles; unseen triangles retain learned color. This is not recovered PBR or geometric detail.'}
 (out/'appearance-evidence.json').write_text(json.dumps(evidence,indent=2))
if job['stage']=='outline':
 import numpy as np
 bpy.ops.wm.open_mainfile(filepath=str(out/'photo-base.blend'),load_ui=False);scene=bpy.context.scene;scene.camera=bpy.data.objects[job['chosen']+'Camera']
 objects=list(bpy.data.collections['RECONSTRUCTED_MODEL'].all_objects);before=geometry_digest(objects);cam=scene.camera;camera_matrix=cam.matrix_world.copy();R=cam.matrix_world.to_3x3();inv=cam.matrix_world.inverted();f=512*cam.data.lens/cam.data.sensor_width
 scene.cycles.samples=1;scene.cycles.use_denoising=False;scene.render.film_transparent=True;scene.view_settings.view_transform='Standard'
 bpy.data.objects['StudioFloor'].hide_render=True;scene.render.filepath=str(out/'initial-mask.png');bpy.ops.render.render(write_still=True)
 flow=np.load(out/'contour-flow.npy',allow_pickle=False);changed=protected=flipped=reverted=0;depth_change=0.;topology_before={o.name:[tuple(p.vertices) for p in o.data.polygons] for o in objects}
 for o in objects:
  original_normals=[p.normal.copy() for p in o.data.polygons];original_positions=[v.co.copy() for v in o.data.vertices];local=o.matrix_world.inverted().to_3x3()
  for v in o.data.vertices:
   point=o.matrix_world@v.co;co=world_to_camera_view(scene,cam,point);x=int(round(co.x*512));y=int(round((1-co.y)*512))
   if not (0<=x<512 and 0<=y<512):protected+=1;continue
   dx,dy=flow[y,x]
   if abs(dx)+abs(dy)<1e-6:protected+=1;continue
   depth=-(inv@point).z;delta=local@(R@Vector((float(dx)*depth/f,-float(dy)*depth/f,0)))
   v.co+=delta;depth_change=max(depth_change,abs((inv@(o.matrix_world@v.co)).z+depth));changed+=1
  # Restore vertices of orientation-invalid triangles instead of accepting a
  # better silhouette with folded faces. Expand restoration if neighbours fold.
  restored=set()
  for attempt in range(12):
   o.data.update();invalid=[p for p,n in zip(o.data.polygons,original_normals) if p.normal.dot(n)<=0]
   if not invalid:break
   indices={i for p in invalid for i in p.vertices};restored.update(indices)
   for i in indices:o.data.vertices[i].co=original_positions[i]
  o.data.update();flipped+=sum(p.normal.dot(n)<=0 for p,n in zip(o.data.polygons,original_normals));reverted+=len(restored)
  changed_object=sum((v.co-original_positions[v.index]).length>1e-10 for v in o.data.vertices)
  # Replace the proposal counters with the actual constrained checkpoint counts.
  if len(objects)==1:changed=changed_object;protected=len(o.data.vertices)-changed
 assert cam.matrix_world==camera_matrix
 evidence={'changedVertices':changed,'protectedVerticesUnchanged':protected,'restoredVerticesForFaceOrientation':reverted,'cameraDepthMaxChange':depth_change,'flippedFaces':flipped,
  'cameraAndTopologyPreserved':all(topology_before[o.name]==[tuple(p.vertices) for p in o.data.polygons] for o in objects),'beforeGeometrySha256':before,'candidateGeometrySha256':geometry_digest(objects),
  'proposal':'Camera-plane flow within a 12px silhouette band, capped at 9.6px displacement; relative depth fixed, estimated mask only.'}
 (out/'outline-evidence.json').write_text(json.dumps(evidence,indent=2));scene.render.filepath=str(out/'candidate-mask.png');bpy.ops.render.render(write_still=True)
 bpy.ops.wm.save_as_mainfile(filepath=str(out/'outline-candidate.blend'),compress=True)
elif job['stage']=='compare':
 bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.unit_settings.system='NONE'
 bpy.ops.wm.ply_import(filepath=job['mesh'],forward_axis='Y',up_axis='Z')
 objects=[o for o in bpy.context.selected_objects if o.type=='MESH'];assert objects
 collection=bpy.data.collections.new('RECONSTRUCTED_MODEL');scene.collection.children.link(collection)
 for i,o in enumerate(objects):
  for c in list(o.users_collection):c.objects.unlink(o)
  collection.objects.link(o);o.name='LearnedSurface_'+str(i);o['persistent_id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'noetra-photo/'+str(i)))
  o['geometry_status']='Learned single-view hypothesis; unobserved surfaces and physical scale unknown'
  for p in o.data.polygons:p.use_smooth=True
  m=material('Estimated vertex appearance '+str(i),(.4,.43,.47),.2,.34)
  if o.data.color_attributes:
   node=m.node_tree.nodes.new('ShaderNodeVertexColor');node.layer_name=o.data.color_attributes[0].name
   m.node_tree.links.new(node.outputs['Color'],m.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
  o.data.materials.clear();o.data.materials.append(m)
 scene.world=bpy.data.worlds.new('Neutral photo reconstruction studio');scene.world.use_nodes=True
 scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.04,.05,.06,1);scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.3
 for name,loc,power,sx,sy in [('Key',(-1,-3,4),600,4,2),('Rim',(1,3,3),700,4,1),('Fill',(4,0,2),350,3,3)]:
  d=bpy.data.lights.new(name,'AREA');d.energy=power;d.shape='RECTANGLE';d.size=sx;d.size_y=sy;o=bpy.data.objects.new(name,d);scene.collection.objects.link(o);o.location=loc;aim(o,(0,0,0))
 low=min((o.matrix_world@Vector(c)).z for o in objects for c in o.bound_box)
 bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,low-.015));floor=bpy.context.object;floor.name='StudioFloor';floor.data.materials.append(material('Charcoal studio floor',(.035,.04,.045),.15,.4))
 before=camera('InitialCamera',job['cameras']['initial']);candidate=camera('CandidateCamera',job['cameras']['candidate']);scene.camera=before
 scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.render.threads_mode='FIXED';scene.render.threads=4;scene.cycles.samples=8;scene.cycles.use_denoising=True
 scene.render.resolution_x=512;scene.render.resolution_y=512;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA'
 scene.view_layers[0].use_pass_z=True;scene.view_layers[0].use_pass_normal=True
 image=bpy.data.images.load(job['reference']);image.use_fake_user=True;image.pack()
 bpy.ops.wm.save_as_mainfile(filepath=str(out/'photo-base.blend'),compress=True)
 white=bpy.data.materials.new('Flat geometric visibility');white.use_nodes=True;t=white.node_tree;t.nodes.clear();e=t.nodes.new('ShaderNodeEmission');e.inputs['Color'].default_value=(1,1,1,1);s=t.nodes.new('ShaderNodeOutputMaterial');t.links.new(e.outputs[0],s.inputs['Surface'])
 floor.hide_render=True;scene.view_layers[0].material_override=white;scene.render.film_transparent=True;scene.cycles.samples=1;scene.cycles.use_denoising=False
 scene.view_settings.view_transform='Standard';scene.view_settings.exposure=0
 for name,c in [('initial',before),('candidate',candidate)]:
  scene.camera=c;scene.render.filepath=str(out/(name+'-mask.png'));bpy.ops.render.render(write_still=True)
  scene.render.image_settings.media_type='MULTI_LAYER_IMAGE';scene.render.image_settings.file_format='OPEN_EXR_MULTILAYER';scene.render.image_settings.color_depth='32'
  bpy.data.images['Render Result'].save_render(filepath=str(out/(name+'-passes.exr')),scene=scene)
  scene.render.image_settings.media_type='IMAGE';scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_depth='8'
 print('PHOTO_CAMERA_COMPARISON_RENDERED',flush=True)
else:
 bpy.ops.wm.open_mainfile(filepath=str(out/'photo-base.blend'),load_ui=False);scene=bpy.context.scene;scene.camera=bpy.data.objects[job['cameraName'] if 'cameraName' in job else job['chosen']+'Camera']
 scene.render.resolution_x=512;scene.render.resolution_y=512
 if job.get('projection'):project_appearance(scene,job['projection']);scene.view_settings.view_transform='Standard'
 bpy.data.objects['StudioFloor'].hide_render=False
 scene.render.resolution_x=1774;scene.render.resolution_y=887;scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.render.film_transparent=False
 observation=scene.camera;observed_matrix=observation.matrix_world.copy()
 presentation=bpy.data.objects.new('Presentation camera',observation.data.copy());scene.collection.objects.link(presentation);presentation.matrix_world=observed_matrix;scene.camera=presentation
 framing=verify_presentation(scene,scene.camera,points_for(bpy.data.collections['RECONSTRUCTED_MODEL']),bpy.data.objects['StudioFloor'])
 assert observation.matrix_world==observed_matrix
 framing['observationCameraUnchanged']=True;framing['observationCamera']=observation.name;framing['presentationCamera']=presentation.name
 (out/'presentation-verification.json').write_text(json.dumps(framing,indent=2))
 scene.render.filepath=str(out/'final.png');bpy.ops.wm.save_as_mainfile(filepath=str(out/'model.blend'),compress=True)
 bpy.ops.object.select_all(action='DESELECT')
 for o in bpy.data.collections['RECONSTRUCTED_MODEL'].all_objects:o.select_set(True)
 bpy.context.view_layer.objects.active=next(o for o in bpy.data.collections['RECONSTRUCTED_MODEL'].all_objects if o.type=='MESH')
 bpy.ops.export_scene.gltf(filepath=str(out/'model.glb'),export_format='GLB',use_selection=True,export_apply=True,export_animations=False,export_extras=True)
 bpy.ops.render.render(write_still=True);print('PHOTO_MODEL_EXPORTED_AND_RENDERED',flush=True)
