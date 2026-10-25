"""Fixed, reviewable Blender adapter for a bounded spatial sheet representation.
Only data is accepted. No arbitrary Python, expressions or remote references.
Run in a NEW --background --factory-startup --disable-autoexec process.
"""
import bpy,json,sys,math
from pathlib import Path
from mathutils import Matrix,Vector
args=sys.argv[sys.argv.index('--')+1:]
source=Path(args[0]).resolve();output=Path(args[1]).resolve()
assert source.parent==output and source.name=='spatial-render-job.json'
data=json.loads(source.read_text(encoding='utf-8'))
assert data['schemaVersion']==1 and len(data['parts'])<=200 and len(data['cameras'])==2
assert not any((output/name).exists() for name in ['before.blend','candidate.blend','before-left.png','candidate-left.png']),'Existing experiment must not be overwritten'
for stage,scales in [('before',data['initialScale']),('candidate',data['candidateScale'])]:
    assert len(scales)==2 and all(math.isfinite(x) and .5<=x<=1.5 for x in scales)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.file_preview_type='NONE'
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU'
    scene.cycles.samples=8;scene.render.threads_mode='FIXED';scene.render.threads=4
    scene.render.film_transparent=True;scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA'
    scene.view_layers[0].use_pass_z=True;scene.view_layers[0].use_pass_normal=True
    scene.view_settings.view_transform='Standard';scene.view_settings.exposure=0;scene.view_settings.gamma=1
    scene.unit_settings.system='NONE' if data['scaleStatus'].startswith('relative') else 'METRIC'
    root=bpy.data.objects.new('NOETRA_Grid_Root',None);scene.collection.objects.link(root)
    surface=data['surface'];ux,uy=[Vector(v) for v in surface['axes']];n=ux.cross(uy).normalized()
    root.location=Vector(surface['centre']);root.rotation_euler=Matrix((ux,uy,n)).transposed().to_euler()
    root['persistent_id']='grid';root['scale_x']=scales[0];root['scale_y']=scales[1];root['scale_status']=data['scaleStatus']
    root['uncertainty']='Open sheet. Thickness, back and exterior beyond observed grid are unknown.'
    for axis,name in [(0,'scale_x'),(1,'scale_y')]:
        driver=root.driver_add('scale',axis).driver;driver.type='SCRIPTED'
        variable=driver.variables.new();variable.name='parameter';variable.type='SINGLE_PROP'
        variable.targets[0].id=root;variable.targets[0].data_path='["'+name+'"]';driver.expression='parameter'
    objects=[root]
    def linear(x):
        x=x/255;return x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4
    for part in data['parts']:
        assert part['id'].startswith('tile-')
        vertices=[]
        for index in part['landmarkIds']:
            q=surface['offsets'][index];vertices.append((q[0]*surface['steps'][0],q[1]*surface['steps'][1],0))
        mesh=bpy.data.meshes.new(part['id']+'_mesh');mesh.from_pydata(vertices,[],[(0,1,2,3)]);mesh.update()
        obj=bpy.data.objects.new(part['id'],mesh);scene.collection.objects.link(obj);obj.parent=root
        obj['persistent_id']=part['id'];obj['source_regions_json']=json.dumps(part['sourceRegions']);obj['material_status']=part['materialStatus']
        material=bpy.data.materials.new(part['id']+'_observed_color');material.use_nodes=True
        tree=material.node_tree;tree.nodes.clear();shader=tree.nodes.new('ShaderNodeEmission');out=tree.nodes.new('ShaderNodeOutputMaterial')
        color=tuple(linear(float(v)) for v in part['observedRGB'])+(1,)
        shader.inputs['Color'].default_value=color;shader.inputs['Strength'].default_value=1
        tree.links.new(shader.outputs['Emission'],out.inputs['Surface']);material.diffuse_color=color;mesh.materials.append(material)
        objects.append(obj)
    for camera in data['cameras']:
        assert camera['id'] in ['left','right']
        K=camera['K'];w=camera['width'];h=camera['height'];assert 1<=w<=8192 and 1<=h<=8192
        d=bpy.data.cameras.new(camera['id']);obj=bpy.data.objects.new(camera['id'],d);scene.collection.objects.link(obj)
        R=Matrix(camera['R']);T=Vector(camera['T']);conversion=Matrix.Diagonal((1.,-1.,-1.))
        transform=(R.transposed()@conversion).to_4x4();transform.translation=-(R.transposed()@T);obj.matrix_world=transform
        d.sensor_fit='HORIZONTAL';d.sensor_width=36;d.lens=K[0][0]*36/w
        ratio=K[0][0]/K[1][1];scene.render.pixel_aspect_x=1;scene.render.pixel_aspect_y=ratio
        d.shift_x=(w/2-K[0][2])/w;d.shift_y=(K[1][2]-h/2)/w*ratio
        d.clip_start=.0001;d.clip_end=100000
        obj['coordinate_convention']='World-to-camera OpenCV converted to Blender camera axes; full-resolution undistorted image domain'
        scene.render.resolution_x=w;scene.render.resolution_y=h;scene.render.resolution_percentage=100;scene.camera=obj
        bpy.context.view_layer.update()
        scene.render.filepath=str(output/(stage+'-'+camera['id']+'.png'))
        bpy.ops.render.render(write_still=True)
        scene.render.image_settings.media_type='MULTI_LAYER_IMAGE';scene.render.image_settings.file_format='OPEN_EXR_MULTILAYER';scene.render.image_settings.color_depth='32'
        bpy.data.images['Render Result'].save_render(filepath=str(output/(stage+'-'+camera['id']+'-passes.exr')),scene=scene)
        scene.render.image_settings.media_type='IMAGE';scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_depth='8'
    # Save only after both cameras exist; keep the editable scene's default view
    # on the left calibration with its own pixel-aspect settings.
    default=data['cameras'][0];scene.camera=bpy.data.objects[default['id']]
    scene.render.pixel_aspect_x=1;scene.render.pixel_aspect_y=default['K'][0][0]/default['K'][1][1]
    scene.render.filepath=str(output/(stage+'-'+default['id']+'.png'))
    bpy.ops.wm.save_as_mainfile(filepath=str(output/(stage+'.blend')))
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:obj.select_set(True)
    bpy.context.view_layer.objects.active=root
    bpy.ops.export_scene.gltf(filepath=str(output/(stage+'.glb')),export_format='GLB',use_selection=True,export_apply=True,export_animations=False,export_extras=True)
print('NOETRA_CONSTRUCTION_RENDER_COMPLETE',flush=True)
