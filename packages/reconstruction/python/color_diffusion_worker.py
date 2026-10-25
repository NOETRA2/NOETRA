"""Fixed SciPy color-fill stage in the operator's vision runtime, outside Blender."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import numpy as np
from color_diffusion import diffuse_colors
source,output,evidence=[Path(p) for p in sys.argv[1:]]
assert source.is_file() and source.stat().st_size<64*1024*1024 and source.parent==output.parent==evidence.parent
with np.load(source,allow_pickle=False) as data:
    vertices,known=data['vertices'],data['known'].copy();samples=data['colors'].copy();symmetry={'enabled':False,'inferredAnchors':0}
    if len(data['symmetry']):
        from scipy.spatial import cKDTree
        plane=data['symmetry'];normal=plane[:3];norm=np.linalg.norm(normal);assert norm>1e-8
        normal=normal/norm;offset=plane[3]/norm;ids=np.flatnonzero(known)
        mirrored=vertices-2*(vertices@normal+offset)[:,None]*normal
        distance,nearest=cKDTree(vertices[ids]).query(mirrored);sources=ids[nearest]
        reflected_normals=data['normals']-2*(data['normals']@normal)[:,None]*normal
        aligned=(reflected_normals*data['normals'][sources]).sum(1)>.4
        supported=(~known)&aligned&(distance<np.linalg.norm(np.ptp(vertices,axis=0))*plane[4])
        samples[supported]=samples[sources[supported]];known[supported]=True
        symmetry={'enabled':True,'inferredAnchors':int(supported.sum()),'scope':'Explicit bilateral appearance hypothesis, not newly observed surface color.','maximumDistanceFraction':float(plane[4])}
    colors,report=diffuse_colors(vertices,data['faces'],samples,known,max_iterations=1000,tolerance=1e-6,fallback_color=data['fallback']);report['symmetryAppearancePrior']=symmetry
np.savez_compressed(output,colors=colors);evidence.write_text(json.dumps(report,indent=2));print('SURFACE_COLOR_FILL_COMPLETE')
