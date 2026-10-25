"""Real xatlas UV seams returned per original triangle corner, without mesh edits.

This module runs in an operator-selected Python runtime with NumPy and xatlas.
Blender can call the fixed uv_atlas_worker.py in that runtime with a 100s child
process deadline. No environment discovery, dependency installation, networking,
geometry repair, vertex welding, or hidden mesh simplification occurs here.
"""
from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version
import time
import numpy as np

MAX_VERTICES = 200_000
MAX_FACES = 400_000


def _inputs(vertices, faces, normals, resolution, padding):
    v = np.asarray(vertices, dtype=np.float64)
    raw = np.asarray(faces)
    if v.ndim != 2 or v.shape[1] != 3 or not len(v) or len(v) > MAX_VERTICES or not np.isfinite(v).all():
        raise ValueError('UV_ATLAS_VERTICES_OR_BUDGET')
    if raw.ndim != 2 or raw.shape[1] != 3 or raw.dtype.kind not in 'iu' or not len(raw) or len(raw) > MAX_FACES:
        raise ValueError('UV_ATLAS_TRIANGULAR_INTEGER_FACES_OR_BUDGET')
    if raw.min() < 0 or raw.max() >= len(v):
        raise ValueError('UV_ATLAS_FACE_INDEX')
    f = raw.astype(np.int64, copy=False)
    if ((f[:,0] == f[:,1]) | (f[:,1] == f[:,2]) | (f[:,2] == f[:,0])).any():
        raise ValueError('UV_ATLAS_REPEATED_FACE_VERTEX')
    if isinstance(resolution, bool) or not isinstance(resolution, (int, np.integer)) or not 64 <= resolution <= 8192:
        raise ValueError('UV_ATLAS_RESOLUTION')
    if isinstance(padding, bool) or not isinstance(padding, (int, np.integer)) or not 0 <= padding <= min(64, resolution//8):
        raise ValueError('UV_ATLAS_PADDING')
    native_v = np.array(v, dtype=np.float32, order='C', copy=True)
    if not np.isfinite(native_v).all():
        raise ValueError('UV_ATLAS_FLOAT32_POSITION_RANGE')
    native_normals = None
    if normals is not None:
        n = np.asarray(normals, dtype=float)
        if n.shape != v.shape or not np.isfinite(n).all():
            raise ValueError('UV_ATLAS_NORMALS')
        length = np.linalg.norm(n, axis=1)
        if (length < 1e-15).any():
            raise ValueError('UV_ATLAS_ZERO_NORMAL')
        native_normals = np.array(n/length[:,None], dtype=np.float32, order='C', copy=True)
    return v, f, native_v, np.array(f,dtype=np.uint32,order='C',copy=True), native_normals


def _digest(array, dtype):
    return hashlib.sha256(np.asarray(array,dtype=dtype,order='C').tobytes()).hexdigest()


def _recover_original_corners(faces, vmapping, indices, uv):
    """Match canonical face IDs, then restore each original face/corner order.

    xatlas may split vertices and reorder faces/corners. Matching by original
    vertex IDs also handles repeated geometric positions and duplicate faces.
    No nearest-position matching can silently join coincident distinct surfaces.
    """
    mapping = np.asarray(vmapping)
    indices = np.asarray(indices)
    uv = np.asarray(uv,dtype=np.float64)
    if mapping.ndim != 1 or mapping.dtype.kind not in 'iu' or indices.shape != faces.shape or indices.dtype.kind not in 'iu':
        raise ValueError('UV_ATLAS_NATIVE_INDEX_SHAPE')
    if uv.shape != (len(mapping),2) or not np.isfinite(uv).all():
        raise ValueError('UV_ATLAS_NATIVE_UV_SHAPE_OR_NONFINITE')
    if indices.min() < 0 or indices.max() >= len(mapping) or mapping.min() < 0:
        raise ValueError('UV_ATLAS_NATIVE_INDEX_RANGE')
    native_original_faces = mapping[indices]
    original_canonical = np.sort(faces,axis=1)
    native_canonical = np.sort(native_original_faces,axis=1)
    original_order = np.lexsort((original_canonical[:,2],original_canonical[:,1],original_canonical[:,0]))
    native_order = np.lexsort((native_canonical[:,2],native_canonical[:,1],native_canonical[:,0]))
    if not np.array_equal(original_canonical[original_order],native_canonical[native_order]):
        raise ValueError('UV_ATLAS_ORIGINAL_FACE_CORRESPONDENCE')
    original = faces[original_order]
    native = native_original_faces[native_order]
    matches = original[:,:,None] == native[:,None,:]
    if not (matches.sum(axis=2) == 1).all():
        raise ValueError('UV_ATLAS_AMBIGUOUS_CORNER_CORRESPONDENCE')
    order = matches.argmax(axis=2)
    if not np.array_equal(np.take_along_axis(native,order,axis=1),original):
        raise ValueError('UV_ATLAS_ORIGINAL_CORNER_CORRESPONDENCE')
    native_uv = uv[indices[native_order]]
    restored = np.take_along_axis(native_uv,order[:,:,None],axis=1)
    loop_uv = np.empty((len(faces),3,2),dtype=np.float64)
    loop_uv[original_order] = restored
    return loop_uv, original_order, native_order, order


def generate_atlas(vertices, faces, resolution=2048, padding=8, normals=None):
    """Return (per_original_face_corner_uv, evidence) from the real xatlas.

    UV array shape is (len(faces),3,2); it maps directly to the original triangle
    corners. xatlas's seam-duplicated vertices never replace the caller mesh.
    UVs use xatlas's UV coordinate convention for mesh UV layers, without an
    image-row flip. Image/texture rasterization owns its own row convention.
    ``resolution`` is xatlas's requested packing resolution; actual atlas width
    and height are reported, as xatlas does not promise that exact dimension.
    """
    v,f,native_v,native_f,native_normals = _inputs(vertices,faces,normals,resolution,padding)
    position_digest = _digest(v,'<f8')
    face_digest = _digest(f,'<i8')
    try:
        import xatlas
    except ImportError as error:
        raise RuntimeError('UV_ATLAS_XATLAS_UNAVAILABLE_IN_SELECTED_RUNTIME') from error
    try:
        installed_version = version('xatlas')
    except PackageNotFoundError:
        installed_version = getattr(xatlas,'__version__','unknown')
    started = time.monotonic()
    atlas = xatlas.Atlas()
    atlas.add_mesh(native_v,native_f,normals=native_normals)
    chart_options = xatlas.ChartOptions()
    # Preserve native chart input winding; do not repair caller geometry.
    chart_options.fix_winding = False
    chart_options.max_iterations = 1
    pack_options = xatlas.PackOptions()
    pack_options.resolution = int(resolution)
    pack_options.padding = int(padding)
    pack_options.bilinear = True
    pack_options.bruteForce = False
    pack_options.rotate_charts = True
    pack_options.create_image = False
    atlas.generate(chart_options=chart_options,pack_options=pack_options,verbose=False)
    if atlas.mesh_count != 1 or atlas.atlas_count != 1:
        raise ValueError('UV_ATLAS_SINGLE_TEXTURE_PAGE_REQUIRED')
    vmapping,indices,uv = atlas[0]
    loop_uv,original_order,native_order,corner_order = _recover_original_corners(f,vmapping,indices,uv)
    if loop_uv.min() < 0 or loop_uv.max() > 1:
        raise ValueError('UV_ATLAS_UV_OUTSIDE_UNIT_SQUARE')
    page_ids,vertex_chart_ids = atlas.get_mesh_vertex_assignment(0)
    page_ids = np.asarray(page_ids)
    vertex_chart_ids = np.asarray(vertex_chart_ids)
    if page_ids.shape != np.asarray(vmapping).shape or vertex_chart_ids.shape != page_ids.shape:
        raise ValueError('UV_ATLAS_PAGE_ASSIGNMENT')
    assigned_vertex = (page_ids == 0)&(vertex_chart_ids < atlas.chart_count)
    corner_charts = vertex_chart_ids[indices]
    native_assigned_faces = assigned_vertex[indices].all(axis=1)
    if not (corner_charts[native_assigned_faces] == corner_charts[native_assigned_faces,0,None]).all():
        raise ValueError('UV_ATLAS_FACE_CROSSES_CHARTS')
    face_charts = np.empty(len(f),dtype=np.int64)
    face_charts[original_order] = corner_charts[native_order,0]
    assigned_faces = np.empty(len(f),dtype=bool)
    assigned_faces[original_order] = native_assigned_faces[native_order]
    artist_fill_faces = np.flatnonzero(~assigned_faces)
    artist_fill = {'enabled':False,'faceCount':0}
    if len(artist_fill_faces):
        # xatlas uses UINT32_MAX for tiny/ignored faces. Keep every original
        # triangle and place these explicitly attributed fill faces in their
        # own reserved atlas strip; never misrepresent them as native charts.
        sentinel = np.iinfo(np.uint32).max
        ignored_corners = indices[~native_assigned_faces]
        ignored_pages = page_ids[ignored_corners]
        ignored_charts = vertex_chart_ids[ignored_corners]
        if not (((ignored_pages == 0)|(ignored_pages == sentinel)) &
                ((ignored_charts < atlas.chart_count)|(ignored_charts == sentinel))).all():
            raise ValueError('UV_ATLAS_UNKNOWN_ASSIGNMENT_METADATA')
        artist_triangles = v[f[artist_fill_faces]]
        artist_area2 = np.linalg.norm(np.cross(artist_triangles[:,1]-artist_triangles[:,0],
                                             artist_triangles[:,2]-artist_triangles[:,0]),axis=1)
        all_triangles = v[f]
        all_area2 = np.linalg.norm(np.cross(all_triangles[:,1]-all_triangles[:,0],
                                          all_triangles[:,2]-all_triangles[:,0]),axis=1)
        area_fraction = float(artist_area2.sum()/max(float(all_area2.sum()),np.finfo(float).tiny))
        if len(artist_fill_faces) > max(64,int(np.ceil(len(f)*.02))) or area_fraction > .002:
            raise ValueError('UV_ATLAS_TOO_MANY_UNPARAMETERIZED_FACES:'+str(len(artist_fill_faces)))
        cell_pixels = max(2*int(padding)+3,5)
        columns = max(1,int(resolution)//cell_pixels)
        rows = int(np.ceil(len(artist_fill_faces)/columns))
        strip_height = max(.02,(rows*cell_pixels+2*int(padding)+2)/int(resolution))
        if strip_height > .25:
            raise ValueError('UV_ATLAS_ARTIST_FILL_STRIP_BUDGET')
        loop_uv[:,:,1] *= 1-strip_height
        margin = min(.2,(int(padding)+.5)/cell_pixels)
        cell_width,cell_height = 1/columns,strip_height/rows
        triangle_uv = np.array([[margin,margin],[1-margin,margin],[margin,1-margin]])
        for i,face in enumerate(artist_fill_faces):
            origin = np.array([(i%columns)*cell_width,1-strip_height+(i//columns)*cell_height])
            loop_uv[face] = origin+triangle_uv*np.array([cell_width,cell_height])
            face_charts[face] = int(atlas.chart_count)+i
        artist_fill = {'enabled':True,'faceCount':len(artist_fill_faces),'faceIndices':artist_fill_faces.tolist(),
                       'surfaceAreaFraction':area_fraction,'maximumGeometryDoubleArea':float(artist_area2.max()),
                       'nativePageSentinelCornerCount':int((ignored_pages == sentinel).sum()),
                       'nativeChartSentinelCornerCount':int((ignored_charts == sentinel).sum()),
                       'reservedStripMinimumV':float(1-strip_height),'reservedStripMaximumV':1.,
                       'stripHeightFraction':float(strip_height),
                       'scope':'Explicit artist-fill UV placement for faces xatlas did not parameterize; '
                               'these are not native xatlas charts or recovered texture. The bake stage must '
                               'use its declared coat/appearance prior on these faces. Original geometry is retained.'}
    edge_a,edge_b = loop_uv[:,1]-loop_uv[:,0],loop_uv[:,2]-loop_uv[:,0]
    signed_double_area = edge_a[:,0]*edge_b[:,1]-edge_a[:,1]*edge_b[:,0]
    area_epsilon = float(np.finfo(np.float32).eps**2)
    positive = signed_double_area > area_epsilon
    negative = signed_double_area < -area_epsilon
    total_chart_count = int(atlas.chart_count)+len(artist_fill_faces)
    if face_charts.min() < 0 or face_charts.max() >= total_chart_count:
        raise ValueError('UV_ATLAS_CHART_ASSIGNMENT')
    positive_counts = np.bincount(face_charts,weights=positive,minlength=total_chart_count)
    negative_counts = np.bincount(face_charts,weights=negative,minlength=total_chart_count)
    mixed_charts = int(((positive_counts>0)&(negative_counts>0)).sum())
    minority_faces = int(np.minimum(positive_counts,negative_counts).sum())
    # UV seams are counted by original vertex ID, not Euclidean coordinates.
    seam_counts = np.bincount(np.asarray(vmapping,dtype=np.int64),minlength=len(v))
    triangle = v[f]
    double_area = np.linalg.norm(np.cross(triangle[:,1]-triangle[:,0],triangle[:,2]-triangle[:,0]),axis=1)
    scale = float(np.linalg.norm(np.ptp(v,axis=0)))
    if position_digest != _digest(v,'<f8') or face_digest != _digest(f,'<i8'):
        raise ValueError('UV_ATLAS_INPUT_GEOMETRY_CHANGED')
    evidence = {'schemaVersion':1,'method':'xatlas','packageVersion':str(installed_version),
                'inputVertices':len(v),'inputFaces':len(f),'atlasVertices':len(vmapping),
                'originalVerticesWithUvSeams':int((seam_counts>1).sum()),
                'chartCount':int(atlas.chart_count),'atlasCount':int(atlas.atlas_count),
                'artistFill':artist_fill,'nativeUnassignedAtlasVertices':int((~assigned_vertex).sum()),
                'requestedResolution':int(resolution),'requestedPadding':int(padding),
                'atlasWidth':int(atlas.width),'atlasHeight':int(atlas.height),'utilization':float(atlas.utilization),
                'allFinite':True,'allUvsInUnitSquare':True,'minimumUv':loop_uv.min(axis=(0,1)).tolist(),
                'maximumUv':loop_uv.max(axis=(0,1)).tolist(),
                'degenerateUvFaces':int((~positive&~negative).sum()),
                'negativeSignedUvAreaFaces':int(negative.sum()),
                'flippedUvFaces':int(minority_faces),'chartsWithMixedUvWinding':int(mixed_charts),
                'minimumAbsoluteUvDoubleArea':float(np.abs(signed_double_area).min()),
                'inputDegenerateGeometryFaces':int((double_area<=max(scale*scale*1e-14,np.finfo(float).tiny)).sum()),
                'originalFaceCornerCorrespondenceVerified':True,
                'nativeFacesReordered':int((original_order != native_order).sum()),
                'nativeCornerOrdersRestored':int((corner_order != np.arange(3)).any(axis=1).sum()),
                'geometryUnchanged':True,'inputPositionsSha256':position_digest,'inputFacesSha256':face_digest,
                'seconds':float(time.monotonic()-started),
                'scope':'Per-corner UVs only. Original vertex positions, triangle indices and corner order are preserved. '
                        'Flipped UV faces means minority signed winding within one chart; a wholly mirrored chart is valid '
                        'and its negative signed areas are reported separately. These statistics do not prove absence of '
                        'all UV triangle overlaps or establish texture/photo correctness.'}
    return loop_uv,evidence
