"""Ground-truth math and deliberate failure tests. Not eight full object benchmarks."""
import unittest,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages'/'reconstruction'/'python'))
import numpy as np
from geometry import project,triangulate_checked,plane_grid,grid_points,optimize_scales,bezier_patch,compare_masks,symmetric_distance,exr_channels
from worker import scope,image_record,load_run,optimize
from PIL import Image

class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.K=np.array([[600.,0,320],[0,600,240],[0,0,1]])
        self.R=np.eye(3);self.T=np.array([[-1.],[0],[0]])
        self.box=np.array([[x,y,z] for x in [-.6,.6] for y in [-.4,.4] for z in [4.,5.]])
    def test_metric_box_ground_truth(self):
        a=project(self.box,self.K);b=project(self.box,self.K,self.R,self.T)
        points,valid,errors,angles=triangulate_checked(a,b,self.K,np.zeros(5),self.K,np.zeros(5),self.R,self.T)
        self.assertTrue(valid.all());self.assertLess(np.sqrt(np.mean((points-self.box)**2)),1e-8)
        np.testing.assert_allclose(np.ptp(points,axis=0),[1.2,.8,1.],atol=1e-8)
    def test_exr_multipart_channel_headers(self):
        import struct
        def header(name):
            channels=name.encode()+b'\0'+struct.pack('<iB3xii',2,0,1,1)+b'\0'
            return b'channels\0chlist\0'+struct.pack('<I',len(channels))+channels+b'\0'
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'passes.exr'
            path.write_bytes(b'\x76\x2f\x31\x01'+struct.pack('<I',2|0x1000)+header('ViewLayer.Combined.R')+header('ViewLayer.Depth.Z')+header('ViewLayer.Normal.X')+b'\0')
            self.assertEqual(exr_channels(path),['ViewLayer.Combined.R','ViewLayer.Depth.Z','ViewLayer.Normal.X'])
    def test_invalid_exr_header_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'bad.exr';path.write_bytes(b'not an EXR')
            with self.assertRaisesRegex(ValueError,'EXR_HEADER'):exr_channels(path)
    def test_zero_baseline_rejected(self):
        with self.assertRaisesRegex(ValueError,'ZERO_BASELINE'):
            triangulate_checked(project(self.box,self.K),project(self.box,self.K),self.K,np.zeros(5),self.K,np.zeros(5),self.R,np.zeros((3,1)))
    def test_wrong_correspondences_rejected(self):
        a=project(self.box,self.K);b=project(self.box,self.K,self.R,self.T)[::-1]
        with self.assertRaisesRegex(ValueError,'INCONSISTENT_MATCHES'):
            triangulate_checked(a,b,self.K,np.zeros(5),self.K,np.zeros(5),self.R,self.T)
    def test_non_rotation_camera_rejected(self):
        with self.assertRaisesRegex(ValueError,'CAMERA_ROTATION'):
            triangulate_checked(project(self.box,self.K),project(self.box,self.K),self.K,np.zeros(5),self.K,np.zeros(5),self.R*2,self.T)
    def test_nonfinite_geometry_rejected(self):
        with self.assertRaisesRegex(ValueError,'NONFINITE'):project([[0,0,np.nan]],self.K)
    def test_behind_camera_rejected(self):
        with self.assertRaisesRegex(ValueError,'BEHIND_CAMERA'):project([[0,0,-1]],self.K)
    def test_bicubic_planar_normal_and_curvature(self):
        c=np.array([[[i/3,j/3,0.] for j in range(4)] for i in range(4)])
        p=bezier_patch(c,.5,.5);np.testing.assert_allclose(p['point'],[.5,.5,0],atol=1e-12)
        np.testing.assert_allclose(p['normal'],[0,0,1]);self.assertAlmostEqual(p['mean_curvature'],0)
    def test_raised_and_recessed_controlled_surface_distinct(self):
        c=np.array([[[i/3,j/3,0.] for j in range(4)] for i in range(4)])
        c[1:3,1:3,2]=.2
        raised=bezier_patch(c,.5,.5);c[:,:,2]*=-1;recessed=bezier_patch(c,.5,.5)
        self.assertGreater(raised['point'][2],0);self.assertLess(recessed['point'][2],0)
        self.assertLess(raised['mean_curvature']*recessed['mean_curvature'],0)
    def test_degenerate_patch_rejected(self):
        with self.assertRaisesRegex(ValueError,'DEGENERATE'):bezier_patch(np.zeros((4,4,3)),.5,.5)
    def test_patch_domain_not_extrapolated(self):
        with self.assertRaisesRegex(ValueError,'DOMAIN'):bezier_patch(np.zeros((4,4,3)),2,.5)
    def test_bounded_scale_optimizer_improves_actual_projection(self):
        x,y=np.meshgrid(np.arange(9)-4,np.arange(6)-2.5)
        xyz=np.c_[x.ravel()*.2,y.ravel()*.2,np.full(54,5.)]
        surface=plane_grid(xyz,[9,6]);observed=project(xyz,self.K)
        initial=np.linalg.norm(project(grid_points(surface,[.8,1.2]),self.K)-observed)
        values,history,report=optimize_scales(surface,[.8,1.2],self.K,observed,24)
        final=np.linalg.norm(project(grid_points(surface,values),self.K)-observed)
        self.assertLess(final,initial/100);self.assertLessEqual(report['nfev'],24)
        np.testing.assert_allclose(values,[1,1],atol=1e-6)
        self.assertTrue(all(.5<=v<=1.5 for h in history for v in h['scales']))
    def test_optimization_budget_rejected(self):
        with self.assertRaisesRegex(ValueError,'BUDGET'):optimize_scales({},[1,1],self.K,[],100)
    def test_invalid_scale_rejected(self):
        with self.assertRaisesRegex(ValueError,'PARAMETER_BOUNDS'):grid_points({},[.1,2])
    def test_mask_overlap_and_boundary_measured(self):
        a=np.zeros((32,32),np.uint8);a[5:20,5:20]=1;b=np.roll(a,2,axis=1)
        perfect=compare_masks(a,a);shifted=compare_masks(a,b)
        self.assertEqual(perfect['silhouette_iou'],1);self.assertEqual(perfect['boundary']['mean_px'],0)
        self.assertLess(shifted['silhouette_iou'],1);self.assertGreater(shifted['boundary']['mean_px'],0)
    def test_empty_mask_not_perfect(self):
        with self.assertRaisesRegex(ValueError,'EMPTY_MASK'):compare_masks(np.zeros((8,8)),np.zeros((8,8)))
    def test_size_mismatch_not_resized_silently(self):
        with self.assertRaisesRegex(ValueError,'IMAGE_SIZE'):compare_masks(np.ones((8,8)),np.ones((9,9)))
    def test_missing_edges_report_unknown(self):
        self.assertIsNone(symmetric_distance(np.zeros((8,8),bool),np.ones((8,8),bool)))
    def test_project_scope_and_path_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve()
            with self.assertRaisesRegex(ValueError,'OUTSIDE_PROJECT'):scope(root,root.parent/'private.png',False)
            with self.assertRaisesRegex(ValueError,'ABSOLUTE_PATH'):scope(root,'relative.png',False)
    def test_preserves_original_rgb_and_alpha(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();run=root/'run';run.mkdir();source=root/'source.png'
            pixels=np.zeros((8,8,4),np.uint8);pixels[:,:,:3]=[12,34,56];pixels[:,:,3]=78
            Image.fromarray(pixels).save(source);record,rgb=image_record(root,source,run,0)
            self.assertEqual(source.read_bytes(),Path(record['preserved']).read_bytes())
            with np.load(record['rgbArray']) as array:
                np.testing.assert_array_equal(array['rgb'],pixels[:,:,:3]);np.testing.assert_array_equal(array['alpha'],pixels[:,:,3])
    def test_blender_execution_requires_operator_consent(self):
        with self.assertRaisesRegex(ValueError,'EXECUTION_NOT_APPROVED'):optimize(None,None,{}, {},{'allowBlenderExecution':False})
    def test_source_mutation_invalidates_run(self):
        import json,hashlib,uuid
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();identifier=str(uuid.uuid4());run=root/'.noetra'/'reconstruction'/identifier;run.mkdir(parents=True)
            source=root/'a.png';source.write_bytes(b'first');copied=run/'a.png';copied.write_bytes(b'first')
            (run/'report.json').write_text(json.dumps({'images':[{'source':str(source),'preserved':str(copied),'sha256':hashlib.sha256(b'first').hexdigest()}]}))
            load_run(root,identifier);source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):load_run(root,identifier)

if __name__=='__main__':unittest.main(verbosity=2)
