import unittest,sys,copy
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/reconstruction/python'))
from shape_matching import measure_shape,propose_part_parameters,correction_gate

class ShapeMatchingTests(unittest.TestCase):
    def metrics(self):return {'silhouetteIoU':.8,'boundaryMeanPx':2.,'boundaryP95Px':4.,'keypointRmsePx':3.}
    def views(self):
        return {v:{'origin':'actual_photo','role':role,'parts':{'wheel':self.metrics(),'body':self.metrics()}} for v,role in [('source','fit'),('other','heldout')]}
    def fingerprints(self):return {'cameras':{'source':'fixed-camera','other':'fixed-other-camera'},'parts':{'wheel':'wheel-before','body':'locked-body'}}
    def parameter(self,identifier,part):return {'id':identifier,'partId':part,'value':0.,'minimum':-2.,'maximum':2.,'maxStep':.25}

    def test_mask_and_named_landmarks_measure_geometry(self):
        a=np.zeros((60,80),bool);a[10:40,20:60]=True;b=np.roll(a,3,axis=1)
        exact=measure_shape(a,a,{'hub':[30,20]},{'hub':[30,20]});moved=measure_shape(a,b,{'hub':[30,20]},{'hub':[33,20]})
        self.assertEqual(exact['silhouetteIoU'],1);self.assertEqual(exact['boundaryMeanPx'],0);self.assertEqual(moved['keypointRmsePx'],3);self.assertLess(moved['silhouetteIoU'],1)

    def test_bounded_proposal_preserves_locked_parameters(self):
        parameters=[self.parameter('wheel-x','wheel'),self.parameter('body-x','body')]
        result=propose_part_parameters(parameters,[1.,3.],np.eye(2),locked_parts=['body'])
        self.assertAlmostEqual(result['parameters'][0]['delta'],-.25);self.assertEqual(result['parameters'][1]['delta'],0);self.assertTrue(result['requiresActualRender'])
        self.assertEqual(parameters[0]['value'],0)

    def test_proposal_requires_finite_nonzero_uncertainty_and_strict_fields(self):
        parameter=self.parameter('wheel-x','wheel')
        with self.assertRaisesRegex(ValueError,'UNCERTAINTY'):propose_part_parameters([parameter],[1],[[1]],uncertainty=[0])
        parameter['camera']='edit-camera'
        with self.assertRaisesRegex(ValueError,'PARAMETER_FIELDS'):propose_part_parameters([parameter],[1],[[1]])

    def test_actual_fit_and_heldout_nonregression_accept(self):
        before=self.views();after=copy.deepcopy(before);after['source']['parts']['wheel']['silhouetteIoU']=.9
        result=correction_gate(before,after,self.fingerprints(),self.fingerprints(),['wheel'],['other'])
        self.assertTrue(result['accepted']);self.assertEqual(result['validationScope'],'heldout-actual-views')

    def test_camera_locked_part_and_heldout_regressions_reject(self):
        before=self.views();after=copy.deepcopy(before);after['source']['parts']['wheel']['silhouetteIoU']=.9
        fingerprints=self.fingerprints();fingerprints['cameras']['source']='changed';fingerprints['parts']['body']='changed'
        after['other']['parts']['wheel']['boundaryMeanPx']=4
        result=correction_gate(before,after,self.fingerprints(),fingerprints,['wheel'],['other'])
        self.assertFalse(result['accepted']);self.assertIn('camera_changed',result['reasons']);self.assertIn('locked_part_changed:body',result['reasons']);self.assertIn('geometry_regression:other:wheel',result['reasons'])

    def test_rendered_heldout_and_texture_only_changes_cannot_accept(self):
        before=self.views();after=copy.deepcopy(before)
        # Cosmetic material changes leave all geometry metrics equal.
        self.assertFalse(correction_gate(before,after,self.fingerprints(),self.fingerprints(),['wheel'])['accepted'])
        for value in [before,after]:value['other']['origin']='rendered'
        after['source']['parts']['wheel']['silhouetteIoU']=.9
        result=correction_gate(before,after,self.fingerprints(),self.fingerprints(),['wheel'],['other'])
        self.assertFalse(result['accepted']);self.assertIn('hypothesis_used_as_validation:other',result['reasons'])

    def test_changed_provenance_or_landmark_coverage_rejected(self):
        before=self.views();after=copy.deepcopy(before);after['source']['origin']='generated'
        result=correction_gate(before,after,self.fingerprints(),self.fingerprints(),['wheel'])
        self.assertFalse(result['accepted'])
        with self.assertRaisesRegex(ValueError,'KEYPOINT_IDS'):measure_shape(np.ones((10,10)),np.ones((10,10)),{'hub':[2,2]},{'rim':[2,2]})

    def test_empty_render_and_border_foreground_have_defined_boundary_metrics(self):
        target=np.ones((20,30),bool)
        self.assertEqual(measure_shape(target,target)['boundaryMeanPx'],0)
        missing=measure_shape(target,np.zeros_like(target));self.assertEqual(missing['silhouetteIoU'],0);self.assertEqual(missing['boundaryMeanPx'],30)
        with self.assertRaisesRegex(ValueError,'MATCH_MASK'):measure_shape(target,np.full(target.shape,np.nan))

    def test_artwork_fit_improvement_accepts_with_explicit_unvalidated_scope(self):
        before=self.views();before.pop('other');before['source']['origin']='reference_artwork';after=copy.deepcopy(before)
        after['source']['parts']['wheel']['silhouetteIoU']=.9
        result=correction_gate(before,after,self.fingerprints(),self.fingerprints(),['wheel'])
        self.assertTrue(result['accepted']);self.assertEqual(result['validationScope'],'reference-artwork-only; hidden geometry unvalidated');self.assertEqual(result['independentHeldoutViews'],[])

    def test_artwork_heldout_is_rejected_and_generated_backview_is_inspection_only(self):
        before=self.views();before['source']['origin']='reference_artwork';before['other']['origin']='reference_artwork';after=copy.deepcopy(before)
        after['source']['parts']['wheel']['silhouetteIoU']=.9
        result=correction_gate(before,after,self.fingerprints(),self.fingerprints(),['wheel'],['other'])
        self.assertFalse(result['accepted']);self.assertIn('artwork_used_as_independent_validation:other',result['reasons'])
        for value in [before,after]:value['other'].update(origin='generated',role='fit')
        result=correction_gate(before,after,self.fingerprints(),self.fingerprints(),['wheel'])
        self.assertFalse(result['accepted']);self.assertIn('hypothesis_used_as_validation:other',result['reasons'])

if __name__=='__main__':unittest.main()
