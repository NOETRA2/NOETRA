"""Independent color-boundary, graph-connectivity and solver-budget fixtures."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/reconstruction/python'))
from color_diffusion import diffuse_colors, srgb_to_linear, linear_to_srgb


def ribbon(segments=12, offset=(0,0,0)):
    v=np.array([[i,j,0] for i in range(segments+1) for j in (0,1)],dtype=float)+offset
    f=[]
    for i in range(segments):
        a=2*i
        f.extend([[a,a+2,a+1],[a+1,a+2,a+3]])
    return v,np.array(f,dtype=int)


class ColorDiffusionTests(unittest.TestCase):
    def test_analytic_dirichlet_average_and_anchors_exact(self):
        v=np.array([[0,0,0],[1,0,0],[0,1,0]],float)
        f=np.array([[0,1,2]])
        colors=np.array([[1,.2,0],[np.nan,np.nan,np.nan],[0,.4,1]],float)
        known=np.array([True,False,True])
        result,evidence=diffuse_colors(v,f,colors,known)
        np.testing.assert_allclose(result[1],[.5,.3,.5],atol=1e-12)
        np.testing.assert_array_equal(result[known],colors[known])
        self.assertEqual(evidence['solver']['status'],'converged')
        self.assertTrue(evidence['anchorsPreservedExactly'])

    def test_coincident_disconnected_surfaces_do_not_bleed(self):
        a,af=ribbon(8)
        v=np.concatenate((a,a))
        f=np.concatenate((af,af+len(a)))
        known=np.zeros(len(v),dtype=bool);known[0]=True;known[len(a)]=True
        c=np.full((len(v),3),np.nan);c[0]=[1,0,0];c[len(a)]=[0,0,1]
        result,evidence=diffuse_colors(v,f,c,known)
        np.testing.assert_array_equal(result[:len(a)],np.tile([1,0,0],(len(a),1)))
        np.testing.assert_array_equal(result[len(a):],np.tile([0,0,1],(len(a),1)))
        self.assertEqual(evidence['connectedComponents'],2)
        self.assertEqual(evidence['nearestGraphSeedFallbackVertices'],0)

    def test_unseen_touching_component_uses_declared_fallback(self):
        a,af=ribbon(3)
        v=np.concatenate((a,a))
        f=np.concatenate((af,af+len(a)))
        known=np.zeros(len(v),bool);known[0]=True
        c=np.full((len(v),3),np.nan);c[0]=[1,0,0]
        result,evidence=diffuse_colors(v,f,c,known,fallback_color=(.12,.15,.2))
        np.testing.assert_array_equal(result[len(a):],np.tile([.12,.15,.2],(len(a),1)))
        self.assertEqual(evidence['componentsWithoutObservations'],1)
        self.assertEqual(evidence['unobservedComponentFallbackVertices'],len(a))

    def test_folded_connected_surface_uses_graph_path_not_nearby_3d_seed(self):
        v,f=ribbon(30)
        # Fold a distant blue tip onto an unknown vertex near the red tip.
        # Their graph path is still long, despite near-zero 3D separation.
        v[-2:]=v[2:4]+[0,0,1e-10]
        known=np.zeros(len(v),bool);known[0]=True;known[-1]=True
        c=np.full((len(v),3),np.nan);c[0]=[1,0,0];c[-1]=[0,0,1]
        result,evidence=diffuse_colors(v,f,c,known,max_iterations=0)
        np.testing.assert_array_equal(result[2],[1,0,0])
        self.assertEqual(evidence['connectedComponents'],1)
        self.assertEqual(evidence['solver']['status'],'graph_seed_fallback')

    def test_differing_regions_interpolate_and_obey_maximum_principle(self):
        v,f=ribbon(40)
        known=np.zeros(len(v),bool);known[:2]=True;known[-2:]=True
        c=np.full((len(v),3),np.nan);c[:2]=[.9,.1,.2];c[-2:]=[.1,.4,.8]
        result,evidence=diffuse_colors(v,f,c,known,max_iterations=400,tolerance=1e-9)
        self.assertEqual(evidence['solver']['status'],'converged')
        self.assertTrue(evidence['maximumPrincipleSatisfied'])
        self.assertTrue(np.all(result>=[.1,.1,.2]))
        self.assertTrue(np.all(result<=[.9,.4,.8]))
        middle=result[len(v)//2]
        self.assertTrue(.3<middle[0]<.7)
        self.assertTrue(.3<middle[2]<.7)
        np.testing.assert_array_equal(result[known],c[known])

    def test_zero_iteration_budget_is_honest_graph_seed_fallback(self):
        v,f=ribbon(20)
        known=np.zeros(len(v),bool);known[0]=True;known[-1]=True
        c=np.full((len(v),3),np.nan);c[0]=[1,0,0];c[-1]=[0,0,1]
        result,evidence=diffuse_colors(v,f,c,known,max_iterations=0)
        self.assertFalse(evidence['solver']['converged'])
        self.assertEqual(evidence['solver']['fallbackReason'],'iteration_budget_zero')
        self.assertEqual(evidence['harmonicVertices'],0)
        self.assertEqual(evidence['nearestGraphSeedFallbackVertices'],len(v)-2)
        self.assertTrue(all(tuple(row) in {(1.,0.,0.),(0.,0.,1.)} for row in result))

    def test_insufficient_cg_budget_does_not_claim_convergence(self):
        v,f=ribbon(80)
        known=np.zeros(len(v),bool);known[0]=True;known[-1]=True
        c=np.full((len(v),3),np.nan);c[0]=[1,.2,0];c[-1]=[0,.8,1]
        result,evidence=diffuse_colors(v,f,c,known,max_iterations=1,tolerance=1e-10)
        self.assertFalse(evidence['solver']['converged'])
        self.assertEqual(evidence['solver']['status'],'graph_seed_fallback')
        self.assertTrue(all(x['iterations']<=1 for x in evidence['solver']['channels']))
        self.assertTrue(np.isfinite(result).all())
        np.testing.assert_array_equal(result[known],c[known])

    def test_solver_exception_falls_back_without_color_or_geometry_corruption(self):
        v,f=ribbon()
        known=np.zeros(len(v),bool);known[0]=True
        c=np.full((len(v),3),np.nan);c[0]=[.4,.3,.2]
        with patch('color_diffusion.cg',side_effect=RuntimeError('deliberate solver failure')):
            result,evidence=diffuse_colors(v,f,c,known)
        np.testing.assert_array_equal(result,np.tile(c[0],(len(v),1)))
        self.assertFalse(evidence['solver']['converged'])
        self.assertEqual(evidence['solver']['fallbackReason'],'solver_exception')

    def test_isolated_vertex_and_no_observations_are_explicit(self):
        v,f=ribbon(2)
        v=np.concatenate((v,[[0,0,0]]))
        c=np.full((len(v),3),np.nan);known=np.zeros(len(v),bool)
        result,evidence=diffuse_colors(v,f,c,known,fallback_color=(.2,.2,.2))
        np.testing.assert_array_equal(result,np.full((len(v),3),.2))
        self.assertEqual(evidence['componentsWithoutObservations'],2)
        self.assertEqual(evidence['solver']['status'],'not_required')
        self.assertIsNone(evidence['solver']['converged'])

    def test_known_hdr_samples_are_preserved_without_global_clipping(self):
        v,f=ribbon(3)
        c=np.full((len(v),3),np.nan);known=np.zeros(len(v),bool)
        known[0]=known[-1]=True;c[0]=[-.1,.3,2];c[-1]=[.2,1.3,3]
        result,evidence=diffuse_colors(v,f,c,known)
        np.testing.assert_array_equal(result[known],c[known])
        self.assertGreater(result[-1,2],1)
        self.assertTrue(evidence['maximumPrincipleSatisfied'])

    def test_transfer_functions_are_separate_reversible_and_do_not_clip(self):
        encoded=np.array([-.2,0,.02,.04045,.18,.5,1,1.5])
        linear=srgb_to_linear(encoded)
        np.testing.assert_allclose(linear_to_srgb(linear),encoded,atol=3e-8)
        self.assertAlmostEqual(float(srgb_to_linear(.5)),.21404114048223255)
        self.assertGreater(linear[-1],1)
        self.assertLess(linear[0],0)

    def test_input_arrays_readonly_and_determinism(self):
        v,f=ribbon(6)
        known=np.zeros(len(v),bool);known[[0,-1]]=True
        c=np.full((len(v),3),np.nan);c[0]=[1,0,0];c[-1]=[0,0,1]
        originals=[x.copy() for x in (v,f,c,known)]
        for array in (v,f,c,known):array.flags.writeable=False
        first,evidence=diffuse_colors(v,f,c,known)
        second,_=diffuse_colors(v,f,c,known)
        np.testing.assert_array_equal(first,second)
        for array,original in zip((v,f,c,known),originals):np.testing.assert_array_equal(array,original)
        self.assertTrue(evidence['geometryUnchanged'])
        json.dumps(evidence,allow_nan=False)

    def test_invalid_anchors_topology_and_budgets_rejected(self):
        v,f=ribbon(2);c=np.zeros((len(v),3));known=np.zeros(len(v),bool)
        known[0]=True;c[0,0]=np.nan
        with self.assertRaisesRegex(ValueError,'NONFINITE_ANCHOR'):diffuse_colors(v,f,c,known)
        c[0,0]=0
        with self.assertRaisesRegex(ValueError,'INTEGER_FACES'):diffuse_colors(v,f.astype(float),c,known)
        with self.assertRaisesRegex(ValueError,'FACE_INDEX'):diffuse_colors(v,np.array([[0,1,100]]),c,known)
        with self.assertRaisesRegex(ValueError,'VERTEX_BUDGET'):diffuse_colors(v,f,c,known,max_vertices=1)
        with self.assertRaisesRegex(ValueError,'ITERATION_BUDGET'):diffuse_colors(v,f,c,known,max_iterations=-1)
        with self.assertRaisesRegex(ValueError,'BOOLEAN_KNOWN'):diffuse_colors(v,f,c,known.astype(int))

    def test_all_known_and_empty_inputs_need_no_solver(self):
        v,f=ribbon(2);c=np.ones((len(v),3));known=np.ones(len(v),bool)
        result,evidence=diffuse_colors(v,f,c,known)
        np.testing.assert_array_equal(result,c)
        self.assertEqual(evidence['solver']['status'],'not_required')
        result,evidence=diffuse_colors(np.empty((0,3)),np.empty((0,3),dtype=int),np.empty((0,3)),np.empty(0,dtype=bool))
        self.assertEqual(result.shape,(0,3))
        self.assertEqual(evidence['vertexCount'],0)


if __name__=='__main__':unittest.main(verbosity=2)
