"""Color actual vertices only after normal/occlusion checks; mesh stays identical."""
from pathlib import Path
import hashlib,struct,json,subprocess,os
import bpy,numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from reference_colors import basis,coordinates,sample,warp_coordinates,region_weights

def bake_surface_texture(objects,out,resolution):
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1
    scene.render.threads_mode='FIXED';scene.render.threads=3
    scene.render.bake.use_selected_to_active=False;scene.render.bake.margin=4
    reports=[]
    for index,o in enumerate(objects):
        bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
        if o.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=1.3962634,island_margin=.0008,area_weight=0,correct_aspect=True,scale_to_bounds=False)
        bpy.ops.object.mode_set(mode='OBJECT')
        image=bpy.data.images.new('Surface color atlas '+str(index),width=resolution,height=resolution,alpha=False)
        image.colorspace_settings.name='sRGB';image.generated_color=(.65,.4,.18,1)
        for material in o.data.materials:
            nodes=material.node_tree.nodes;links=material.node_tree.links;output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL')
            color=next(n for n in nodes if n.type=='VERTEX_COLOR');emission=nodes.new('ShaderNodeEmission');links.new(color.outputs['Color'],emission.inputs['Color']);links.new(emission.outputs[0],output.inputs['Surface'])
            texture=nodes.new('ShaderNodeTexImage');texture.image=image;nodes.active=texture
        bpy.ops.object.bake(type='EMIT')
        path=Path(out)/('surface-color-'+str(index)+'.png');image.filepath_raw=str(path);image.file_format='PNG';image.save();image.pack()
        for material in o.data.materials:
            nodes=material.node_tree.nodes;links=material.node_tree.links;texture=next(n for n in nodes if n.type=='TEX_IMAGE')
            p=nodes.get('Principled BSDF');output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL')
            links.new(texture.outputs['Color'],p.inputs['Base Color']);links.new(p.outputs['BSDF'],output.inputs['Surface'])
            p.inputs['Metallic'].default_value=0;p.inputs['Roughness'].default_value=.86
        # glTF multiplies COLOR_0 with the base-colour texture. The atlas already
        # contains these samples, so exporting both would apply colour twice.
        for attribute in list(o.data.color_attributes):o.data.color_attributes.remove(attribute)
        reports.append({'object':o.name,'image':str(path),'resolution':resolution,'packedInBlend':True,'UVLayer':o.data.uv_layers.active.name,'lightingBaked':False})
    return reports

def geometry_hash(objects):
    h=hashlib.sha256()
    for o in objects:
        h.update(o.name.encode())
        h.update(np.asarray([tuple(o.matrix_world@v.co) for v in o.data.vertices],dtype='<f8').tobytes())
        for p in o.data.polygons:h.update(struct.pack('<I',len(p.vertices)));h.update(np.asarray(p.vertices,dtype='<u4').tobytes())
    return h.hexdigest()

