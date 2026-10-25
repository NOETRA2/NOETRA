"""Read-only Dirichlet color diffusion on indexed mesh adjacency.

Pass linear RGB samples and an explicit known mask. No color-space conversion,
Euclidean neighbor search, geometry repair, UV change, or mesh welding occurs.
Coincident vertices on disconnected surfaces therefore do not exchange color.
"""
from __future__ import annotations

from collections import deque
import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import cg


HARD_MAX_VERTICES = 200_000
HARD_MAX_FACES = 1_200_000


def _finite_colors(values):
    result = np.asarray(values, dtype=np.float64)
    if not np.isfinite(result).all():
        raise ValueError('COLOR_DIFFUSION_NONFINITE_COLOR')
    return result


def srgb_to_linear(values):
    """IEC sRGB transfer, without clipping or changing alpha/geometry implicitly.

    Input must contain RGB channel values only. Finite extended values are
    supported using the conventional linear branch below the sRGB threshold.
    """
    values = _finite_colors(values)
    result = np.empty_like(values)
    low = values <= .04045
    result[low] = values[low] / 12.92
    result[~low] = ((values[~low] + .055) / 1.055) ** 2.4
    return result


def linear_to_srgb(values):
    """Encode linear RGB with the sRGB transfer; no clipping is performed."""
    values = _finite_colors(values)
    result = np.empty_like(values)
    low = values <= .0031308
    result[low] = 12.92 * values[low]
    result[~low] = 1.055 * values[~low] ** (1 / 2.4) - .055
    return result


def _inputs(vertices, faces, colors, known, max_vertices):
    if isinstance(max_vertices, bool) or not isinstance(max_vertices, (int, np.integer)) or not 0 <= max_vertices <= HARD_MAX_VERTICES:
        raise ValueError('COLOR_DIFFUSION_VERTEX_BUDGET')
    v = np.asarray(vertices, dtype=np.float64)
    raw = np.asarray(faces)
    c = np.asarray(colors, dtype=np.float64)
    k = np.asarray(known)
    if v.ndim != 2 or v.shape[1] != 3 or not np.isfinite(v).all():
        raise ValueError('COLOR_DIFFUSION_VERTICES')
    if len(v) > max_vertices:
        raise ValueError('COLOR_DIFFUSION_VERTEX_BUDGET')
    if raw.ndim != 2 or raw.shape[1] != 3 or raw.dtype.kind not in 'iu':
        raise ValueError('COLOR_DIFFUSION_TRIANGULAR_INTEGER_FACES')
    f = raw.astype(np.int64, copy=False)
    if len(f) > HARD_MAX_FACES:
        raise ValueError('COLOR_DIFFUSION_FACE_BUDGET')
    if len(f) and (f.min() < 0 or f.max() >= len(v)):
        raise ValueError('COLOR_DIFFUSION_FACE_INDEX')
    if c.shape != (len(v), 3):
        raise ValueError('COLOR_DIFFUSION_RGB_SHAPE')
    if k.shape != (len(v),) or k.dtype.kind != 'b':
        raise ValueError('COLOR_DIFFUSION_BOOLEAN_KNOWN_MASK')
    if not np.isfinite(c[k]).all():
        raise ValueError('COLOR_DIFFUSION_NONFINITE_ANCHOR')
    return v, f, c, k


def _adjacency(faces, count):
    edges = np.concatenate((faces[:, [0,1]], faces[:, [1,2]], faces[:, [2,0]]))
    edges = np.unique(np.sort(edges, axis=1), axis=0)
    edges = edges[edges[:,0] != edges[:,1]]
    rows = np.r_[edges[:,0], edges[:,1]]
    columns = np.r_[edges[:,1], edges[:,0]]
    graph = coo_matrix((np.ones(len(rows), dtype=float), (rows, columns)), shape=(count,count)).tocsr()
    graph.sort_indices()
    return graph, len(edges)


