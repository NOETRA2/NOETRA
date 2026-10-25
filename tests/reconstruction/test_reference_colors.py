import unittest,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/reconstruction/python'))
from reference_colors import basis,foreground,coordinates,sample,warp_coordinates,region_weights

class ReferenceColors(unittest.TestCase):
    def test_basis_preserves_orientation(self):
        toward,up,right=basis([-1,0,0],[0,0,1]);self.assertTrue(np.allclose(right,[0,-1,0]));self.assertAlmostEqual(np.dot(up,toward),0)
    def test_parallel_up_rejected(self):
        with np.errstate(invalid='ignore',divide='ignore'):
            with self.assertRaises(ValueError):basis([0,0,1],[0,0,1])
    def test_white_background_and_transparent_alpha(self):
        rgb=np.full((30,30,3),255,np.uint8);rgb[5:25,5:25]=[150,80,30]
        self.assertEqual(foreground(rgb).sum(),400)
        alpha=np.zeros((30,30),np.uint8);alpha[7:22,7:22]=255;self.assertEqual(foreground(rgb,alpha).sum(),225)
    def test_alignment_preserves_aspect_and_bottom(self):
        points=np.array([[0,-1,0],[0,1,0],[0,1,2],[0,-1,2]]);mask=np.zeros((60,80),bool);mask[10:50,20:60]=True
        uv,record=coordinates(points,[-1,0,0],[0,0,1],mask)
        self.assertAlmostEqual(uv[:,1].max(),49);self.assertAlmostEqual(np.ptp(uv[:,0]),np.ptp(uv[:,1]));self.assertGreater(record['scalePixelsPerUnit'],0)
    def test_sample_rejects_background_and_converts_srgb(self):
        rgb=np.full((10,10,3),128,np.uint8);mask=np.ones((10,10),bool);mask[2,2]=False
        colors,valid=sample(rgb,mask,np.array([[4,4],[2,2],[-1,2],[20,4]]));self.assertEqual(valid.tolist(),[True,False,False,False]);self.assertAlmostEqual(colors[0,0],.2158605,places=5)
    def test_sampling_landmarks_interpolate_exactly_without_moving_geometry(self):
        points=np.array([[20,20],[60,20],[30,70]],float);copy=points.copy()
        targets=points+[[5,2],[3,-1],[-4,2]]
        controls=[{'modelPixel':s.tolist(),'referencePixel':t.tolist()} for s,t in zip(points,targets)]
        warped,evidence=warp_coordinates(points,controls,(100,100))
        self.assertTrue(np.allclose(warped,targets));self.assertTrue(np.array_equal(points,copy));self.assertFalse(evidence['geometryMoved'])
        corners=np.array([[0,0],[99,0],[0,99],[99,99]],float);warped,_=warp_coordinates(corners,controls,(100,100));self.assertTrue(np.allclose(warped,corners))
    def test_invalid_or_duplicate_sampling_controls_fail(self):
        for source in [[[1,1],[1,1],[3,3]],[[1,1],[2,2],[3,3]]]:
            controls=[{'modelPixel':p,'referencePixel':p} for p in source]
            with self.assertRaises(ValueError):warp_coordinates(np.array([[2,2]]),controls,(100,100))
    def test_bounded_color_patch_cannot_touch_other_body_regions(self):
        region={'center':[0,0,0],'radii':[1,2,1],'feather':.2}
        values=region_weights(np.array([[0,0,0],[1,0,0],[2,0,0],[0,1.8,0]]),region)
        self.assertEqual(values[0],1);self.assertEqual(values[1],0);self.assertEqual(values[2],0);self.assertAlmostEqual(values[3],.5)
        with self.assertRaises(ValueError):region_weights(np.zeros((1,3)),{'center':[0,0,0],'radii':[0,1,1]})

if __name__=='__main__':unittest.main()
