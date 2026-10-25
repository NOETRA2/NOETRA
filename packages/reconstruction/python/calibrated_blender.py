"""Fresh scene, computed mesh only, exact supplied cameras, neutral geometry renders."""
import bpy,sys,json,math
from pathlib import Path
from mathutils import Matrix,Vector
from bpy_extras.object_utils import world_to_camera_view

job=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text());out=Path(job['output'])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.file_preview_type='NONE';bpy.context.preferences.filepaths.save_version=0
scene=bpy.context.scene
bpy.ops.wm.ply_import(filepath=str(out/'mesh.ply'))
objects=list(bpy.context.selected_objects);assert objects and all(o.type=='MESH' for o in objects)
material=bpy.data.materials.new('Neutral reconstructed geometry');material.use_nodes=True
p=material.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(.24,.27,.31,1);p.inputs['Roughness'].default_value=.42
for o in objects:
    o.data.materials.clear();o.data.materials.append(material)
    for polygon in o.data.polygons:polygon.use_smooth=True
scene.world=bpy.data.worlds.new('Inspection studio');scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.18,.18,.18,1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.6
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=8;scene.cycles.use_denoising=True
scene.render.threads_mode='FIXED';scene.render.threads=3;scene.render.film_transparent=True
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX';points=[o.matrix_world@v.co for o in objects for v in o.data.vertices]
lo=Vector(tuple(min(p[i] for p in points) for i in range(3)));hi=Vector(tuple(max(p[i] for p in points) for i in range(3)));center=(lo+hi)/2;extent=(hi-lo).length
for position,power,size in [((0,-1,2),650,1.5),((1,1,1.5),500,1.2),((-1,0,1),450,1)]:
    data=bpy.data.lights.new('Inspection light','AREA');data.energy=power;data.shape='DISK';data.size=extent*size
    light=bpy.data.objects.new(data.name,data);scene.collection.objects.link(light);light.location=center+Vector(position)*extent
    light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler()
evidence=[]
for i,view in enumerate(job['views']):
    image=bpy.data.images.load(view['mask']['path']);w,h=image.size;bpy.data.images.remove(image)
    scene.render.resolution_x=w;scene.render.resolution_y=h
    k=view['camera']['K'];fx,fy=k[0][0],k[1][1];cx,cy=k[0][2],k[1][2]
    assert abs(k[0][1])<1e-8
    data=bpy.data.cameras.new(view['id']);data.type='PERSP';data.sensor_fit='HORIZONTAL';data.sensor_width=36;data.lens=fx*36/w
    ratio=fx/fy;scene.render.pixel_aspect_x=1;scene.render.pixel_aspect_y=ratio
    data.shift_x=(w/2-cx)/w;data.shift_y=(cy-h/2)/w*ratio
    camera=bpy.data.objects.new(view['id'],data);scene.collection.objects.link(camera)
    r=Matrix(view['camera']['R']);t=Vector(view['camera']['t']);cv_to_blender=Matrix.Diagonal((1,-1,-1))
    rotation=r.transposed()@cv_to_blender
    camera.matrix_world=rotation.to_4x4();camera.location=-(r.transposed()@t);scene.camera=camera;bpy.context.view_layer.update()
    maximum=0;clipped=0
    for point in points[::max(1,len(points)//2000)]:
        q=r@point+t
        if q.z<=0:clipped+=1;continue
        expected=Vector((fx*q.x/q.z+cx,fy*q.y/q.z+cy));actual=world_to_camera_view(scene,camera,point)
        maximum=max(maximum,(expected-Vector((actual.x*w,(1-actual.y)*h))).length)
    assert maximum<.05 and clipped==0,(view['id'],maximum,clipped)
    scene.render.filepath=str(out/(view['id']+'-render.png'));bpy.ops.render.render(write_still=True)
    evidence.append({'view':view['id'],'maximumProjectionErrorPx':maximum,'allSampledVerticesInFront':clipped==0})
    if i==0:
        bpy.ops.wm.save_as_mainfile(filepath=str(out/'model.blend'),compress=True)
        bpy.ops.object.select_all(action='DESELECT')
        for o in objects:o.select_set(True)
        bpy.context.view_layer.objects.active=objects[0]
        bpy.ops.export_scene.gltf(filepath=str(out/'model.glb'),export_format='GLB',use_selection=True,export_apply=True,export_animations=False)
(out/'render-evidence.json').write_text(json.dumps({'freshScene':True,'sourceSceneOpened':False,'suppliedCameras':evidence},indent=2))
print('NOETRA_CALIBRATED_HULL_RENDERED')