def _nearest_seed_on_graph(graph, known):
    """Deterministic multi-source BFS. Ties follow ascending seed/vertex order."""
    owner = np.full(len(known), -1, dtype=np.int64)
    seeds = np.flatnonzero(known)
    owner[seeds] = seeds
    queue = deque(seeds.tolist())
    while queue:
        vertex = queue.popleft()
        for neighbor in graph.indices[graph.indptr[vertex]:graph.indptr[vertex+1]]:
            if owner[neighbor] < 0:
                owner[neighbor] = owner[vertex]
                queue.append(int(neighbor))
    return owner


def diffuse_colors(vertices, faces, colors, known, *, max_iterations=400,
                   tolerance=1e-7, max_vertices=HARD_MAX_VERTICES,
                   fallback_color=(.18,.18,.18)):
    """Fill unknown linear RGB by the uniform positive mesh-graph Laplacian.

    Known RGB values are exact Dirichlet anchors. The solve has at most three CG
    runs, each bounded by max_iterations, with diagonal preconditioning and an
    independent residual check. A failed/budget-exhausted solve uses nearest
    known seeds by *mesh-edge hop distance*, never 3D Euclidean distance. An
    entirely unobserved component uses the explicit fallback_color. These two
    fallbacks are disclosed and are not reported as converged harmonic fills.

    Returns (new_float64_rgb, JSON_serializable_evidence). Unknown input RGB can
    be NaN placeholders; only finite, explicitly known samples constrain color.
    """
    v, f, c, k = _inputs(vertices, faces, colors, known, max_vertices)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, (int, np.integer)) or not 0 <= max_iterations <= 10_000:
        raise ValueError('COLOR_DIFFUSION_ITERATION_BUDGET')
    tolerance = float(tolerance)
    if not np.isfinite(tolerance) or not 1e-12 <= tolerance <= .1:
        raise ValueError('COLOR_DIFFUSION_TOLERANCE')
    fallback = _finite_colors(fallback_color)
    if fallback.shape != (3,):
        raise ValueError('COLOR_DIFFUSION_FALLBACK_RGB')
    graph, edge_count = _adjacency(f, len(v))
    if len(v):
        component_count, labels = connected_components(graph, directed=False)
    else:
        component_count, labels = 0, np.empty(0, dtype=int)
    seed_counts = np.bincount(labels[k], minlength=component_count)
    observed_component = seed_counts[labels] > 0
    solve_mask = ~k & observed_component
    no_observations = ~observed_component
    owner = _nearest_seed_on_graph(graph, k)
    result = np.broadcast_to(fallback, c.shape).copy()
    reached = owner >= 0
    result[reached] = c[owner[reached]]
    result[k] = c[k]
    unknown_indices = np.flatnonzero(solve_mask)
    channel_reports = []
    convergence = None
    reason = None
    clipped_values = 0
    if len(unknown_indices):
        degree = np.asarray(graph.sum(axis=1)).ravel()
        matrix = (diags(degree[solve_mask]) - graph[solve_mask][:,solve_mask]).tocsr()
        rhs = graph[solve_mask][:,k] @ c[k]
        preconditioner = diags(1 / degree[solve_mask]).tocsr()
        candidate = result[solve_mask].copy()
        convergence = True
        if max_iterations == 0:
            convergence = False
            reason = 'iteration_budget_zero'
        else:
            for channel in range(3):
                iterations = [0]
                def count_iteration(_):
                    iterations[0] += 1
                try:
                    solution, info = cg(matrix, rhs[:,channel], x0=candidate[:,channel],
                                        M=preconditioner, rtol=tolerance, atol=1e-12,
                                        maxiter=int(max_iterations), callback=count_iteration)
                    finite = bool(np.isfinite(solution).all())
                    residual = float(np.linalg.norm(matrix @ solution-rhs[:,channel])) if finite else None
                    bound = max(tolerance * float(np.linalg.norm(rhs[:,channel])), 1e-12)
                    passed = bool(info == 0 and finite and residual <= bound * 1.01)
                    channel_reports.append({'channel':channel,'iterations':iterations[0],'scipyInfo':int(info),
                                            'converged':passed,'residualL2':residual,'residualBound':bound})
                    if passed:
                        candidate[:,channel] = solution
                    else:
                        convergence = False
                        reason = ('nonfinite_solution' if not finite else 'cg_budget_exhausted' if info > 0 else
                                  'cg_breakdown' if info < 0 else 'residual_check_failed')
                except Exception as error:
                    convergence = False
                    reason = 'solver_exception'
                    channel_reports.append({'channel':channel,'iterations':iterations[0],'converged':False,
                                            'error':type(error).__name__+': '+str(error)[:200]})
        if convergence:
            # Positive edge weights imply the component-wise maximum principle.
            lower = np.full((component_count,3), np.inf)
            upper = np.full((component_count,3), -np.inf)
            np.minimum.at(lower, labels[k], c[k])
            np.maximum.at(upper, labels[k], c[k])
            clamped = np.clip(candidate, lower[labels[solve_mask]], upper[labels[solve_mask]])
            clipped_values = int((clamped != candidate).sum())
            # Enforcing the maximum principle must not invalidate the advertised
            # solve tolerance. Check the actual final candidate, not just CG's
            # pre-clamp iterate.
            final_residuals = np.linalg.norm(matrix @ clamped-rhs, axis=0)
            for channel, report in enumerate(channel_reports):
                report['finalResidualL2'] = float(final_residuals[channel])
                report['finalResidualPassed'] = bool(final_residuals[channel] <= report['residualBound'] * 1.01)
            if all(report['finalResidualPassed'] for report in channel_reports):
                result[solve_mask] = clamped
            else:
                convergence = False
                reason = 'maximum_principle_clamp_residual_check_failed'
                clipped_values = 0
    # Assign anchors last, so no floating operation or clamp can change them.
    result[k] = c[k]
    if not np.isfinite(result).all():
        raise ValueError('COLOR_DIFFUSION_INTERNAL_NONFINITE_RESULT')
    anchored_exact = bool(np.array_equal(result[k], c[k]))
    if not anchored_exact:
        raise ValueError('COLOR_DIFFUSION_ANCHOR_CHANGED')
    maxima_ok = True
    if k.any():
        lower = np.full((component_count,3), np.inf)
        upper = np.full((component_count,3), -np.inf)
        np.minimum.at(lower, labels[k], c[k])
        np.maximum.at(upper, labels[k], c[k])
        maxima_ok = bool(((result[observed_component] >= lower[labels[observed_component]]) &
                          (result[observed_component] <= upper[labels[observed_component]])).all())
    evidence = {'schemaVersion':1,'colorSpace':'linear RGB supplied by caller; no implicit conversion',
                'vertexCount':len(v),'faceCount':len(f),'edgeCount':edge_count,
                'knownVertices':int(k.sum()),'unknownVertices':int((~k).sum()),
                'connectedComponents':int(component_count),
                'componentsWithoutObservations':int((seed_counts == 0).sum()),
                'unobservedComponentFallbackVertices':int(no_observations.sum()),
                'unobservedComponentFallbackColor':fallback.tolist(),
                'harmonicVertices':int(solve_mask.sum()) if convergence else 0,
                'nearestGraphSeedFallbackVertices':int(solve_mask.sum()) if convergence is False else 0,
                'anchorsPreservedExactly':anchored_exact,'allFinite':True,
                'geometryUnchanged':True,'maximumPrincipleSatisfied':maxima_ok,
                'maximumPrincipleClippedChannelValues':clipped_values,
                'solver':{'method':'scipy.sparse.linalg.cg with Jacobi preconditioner',
                          'status':'not_required' if convergence is None else 'converged' if convergence else 'graph_seed_fallback',
                          'converged':convergence,'maxIterationsPerChannel':int(max_iterations),
                          'relativeTolerance':tolerance,'fallbackReason':reason,'channels':channel_reports},
                'scope':'Uniform positive Laplacian on indexed triangle edges. Disconnected or coincident but unjoined '
                        'surfaces cannot exchange color. Shared-index junctions can exchange color through their actual '
                        'topological paths. No geometric coordinate, UV, topology, material, or observed color is modified. '
                        'Unobserved colors remain inferred; graph fallback is deterministic edge-hop nearest-seed color, '
                        'and entirely unobserved components use the declared constant.'}
    return result, evidence


# Descriptive alias for callers that prefer the numerical operation's name.
harmonic_color_fill = diffuse_colors
