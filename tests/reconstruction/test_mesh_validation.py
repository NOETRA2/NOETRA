"""Adversarial independent fixtures for read-only geometric audit contracts."""
import json
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'packages' / 'reconstruction' / 'python'))
from mesh_validation import validate_mesh, compare_meshes, part_fingerprints


def cube(center=(0, 0, 0), scale=1):
    vertices = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                         [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]], float) * scale + center
    faces = np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7], [0,1,5],[0,5,4],
                      [1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]])
    return vertices, faces


def combine(*meshes):
    vertices, faces, offset = [], [], 0
    for v, f in meshes:
        vertices.append(v)
        faces.append(f + offset)
        offset += len(v)
    return np.concatenate(vertices), np.concatenate(faces)


def ring(start=0, end=2*np.pi, segments=48):
    # Closed outer cylindrical band, or a literal cut band (not a circle hull).
    full = end - start >= 2*np.pi - 1e-10
    angles = np.linspace(start, end, segments, endpoint=not full)
    vertices = np.array([[np.cos(a), np.sin(a), z] for z in [-.2, .2] for a in angles])
    faces = []
    for i in range(segments if full else segments-1):
        j = (i+1) % segments
        faces.extend([[i,j,j+segments],[i,j+segments,i+segments]])
    return vertices, np.array(faces)


