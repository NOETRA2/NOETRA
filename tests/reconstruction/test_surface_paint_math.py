from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/reconstruction/python'))
from surface_paint_math import paint_fields,linear
from reference_colors import region_weights

class SurfacePaintTests(unittest.TestCase):
    def test_box_covers_outer_part_without_ellipsoid_corner_holes(self):
        points=np.array([[.8,.8,0],[1,0,0],[0,0,0]],float)
        region={'center':[0,0,0],'radii':[1,1,1],'feather':.1}
        self.assertEqual(region_weights(points,region)[0],0)
        np.testing.assert_array_equal(region_weights(points,{**region,'shape':'box'}),[1,0,1])

    def test_local_paint_preserves_outside_and_inputs_in_linear_space(self):
        points=np.array([[0,0,0],[2,0,0]],float);before=points.copy()
        design={'baseSRGB':[.7,.4,.2],'baseRoughness':.8,'layers':[{
            'id':'nose','region':{'shape':'box','center':[0,0,0],'radii':[1,1,1]},
            'colorSRGB':[.1,.05,.02],'roughness':.4,'verticalFiber':1,'provenance':'Test region'}]}
        colors,rough,flow,layers=paint_fields(points,design)
        np.testing.assert_array_equal(points,before)
        np.testing.assert_allclose(colors[0],linear([.1,.05,.02]))
        np.testing.assert_allclose(colors[1],linear(design['baseSRGB']))
        np.testing.assert_allclose(rough,[.4,.8]);np.testing.assert_allclose(flow,[1,0])
        self.assertEqual(layers[0]['affectedVertices'],1)

    def test_gradient_clamps_to_bounds_without_repainting_unrelated_points(self):
        points=np.array([[0,0,-2],[0,0,0],[0,0,2],[20,0,0]],float)
        layer={'id':'mane','region':{'shape':'box','center':[0,0,0],'radii':[4,4,4]},
               'colorSRGB':[0,0,0],'roughness':.9,'provenance':'Bounded gradient',
               'gradient':{'axis':'Z','minimum':-1,'maximum':1,'colorSRGB':[1,1,1]}}
        design={'baseSRGB':[.5,.5,.5],'baseRoughness':.8,'layers':[layer]}
        colors,_,_,_=paint_fields(points,design)
        np.testing.assert_allclose(colors[:3],[[0,0,0],[.5,.5,.5],[1,1,1]])
        np.testing.assert_allclose(colors[3],linear([.5,.5,.5]))

    def test_unknown_region_shape_fails_instead_of_silent_ellipsoid(self):
        with self.assertRaisesRegex(ValueError,'REGION_SHAPE'):
            region_weights(np.zeros((1,3)),{'shape':'polygon','center':[0,0,0],'radii':[1,1,1]})
