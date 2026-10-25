"""Read-only, bounded triangle-mesh checks. No shape is repaired or inferred here.

Arrays are in one caller-defined coordinate frame and units. ``face_part_ids`` is
one explicit ID per face. ``parts`` maps those IDs to declarations; a tyre uses
{"role": "tyre", "center": [x,y,z], "axis": [x,y,z]}. A ground plane uses
{"normal": [x,y,z], "offset": d}, with normal.dot(point) + d >= 0 above ground.
The caller owns the accuracy/provenance of labels, coordinates and priors.
"""
from __future__ import annotations

import hashlib
import json
import math
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


def _mesh(vertices, faces):
    v = np.asarray(vertices, dtype=np.float64)
    raw = np.asarray(faces)
    if v.ndim != 2 or v.shape[1] != 3 or not np.isfinite(v).all():
        raise ValueError('MESH_VALIDATION_VERTICES')
    if raw.ndim != 2 or raw.shape[1] != 3 or raw.dtype.kind not in 'iu':
        raise ValueError('MESH_VALIDATION_TRIANGULAR_INTEGER_FACES')
    f = raw.astype(np.int64, copy=False)
    if len(f) and (f.min() < 0 or f.max() >= len(v)):
        raise ValueError('MESH_VALIDATION_FACE_INDEX')
    if len(v) > 2_000_000 or len(f) > 4_000_000:
        raise ValueError('MESH_VALIDATION_SIZE_LIMIT')
    return v, f


def _labels(face_part_ids, count):
    if face_part_ids is None:
        return None
    ids = np.asarray([str(x) for x in face_part_ids], dtype=object)
    if ids.ndim != 1 or len(ids) != count:
        raise ValueError('MESH_VALIDATION_PART_LABELS')
    return ids


def _budget(value):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 0:
        raise ValueError('MESH_VALIDATION_BUDGET')
    return int(value)


