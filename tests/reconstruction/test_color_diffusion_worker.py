import unittest,sys,tempfile,json,subprocess
from pathlib import Path
import numpy as np
WORKER=Path(__file__).resolve().parents[2]/'packages/reconstruction/python/color_diffusion_worker.py'

class FillWorkerTests(unittest.TestCase):
    def run_fixture(self,aligned):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'input.npz';output=root/'output.npz';evidence=root/'evidence.json'
            vertices=np.array([[-1,-1,0],[0,-1,0],[0,-1,1],[-1,1,0],[0,1,0],[0,1,1]],float)
            faces=np.array([[0,1,2],[3,5,4]]);colors=np.array([[.1,.2,.3],[.4,.5,.6],[.7,.8,.9],[0,0,0],[0,0,0],[0,0,0]])
            normals=np.array([[0,-1,0]]*3+[[0,1 if aligned else -1,0]]*3)
            np.savez_compressed(source,vertices=vertices,faces=faces,colors=colors,normals=normals,known=np.array([1,1,1,0,0,0],bool),fallback=[.2,.3,.1],symmetry=[0,1,0,0,.035])
            before=source.read_bytes();result=subprocess.run([sys.executable,'-I',str(WORKER),str(source),str(output),str(evidence)],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode());self.assertEqual(before,source.read_bytes())
            with np.load(output) as data:filled=data['colors'].copy()
            report=json.loads(evidence.read_text());self.assertTrue(np.array_equal(filled[:3],colors[:3]))
            return filled,report
    def test_explicit_symmetry_preserves_original_samples_and_maps_matching_normals(self):
        colors,report=self.run_fixture(True);self.assertTrue(np.array_equal(colors[:3],colors[3:]));self.assertEqual(report['symmetryAppearancePrior']['inferredAnchors'],3)
    def test_opposite_orientation_rejected_not_smeared_across_components(self):
        colors,report=self.run_fixture(False);self.assertTrue(np.allclose(colors[3:],[.2,.3,.1]));self.assertEqual(report['symmetryAppearancePrior']['inferredAnchors'],0)

if __name__=='__main__':unittest.main()
