import unittest,tempfile,json,hashlib,sys,importlib.util
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/reconstruction/python'))
from photo_provider import validate_models
from photo_geometry import silhouette,camera
from photo_pipeline import contour_flow
from surface_repair import repair,face_normals,constrained_step

class PhotoTests(unittest.TestCase):
    def fixture(self,root):
        source=root/'source';source.mkdir();(source/'provider.py').write_text('approved = True\n')
        files={}
        for key in ['config','weights','dinoConfig','background']:
            path=root/(key+'.bin');path.write_bytes(key.encode());files[key]={'path':str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        manifest=root/'models.json';manifest.write_text(json.dumps({'sourceCommit':'pinned','files':files}))
        approvals=root/'source.json';approvals.write_text(json.dumps({'sourceCommit':'pinned','pythonFiles':{'provider.py':hashlib.sha256((source/'provider.py').read_bytes()).hexdigest()}}))
        return {'sourceDirectory':str(source),'sourceManifest':str(approvals),'modelManifest':str(manifest)}

    def test_changed_model_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);config=self.fixture(root);validate_models(config);(root/'weights.bin').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'RECONSTRUCTION_MODEL_CHANGED'):validate_models(config)

    def test_changed_provider_source_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);config=self.fixture(root);(root/'source/provider.py').write_text('approved = False\n')
            with self.assertRaisesRegex(ValueError,'RECONSTRUCTION_MODEL_SOURCE_CHANGED'):validate_models(config)

    def test_pinned_source_identity_required(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);config=self.fixture(root);manifest=json.loads((root/'models.json').read_text());manifest['sourceCommit']='other';(root/'models.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'RECONSTRUCTION_MODEL_SOURCE_IDENTITY'):validate_models(config)

    def test_proxy_projects_actual_geometry_not_a_reference_bitmap(self):
        vertices=np.array([[0,-.2,-.2],[0,.2,-.2],[0,.2,.2],[0,-.2,.2]])
        faces=np.array([[0,1,2],[0,2,3]]);mask=silhouette(vertices,faces,[0,0,1.9,0,0]);moved=silhouette(vertices+np.array([0,.3,0]),faces,[0,0,1.9,0,0])
        self.assertGreater((mask>0).sum(),100);self.assertFalse(np.array_equal(mask,moved))
        c=camera([0,0,1.9,0,0]);self.assertAlmostEqual(np.linalg.det(c['R']),1.)

    def test_contour_proposal_bounded_and_distant_interiors_protected(self):
        prediction=np.zeros((128,128),bool);prediction[20:108,20:108]=True
        target=np.zeros_like(prediction);target[22:106,24:104]=True
        flow=contour_flow(prediction,target)
        self.assertLessEqual(float(np.linalg.norm(flow,axis=2).max()),9.60001)
        np.testing.assert_array_equal(flow[64,64],[0.,0.]);self.assertGreater(float(np.linalg.norm(flow[20,64])),0)

    def test_surface_repair_reduces_spike_preserving_interior_and_orientation(self):
        n=33;xx,yy=np.meshgrid(np.linspace(-.8,.8,n),np.linspace(-.8,.8,n));zz=np.zeros_like(xx);zz[n//2,1]=.08
        vertices=np.column_stack([xx.ravel(),yy.ravel(),zz.ravel()]);faces=[]
        for y in range(n-1):
            for x in range(n-1):
                i=y*n+x;faces.extend([[i,i+1,i+n+1],[i,i+n+1,i+n]])
        faces=np.array(faces);pixels=np.column_stack([xx.ravel()*100/3+64,-yy.ravel()*100/3+64])
        mask=np.zeros((128,128),bool);mask[37:92,37:92]=True
        candidate,report=repair(vertices,faces,pixels,np.full(len(vertices),3.),np.eye(3),100.,mask)
        self.assertEqual(report['flippedFaces'],0);self.assertGreater(report['protectedVerticesUnchanged'],0)
        np.testing.assert_array_equal(candidate[n*n//2],vertices[n*n//2])
        self.assertLess(report['localLaplacianResidualAfter'],report['localLaplacianResidualBefore'])
        self.assertLessEqual(report['maxDisplacementRelativeUnits'],report['displacementLimit']+1e-12)
        self.assertGreater(candidate[n+1,0],-1.)

    def test_bad_triangle_limits_only_its_local_neighbourhood(self):
        vertices=np.array([[0,0,0],[1,0,0],[0,1,0],[3,0,0],[4,0,0],[3,1,0]],float);faces=np.array([[0,1,2],[3,4,5]])
        normals,areas=face_normals(vertices,faces);proposal=vertices.copy();proposal[[1,2]]=proposal[[2,1]];proposal[3:,2]=.2
        candidate,decision=constrained_step(vertices,proposal,faces,normals,areas)
        self.assertTrue(decision['accepted']);self.assertEqual(decision['limitedVertices'],3)
        np.testing.assert_array_equal(candidate[3:],proposal[3:]);updated,_=face_normals(candidate,faces)
        self.assertTrue(np.all((updated*normals).sum(1)>.05))

    @unittest.skipUnless(importlib.util.find_spec('torch'),'Optional local Torch environment is not installed')
    def test_cpu_isosurface_preserves_asymmetric_axes(self):
        import torch,trimesh
        source=Path(__file__).resolve().parents[2]/'.tools/TripoSR';sys.path.insert(0,str(source))
        from tsr.models.isosurface import MarchingCubeHelper
        helper=MarchingCubeHelper(64);points=helper.grid_vertices;center=torch.tensor([.3,.55,.7]);radii=torch.tensor([.2,.15,.08])
        field=1-(((points-center)/radii)**2).sum(-1);vertices,faces=helper(field)
        bounds=np.array([vertices.min(0).values.numpy(),vertices.max(0).values.numpy()]);expected=np.array([(center-radii).numpy(),(center+radii).numpy()])
        self.assertLess(np.max(np.abs(bounds-expected)),.002)
        mesh=trimesh.Trimesh(vertices.numpy(),faces.numpy(),process=False);self.assertTrue(mesh.is_watertight);self.assertGreater(mesh.volume,0)

if __name__=='__main__':unittest.main()
