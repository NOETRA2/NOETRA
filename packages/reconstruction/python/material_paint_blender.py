"""Data-only surface paint layers, real xatlas UVs and portable PBR map baking."""
from pathlib import Path
import bpy,numpy as np,json,subprocess,os
from reference_colors import region_weights
from reference_colors_blender import geometry_hash
from surface_paint_math import paint_fields

def linear(rgb):
    a=np.asarray(rgb,float);return np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)

def attribute(mesh,name,values):
    attr=mesh.color_attributes.new(name=name,type='FLOAT_COLOR',domain='POINT')
    rgba=np.ones((len(values),4),np.float32);rgba[:,:3]=np.asarray(values).reshape(-1,3);attr.data.foreach_set('color',rgba.ravel())
    return attr

def bake_image(obj,image,channel,material,out):
    nodes=material.node_tree.nodes;links=material.node_tree.links;target=nodes.new('ShaderNodeTexImage');target.image=image;nodes.active=target
    output=nodes.get('Material Output');p=nodes.get('Principled BSDF')
    if channel!='normal':
        emit=nodes.get('Bake emission') or nodes.new('ShaderNodeEmission');emit.name='Bake emission'
        socket=material['bake_color_socket'] if channel=='base-color' else material['bake_roughness_socket']
        node,port=socket.split('|');links.new(nodes[node].outputs[port],emit.inputs['Color']);links.new(emit.outputs[0],output.inputs['Surface'])
    else:links.new(p.outputs['BSDF'],output.inputs['Surface'])
    bpy.ops.object.bake(type='NORMAL' if channel=='normal' else 'EMIT',normal_space='TANGENT',margin=6)
    path=Path(out)/(channel+'.png');image.filepath_raw=str(path);image.file_format='PNG';image.save();image.pack()
    return path

