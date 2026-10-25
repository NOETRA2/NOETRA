"""Independent GLB round-trip check in a fresh background process."""
import bpy
import json
import sys
from pathlib import Path

root=Path(sys.argv[sys.argv.index('--')+1]).resolve()
results=[]
for arm in ['baseline','with-noetra']:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    path=root/arm/'sports-car.glb'
    result=bpy.ops.import_scene.gltf(filepath=str(path))
    if 'FINISHED' not in result:
        raise RuntimeError('GLB import did not finish.')
    meshes=[obj for obj in bpy.context.scene.objects if obj.type=='MESH']
    tires=[obj for obj in meshes if obj.name.startswith('Tire_')]
    if not meshes or len(tires)!=4:
        raise RuntimeError('GLB is missing expected car meshes/four tires.')
    count=0
    for obj in meshes:
        obj.data.calc_loop_triangles()
        count+=len(obj.data.loop_triangles)
    results.append({'arm':arm,'glb_import':'passed','mesh_objects':len(meshes),'tires':len(tires),'triangles':count,'bytes':path.stat().st_size})
(root/'glb-round-trip.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print('BOTH_GLB_IMPORTS_PASSED '+json.dumps(results))
