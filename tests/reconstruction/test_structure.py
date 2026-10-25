import unittest,sys,tempfile,json,uuid,hashlib
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/reconstruction/python'))
from structural_math import coons,cubic,fit_camera_distance,wheel_roundness
from worker import load_run

class StructureTests(unittest.TestCase):
    def test_coons_patch_matches_all_four_boundaries(self):
        left=[[0,0,0],[0,.3,.1],[0,.7,.1],[0,1,0]];right=[[1,0,0],[1,.3,.2],[1,.7,.2],[1,1,0]]
        bottom=[[0,0,0],[.3,0,-.1],[.7,0,-.1],[1,0,0]];top=[[0,1,0],[.3,1,.1],[.7,1,.1],[1,1,0]]
        curves={'left':left,'right':right,'bottom':bottom,'top':top}
        for t in np.linspace(0,1,21):
            np.testing.assert_allclose(coons(curves,0,t),cubic(left,t),atol=1e-12)
            np.testing.assert_allclose(coons(curves,1,t),cubic(right,t),atol=1e-12)
            np.testing.assert_allclose(coons(curves,t,0),cubic(bottom,t),atol=1e-12)
            np.testing.assert_allclose(coons(curves,t,1),cubic(top,t),atol=1e-12)

    def test_disconnected_patch_corners_rejected(self):
        line=[[0,0,0],[0,0,.3],[0,0,.7],[0,0,1]]
        with self.assertRaisesRegex(ValueError,'OPEN_CORNERS'):coons({k:line for k in ['left','right','bottom','top']},.5,.5)

    def test_framing_keeps_wheel_bottoms_and_near_corners_inside_margin(self):
        points=np.array([[x,y,z] for x in [-2.5,2.5] for y in [-1.1,1.1] for z in [0,1.2]])
        for angle in [.2,.7,1.5]:
            R=np.array([[np.cos(angle),0,np.sin(angle)],[0,1,0],[-np.sin(angle),0,np.cos(angle)]])
            target=np.array([0,0,.6]);fov=np.deg2rad(42);aspect=16/9;distance=fit_camera_distance(points,R,target,fov,aspect,.075)*1.001
            q=(points-(target+R@np.array([0,0,distance])))@R;tx=np.tan(fov/2);ty=tx/aspect
            xy=.5+q[:,:2]/(-q[:,2,None]*np.array([2*tx,2*ty]))
            self.assertGreater(xy.min(),.075);self.assertLess(xy.max(),.925)

    def test_complete_round_wheel_and_missing_lower_arc_are_distinguished(self):
        angle=np.linspace(0,2*np.pi,128,endpoint=False);points=np.array([[np.cos(t),a,np.sin(t)+1] for a in [-.15,.15] for t in angle])
        self.assertTrue(wheel_roundness(points)['completeCircle'])
        self.assertFalse(wheel_roundness(points[points[:,2]>.65])['completeCircle'])

    def test_modified_prior_invalidates_saved_report(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);identifier=str(uuid.uuid4());run=root/'.noetra/reconstruction'/identifier;run.mkdir(parents=True)
            source=root/'source.blend';saved=run/'prior.blend';source.write_bytes(b'prior');saved.write_bytes(b'prior');digest=hashlib.sha256(b'prior').hexdigest()
            (run/'report.json').write_text(json.dumps({'images':[],'prior':{'source':str(source),'preserved':str(saved),'sha256':digest}}))
            load_run(root,identifier);source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'PRIOR_CHANGED'):load_run(root,identifier)

if __name__=='__main__':unittest.main()