def apply_material_design(objects,out,profile):
    assert len(objects)==1,'Surface painting currently requires one triangular mesh; separate multi-object materials are not supported'
    before=geometry_hash(objects);design=profile['design'];scene=bpy.context.scene
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1;scene.render.threads_mode='FIXED';scene.render.threads=3
    scene.render.bake.use_selected_to_active=False;scene.render.bake.margin=6
    evidence=[]
    for index,o in enumerate(objects):
        assert all(len(p.vertices)==3 for p in o.data.polygons),'Triangle mesh required; geometry will not be triangulated automatically'
        points=np.asarray([tuple(o.matrix_world@v.co) for v in o.data.vertices]);faces=np.asarray([list(p.vertices) for p in o.data.polygons],np.int32)
        fitted={};region_fit=None
        if profile.get('measuredPreview'):
            from surface_region_fit import fit_fibre_region
            fitted,region_fit=fit_fibre_region(points,faces,design)
        colors,rough,flow,layers=paint_fields(points,design,fitted)
        attribute(o.data,'Paint albedo',colors);attribute(o.data,'Paint roughness',np.repeat(rough[:,None],3,axis=1));attribute(o.data,'Paint flow',np.repeat(flow[:,None],3,axis=1))
        inputs=Path(out)/('atlas-input-'+str(index)+'.npz');output=Path(out)/('atlas-output-'+str(index)+'.npz');qa=Path(out)/('atlas-'+str(index)+'.json')
        np.savez_compressed(inputs,vertices=points,faces=faces,resolution=design['resolution'],padding=6)
        from uv_cache import reuse_cache
        reused=reuse_cache(profile.get('verifiedAtlasCache'),points,faces,design['resolution'],output,qa)
        if reused:(Path(out)/'xatlas-log.txt').write_text('Verified existing atlas reused: exact geometry, resolution, padding and source hashes match.')
        else:
            process=subprocess.run([profile['pythonExecutable'],'-I','-B',str(Path(__file__).with_name('uv_atlas_worker.py')),str(inputs),str(output),str(qa)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=160,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            (Path(out)/'xatlas-log.txt').write_bytes(process.stdout[-65536:]);assert process.returncode==0,'xatlas failed; no replacement UV fallback'
        with np.load(output,allow_pickle=False) as data:uv=data['loop_uv']
        assert uv.shape==(len(faces),3,2)
        atlas_report=json.loads(qa.read_text());fill_faces=atlas_report.get('artistFill',{}).get('faceIndices',[])
        # This operation replaces the surface material and its UV set together.
        # Retaining an older active-render UV would bake/export different maps.
        for previous_uv in list(o.data.uv_layers):o.data.uv_layers.remove(previous_uv)
        layer=o.data.uv_layers.new(name='xatlas surface');layer.active_render=True
        o.data.uv_layers.active=layer;layer.data.foreach_set('uv',np.asarray(uv,dtype=np.float32).ravel())
        fallback_values=np.zeros((len(o.data.loops),4),np.float32);fallback_values[:,3]=1
        for face_id in fill_faces:
            for loop_id in o.data.polygons[face_id].loop_indices:fallback_values[loop_id,:3]=1
        fallback=o.data.color_attributes.new(name='Atlas fallback',type='FLOAT_COLOR',domain='CORNER');fallback.data.foreach_set('color',fallback_values.ravel())
        m=bpy.data.materials.new('Designed coat PBR');m.use_nodes=True;o.data.materials.clear();o.data.materials.append(m);nodes=m.node_tree.nodes;links=m.node_tree.links
        p=nodes.get('Principled BSDF');p.inputs['Metallic'].default_value=0
        coord=nodes.new('ShaderNodeTexCoord')
        noises=[]
        for name,scale in [('Coat fibers',(10,160,160)),('Mane fibers',(160,160,12))]:
            mapping=nodes.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY';mapping.inputs[1].default_value=scale;links.new(coord.outputs['Generated'],mapping.inputs[0])
            noise=nodes.new('ShaderNodeTexNoise');noise.name=name;noise.inputs['Scale'].default_value=1;noise.inputs['Detail'].default_value=2;links.new(mapping.outputs[0],noise.inputs['Vector']);noises.append(noise)
        flow_node=nodes.new('ShaderNodeVertexColor');flow_node.layer_name='Paint flow'
        fiber=nodes.new('ShaderNodeMixRGB');fiber.name='Directional fur';links.new(flow_node.outputs['Color'],fiber.inputs[0]);links.new(noises[0].outputs['Fac'],fiber.inputs[1]);links.new(noises[1].outputs['Fac'],fiber.inputs[2])
        range_node=nodes.new('ShaderNodeMapRange');range_node.name='Coat variation';range_node.inputs['From Min'].default_value=0;range_node.inputs['From Max'].default_value=1
        range_node.inputs['To Min'].default_value=.84;range_node.inputs['To Max'].default_value=1.10;links.new(fiber.outputs[0],range_node.inputs['Value'])
        albedo=nodes.new('ShaderNodeVertexColor');albedo.layer_name='Paint albedo'
        multiply=nodes.new('ShaderNodeMixRGB');multiply.name='Albedo design';multiply.blend_type='MULTIPLY';multiply.inputs[0].default_value=1;links.new(albedo.outputs['Color'],multiply.inputs[1]);links.new(range_node.outputs[0],multiply.inputs[2])
        fallback_node=nodes.new('ShaderNodeVertexColor');fallback_node.layer_name='Atlas fallback'
        final_color=nodes.new('ShaderNodeMixRGB');final_color.name='Albedo with declared tiny-face prior';links.new(fallback_node.outputs['Color'],final_color.inputs[0]);links.new(multiply.outputs[0],final_color.inputs[1]);final_color.inputs[2].default_value=(*linear(design['baseSRGB']),1);links.new(final_color.outputs[0],p.inputs['Base Color'])
        rough_node=nodes.new('ShaderNodeVertexColor');rough_node.name='Roughness design';rough_node.layer_name='Paint roughness';links.new(rough_node.outputs['Color'],p.inputs['Roughness'])
        bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.35;bump.inputs['Distance'].default_value=float(np.linalg.norm(np.ptp(points,axis=0)))*.001;links.new(fiber.outputs[0],bump.inputs['Height']);links.new(bump.outputs[0],p.inputs['Normal'])
        m['bake_color_socket']='Albedo with declared tiny-face prior|Color';m['bake_roughness_socket']='Roughness design|Color'
        bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
        maps={};textures={}
        for channel in ['base-color','roughness','normal']:
            image=bpy.data.images.new('Lion '+channel,width=design['resolution'],height=design['resolution'],alpha=False)
            image.colorspace_settings.name='sRGB' if channel=='base-color' else 'Non-Color'
            maps[channel]=str(bake_image(o,image,channel,m,out));textures[channel]=image
        # Final material reads the baked maps only. No doubled procedural bump,
        # baked illumination, or duplicate vertex-colour multiplication.
        links.new(p.outputs['BSDF'],nodes.get('Material Output').inputs['Surface'])
        final_nodes={}
        for channel,image in textures.items():
            node=nodes.new('ShaderNodeTexImage');node.name='Baked '+channel;node.image=image;final_nodes[channel]=node
        links.new(final_nodes['base-color'].outputs['Color'],p.inputs['Base Color']);links.new(final_nodes['roughness'].outputs['Color'],p.inputs['Roughness'])
        normal=nodes.new('ShaderNodeNormalMap');links.new(final_nodes['normal'].outputs['Color'],normal.inputs['Color']);links.new(normal.outputs[0],p.inputs['Normal'])
        for a in list(o.data.color_attributes):o.data.color_attributes.remove(a)
        evidence.append({'object':o.name,'layers':layers,'surfaceRegionFit':region_fit,'atlas':atlas_report,'maps':maps,'colorSpaces':{'base-color':'sRGB','roughness':'Non-Color','normal':'Non-Color'},'roughnessRange':[float(rough.min()),float(rough.max())],'tinyIgnoredFaceAppearance':'Declared base-coat prior baked on reserved UV triangles; no geometry dropped',
            'appearanceStatus':'Artist-authored part masks and palette; procedural directional fur detail. Not automatic intrinsic-material recovery or a verified photographic match.'})
    after=geometry_hash(objects);assert before==after
    result={'geometryExactlyUnchanged':True,'geometrySha256Before':before,'geometrySha256After':after,'uvBackend':'xatlas','objects':evidence,'lightingBakedIntoAlbedo':False,'materialModel':'Separate base-color, roughness and tangent normal maps; metallic=0','colorManagement':'Blender OCIO scene-linear processing; sRGB base color and Non-Color data maps'}
    (Path(out)/'material-verification.json').write_text(json.dumps(result,indent=2));return result