def _declarations(parts):
    if parts is None:
        return {}
    if not isinstance(parts, dict) or not all(isinstance(value, dict) for value in parts.values()):
        raise ValueError('MESH_VALIDATION_PART_DECLARATIONS')
    def native(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        raise TypeError('Unsupported declaration value')
    try:
        # Copy caller declarations and make the public report safely serializable.
        return json.loads(json.dumps({str(k): value for k, value in parts.items()}, default=native, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError('MESH_VALIDATION_PART_DECLARATIONS') from error


def _components(faces, count):
    used = np.unique(faces)
    if not len(used):
        return [], np.full(count, -1, dtype=int)
    local = np.searchsorted(used, faces)
    edges = np.concatenate((local[:, [0, 1]], local[:, [1, 2]], local[:, [2, 0]]))
    graph = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(len(used), len(used)))
    number, labels = connected_components(graph, directed=False)
    sizes = np.bincount(labels, minlength=number)
    full = np.full(count, -1, dtype=int)
    full[used] = labels
    return sorted(sizes.tolist(), reverse=True), full


def _topology(vertices, faces, tolerance):
    sizes, components = _components(faces, len(vertices))
    if not len(faces):
        return {'connectedComponents': 0, 'componentVertexCounts': [], 'componentCountsTruncated': False, 'isolatedVertices': len(vertices),
                'boundaryEdges': 0, 'nonmanifoldEdges': 0, 'inconsistentlyOrientedEdges': 0,
                'degenerateFaces': 0, 'sliverFaces': 0, 'duplicateFaces': 0,
                'minimumTriangleQuality': None, 'watertight': False}, components
    directed = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    edges = np.sort(directed, axis=1)
    _, inverse, counts = np.unique(edges, axis=0, return_inverse=True, return_counts=True)
    direction = np.where(directed[:, 0] < directed[:, 1], 1, -1)
    winding = np.bincount(inverse, weights=direction, minlength=len(counts))
    triangle = vertices[faces]
    area2 = np.linalg.norm(np.cross(triangle[:, 1] - triangle[:, 0], triangle[:, 2] - triangle[:, 0]), axis=1)
    edge2 = sum(np.sum((triangle[:, i] - triangle[:, (i + 1) % 3]) ** 2, axis=1) for i in range(3))
    # 1 for equilateral, approaches zero for a needle, independent of units.
    quality = 2 * np.sqrt(3) * area2 / np.maximum(edge2, np.finfo(float).tiny)
    degenerate = area2 <= tolerance * tolerance
    duplicate = len(faces) - len(np.unique(np.sort(faces, axis=1), axis=0))
    report = {'connectedComponents': len(sizes), 'componentVertexCounts': sizes[:128],
              'componentCountsTruncated': len(sizes) > 128,
              'isolatedVertices': int((components < 0).sum()), 'boundaryEdges': int((counts == 1).sum()),
              'nonmanifoldEdges': int((counts > 2).sum()),
              'inconsistentlyOrientedEdges': int(((counts == 2) & (winding != 0)).sum()),
              'degenerateFaces': int(degenerate.sum()), 'sliverFaces': int(((quality < .01) & ~degenerate).sum()),
              'duplicateFaces': int(duplicate), 'minimumTriangleQuality': float(quality.min()),
              'watertight': bool(np.all(counts == 2) and not degenerate.any() and not duplicate)}
    return report, components


def _triangles_intersect(a, b, epsilon):
    """Triangle SAT, including coplanar in-plane axes. Touch counts as contact."""
    ea = np.roll(a, -1, axis=0) - a
    eb = np.roll(b, -1, axis=0) - b
    na, nb = np.cross(ea[0], ea[1]), np.cross(eb[0], eb[1])
    axes = [na, nb]
    axes.extend(np.cross(x, y) for x in ea for y in eb)
    # Necessary when planes coincide; harmless additional separating axes otherwise.
    axes.extend(np.cross(na, x) for x in ea)
    axes.extend(np.cross(nb, x) for x in eb)
    for axis in axes:
        length = np.linalg.norm(axis)
        if length <= np.finfo(float).tiny:
            continue
        axis = axis / length
        pa, pb = a @ axis, b @ axis
        if pa.max() < pb.min() - epsilon or pb.max() < pa.min() - epsilon:
            return False
    return True


def _intersections(vertices, faces, ids, epsilon, max_pairs, max_broadphase):
    tri = vertices[faces]
    if not len(tri):
        return {'status': 'complete', 'budgetExhausted': False, 'testedTrianglePairs': 0, 'broadphasePairChecks': 0,
                'maxTrianglePairs': max_pairs, 'maxBroadphasePairs': max_broadphase,
                'detectedPairs': [], 'detectedPairCount': 0, 'excludedAdjacentPairs': 0,
                'degenerateFacesExcluded': 0, 'pairListTruncated': False, 'conclusion': 'empty_surface',
                'coverage': 'All nonadjacent nondegenerate triangle pairs.'}, set()
    lo, hi = tri.min(axis=1), tri.max(axis=1)
    area2 = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    good = area2 > epsilon * epsilon
    order = np.argsort(lo[:, 0], kind='stable')
    active, hits, colliding_parts = [], [], set()
    scanned = tested = adjacent = hit_count = 0
    exhausted = False
    for i in order:
        if not good[i]:
            continue
        active = [j for j in active if hi[j, 0] >= lo[i, 0] - epsilon]
        for j in active:
            if scanned >= max_broadphase:
                exhausted = True
                break
            scanned += 1
            if np.any(hi[j, 1:] < lo[i, 1:] - epsilon) or np.any(hi[i, 1:] < lo[j, 1:] - epsilon):
                continue
            if np.isin(faces[i], faces[j]).any():
                adjacent += 1
                continue
            if tested >= max_pairs:
                exhausted = True
                break
            tested += 1
            if _triangles_intersect(tri[i], tri[j], epsilon):
                hit_count += 1
                if len(hits) < 100:
                    hits.append([int(j), int(i)])
                if ids is not None and ids[i] != ids[j]:
                    colliding_parts.add(tuple(sorted((str(ids[i]), str(ids[j])))))
        if exhausted:
            break
        active.append(int(i))
    excluded = int((~good).sum())
    status = 'partial' if exhausted or excluded else 'complete'
    return {'status': status, 'budgetExhausted': exhausted, 'testedTrianglePairs': tested,
            'broadphasePairChecks': scanned, 'maxTrianglePairs': max_pairs, 'maxBroadphasePairs': max_broadphase,
            'detectedPairs': hits, 'detectedPairCount': hit_count, 'pairListTruncated': hit_count > len(hits),
            'excludedAdjacentPairs': adjacent, 'degenerateFacesExcluded': excluded,
            'coverage': 'Nonadjacent triangles only; shared-vertex contacts and excess overlap between adjacent faces are untested. '
                        'Detections include coplanar overlap and tangential contact; this is not a penetration-volume measurement.',
            'conclusion': 'intersections_or_contacts_detected' if hit_count else
                          ('none_detected_in_tested_scope' if status == 'complete' else 'unknown_outside_tested_pairs')}, colliding_parts


def _plane(ground_plane):
    if ground_plane is None:
        return None
    normal = np.asarray(ground_plane.get('normal'), dtype=float)
    offset = float(ground_plane.get('offset', 0))
    if normal.shape != (3,) or not np.isfinite(normal).all() or np.linalg.norm(normal) < 1e-12 or not math.isfinite(offset):
        raise ValueError('MESH_VALIDATION_GROUND_PLANE')
    length = np.linalg.norm(normal)
    return normal / length, offset / length


def _ground(vertices, faces, plane, tolerance):
    if plane is None or not len(faces):
        return {'status': 'unknown', 'reason': 'An explicit ground plane and nonempty part are required.'}
    distances = vertices @ plane[0] + plane[1]
    triangle_distances = distances[faces]
    referenced_distances = distances[np.unique(faces)]
    return {'status': 'complete', 'minimumSignedDistance': float(referenced_distances.min()),
            'penetratingVertices': int((referenced_distances < -tolerance).sum()),
            'crossingFaces': int(((triangle_distances.min(axis=1) < -tolerance) &
                                  (triangle_distances.max(axis=1) > tolerance)).sum()),
            'penetratesGround': bool((referenced_distances < -tolerance).any()), 'tolerance': tolerance,
            'scope': 'Exact vertex/linear-triangle test against the supplied plane; plane provenance is caller supplied.'}


def _tyre(vertices, faces, spec, tolerance):
    center = np.asarray(spec.get('center'), dtype=float)
    axis = np.array(spec.get('axis'), dtype=float, copy=True)
    if center.shape != (3,) or axis.shape != (3,) or not np.isfinite(center).all() or not np.isfinite(axis).all() or np.linalg.norm(axis) < 1e-12:
        return {'status': 'unknown', 'reason': 'A declared tyre needs explicit center and axle axis in the mesh coordinate frame.'}
    if not len(faces):
        return {'status': 'unknown', 'reason': 'No faces belong to the declared tyre.'}
    axis /= np.linalg.norm(axis)
    basis = np.eye(3)[np.argmin(np.abs(axis))]
    u = np.cross(axis, basis)
    u /= np.linalg.norm(u)
    w = np.cross(axis, u)
    relative = vertices - center
    projected = np.column_stack((relative @ u, relative @ w))
    radii = np.linalg.norm(projected, axis=1)
    outer_radius = float(np.percentile(radii, 95))
    if outer_radius <= tolerance:
        return {'status': 'unknown', 'reason': 'Declared axis has no measurable radial surface.'}
    # Follow actual outer-band edges, never bridge a missing arc using a point hull.
    edges = np.unique(np.sort(np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]])), axis=1), axis=0)
    edges = edges[(radii[edges] >= outer_radius * .8).all(axis=1)]
    intervals = []
    period = 2 * np.pi
    angular_tolerance = max(tolerance / outer_radius, 1e-12)
    angles = np.arctan2(projected[:, 1], projected[:, 0]) % (2 * np.pi)
    for a, b in edges:
        start = angles[a]
        delta = (angles[b] - start + np.pi) % (2 * np.pi) - np.pi
        # Edges crossing near the axle cannot support an outer circumference claim.
        if abs(delta) > np.pi / 2:
            continue
        lower = (start + min(0, delta)) % period
        upper = lower + abs(delta)
        intervals.append((lower, min(upper, period)))
        if upper > period:
            intervals.append((0, upper - period))
    merged = []
    for lower, upper in sorted(intervals):
        if merged and lower <= merged[-1][1] + angular_tolerance:
            merged[-1][1] = max(merged[-1][1], upper)
        else:
            merged.append([lower, upper])
    covered = min(period, sum(upper - lower for lower, upper in merged))
    gaps = ([merged[i+1][0] - merged[i][1] for i in range(len(merged)-1)] +
            [merged[0][0] + period - merged[-1][1]]) if merged else [period]
    longest = max(gaps)
    return {'status': 'complete', 'angularCoverageFraction': float(covered / period),
            'largestMissingArcDegrees': float(np.degrees(longest)), 'fullCircumference': bool(longest <= angular_tolerance),
            'outerRadius95': outer_radius, 'angularToleranceDegrees': float(np.degrees(angular_tolerance)),
            'scope': 'Projected outer-band mesh edges around the declared axle. This checks angular support, '
                     'not tread fidelity, circularity, thickness, watertightness, or photographic evidence.'}