def apply_reference_colors(objects,out,profile):
    before=geometry_hash(objects);base=np.asarray(profile['fallbackSRGB'],float)
    base=np.where(base<=.04045,base/12.92,((base+.055)/1.055)**2.4)
    views=[]
    for view in profile['views']:
        with np.load(view['array'],allow_pickle=False) as a:views.append((view,a['rgb'].copy(),a['mask'].copy()))
    points=np.concatenate([np.asarray([tuple(o.matrix_world@v.co) for v in o.data.vertices]) for o in objects]);extent=float(np.linalg.norm(np.ptp(points,axis=0)))
    all_colors=[];all_weights=[];alignment=[]
    for view,rgb,mask in views:
        uv,registration=coordinates(points,view['direction'],view['up'],mask)
        uv,warp=warp_coordinates(uv,view.get('controlPoints',[]),(rgb.shape[1],rgb.shape[0]));colors,supported=sample(rgb,mask,uv)
        all_colors.append(colors);all_weights.append(supported.astype(float));alignment.append({'id':view['id'],**registration,'landmarkWarp':warp})
    # A combined world-space tree also catches occluders belonging to other objects.
    polygons=[];vertex_offset=0
    for o in objects:
        polygons.extend([[vertex_offset+i for i in p.vertices] for p in o.data.polygons]);vertex_offset+=len(o.data.vertices)
    tree=BVHTree.FromPolygons([Vector(p) for p in points],polygons)
    offset=0;covered=0;total=0
    for o in objects:
        vertices=[o.matrix_world@v.co for v in o.data.vertices];normal_matrix=o.matrix_world.to_3x3().inverted().transposed()
        normals=np.asarray([tuple((normal_matrix@v.normal).normalized()) for v in o.data.vertices])
        n=len(vertices);sums=np.zeros((n,3));weights=np.zeros(n)
        for j,(view,rgb,mask) in enumerate(views):
            toward,_,_=basis(view['direction'],view['up']);direction=Vector(toward)
            facing=np.maximum(0,normals@toward)
            # For one coherent source, visibility decides support. Do not drop
            # grazing visible faces (nose/eyes) merely to blend competing views.
            w=(np.ones(n) if profile.get('mappingMode')=='primary-view' else facing**4)*view['weight']*all_weights[j][offset:offset+n]
            for i in np.flatnonzero(w>.0005):
                origin=vertices[i]+direction*extent*3;hit=tree.ray_cast(origin,-direction,extent*3+.01)
                if hit[0] is None or abs(hit[3]-extent*3)>max(extent*.0008,1e-5):w[i]=0
            support=region_weights(np.asarray(vertices),view.get('region'));w*=support
            if view.get('region'):
                # An explicitly bounded patch corrects only its own surface.
                # Preserve the primary mapping outside the feathered region.
                replace=np.minimum(1,w);sums*=1-replace[:,None];weights*=1-replace
            sums+=all_colors[j][offset:offset+n]*w[:,None];weights+=w
        rgba=np.ones((n,4),np.float32);rgba[:,:3]=base;good=weights>1e-6;rgba[good,:3]=sums[good]/weights[good,None]
        diffusion=None
        if profile.get('mappingMode')=='primary-view':
            o.data.calc_loop_triangles();faces=np.asarray([list(t.vertices) for t in o.data.loop_triangles],dtype=int)
            inputs=Path(out)/('surface-fill-'+str(offset)+'.npz');outputs=Path(out)/('surface-filled-'+str(offset)+'.npz');evidence=Path(out)/('surface-fill-'+str(offset)+'.json')
            symmetry=profile.get('symmetryPlane');plane=np.array([*symmetry['normal'],symmetry['offset'],symmetry['maxDistanceFraction']]) if symmetry else np.empty(0)
            np.savez_compressed(inputs,vertices=np.asarray(vertices),normals=normals,faces=faces,colors=rgba[:,:3],known=good,fallback=base,symmetry=plane)
            process=subprocess.run([profile['diffusionPython'],'-I','-B',str(Path(__file__).with_name('color_diffusion_worker.py')),str(inputs),str(outputs),str(evidence)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=100,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            (Path(out)/'surface-fill-log.txt').write_bytes(process.stdout[-65536:]);assert process.returncode==0,'Surface color fill failed'
            with np.load(outputs,allow_pickle=False) as data:rgba[:,:3]=data['colors']
            diffusion=json.loads(evidence.read_text())
        attr=o.data.color_attributes.new(name='Reference color',type='FLOAT_COLOR',domain='POINT');attr.data.foreach_set('color',rgba.ravel())
        o.data.color_attributes.active_color=attr
        m=bpy.data.materials.new('Reference-guided coat colors');m.use_nodes=True;nodes=m.node_tree.nodes
        p=nodes.get('Principled BSDF');p.inputs['Metallic'].default_value=0;p.inputs['Roughness'].default_value=.86
        color=nodes.new('ShaderNodeVertexColor');color.layer_name=attr.name;m.node_tree.links.new(color.outputs['Color'],p.inputs['Base Color'])
        o.data.materials.clear();o.data.materials.append(m);covered+=int(good.sum());total+=n;offset+=n
    atlases=bake_surface_texture(objects,out,profile['textureResolution']) if profile.get('textureResolution') else []
    after=geometry_hash(objects);assert before==after
    evidence={'geometryExactlyUnchanged':True,'geometrySha256Before':before,'geometrySha256After':after,'coloredVertices':covered,'totalVertices':total,
        'coverage':covered/max(total,1),'unobservedFallback':'Explicit supplied fallback color, not recovered hidden appearance.',
        'alignments':alignment,'mappingMode':profile.get('mappingMode','multi-view'),'UVTextures':atlases,'surfaceFill':diffusion,'boundedColorPatches':[v[0]['region'] for v in views if v[0].get('region')],
        'scope':'Visible primary reference samples with authored alignment, mesh-adjacency fill and optional UV albedo bake; no recovered hidden texture or intrinsic PBR guarantee.'}
    (Path(out)/'color-verification.json').write_text(json.dumps(evidence,indent=2));return evidence
