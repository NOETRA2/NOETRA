"""Inspect an actual isolated-provider GLB in a fresh scene, without source projection."""
import bpy,sys,json
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).parent))
from blender_framing import points_for,verify_presentation
job=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text());out=Path(job['output'])
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
bpy.context.preferences.filepaths.file_preview_type='NONE';bpy.context.preferences.filepaths.save_version=0
bpy.ops.import_scene.gltf(filepath=str(out/'learned-mesh.glb'))
objects=[o for o in bpy.context.selected_objects if o.type=='MESH']
assert objects
collection=bpy.data.collections.new('LEARNED_SHAPE');scene.collection.children.link(collection)
material=bpy.data.materials.new('Neutral geometry inspection');material.use_nodes=True
p=material.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(.25,.29,.34,1);p.inputs['Roughness'].default_value=.38;p.inputs['Metallic'].default_value=.3
for o in objects:
    for c in list(o.users_collection):c.objects.unlink(o)
    collection.objects.link(o)
    o.data.materials.clear();o.data.materials.append(material)
    for polygon in o.data.polygons:polygon.use_smooth=True
if job.get('referenceColorProfile'):
    from reference_colors_blender import apply_reference_colors
    apply_reference_colors(objects,out,job['referenceColorProfile'])
if job.get('materialProfile'):
    if job.get('baseRefinement'):
        from base_surface import refine_base
        refine_base(objects,out,job['baseRefinement'])
    from material_paint_blender import apply_material_design
    apply_material_design(objects,out,job['materialProfile'])
scene.world=bpy.data.worlds.new('Inspection environment');scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.5
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.15,.15,.15,1)
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=12;scene.cycles.use_denoising=True
scene.render.threads_mode='FIXED';scene.render.threads=3;scene.render.resolution_x=960;scene.render.resolution_y=640;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.film_transparent=True
if job.get('materialProfile'):
    scene.view_settings.view_transform='AgX';scene.view_settings.look='None';scene.view_settings.exposure=-.5;scene.view_settings.gamma=1
points=points_for(collection);lo=Vector(points.min(0));hi=Vector(points.max(0));center=(lo+hi)/2;extent=(hi-lo).length
for position,power in [((1,-1,2),500),((-1,0,1),300),((0,1,2),600),((0,-1,-1.5),250)]:
    data=bpy.data.lights.new('Inspection area','AREA');data.energy=power;data.size=extent*1.2
    light=bpy.data.objects.new(data.name,data);scene.collection.objects.link(light);light.location=center+Vector(position)*extent
    light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler()
data=bpy.data.cameras.new('Inspection camera');data.lens=55;data.sensor_fit='HORIZONTAL'
camera=bpy.data.objects.new(data.name,data);scene.collection.objects.link(camera);scene.camera=camera
views=[]
# Proposed canonical front is -X after GLB import. These names describe this
# presentation assumption, not automatic semantic pose recognition.
for name,direction in [('three-quarter',(-1,1,.45)),('front',(-1,0,.1)),('left',(0,-1,.1)),('rear',(1,0,.1)),('right',(0,1,.1)),('top',(0,0,1)),('bottom',(0,0,-1)),('rear-three-quarter',(1,-1,.45))]:
    camera.location=center+Vector(direction).normalized()*extent*2
    camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler();bpy.context.view_layer.update()
    verification=verify_presentation(scene,camera,points,margin=.08);assert verification['allVerticesInFrame']
    scene.render.filepath=str(out/(name+'.png'));bpy.ops.render.render(write_still=True)
    views.append({'name':name,'render':str(out/(name+'.png')),'verification':verification,'cameraDirection':direction,'presentationFrontAssumption':[-1,0,0]})
    if name=='three-quarter':
        bpy.ops.wm.save_as_mainfile(filepath=str(out/'model.blend'),compress=True)
        bpy.ops.object.select_all(action='DESELECT')
        for o in objects:o.select_set(True)
        bpy.context.view_layer.objects.active=objects[0]
        bpy.ops.export_scene.gltf(filepath=str(out/'model.glb'),export_format='GLB',use_selection=True,export_apply=True,export_animations=False)
(out/'shape-export-verification.json').write_text(json.dumps(views,indent=2))
print('NOETRA_LEARNED_SHAPE_EXPORTED')