def part_fingerprints(vertices, faces, face_part_ids):
    """Exact coordinate triangle hashes, insensitive to index/face order and winding.

    A change of triangulation changes the hash; no rounding hides small edits.
    Unreferenced vertices/material/UV/transform metadata are outside this contract.
    """
    v, f = _mesh(vertices, faces)
    ids = _labels(face_part_ids, len(f))
    if ids is None:
        raise ValueError('MESH_VALIDATION_PART_LABELS_REQUIRED')
    result = {}
    for part in sorted(set(ids)):
        triangles = v[f[ids == part]].copy()
        triangles[triangles == 0] = 0  # canonicalize signed zero only
        rows = []
        for triangle in triangles:
            triangle = triangle[np.lexsort((triangle[:, 2], triangle[:, 1], triangle[:, 0]))]
            rows.append(np.asarray(triangle, dtype='<f8').tobytes())
        digest = hashlib.sha256()
        for row in sorted(rows):
            digest.update(row)
        result[str(part)] = {'sha256': digest.hexdigest(), 'faceCount': len(triangles),
                             'contract': 'Exact unordered triangle coordinates; no tolerance, no UV/material metadata.'}
    return result


def _inside(point, triangles, tolerance):
    """Generalized winding for a closed consistently oriented triangle surface."""
    q = triangles - point
    length = np.linalg.norm(q, axis=2)
    if (length < tolerance).any():
        return None
    numerator = np.einsum('ij,ij->i', q[:, 0], np.cross(q[:, 1], q[:, 2]))
    denominator = (length.prod(axis=1) + np.einsum('ij,ij->i', q[:, 0], q[:, 1]) * length[:, 2] +
                   np.einsum('ij,ij->i', q[:, 1], q[:, 2]) * length[:, 0] +
                   np.einsum('ij,ij->i', q[:, 2], q[:, 0]) * length[:, 1])
    winding = float(np.sum(2 * np.arctan2(numerator, denominator)) / (4 * np.pi))
    if abs(abs(winding) - .5) < .05:
        return None
    return abs(winding) > .5


