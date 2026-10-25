from pathlib import Path
import sys,unittest,tempfile,json,hashlib
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/reconstruction/python'))
from uv_cache import reuse_cache

class AtlasCacheTests(unittest.TestCase):
    def test_exact_cache_reused_but_changed_geometry_and_modified_files_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);points=np.array([[0,0,0],[1,0,0],[0,1,0]],float);faces=np.array([[0,1,2]])
            np.savez(root/'input.npz',vertices=points,faces=faces,resolution=1024,padding=6)
            np.savez(root/'uv.npz',loop_uv=np.array([[[.1,.1],[.9,.1],[.1,.9]]]))
            (root/'qa.json').write_text('{}')
            files={k:str(root/name) for k,name in {'input':'input.npz','output':'uv.npz','qa':'qa.json'}.items()}
            cache={'files':files,'sha256':{k:hashlib.sha256(Path(p).read_bytes()).hexdigest() for k,p in files.items()},'sourceRun':'existing'}
            self.assertTrue(reuse_cache(cache,points,faces,1024,root/'out.npz',root/'out.json'))
            self.assertTrue(json.loads((root/'out.json').read_text())['cacheReuse']['exactGeometryAndSettingsMatched'])
            moved=points.copy();moved[0,2]=.01
            self.assertFalse(reuse_cache(cache,moved,faces,1024,root/'out.npz',root/'out.json'))
            self.assertFalse(reuse_cache(cache,points,faces,2048,root/'out.npz',root/'out.json'))
            (root/'qa.json').write_text('{"tampered":true}')
            self.assertFalse(reuse_cache(cache,points,faces,1024,root/'out.npz',root/'out.json'))
