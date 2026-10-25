"""Real xatlas seam preservation and fixed data-worker regression tests."""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/reconstruction/python'))
from uv_atlas import generate_atlas, _recover_original_corners

HAS_XATLAS = importlib.util.find_spec('xatlas') is not None
WORKER = Path(__file__).resolve().parents[2]/'packages/reconstruction/python/uv_atlas_worker.py'
TEST_DIRECTORY = Path(__file__).resolve().parent


def cube():
    v=np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]],float)
    f=np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
                [1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]])
    return v,f


class CorrespondenceTests(unittest.TestCase):
    def test_reordered_native_faces_and_rotated_corners_restore_original_loops(self):
        faces=np.array([[0,1,2],[0,2,3]])
        mapping=np.array([3,0,2,1,0,2],dtype=np.uint32)
        indices=np.array([[2,0,1],[4,3,5]],dtype=np.uint32)
        uv=np.array([[.1,.1],[.2,.2],[.3,.3],[.4,.4],[.5,.5],[.6,.6]])
        loops,_,_,_= _recover_original_corners(faces,mapping,indices,uv)
        np.testing.assert_array_equal(loops[0],uv[[4,3,5]])
        np.testing.assert_array_equal(loops[1],uv[[1,2,0]])
        # Original vertex 0 deliberately has two seam UVs, one per face.
        self.assertFalse(np.array_equal(loops[0,0],loops[1,0]))

    def test_native_missing_face_or_changed_vertex_id_rejected(self):
        faces=np.array([[0,1,2],[0,2,3]])
        uv=np.array([[0,0],[1,0],[1,1],[0,1]],float)
        with self.assertRaisesRegex(ValueError,'FACE_CORRESPONDENCE'):
            _recover_original_corners(faces,np.arange(4,dtype=np.uint32),
                                      np.array([[0,1,2],[0,1,3]],dtype=np.uint32),uv)
        with self.assertRaisesRegex(ValueError,'INDEX_SHAPE'):
            _recover_original_corners(faces,np.arange(4,dtype=np.uint32),np.array([[0,1,2]],dtype=np.uint32),uv)

    def test_invalid_inputs_and_limits_rejected_before_native_code(self):
        v,f=cube()
        with self.assertRaisesRegex(ValueError,'INTEGER_FACES'):
            generate_atlas(v,f.astype(float))
        with self.assertRaisesRegex(ValueError,'FACE_INDEX'):
            generate_atlas(v,np.array([[0,1,99]]))
        with self.assertRaisesRegex(ValueError,'REPEATED_FACE_VERTEX'):
            generate_atlas(v,np.array([[0,0,1]]))
        with self.assertRaisesRegex(ValueError,'RESOLUTION'):
            generate_atlas(v,f,resolution=100000)
        with self.assertRaisesRegex(ValueError,'PADDING'):
            generate_atlas(v,f,padding=-1)
        with self.assertRaisesRegex(ValueError,'NORMALS'):
            generate_atlas(v,f,normals=np.ones((3,3)))
        with self.assertRaisesRegex(ValueError,'ZERO_NORMAL'):
            generate_atlas(v,f,normals=np.zeros_like(v))
        with self.assertRaisesRegex(ValueError,'VERTICES_OR_BUDGET'):
            generate_atlas(np.zeros((200001,3)),np.array([[0,1,2]]))