def _part_collisions(vertices, faces, ids, part_reports, contacts, intersection_report, epsilon, max_tests):
    if ids is None:
        return {'status': 'unknown', 'reason': 'Explicit per-face part IDs are required.', 'pairs': []}
    names = sorted(set(ids))
    records = []
    tests = pair_checks = 0
    truncated = False
    for ai, a in enumerate(names):
        af = faces[ids == a]
        av = vertices[np.unique(af)]
        for b in names[ai + 1:]:
            if pair_checks >= 4096:
                truncated = True
                break
            pair_checks += 1
            bf = faces[ids == b]
            bv = vertices[np.unique(bf)]
            if np.any(av.max(axis=0) < bv.min(axis=0) - epsilon) or np.any(bv.max(axis=0) < av.min(axis=0) - epsilon):
                records.append({'parts': [a, b], 'status': 'disjoint_aabbs'})
                continue
            if (a, b) in contacts:
                records.append({'parts': [a, b], 'status': 'surface_intersection_or_contact_detected'})
                continue
            contained = False
            unknown = intersection_report['status'] != 'complete'
            for source, target, source_faces, target_faces in ((a, b, af, bf), (b, a, bf, af)):
                target_topology = part_reports[target]['topology']
                if not target_topology['watertight'] or target_topology['inconsistentlyOrientedEdges']:
                    unknown = True
                    continue
                _, components = _components(source_faces, len(vertices))
                representative = np.unique(components[components >= 0], return_index=True)[1]
                used = np.flatnonzero(components >= 0)
                for index in used[representative]:
                    if tests + len(target_faces) > max_tests:
                        unknown = True
                        break
                    inside = _inside(vertices[index], vertices[target_faces], epsilon)
                    tests += len(target_faces)
                    unknown |= inside is None
                    contained |= inside is True
            records.append({'parts': [a, b], 'status': 'containment_detected' if contained else
                            ('unknown' if unknown else 'no_overlap_detected_in_tested_scope')})
        if truncated:
            break
    return {'status': 'partial' if truncated or any(x['status'] == 'unknown' for x in records) else 'complete',
            'pairs': records, 'partPairChecks': pair_checks, 'pairLimit': 4096,
            'containmentPointTriangleTests': tests, 'maxContainmentPointTriangleTests': max_tests,
            'scope': 'AABB separation, nonadjacent triangle surface contacts, and component representative winding tests '
                     'against closed consistently oriented parts. Adjacent overlap, ambiguous boundary contacts, self-overlapping '
                     'solids and penetration volume are outside the contract. Open parts yield unknown containment.'}


