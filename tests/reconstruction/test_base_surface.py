from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/reconstruction/python'))
from base_surface import bounded_deform

class BaseSurfaceTests(unittest.TestCase):
    def test_connected_base_keeps_topology_and_protected_vertices_exact(self):
        points=np.array([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0],[0,0,0]],float)
        faces=np.array([[0,1,4],[1,2,4],[2,3,4],[3,0,4]])
        before=points.copy();original_faces=faces.copy()
        spec={'maximumDisplacement':.01,'deformations':[{'id':'bounded','region':{'center':[0,0,0],'radii':[.5,.5,.5]},'direction':[0,0,1],'distance':.02}]}
        result,qa=bounded_deform(points,faces,spec)
        np.testing.assert_array_equal(result[:4],points[:4]);self.assertAlmostEqual(result[4,2],.01)
        np.testing.assert_array_equal(points,before);np.testing.assert_array_equal(faces,original_faces)
        self.assertTrue(qa['protectedVerticesExactlyUnchanged']);self.assertEqual(qa['addedObjects'],0)

    def test_invalid_direction_fails(self):
        with self.assertRaisesRegex(ValueError,'DIRECTION'):
            bounded_deform(np.array([[0,0,0],[1,0,0],[0,1,0]]),np.array([[0,1,2]]),{'maximumDisplacement':.01,'deformations':[{'id':'x','region':None,'direction':[0,0,0],'distance':.01}]})