@unittest.skipUnless(HAS_XATLAS,'Real xatlas is required in the selected vision runtime')
class RealXatlasTests(unittest.TestCase):
    def test_closed_cube_has_real_uv_seams_without_position_or_index_changes(self):
        v,f=cube();before_v,before_f=v.copy(),f.copy()
        v.flags.writeable=False;f.flags.writeable=False
        uv,evidence=generate_atlas(v,f,resolution=512,padding=4)
        self.assertEqual(uv.shape,(12,3,2))
        self.assertTrue(np.isfinite(uv).all())
        self.assertTrue(((uv>=0)&(uv<=1)).all())
        np.testing.assert_array_equal(v,before_v);np.testing.assert_array_equal(f,before_f)
        self.assertGreater(evidence['originalVerticesWithUvSeams'],0)
        self.assertGreater(evidence['atlasVertices'],len(v))
        self.assertGreaterEqual(evidence['chartCount'],6)
        self.assertEqual(evidence['degenerateUvFaces'],0)
        self.assertEqual(evidence['flippedUvFaces'],0)
        self.assertTrue(evidence['geometryUnchanged'])
        self.assertTrue(evidence['originalFaceCornerCorrespondenceVerified'])
        json.dumps(evidence,allow_nan=False)
        # The same original corner must have distinct UV locations across cuts.
        corner_uv=uv[f==0]
        self.assertGreater(len(np.unique(corner_uv,axis=0)),1)

    def test_coplanar_shared_edge_stays_continuous_with_optional_normals(self):
        v=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]],float)
        f=np.array([[0,1,2],[0,2,3]])
        normals=np.tile([0,0,5.],(4,1));original=normals.copy()
        uv,evidence=generate_atlas(v,f,resolution=256,padding=2,normals=normals)
        np.testing.assert_array_equal(normals,original)
        np.testing.assert_array_equal(uv[0,0],uv[1,0])
        np.testing.assert_array_equal(uv[0,2],uv[1,1])
        self.assertEqual(evidence['chartCount'],1)
        self.assertEqual(evidence['degenerateUvFaces'],0)

    def test_coincident_disconnected_triangles_keep_distinct_mesh_identity(self):
        one=np.array([[0,0,0],[1,0,0],[0,1,0]],float)
        v=np.concatenate((one,one));f=np.array([[0,1,2],[3,4,5]])
        uv,evidence=generate_atlas(v,f,resolution=256,padding=2)
        self.assertEqual(evidence['inputVertices'],6)
        self.assertEqual(evidence['inputFaces'],2)
        self.assertEqual(evidence['chartCount'],2)
        self.assertFalse(np.allclose(uv[0],uv[1]))
        self.assertTrue(evidence['originalFaceCornerCorrespondenceVerified'])

    def test_real_ignored_tiny_face_gets_explicit_artist_fill_without_mesh_edit(self):
        v,f=cube()
        # At x=3 these distinct double-precision points collapse along one
        # float32 edge in native xatlas. The original face must still survive.
        v=np.concatenate((v,[[3,0,0],[3+1e-7,0,0],[3,1e-7,0]]))
        f=np.concatenate((f,[[8,9,10]]))
        before_v,before_f=v.copy(),f.copy()
        uv,evidence=generate_atlas(v,f,resolution=512,padding=4)
        self.assertEqual(uv.shape,(13,3,2))
        self.assertTrue(evidence['artistFill']['enabled'])
        self.assertEqual(evidence['artistFill']['faceIndices'],[12])
        self.assertEqual(evidence['artistFill']['faceCount'],1)
        self.assertEqual(evidence['degenerateUvFaces'],0)
        self.assertTrue((uv[12,:,1] > evidence['artistFill']['reservedStripMinimumV']).all())
        self.assertTrue((uv[:12,:,1] <= evidence['artistFill']['reservedStripMinimumV']).all())
        np.testing.assert_array_equal(v,before_v);np.testing.assert_array_equal(f,before_f)

    def test_fixed_worker_real_npz_roundtrip_and_qa(self):
        v,f=cube()
        with tempfile.TemporaryDirectory(prefix='noetra-uv-test-',dir=TEST_DIRECTORY) as folder:
            root=Path(folder).resolve();source=root/'input.npz';output=root/'output.npz';qa=root/'qa.json'
            self.assertTrue(root.is_relative_to(TEST_DIRECTORY))
            options=root/'options.json';options.write_text(json.dumps({'resolution':512,'padding':4}))
            np.savez_compressed(source,vertices=v,faces=f)
            original=source.read_bytes()
            process=subprocess.run([sys.executable,str(WORKER),str(source),str(output),str(qa),str(options)],
                                   capture_output=True,text=True,timeout=100)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertIn('UV_ATLAS_COMPLETE',process.stdout)
            self.assertEqual(source.read_bytes(),original)
            with np.load(output,allow_pickle=False) as arrays:
                self.assertEqual(arrays.files,['loop_uv'])
                self.assertEqual(arrays['loop_uv'].shape,(len(f),3,2))
                self.assertTrue(np.isfinite(arrays['loop_uv']).all())
            report=json.loads(qa.read_text())
            self.assertEqual(report['method'],'xatlas')
            self.assertEqual(report['requestedResolution'],512)
            self.assertTrue(report['geometryUnchanged'])

    def test_worker_rejects_output_escape_and_executable_job_options(self):
        v,f=cube()
        with tempfile.TemporaryDirectory(prefix='noetra-uv-test-',dir=TEST_DIRECTORY) as folder:
            root=Path(folder).resolve();source=root/'input.npz';np.savez(source,vertices=v,faces=f)
            self.assertTrue(root.is_relative_to(TEST_DIRECTORY))
            other=root/'other';other.mkdir()
            p=subprocess.run([sys.executable,str(WORKER),str(source),str(other/'out.npz'),str(root/'qa.json')],
                             capture_output=True,text=True,timeout=100)
            self.assertNotEqual(p.returncode,0)
            self.assertIn('PATH_SCOPE',p.stderr)
            self.assertFalse((other/'out.npz').exists())
            options=root/'options.json';options.write_text(json.dumps({'script':'raise RuntimeError()'}))
            p=subprocess.run([sys.executable,str(WORKER),str(source),str(root/'out.npz'),str(root/'qa.json'),str(options)],
                             capture_output=True,text=True,timeout=100)
            self.assertNotEqual(p.returncode,0)
            self.assertIn('WORKER_OPTIONS',p.stderr)
            self.assertFalse((root/'out.npz').exists())


if __name__=='__main__':unittest.main(verbosity=2)