def validate_mesh(vertices, faces, *, face_part_ids=None, parts=None, ground_plane=None,
                  tolerance=None, max_intersection_pairs=20000, max_broadphase_pairs=200000,
                  max_containment_tests=200000):
    """Return JSON-serializable topology, intersections, declared part and plane checks.

    The function never mutates input arrays. ``status=complete`` always describes
    the documented scope, never recovery of hidden geometry or real-world truth.
    """
    v, f = _mesh(vertices, faces)
    ids = _labels(face_part_ids, len(f))
    max_pairs, max_broadphase, containment_budget = map(_budget, (max_intersection_pairs, max_broadphase_pairs, max_containment_tests))
    scale = float(np.linalg.norm(np.ptp(v, axis=0))) if len(v) else 0
    epsilon = max(scale * 1e-9, np.finfo(float).eps * max(scale, 1) * 16) if tolerance is None else float(tolerance)
    if not math.isfinite(epsilon) or epsilon <= 0:
        raise ValueError('MESH_VALIDATION_TOLERANCE')
    plane = _plane(ground_plane)
    topology, _ = _topology(v, f, epsilon)
    intersections, contacts = _intersections(v, f, ids, epsilon, max_pairs, max_broadphase)
    declarations = _declarations(parts)
    reports = {}
    names = sorted(set(ids) | set(declarations)) if ids is not None else sorted(declarations)
    for name in names:
        subset = f[ids == name] if ids is not None else np.empty((0, 3), dtype=int)
        used = np.unique(subset)
        local_v = v[used]
        local_f = np.searchsorted(used, subset)
        subtopology, _ = _topology(local_v, local_f, epsilon)
        declaration = declarations.get(name, {})
        reports[name] = {'faceCount': len(subset), 'vertexCount': len(used), 'declaration': declaration,
                         'topology': subtopology, 'ground': _ground(local_v, local_f, plane, epsilon)}
        if declaration.get('role', declaration.get('type')) in ('tyre', 'tire', 'wheel'):
            reports[name]['circumference'] = _tyre(local_v, local_f, declaration, epsilon)
    return {'schemaVersion': 1, 'vertexCount': len(v), 'faceCount': len(f), 'units': 'caller_supplied',
            'tolerance': epsilon, 'topology': topology, 'selfIntersections': intersections,
            'ground': _ground(v, f, plane, epsilon), 'parts': reports,
            'partCollisions': _part_collisions(v, f, ids, reports, contacts, intersections, epsilon, containment_budget),
            'partFingerprints': part_fingerprints(v, f, ids) if ids is not None else {},
            'limits': ['Part identity, tyre axes/centers and ground plane must come from explicit caller declarations.',
                       'Topology uses shared vertex indices. Coincident unwelded seams remain boundaries; no welding or repair is performed.',
                       'No photograph, hidden shape, semantic correctness, or source-prior fidelity is established by these checks.']}


