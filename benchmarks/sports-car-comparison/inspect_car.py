"""Read-only geometric observations from a generated comparison .blend."""
import bpy
import json
import sys
from pathlib import Path
from mathutils.bvhtree import BVHTree

args=sys.argv[sys.argv.index('--')+1:]
output=Path(args[0]).resolve()
scene=bpy.context.scene
bpy.context.view_layer.update()
depsgraph=bpy.context.evaluated_depsgraph_get()
objects=list(bpy.data.collections['SPORTS_CAR'].objects)
records=[]
for obj in objects:
    if obj.type not in {'MESH','CURVE'}:
        continue
    evaluated=obj.evaluated_get(depsgraph)
    data=evaluated.to_mesh()
    positions=[evaluated.matrix_world@v.co for v in data.vertices]
    low=[min(p[i] for p in positions) for i in range(3)]
    high=[max(p[i] for p in positions) for i in range(3)]
    records.append({'name':obj.name,'min':low,'max':high})
    evaluated.to_mesh_clear()

targets={}
for name in ['Continuous sculpted body shell','Wraparound cockpit glazing']:
    obj=bpy.data.objects[name]
    evaluated=obj.evaluated_get(depsgraph)
    data=evaluated.to_mesh()
    data.calc_loop_triangles()
    vertices=[evaluated.matrix_world@v.co for v in data.vertices]
    targets[name]=BVHTree.FromPolygons(vertices,[list(poly.vertices) for poly in data.polygons])
    evaluated.to_mesh_clear()
trim_gaps=[]
for obj in objects:
    if obj.type!='CURVE':
        continue
    target='Wraparound cockpit glazing' if obj.name.startswith(('A pillar','Roof side rail','Cockpit brightwork')) else 'Continuous sculpted body shell' if obj.name.startswith(('Cyan headlight','Front lamp recess')) else None
    if not target:
        continue
    evaluated=obj.evaluated_get(depsgraph)
    data=evaluated.to_mesh()
    distances=[]
    for vertex in data.vertices:
        hit=targets[target].find_nearest(evaluated.matrix_world@vertex.co)
        if hit[0] is not None:
            distances.append(hit[3])
    if distances:
        trim_gaps.append({'name':obj.name,'target':target,'maximum_surface_distance_m':max(distances),'mean_surface_distance_m':sum(distances)/len(distances)})
    evaluated.to_mesh_clear()
result={'observed_from':bpy.data.filepath,'method':'Evaluated mesh bounding boxes and nearest target-surface distances in Blender; read-only analysis.',
    'component_bounds':records,'trim_distances':trim_gaps,
    'limitations':['Unsigned nearest-surface distance is not a full collision/manufacturability test.','Distance includes the visible trim tube radius and attachment offset.']}
output.write_text(json.dumps(result,indent=2),encoding='utf-8')
print('READ_ONLY_CAR_AUDIT_COMPLETE '+str(output))
