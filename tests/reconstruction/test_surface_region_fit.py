from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/reconstruction/python'))
from surface_region_fit import fit_fibre_region
from reference_colors import region_weights

class SurfaceRegionFitTests(unittest.TestCase):
    def test_geometric_fit_is_bounded_and_never_changes_mesh_or_layout(self):
        import copy
        n=41;x,y=np.meshgrid(np.linspace(-1,1,n),np.linspace(-1,1,n));z=np.where(x<.15,.05*np.sin(x*30)*np.cos(y*25),0)
        vertices=np.column_stack([x.ravel(),y.ravel(),z.ravel()]);faces=[]
        for j in range(n-1):
            for i in range(n-1):
                a=j*n+i;faces.extend([[a,a+1,a+n],[a+1,a+n+1,a+n]])
        faces=np.asarray(faces);before=vertices.copy();original_faces=faces.copy()
        layout={'layers':[{'id':'rough-area','region':{'center':[-.4,0,0],'radii':[.35,.7,.2],'feather':.2},'verticalFiber':1}]};original_layout=copy.deepcopy(layout)
        masks,qa=fit_fibre_region(vertices,faces,layout)
        self.assertEqual(qa['status'],'provisional-geometric-fit');self.assertFalse(qa['semanticIdentityVerified'])
        weights=masks['rough-area'];self.assertTrue(((weights>=0)&(weights<=1)).all())
        expanded=copy.deepcopy(layout['layers'][0]['region']);expanded['radii']=(np.asarray(expanded['radii'])*1.55).tolist();expanded['feather']=.4
        np.testing.assert_array_equal(weights[region_weights(vertices,expanded)==0],0)
        np.testing.assert_array_equal(vertices,before);np.testing.assert_array_equal(faces,original_faces);self.assertEqual(layout,original_layout)

    def test_no_fibre_mask_does_not_invent_one(self):
        masks,qa=fit_fibre_region(np.zeros((3,3)),np.array([[0,1,2]]),{'layers':[]})
        self.assertEqual(masks,{});self.assertEqual(qa['status'],'no-attributed-fibre-region')
