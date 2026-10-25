from pathlib import Path
import sys,unittest,copy
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/reconstruction/python'))
from measured_paint import derive_design,checked_layout

class MeasuredPaintTests(unittest.TestCase):
    def layout(self):
        return {'baseSRGB':[.6,.3,.1],'baseRoughness':.8,'resolution':1024,'provenance':'Existing attributed layout','layers':[
          {'id':'region-a','region':{'center':[0,0,0],'radii':[1,1,1],'provenance':'Hypothesis'},'colorSRGB':[.12,.06,.02],
           'roughness':.85,'gradient':{'axis':'Z','minimum':0,'maximum':1,'colorSRGB':[.8,.6,.3]},'provenance':'Authored mask'}]}
    def palette(self):
        return [{'family':i+1,'hex':'#'+''.join(f'{x:02X}' for x in c),'observedSRGB8':c} for i,c in enumerate([[40,22,14],[170,95,45],[210,165,100]])]
    def test_software_uses_only_measured_colours_and_keeps_spatial_layout(self):
        layout=self.layout();before=copy.deepcopy(layout);palette=self.palette()
        design,assignments=derive_design(layout,palette)
        np.testing.assert_allclose(design['layers'][0]['region']['center'],layout['layers'][0]['region']['center'])
        self.assertEqual(layout,before);self.assertEqual(len(assignments),3)
        allowed={tuple(p['observedSRGB8']) for p in palette}
        colors=[design['baseSRGB'],design['layers'][0]['colorSRGB'],design['layers'][0]['gradient']['colorSRGB']]
        self.assertTrue(all(tuple(np.rint(np.asarray(c)*255).astype(int)) in allowed for c in colors))
    def test_same_inputs_give_same_design_without_sampling_random_colours(self):
        self.assertEqual(derive_design(self.layout(),self.palette()),derive_design(self.layout(),self.palette()))
    def test_layout_cannot_supply_code_or_photographic_projection(self):
        for extra in [{'code':'import os'},{'referenceSurface':{'image':'photo.png'}},{'layers':[]}]:
            with self.assertRaises(ValueError):checked_layout({**self.layout(),**extra})
    def test_nonfinite_or_unbounded_regions_are_rejected(self):
        for value in [float('nan'),10001]:
            layout=self.layout();layout['layers'][0]['region']['radii'][0]=value
            with self.assertRaises(ValueError):checked_layout(layout)
