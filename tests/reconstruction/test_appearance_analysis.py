from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/reconstruction/python'))
from appearance_analysis import analyze_pixels,estimate_foreground,colour_families

class AppearanceAnalysisTests(unittest.TestCase):
    def test_colour_measurements_are_repeatable_actual_pixels_not_random_design(self):
        rgb=np.full((60,90,3),255,np.uint8)
        rgb[10:50,10:35]=[170,100,45];rgb[10:50,35:60]=[45,25,15];rgb[10:50,60:80]=[215,190,150]
        before=rgb.copy();mask=np.zeros((60,90),bool);mask[10:50,10:80]=True
        first,palette=colour_families(rgb,mask,3);second,again=colour_families(rgb,mask,3)
        np.testing.assert_array_equal(first,second);self.assertEqual(palette,again);np.testing.assert_array_equal(rgb,before)
        actual={tuple(p) for p in rgb[mask]}
        self.assertTrue(all(tuple(p['observedSRGB8']) in actual for p in palette))
        self.assertAlmostEqual(sum(p['objectPixelShare'] for p in palette),1)

    def test_alpha_overrides_background_colour_and_preserves_pale_object(self):
        rgb=np.full((40,40,3),255,np.uint8);alpha=np.zeros((40,40),np.uint8);alpha[10:30,10:30]=255
        mask,qa=estimate_foreground(rgb,alpha)
        self.assertEqual(mask.sum(),400);self.assertEqual(qa['method'],'source-alpha')

    def test_background_is_border_connected_not_all_white_pixels(self):
        rgb=np.full((50,50,3),255,np.uint8);rgb[8:42,8:42]=[130,80,20];rgb[19:30,19:30]=255
        mask,qa=estimate_foreground(rgb)
        self.assertTrue(mask[23,23]);self.assertFalse(mask[0,0]);self.assertEqual(qa['status'],'estimated-matte')

    def test_regions_never_claim_anatomy_or_physical_depth(self):
        rgb=np.full((70,100,3),255,np.uint8);rgb[10:60,10:50]=[180,100,40];rgb[10:60,50:90]=[40,20,10]
        analysis=analyze_pixels(rgb,families=3)
        self.assertGreater(len(analysis['regions']),0)
        for region in analysis['regions']:
            self.assertIsNone(region['partName']);self.assertIsNone(region['depthMetres']);self.assertEqual(region['semanticConfidence'],0)
            self.assertGreater(region['areaPixels'],0)
            for polygon in region['boundaries']:
                self.assertLessEqual(len(polygon['pointsPx']),128)

    def test_nonstudio_background_is_explicitly_ambiguous(self):
        rgb=np.full((40,40,3),[10,30,50],np.uint8)
        mask,qa=estimate_foreground(rgb)
        self.assertEqual(qa['status'],'ambiguous-background');self.assertTrue(mask.all())

    def test_large_white_air_gap_is_not_silently_a_material(self):
        rgb=np.full((180,180,3),255,np.uint8);rgb[10:170,10:170]=[170,110,60];rgb[50:130,50:130]=255
        mask,qa=estimate_foreground(rgb)
        self.assertFalse(mask[90,90]);self.assertGreater(qa['ambiguousEnclosedWhitePixelsExcluded'],0)
