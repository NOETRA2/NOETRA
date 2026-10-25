"""Fixed data-only part editor/renderer for trusted project-local Blender scenes.
Runs only in a fresh --disable-autoexec background process. No supplied code.
Not an OS sandbox and not an automatic semantic reconstruction model.
"""
import bpy,sys,json,hashlib,math,struct,uuid
from pathlib import Path
from mathutils import Vector

def need(ok,code):
    if not ok:raise ValueError('RECONSTRUCTION_'+code)

def palette(index):return [64+64*(index%3),64+64*((index//3)%3),64+64*((index//9)%3)]

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def material_state(m):
    if m is None:return None
    state={'name':m.name,'color':list(getattr(m,'diffuse_color',getattr(m,'color',[]))),'nodes':[],'links':[]}
    if m.use_nodes:
        for n in sorted(m.node_tree.nodes,key=lambda n:n.name):
            inputs=[]
            for s in n.inputs:
                if not hasattr(s,'default_value'):continue
                v=s.default_value
                if isinstance(v,(str,bool,int,float)):inputs.append([s.identifier,v])
                elif hasattr(v,'__len__'):
                    try:inputs.append([s.identifier,list(v)])
                    except TypeError:pass
            state['nodes'].append([n.name,n.bl_idname,inputs])
        state['links']=sorted([l.from_node.name,l.from_socket.identifier,l.to_node.name,l.to_socket.identifier] for l in m.node_tree.links)
    return state

def fingerprint(scene):
    dep=bpy.context.evaluated_depsgraph_get();result={}
    for o in sorted(scene.objects,key=lambda o:o.name):
        h=hashlib.sha256();meta={'type':o.type,'matrix':[list(r) for r in o.matrix_world],
            'hidden':o.hide_render,'parent':o.parent.name if o.parent else None,
            'materials':[material_state(s.material) for s in o.material_slots]}
        if o.type in {'MESH','CURVE'}:
            e=o.evaluated_get(dep);m=e.to_mesh();m.calc_loop_triangles()
            for v in m.vertices:
                need(all(math.isfinite(x) for x in v.co),'NONFINITE')
                h.update(struct.pack('<3d',*v.co))
            for t in m.loop_triangles:h.update(struct.pack('<4I',*t.vertices,t.material_index))
            meta['vertices']=len(m.vertices);meta['triangles']=len(m.loop_triangles);e.to_mesh_clear()
        elif o.type=='CAMERA':
            meta['camera']={k:getattr(o.data,k) for k in ['type','lens','sensor_width','sensor_height','sensor_fit','shift_x','shift_y','ortho_scale','clip_start','clip_end']}
        elif o.type=='LIGHT':
            meta['light']={'type':o.data.type,'energy':o.data.energy,'color':list(o.data.color)}
        h.update(json.dumps(meta,sort_keys=True,allow_nan=False).encode());result[o.name]=h.hexdigest()
    return {'objects':result,'world':digest(material_state(scene.world)) if scene.world else None,
        'frame':scene.frame_current,'active_camera':scene.camera.name if scene.camera else None}

def validate_scene(scene):
    need(not bpy.data.libraries,'LINKED_LIBRARIES_UNSUPPORTED')
    need(not scene.sequence_editor or len(scene.sequence_editor.strips)==0,'SEQUENCER_UNSUPPORTED')
    for img in bpy.data.images:
        need(img.source in {'GENERATED','VIEWER'} or bool(img.packed_file),'EXTERNAL_IMAGE_UNSUPPORTED')
    need(not bpy.data.movieclips and not bpy.data.volumes and not bpy.data.cache_files,'EXTERNAL_CACHE_UNSUPPORTED')
    for blocks in [bpy.data.objects,bpy.data.meshes,bpy.data.curves,bpy.data.materials,bpy.data.worlds,bpy.data.scenes,bpy.data.shape_keys]:
        for d in blocks:
            need(not getattr(d,'animation_data',None),'ANIMATION_UNSUPPORTED')
            tree=getattr(d,'node_tree',None)
            need(not tree or not tree.animation_data,'ANIMATION_UNSUPPORTED')
    for o in scene.objects:
        need(not o.constraints,'CONSTRAINTS_UNSUPPORTED')
        need(not any(m.type in {'NODES','MESH_SEQUENCE_CACHE','FLUID','CLOTH','PARTICLE_SYSTEM'} for m in o.modifiers),'DYNAMIC_MODIFIER_UNSUPPORTED')

def apply_parameters(spec,values,objects):
    parts={p['id']:p for p in spec['parts']}
    for p in spec['parameters']:
        value=values[p['id']];need(math.isfinite(value) and p['minimum']<=value<=p['maximum'],'PARAMETER_BOUNDS')
        names=parts[p['partId']]['objects'];axis='XYZ'.index(p['axis'])
        if p['kind']=='translate':
            for name in names:
                o=objects[name];move=Vector((0,0,0));move[axis]=value
                # World-space displacement, including parented objects.
                m=o.matrix_world.copy();m.translation+=move;o.matrix_world=m
        else:
            name=p['object'];need(name in names,'PARAMETER_PART_OWNERSHIP');o=objects[name]
            # Never mutate another object's shared data block.
            if o.data.users>1:o.data=o.data.copy()
            ids=p['indices'];need(len(ids)==len(set(ids)),'DUPLICATE_CONTROL')
            if p['kind']=='mesh_offset':
                need(o.type=='MESH' and max(ids)<len(o.data.vertices),'MESH_CONTROL')
                need(not o.data.shape_keys,'SHAPE_KEYS_UNSUPPORTED')
                for index in ids:o.data.vertices[index].co[axis]+=value
                o.data.update()
            else:
                need(o.type=='CURVE' and p['spline']<len(o.data.splines),'CURVE_CONTROL')
                spline=o.data.splines[p['spline']];points=spline.bezier_points if spline.type=='BEZIER' else spline.points
                need(max(ids)<len(points) and spline.type in {'BEZIER','POLY'},'CURVE_CONTROL')
                for index in ids:
                    point=points[index];point.co[axis]+=value
                    if spline.type=='BEZIER':point.handle_left[axis]+=value;point.handle_right[axis]+=value
    bpy.context.view_layer.update()

def linear(x):
    x/=255;return x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4

def emission(name,rgb):
    m=bpy.data.materials.new(name);m.use_nodes=True;t=m.node_tree;t.nodes.clear()
    out=t.nodes.new('ShaderNodeOutputMaterial');s=t.nodes.new('ShaderNodeEmission')
    s.inputs['Color'].default_value=tuple(linear(x) for x in rgb)+(1,);s.inputs['Strength'].default_value=1
    t.links.new(s.outputs[0],out.inputs['Surface']);return m

def main(job):
    spec=job['spec'];out=Path(job['output']);need(out.is_dir(),'OUTPUT_MISSING')
    bpy.ops.wm.open_mainfile(filepath=job['source'],load_ui=False)
    bpy.context.preferences.filepaths.file_preview_type='NONE';bpy.context.preferences.filepaths.save_version=0
    scene=bpy.context.scene;validate_scene(scene)
    collection=bpy.data.collections.get(spec['collection']);need(collection is not None,'COLLECTION_MISSING')
    objects={o.name:o for o in collection.all_objects}
    need(0<len(objects)<=5000,'OBJECT_LIMIT')
    for part in spec['parts']:
        for name in part['objects']:need(name in objects and objects[name].type in {'MESH','CURVE'},'PART_OBJECT_MISSING')
    apply_parameters(spec,job['values'],objects)
    state=fingerprint(scene)
    (out/'fingerprints.json').write_text(json.dumps(state,indent=2),encoding='utf8')
    for o in objects.values():o['noetra_component_id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'noetra-part/'+o.name))
    # Save before changing any materials, visibility, camera, or render settings.
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'),compress=True)
    if job.get('export'):
        bpy.ops.object.select_all(action='DESELECT')
        for o in objects.values():o.select_set(True)
        bpy.context.view_layer.objects.active=next(iter(objects.values()))
        bpy.ops.export_scene.gltf(filepath=str(out/'scene.glb'),export_format='GLB',use_selection=True,export_apply=True,export_animations=False,export_extras=True)
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.render.threads_mode='FIXED';scene.render.threads=8
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.resolution_percentage=100
    if job.get('beauty'):
        scene.cycles.samples=8;scene.cycles.use_denoising=True
        for view in spec['views']:
            camera=scene.objects.get(view['camera']);need(camera is not None and camera.type=='CAMERA','CAMERA_MISSING')
            scene.camera=camera;scene.render.resolution_x=view['width'];scene.render.resolution_y=view['height']
            scene.render.filepath=str(out/(view['id']+'-beauty.png'));bpy.ops.render.render(write_still=True)
    # A flat geometric part-ID pass avoids scoring painted reflections as ridges.
    # Glass is opaque here: this measures visible geometric coverage, not optics.
    for o in scene.objects:
        if o.type not in {'CAMERA','LIGHT'} and o.name not in objects:o.hide_render=True
    ids={name:i for i,p in enumerate(spec['parts']) for name in p['objects']}
    materials=[emission('NOETRA_ID_'+str(i),palette(i)) for i in range(len(spec['parts']))]
    other=emission('NOETRA_UNANNOTATED_GEOMETRY',[8,8,8])
    for o in objects.values():
        if o.type not in {'MESH','CURVE'}:continue
        # Object-linked overrides also preserve shared geometry between instances.
        if not o.material_slots:o.data.materials.append(other)
        for slot in o.material_slots:slot.link='OBJECT';slot.material=materials[ids[o.name]] if o.name in ids else other
    if scene.world:
        scene.world.use_nodes=True
        for n in scene.world.node_tree.nodes:
            if n.type=='BACKGROUND':n.inputs['Strength'].default_value=0
    scene.render.film_transparent=True;scene.cycles.samples=1;scene.cycles.use_denoising=False
    scene.view_settings.view_transform='Standard';scene.view_settings.exposure=0;scene.view_settings.gamma=1
    try:scene.view_settings.look='None'
    except TypeError:pass
    scene.render.dither_intensity=0
    for view in spec['views']:
        camera=scene.objects.get(view['camera']);need(camera is not None and camera.type=='CAMERA','CAMERA_MISSING')
        scene.camera=camera;scene.render.resolution_x=view['width'];scene.render.resolution_y=view['height']
        scene.render.filepath=str(out/(view['id']+'-ids.png'));bpy.ops.render.render(write_still=True)
    print('NOETRA_PART_RENDER_COMPLETE',flush=True)

if __name__=='__main__':
    try:main(json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf8')))
    except Exception as error:
        print(str(error) if isinstance(error,ValueError) else 'RECONSTRUCTION_PART_ADAPTER_FAILED',flush=True);raise
