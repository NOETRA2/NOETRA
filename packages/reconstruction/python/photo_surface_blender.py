"""Fixed mesh inspection, candidate application and multi-angle rendering."""
import bpy,sys,json,math,hashlib,struct
from pathlib import Path
import numpy as np
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
sys.path.insert(0,str(Path(__file__).parent))
from blender_framing import verify_presentation
job=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text());out=Path(job['output']);stage=job['stage']
bpy.context.preferences.filepaths.file_preview_type='NONE';bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.open_mainfile(filepath=job['source'],load_ui=False);scene=bpy.context.scene
objects=[o for o in bpy.data.collections['RECONSTRUCTED_MODEL'].all_objects if o.type=='MESH'];assert len(objects)==1
obj=objects[0];scene.render.resolution_x=512;scene.render.resolution_y=512;scene.render.resolution_percentage=100
scene.render.threads_mode='FIXED';scene.render.threads=4;scene.cycles.samples=4;scene.cycles.use_denoising=False
vertices=np.array([tuple(obj.matrix_world@v.co) for v in obj.data.vertices]);faces=np.array([list(p.vertices) for p in obj.data.polygons],dtype=int);assert faces.shape[1]==3
camera_before=scene.camera.matrix_world.copy();world={o.name:[list(row) for row in o.matrix_world] for o in scene.objects if o!=obj}
def mask(name):
 floor=bpy.data.objects.get('StudioFloor');floor.hide_render=True
 scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.film_transparent=True
 scene.render.filepath=str(out/name);bpy.ops.render.render(write_still=True);floor.hide_render=False
def geometry_digest():
 h=hashlib.sha256()
 for v in obj.data.vertices:h.update(struct.pack('<3d',*(obj.matrix_world@v.co)))
 return h.hexdigest()
if stage=='inspect':
 coordinates=np.array([tuple(world_to_camera_view(scene,scene.camera,Vector(v))) for v in vertices]);pixels=np.column_stack([coordinates[:,0]*512,(1-coordinates[:,1])*512])
 np.savez_compressed(out/'surface-input.npz',vertices=vertices,faces=faces,pixels=pixels,depths=coordinates[:,2],cameraRotation=np.array(scene.camera.matrix_world.to_3x3()),focal=512*scene.camera.data.lens/scene.camera.data.sensor_width)
 (out/'surface-camera.json').write_text(json.dumps({'name':scene.camera.name,'matrix':[list(row) for row in scene.camera.matrix_world]}))
 mask('initial-mask.png')
elif stage=='apply':
 proposed=np.load(out/'candidate-vertices.npy',allow_pickle=False);assert proposed.shape==vertices.shape and np.isfinite(proposed).all()
 inverse=obj.matrix_world.inverted()
 for v,value in zip(obj.data.vertices,proposed):v.co=inverse@Vector(value)
 obj.data.update();assert scene.camera.matrix_world==camera_before
 assert world=={o.name:[list(row) for row in o.matrix_world] for o in scene.objects if o!=obj}
 assert np.array_equal(faces,np.array([list(p.vertices) for p in obj.data.polygons]))
 for p in obj.data.polygons:p.material_index=0
 # Remove old projected slots. Appearance will be rebuilt for the repaired mesh.
 while len(obj.data.materials)>1:obj.data.materials.pop(index=len(obj.data.materials)-1)
 while obj.data.uv_layers:obj.data.uv_layers.remove(obj.data.uv_layers[-1])
 mask('candidate-mask.png');scene.render.film_transparent=False
 bpy.ops.wm.save_as_mainfile(filepath=str(out/'surface-candidate.blend'),compress=True)
 (out/'surface-scene-evidence.json').write_text(json.dumps({'cameraAndOtherObjectsUnchanged':True,'topologyUnchanged':True,'geometrySha256':geometry_digest()}))
elif stage=='views':
 scene.cycles.samples=12;scene.cycles.use_denoising=True;scene.render.film_transparent=False
 scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA'
 center=Vector(tuple((vertices.min(0)+vertices.max(0))/2));center.z=float(vertices.min(0)[2]+np.ptp(vertices[:,2])*.45)
 points=vertices[:,:2]-vertices[:,:2].mean(0);_,vectors=np.linalg.eigh(points.T@points);axis=vectors[:,-1]
 if axis[1]<0:axis=-axis
 forward=Vector((-float(axis[0]),-float(axis[1]),0));side=Vector((-forward.y,forward.x,0))
 observed=(scene.camera.location-center);observed.z=0
 if side.dot(observed)<0:side=-side
 distance=max(1.7,float(np.linalg.norm(np.ptp(vertices,axis=0)))*1.65)
 poses=[('reference',None),('front',forward+Vector((0,0,.22))),('left',side+Vector((0,0,.18))),('rear',-forward+Vector((0,0,.22))),('right',-side+Vector((0,0,.18))),('top',Vector((0,0,1))),('rear-three-quarter',(-forward+side+Vector((0,0,.6))).normalized())]
 original=scene.camera;meta=[]
 for name,direction in poses:
  data=original.data.copy();camera=bpy.data.objects.new('Inspection_'+name,data);scene.collection.objects.link(camera)
  if direction is None:camera.matrix_world=original.matrix_world.copy()
  else:
   camera.location=center+direction.normalized()*distance;camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
  scene.camera=camera;scene.render.resolution_x=1200;scene.render.resolution_y=750
  bpy.context.view_layer.update();framing=verify_presentation(scene,camera,vertices,bpy.data.objects.get('StudioFloor'))
  if not job.get('geometryOnly'):
   scene.render.filepath=str(out/(name+'.png'));bpy.ops.render.render(write_still=True)
  meta.append({'name':name,'position':list(camera.location),'matrixWorld':[list(row) for row in camera.matrix_world],'image':str(out/(name+'.png')),'framing':framing})
  if name!='reference':
   # Same geometry, neutral material makes defects visible without photo texture.
   material=bpy.data.materials.get('Geometry inspection clay')
   if material is None:
    material=bpy.data.materials.new('Geometry inspection clay');material.diffuse_color=(.26,.3,.34,1);material.use_nodes=True;p=material.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(.26,.3,.34,1);p.inputs['Roughness'].default_value=.55
   transform=scene.view_settings.view_transform;exposure=scene.view_settings.exposure;scene.view_settings.view_transform='AgX';scene.view_settings.exposure=-2
   scene.view_layers[0].material_override=material;scene.render.resolution_x=800;scene.render.resolution_y=500;scene.render.filepath=str(out/(name+'-geometry.png'));bpy.ops.render.render(write_still=True);scene.view_layers[0].material_override=None
   scene.view_settings.view_transform=transform;scene.view_settings.exposure=exposure
  scene.camera=original;bpy.data.objects.remove(camera,do_unlink=True)
 (out/'view-cameras.json').write_text(json.dumps({'geometrySha256':geometry_digest(),'poses':meta,'geometryFixedAcrossViews':True,'scope':'Views of one inferred mesh, not additional photographic evidence. Left/right labels refer to displayed inspection side.'},indent=2))
print('NOETRA_SURFACE_STAGE_COMPLETE',stage)