def _samples(vertices, faces, maximum):
    if not len(faces) or maximum == 0:
        return np.empty((0, 3)), {'sampledFaces': 0, 'totalFaces': len(faces)}
    triangles = vertices[faces]
    area = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1)
    if not area.sum():
        return np.empty((0, 3)), {'sampledFaces': 0, 'totalFaces': len(faces)}
    # Include extreme vertices: a small, remote defect should not disappear behind area weighting.
    referenced = vertices[np.unique(faces)]
    extremes = np.unique(np.r_[np.argmin(referenced, axis=0), np.argmax(referenced, axis=0)])
    extreme_points = referenced[extremes[:maximum]]
    count = maximum - len(extreme_points)
    if count:
        indices = np.searchsorted(np.cumsum(area), (np.arange(count) + .5) / count * area.sum())
        # Deterministic interior samples; no random state or caller-array mutation.
        u = np.sqrt(((np.arange(count) + 1) * .6180339887498949) % 1)
        w = ((np.arange(count) + 1) * .4142135623730951) % 1
        bary = np.column_stack((1 - u, u * (1 - w), u * w))
        points = np.einsum('ij,ijk->ik', bary, triangles[indices])
        points = np.concatenate((extreme_points, points))
    else:
        indices = np.empty(0, dtype=int)
        points = extreme_points
    return points, {'sampledFaces': len(np.unique(indices)), 'totalFaces': len(faces), 'sampleCount': len(points)}


def _point_distances(points, triangles):
    """Exact nearest point-to-triangle distances for the supplied finite sample."""
    distances = np.full(len(points), np.inf)
    for start in range(0, len(triangles), 256):
        t = triangles[start:start + 256]
        a, b, c = t[:, 0], t[:, 1], t[:, 2]
        ab, ac = b - a, c - a
        normal = np.cross(ab, ac)
        n2 = np.einsum('ij,ij->i', normal, normal)
        for pi, point in enumerate(points):
            offset = point - a
            height = np.einsum('ij,ij->i', offset, normal)
            projection = point - (height / np.maximum(n2, np.finfo(float).tiny))[:, None] * normal
            ap = projection - a
            # Cross-product barycentrics avoid subtracting nearly equal dot
            # products on long, thin triangles.
            usable = n2 > np.finfo(float).tiny
            denom = np.where(usable, n2, 1)
            s = np.einsum('ij,ij->i', np.cross(ap, ac), normal) / denom
            u = np.einsum('ij,ij->i', np.cross(ab, ap), normal) / denom
            inside = usable & (s >= 0) & (u >= 0) & (s + u <= 1)
            distance2 = np.where(inside, height * height / np.maximum(n2, np.finfo(float).tiny), np.inf)
            for x, y in ((a, b), (b, c), (c, a)):
                edge = y - x
                fraction = np.clip(np.einsum('ij,ij->i', point - x, edge) /
                                   np.maximum(np.einsum('ij,ij->i', edge, edge), np.finfo(float).tiny), 0, 1)
                delta = point - (x + fraction[:, None] * edge)
                distance2 = np.minimum(distance2, np.einsum('ij,ij->i', delta, delta))
            distances[pi] = min(distances[pi], float(np.sqrt(max(0, distance2.min()))))
    return distances