class MeshValidationTests(unittest.TestCase):
    def test_closed_cube_and_detached_debris_are_different(self):
        v, f = cube()
        clean = validate_mesh(v, f)
        self.assertTrue(clean['topology']['watertight'])
        self.assertEqual(clean['topology']['connectedComponents'], 1)
        self.assertEqual(clean['selfIntersections']['detectedPairCount'], 0)
        debris_v, debris_f = combine((v, f), cube((4, 4, 4), .01))
        self.assertEqual(validate_mesh(debris_v, debris_f)['topology']['connectedComponents'], 2)

    def test_open_cube_and_three_faces_on_one_edge(self):
        v, f = cube()
        self.assertEqual(validate_mesh(v, f[:-1])['topology']['boundaryEdges'], 3)
        report = validate_mesh(v, np.concatenate((f, f[:1])))['topology']
        self.assertEqual(report['nonmanifoldEdges'], 3)
        self.assertEqual(report['duplicateFaces'], 1)
        self.assertFalse(report['watertight'])

    def test_degenerate_needle_and_flipped_winding(self):
        v = np.array([[0,0,0],[1,0,0],[2,0,0],[0,1e-6,0]], float)
        f = np.array([[0,1,2],[0,1,3]])
        report = validate_mesh(v, f)
        self.assertEqual(report['topology']['degenerateFaces'], 1)
        self.assertEqual(report['topology']['sliverFaces'], 1)
        self.assertEqual(report['selfIntersections']['status'], 'partial')
        v, f = cube()
        f[0] = f[0, ::-1]
        self.assertEqual(validate_mesh(v, f)['topology']['inconsistentlyOrientedEdges'], 3)

    def test_crossing_triangles_without_shared_indices(self):
        v = np.array([[-1,-1,0],[1,-1,0],[0,1,0], [0,-.5,-1],[0,-.5,1],[0,.5,0]], float)
        report = validate_mesh(v, np.array([[0,1,2],[3,4,5]]))['selfIntersections']
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['detectedPairCount'], 1)

    def test_coplanar_overlap_and_aabb_false_positive(self):
        v = np.array([[0,0,0],[2,0,0],[0,2,0], [.2,.2,0],[.8,.2,0],[.2,.8,0]])
        faces = np.array([[0,1,2],[3,4,5]])
        self.assertEqual(validate_mesh(v, faces)['selfIntersections']['detectedPairCount'], 1)
        v[3:] = [[1.2,1.2,0],[2,1.2,0],[1.2,2,0]]
        self.assertEqual(validate_mesh(v, faces)['selfIntersections']['detectedPairCount'], 0)

    def test_budget_exhaustion_is_unknown_not_clean(self):
        v, f = combine(cube(), cube((.5, .5, .5)))
        report = validate_mesh(v, f, max_intersection_pairs=0)['selfIntersections']
        self.assertEqual(report['status'], 'partial')
        self.assertTrue(report['budgetExhausted'])
        self.assertEqual(report['conclusion'], 'unknown_outside_tested_pairs')

    def test_shared_vertex_overlap_is_explicitly_outside_scope(self):
        v = np.array([[0,0,0],[2,0,0],[0,2,0],[1,0,0],[0,1,0]], float)
        report = validate_mesh(v, np.array([[0,1,2],[0,3,4]]))['selfIntersections']
        self.assertEqual(report['excludedAdjacentPairs'], 1)
        self.assertIn('untested', report['coverage'])
        self.assertNotIn('no_intersections', report['conclusion'])

    def test_full_tyre_and_missing_lower_half(self):
        spec = {'rubber': {'role': 'tyre', 'axis': [0,0,1], 'center': [0,0,0]}}
        v, f = ring()
        report = validate_mesh(v, f, face_part_ids=['rubber']*len(f), parts=spec,
                               ground_plane={'normal': [0,1,0], 'offset': 1})
        tyre = report['parts']['rubber']
        self.assertTrue(tyre['circumference']['fullCircumference'])
        self.assertFalse(tyre['ground']['penetratesGround'])
        v, f = ring(0, np.pi)
        report = validate_mesh(v, f, face_part_ids=['rubber']*len(f), parts=spec)
        self.assertFalse(report['parts']['rubber']['circumference']['fullCircumference'])
        self.assertGreaterEqual(report['parts']['rubber']['circumference']['largestMissingArcDegrees'], 175)

    def test_ground_penetration_and_missing_wheel_axis(self):
        v, f = cube()
        report = validate_mesh(v, f, face_part_ids=['arbitrary-wheel']*len(f),
                               parts={'arbitrary-wheel': {'role': 'wheel'}},
                               ground_plane={'normal': [0,0,2], 'offset': 1})
        self.assertTrue(report['ground']['penetratesGround'])
        self.assertAlmostEqual(report['ground']['minimumSignedDistance'], -.5)
        self.assertEqual(report['parts']['arbitrary-wheel']['circumference']['status'], 'unknown')

    def test_subdegree_tyre_slit_is_not_rounded_to_full_circle(self):
        v, f = ring(0, 2*np.pi - np.radians(.2), segments=96)
        report = validate_mesh(v,f,face_part_ids=['tyre']*len(f),
                               parts={'tyre':{'role':'tyre','axis':[0,0,1],'center':[0,0,0]}})
        circumference = report['parts']['tyre']['circumference']
        self.assertFalse(circumference['fullCircumference'])
        self.assertAlmostEqual(circumference['largestMissingArcDegrees'], .2, places=6)

    def test_distinct_parts_surface_overlap_and_containment(self):
        v, f = combine(cube(), cube((1,1,1)))
        ids = ['shell']*12 + ['insert']*12
        report = validate_mesh(v, f, face_part_ids=ids)
        self.assertEqual(report['partCollisions']['pairs'][0]['status'], 'surface_intersection_or_contact_detected')
        v, f = combine(cube(scale=2), cube(scale=.1))
        report = validate_mesh(v, f, face_part_ids=ids)
        self.assertEqual(report['partCollisions']['pairs'][0]['status'], 'containment_detected')
        v, f = combine(cube(), cube((4,4,4)))
        self.assertEqual(validate_mesh(v, f, face_part_ids=ids)['partCollisions']['pairs'][0]['status'], 'disjoint_aabbs')

    def test_open_part_containment_unknown_and_budget_limited(self):
        a, af = cube(scale=2)
        b, bf = cube(scale=.1)
        v, f = combine((a, af[:-1]), (b, bf[:-1]))
        ids = ['a']*11 + ['b']*11
        self.assertEqual(validate_mesh(v, f, face_part_ids=ids)['partCollisions']['pairs'][0]['status'], 'unknown')
        v, f = combine(cube(scale=2), cube(scale=.1))
        report = validate_mesh(v, f, face_part_ids=['a']*12 + ['b']*12, max_containment_tests=0)
        self.assertEqual(report['partCollisions']['pairs'][0]['status'], 'unknown')

    def test_surface_difference_uses_triangle_distance_not_vertex_distance(self):
        v, f = cube()
        shifted = v + [0,0,3]
        report = compare_meshes(v, f, shifted, f, max_samples=128)
        self.assertAlmostEqual(report['correspondingVertices']['maximumDistance'], 3)
        self.assertAlmostEqual(report['surfaceDistance']['beforeToAfter']['maximumSampleDistance'], 3)
        self.assertGreater(report['surfaceDistance']['beforeToAfter']['meanDistance'], 1)
        self.assertIsNone(report['surfaceDistance']['continuousHausdorffDistance'])
        # Same planar surface represented with a center vertex and four triangles.
        square = np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]], float)
        first = np.array([[0,1,2],[0,2,3]])
        subdivided = np.concatenate((square, [[.5,.5,0]]))
        second = np.array([[0,1,4],[1,2,4],[2,3,4],[3,0,4]])
        report = compare_meshes(square, first, subdivided, second, max_samples=64)
        self.assertFalse(report['sameIndexedTopology'])
        self.assertLess(report['surfaceDistance']['afterToBefore']['maximumSampleDistance'], 1e-12)

    def test_small_remote_spike_is_sampled_and_empty_budget_unknown(self):
        v, f = cube()
        damaged = v.copy()
        damaged[6, 2] += 10
        report = compare_meshes(v, f, damaged, f, max_samples=32)
        self.assertGreater(report['surfaceDistance']['afterToBefore']['maximumSampleDistance'], 9)
        unknown = compare_meshes(v, f, damaged, f, max_point_triangle_tests=1)
        self.assertEqual(unknown['surfaceDistance']['status'], 'unknown')

    def test_protected_part_hash_reindexing_and_single_vertex_change(self):
        v, f = combine(cube(), cube((4,0,0)))
        ids = ['protected']*12 + ['editable']*12
        changed = v.copy()
        changed[8:, 1] += .25
        report = compare_meshes(v, f, changed, f, before_part_ids=ids, after_part_ids=ids,
                                protected_part_ids=['protected','editable','missing'], max_samples=16)
        self.assertEqual(report['protectedParts']['protected']['status'], 'unchanged')
        self.assertEqual(report['protectedParts']['editable']['status'], 'changed')
        self.assertEqual(report['protectedParts']['missing']['status'], 'missing')
        order = np.arange(len(v))[::-1]
        inverse = np.argsort(order)
        reordered = part_fingerprints(v[order], inverse[f[::-1, ::-1]], ids[::-1])
        self.assertEqual(part_fingerprints(v, f, ids), reordered)
        changed[0,0] = np.nextafter(changed[0,0], 2)
        self.assertNotEqual(part_fingerprints(v,f,ids)['protected'], part_fingerprints(changed,f,ids)['protected'])

    def test_read_only_and_json_serializable(self):
        v, f = ring()
        axis = np.array([0.,0.,2.])
        spec = {'ring': {'role': 'tyre', 'axis': axis, 'center': [0,0,0]}}
        vc, fc = v.copy(), f.copy()
        v.flags.writeable = False
        f.flags.writeable = False
        report = validate_mesh(v, f, face_part_ids=['ring']*len(f), parts=spec)
        json.dumps(report, allow_nan=False)
        np.testing.assert_array_equal(v, vc)
        np.testing.assert_array_equal(f, fc)
        np.testing.assert_array_equal(axis, [0,0,2])
        json.dumps(compare_meshes(v,f,v,f,max_samples=16), allow_nan=False)

    def test_unreferenced_outlier_is_not_a_surface_sample(self):
        v, f = cube()
        isolated = np.concatenate((v, [[100,100,100]]))
        report = compare_meshes(v,f,isolated,f,max_samples=32)
        self.assertLess(report['surfaceDistance']['afterToBefore']['maximumSampleDistance'], 1e-12)
        self.assertEqual(validate_mesh(isolated,f)['topology']['isolatedVertices'], 1)

    def test_invalid_inputs_rejected_without_silent_coercion(self):
        v, f = cube()
        with self.assertRaisesRegex(ValueError, 'INTEGER_FACES'):
            validate_mesh(v, f.astype(float))
        with self.assertRaisesRegex(ValueError, 'FACE_INDEX'):
            validate_mesh(v, np.array([[0,1,100]]))
        with self.assertRaisesRegex(ValueError, 'VERTICES'):
            validate_mesh([[np.nan,0,0]], np.empty((0,3), dtype=int))
        with self.assertRaisesRegex(ValueError, 'PART_LABELS'):
            validate_mesh(v, f, face_part_ids=['bad'])
        with self.assertRaisesRegex(ValueError, 'BUDGET'):
            validate_mesh(v, f, max_intersection_pairs=-1)

    def test_empty_mesh_has_no_solid_or_surface_claim(self):
        v = np.empty((0,3), dtype=float)
        f = np.empty((0,3), dtype=int)
        self.assertFalse(validate_mesh(v,f)['topology']['watertight'])
        self.assertEqual(compare_meshes(v,f,v,f)['surfaceDistance']['status'], 'unknown')


if __name__ == '__main__':
    unittest.main(verbosity=2)
