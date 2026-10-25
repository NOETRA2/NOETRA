"""Actual fixed-export regression: clipped camera and intersecting ground fixture."""
import bpy,sys,json,runpy
from pathlib import Path
from mathutils import Vector
base=Path(sys.argv[sys.argv.index('--')+1]).resolve();base.mkdir(exist_ok=True,parents=True)
adapter=Path(__file__).resolve().parents[2]/'packages/reconstruction/python/photo_blender.py'
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;collection=bpy.data.collections.new('RECONSTRUCTED_MODEL');scene.collection.children.link(collection)
bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=16,location=(0,0,1));o=bpy.context.object
for c in list(o.users_collection):c.objects.unlink(o)
collection.objects.link(o)
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,.35));floor=bpy.context.object;floor.name='StudioFloor'
d=bpy.data.cameras.new('InitialCamera');camera=bpy.data.objects.new('InitialCamera',d);scene.collection.objects.link(camera);camera.location=(0,-1.5,1);camera.rotation_euler=(Vector((0,0,1))-camera.location).to_track_quat('-Z','Y').to_euler();scene.camera=camera;bpy.context.view_layer.update();expected=[list(r) for r in camera.matrix_world]
scene.world=bpy.data.worlds.new('Test world');scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.6
scene.render.engine='CYCLES';scene.render.resolution_x=512;scene.render.resolution_y=512;bpy.context.preferences.filepaths.file_preview_type='NONE';bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(base/'photo-base.blend'),compress=True)
job=base/'job.json';job.write_text(json.dumps({'stage':'export','output':str(base),'chosen':'Initial'}));sys.argv=[str(adapter),'--',str(job)];runpy.run_path(str(adapter),run_name='__main__')
scene=bpy.context.scene
verification=json.loads((base/'presentation-verification.json').read_text());assert verification['cameraRetreatRelativeUnits']>0 and verification['floorAdjusted'] and verification['allVerticesInFrame'] and verification['groundClearance']>0
assert [list(r) for r in bpy.data.objects['InitialCamera'].matrix_world]==expected and scene.camera.name=='Presentation camera'
(base/'regression-result.json').write_text(json.dumps({'ok':True,'observationCameraExactlyUnchanged':True,'presentationCameraSeparate':True,'cameraClippingCorrected':True,'intersectingGroundCorrected':True,'verification':verification},indent=2));print('FRAMING_EXPORT_REGRESSION_PASSED')