def compare_meshes(before_vertices, before_faces, after_vertices, after_faces, *,
                   before_part_ids=None, after_part_ids=None, protected_part_ids=None,
                   max_samples=1024, max_point_triangle_tests=2000000):
    """Measured distances in the existing common frame; never aligns away an edit.

    Surface distances are exact for deterministic sample points, not an exact
    continuous Hausdorff distance. The reported maximum is a sampled lower bound.
    """
    av, af = _mesh(before_vertices, before_faces)
    bv, bf = _mesh(after_vertices, after_faces)
    samples, budget = _budget(max_samples), _budget(max_point_triangle_tests)
    same_topology = av.shape == bv.shape and np.array_equal(af, bf)
    result = {'sameIndexedTopology': same_topology, 'exactGeometryEqual': bool(same_topology and np.array_equal(av, bv)),
              'coordinateFrame': 'Caller common frame; no alignment or rescaling performed.'}
    if same_topology:
        displacement = np.linalg.norm(bv - av, axis=1)
        result['correspondingVertices'] = {'count': len(av), 'changed': int((displacement > 0).sum()),
                                            'maximumDistance': float(displacement.max()) if len(av) else 0,
                                            'rmsDistance': float(np.sqrt(np.mean(displacement ** 2))) if len(av) else 0}
    # Both directions receive a fair independent half of the budget.
    directional = []
    for source_v, source_f, target_v, target_f in ((av, af, bv, bf), (bv, bf, av, af)):
        allowed = min(samples, budget // (2 * max(len(target_f), 1)))
        points, coverage = _samples(source_v, source_f, allowed)
        if not len(points) or not len(target_f):
            directional.append({'status': 'unknown', 'reason': 'Empty surface or point-triangle budget too small.', **coverage})
            continue
        distance = _point_distances(points, target_v[target_f])
        directional.append({'status': 'sampled', 'meanDistance': float(distance.mean()),
                            'rmsDistance': float(np.sqrt(np.mean(distance ** 2))),
                            'maximumSampleDistance': float(distance.max()),
                            'pointTriangleTests': int(len(points) * len(target_f)), **coverage})
    result['surfaceDistance'] = {'beforeToAfter': directional[0], 'afterToBefore': directional[1],
                                 'status': 'sampled' if all(x['status'] == 'sampled' for x in directional) else 'unknown',
                                 'continuousHausdorffDistance': None,
                                 'scope': 'Exact distances for sampled surface points and extreme vertices. '
                                          'Small unsampled defects may be missed; no full-surface upper bound is claimed.'}
    result['protectedParts'] = {}
    if protected_part_ids:
        if before_part_ids is None or after_part_ids is None:
            result['protectedParts'] = {str(x): {'status': 'unknown', 'reason': 'Both per-face part label arrays are required.'}
                                        for x in protected_part_ids}
        else:
            ah = part_fingerprints(av, af, before_part_ids)
            bh = part_fingerprints(bv, bf, after_part_ids)
            result['protectedParts'] = {str(x): {'status': 'unchanged' if str(x) in ah and ah.get(str(x)) == bh.get(str(x)) else
                                                        ('missing' if str(x) not in ah or str(x) not in bh else 'changed'),
                                                 'before': ah.get(str(x)), 'after': bh.get(str(x))} for x in protected_part_ids}
    return result
