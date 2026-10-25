# Local photo reconstruction and observed appearance

The tools run inside NOETRA's independently configured local reconstruction
module. They do not install Nexa Chat/Browser, alter global AI-client settings,
upload photographs or download models during a tool call. REA/Ghidra remains
software analysis, not the vision model or mesh generator.

## Implemented routes

| Tool | Actual behavior |
| --- | --- |
| `noetra.reconstruction_backends` | Inspect configured environment/package versions; no inference |
| `noetra.reconstruct_photos` with `backend=triposr` | Preserve one source image; local foreground estimate, learned triplane inference, real triangle extraction, Open3D/Trimesh cleanup, camera proposal, actual Blender comparison and editable exports |
| `noetra.reconstruct_photos` with `backend=colmap` | Preserve 3–16 overlapping photos; CPU SIFT, exhaustive geometric matching, incremental camera/landmark reconstruction, relative-scale sparse PLY and camera/track exports |
| `noetra.reconstruct_photos` with `backend=hunyuan-mini` | Explicitly configured isolated Hunyuan3D-2mini Turbo; one source image and attributed foreground alpha; pinned source/config/safetensors, staged execution and fresh neutral Blender inspection renders. Resource limits and real inference must pass; no placeholder or silent fallback. This is not multi-image fusion. |
| `noetra.refine_photo_appearance` | Visibility-tested projection of original photo radiance onto a validated learned mesh; geometry and camera fingerprints must remain identical |
| `noetra.fit_photo_outline` | Bounded camera-plane changes near the estimated outline; depth/camera/topology fixed, distant vertices protected. Restore orientation-invalid edits, then accept only after actual silhouette/boundary improvement; otherwise export original geometry |
| `noetra.repair_photo_surface` | Repair an existing generated photo mesh without rerunning inference: locally anchored contour fairing, capped displacement and per-neighbourhood triangle safeguards. Protect distant vertices, camera and topology. Accept only after actual rendered mask and local roughness checks; export seven camera angles and neutral mesh views |

The original ten operations for image inspection, calibration-grid reconstruction,
guided outline lofts and part-scoped correction remain available. Reconstruction
configuration adds fifteen tools to the eleven-tool core. Configured Ghidra adds
one separate native-investigation tool. Missing dependencies/consent fail closed.

## Local configuration

Use Python 3.12 for the tested optional vision environment. The core Node runtime
does not depend on Python. Install the optional libraries only in a dedicated
virtual environment; `requirements-vision-cpu.txt` is distributed beside the
Python runtime. Install official CPU Torch/Torchvision separately. Independently
review and cache upstream source/model assets; no arbitrary model URL or code is
accepted in a public tool request.

```json
{
  "pythonExecutable": "C:/absolute/python.exe",
  "blenderExecutable": "C:/absolute/blender.exe",
  "allowBlenderExecution": true,
  "vision": {
    "pythonExecutable": "C:/NOETRA/.tools/vision-env/Scripts/python.exe",
    "sourceDirectory": "C:/NOETRA/.tools/TripoSR",
    "sourceManifest": "C:/NOETRA/.tools/models/triposr-source-manifest.json",
    "modelManifest": "C:/NOETRA/.tools/models/model-manifest.json",
    "allowModelExecution": true,
    "cpuPrecision": "float32",
    "maxResolution": 192
  }
}
```

Both execution permissions default to false and belong to trusted operator
configuration. They are not tool-input switches. The model manifest pins source
commit/model revision and hashes/sizes of weights, model config, DINO config and
foreground checkpoint. The source manifest pins the reviewed provider Python
files. Changes are rejected before inference. Hugging Face access is offline and
caches are local to the run. The proof contains an explicitly recorded CPU
scikit-image fallback patch to TripoSR's optional torchmcubes extractor. An
asymmetric ellipsoid test checks coordinate axes and outward surface winding.

Float32 is the default: the measured car's image-space outline was better than
the experimental int8 feature-network mode. Density/color decoding is always
float32. CPU inference uses at most four Torch threads. A model-cache OS file lock
prevents concurrent heavy calls; one photo job is bounded to 20 minutes. Fresh
Blender children have separate runtime directories and bounded execution. C/C++
diagnostics cannot contaminate the worker's JSON response pipe.

Run through the normal SDK or:

```text
noetra mcp --project ABSOLUTE_PHOTO_PROJECT --reconstruction-config ABSOLUTE_CONFIG_JSON
```

## Verified local evidence, 2026-10-24

- Real local TripoSR inference, original silver-car image preserved by SHA-256;
  float32 CPU extraction at grid resolution 192. The initial learned surface has
  21,923 vertices / 43,846 triangles and is watertight with consistent outward
  winding. No smoothing or small-part removal was applied to that raw checkpoint.
- Actual full-mesh Blender camera comparison: silhouette overlap 0.65186 →
  0.90090, mean boundary distance 15.9005 → 3.7368 pixels at 512px. This is alignment
  against an estimated foreground mask, **not 90% 3D fidelity**.
- Reusable outline fit then improved overlap 0.90090 → 0.94509 and mean boundary
  distance 3.7368 → 1.7982px. It changed 7,137 vertices near the contour, preserved
  14,786 others, restored 273 orientation-invalid vertex proposals and left zero
  flipped faces. Camera, topology and camera-axis depth were preserved. The first
  unconstrained candidate was rejected despite better overlap because it folded
  111 faces; that failed candidate remains available as regression evidence.
- Full photo run about 121 seconds; measured Python peak working set about
  2.15 GB, excluding Blender and other applications. No CUDA claim is made.
- Separate synthetic six-view perspective fixture: PyCOLMAP registered all six
  images and triangulated 4,005 landmarks, mean reprojection error 0.11432px.
  These are synthetic test views, not invented extra car photographs.
- Real Open3D normal/mesh processing, Trimesh exports, Mitsuba `scalar_rgb`
  inspection render and Blender BLEND/GLB/renders all executed. Mitsuba reports
  unavailable LLVM initialization; the explicitly selected scalar renderer works.
- Source, candidates, masks, overlays, depth/normal EXR passes, scene code,
  provenance, decisions and artifact hashes stay in immutable run folders.

## Isolated staged Hunyuan provider

The optional trusted `vision.hunyuan` configuration selects its own
`pythonExecutable`, pinned `sourceDirectory`, `assetDirectory`, `device`, `steps`,
`seed`, `timeoutSeconds`, `numChunks` and `cpuThreads`. Public tool arguments cannot
provide these paths or grant execution. `vision.allowModelExecution` must already
be enabled. Foreground preparation runs in a short-lived process before shape
inference; the existing TripoSR CPU environment remains unchanged. See the
[provider contract](../packages/reconstruction/python/providers/HUNYUAN_MINI.md)
for exact source/model identity, staging, offline behavior and resource guards.

One actual local lion call completed on an RTX 3050 Laptop 4 GB using an isolated
PyTorch 2.6 CUDA 12.4 environment: 8 steps, grid 192, 1,024 chunks, FP16 staged
conditioner → DiT → VAE. Learned shape generation took 86.985 seconds with
2,571,237,376 bytes peak **allocated** VRAM (not total process/device use). It
produced 81,326 vertices / 162,196 triangles; the full SDK call including eight
actual Blender renders took 177.532 seconds. These are one tested input and
configuration, not a guarantee that every image or laptop fits.

Two initial calls stopped at the default physical-RAM guard. The successful
trusted configuration explicitly enabled `experimentalLowRam:true`, which keeps
at least 768 MiB available physical memory **and** 6 GiB measured Windows commit
headroom. Commit space is not extra physical RAM; CPU still requires 6 GiB physical
availability. This setting defaults false. GPU, attention, timeout, pinned-file
and offline guards remain enforced. Model inference succeeded without a CPU
fallback; failures remain recorded rather than receiving a substitute mesh.

The lion has a recognizable body, four legs, mane and tail. Face and mane detail
remain coarse. Generated reference views are not measured photographs and were
not fused by the single-image backend. Neutral inspection materials do not
recover fur textures or intrinsic PBR. Presentation camera labels follow a
proposed canonical -X front, not automatic semantic orientation recognition.

### Surface repair of the earlier TripoSR mesh

The original outline-only gate did not detect every local rough fold or texture
coverage gap. `repair_photo_surface` now works on the saved source mesh and its
verified photo lineage. It defines a fixed contour-neighbourhood selection,
caps movement at 1.8% of the mesh bounding diagonal, anchors all other vertices,
and applies local Laplacian fairing followed by smooth silhouette contraction.
Per-vertex backtracking limits only triangles that would lose orientation or
collapse, instead of letting one tiny face block repair elsewhere. This does not
prove absence of self-intersections or correct physical hidden shape.

Acceptance checks zero newly reversed faces, minimum triangle-area ratio,
improved local Laplacian residual, preserved camera/topology/other objects, and
actual Blender mask overlap/boundary non-regression. A failed candidate remains
saved; exported geometry falls back to the original source. The worker reserves
ten minutes for this operation and the fixed multi-view Blender child is bounded
to five minutes. No model inference, cloud upload or new dependency download is
performed by this saved-mesh route.

Texture projection tests the centroid and three inset corner samples for a
partly visible triangle, addressing gaps missed by centroid-only visibility.
It still records source-image radiance rather than intrinsic materials.
Seven camera poses (reference, front, both displayed sides, rear, top and rear
three-quarter) render the **same** saved geometry. Six neutral-material renders
also expose the underlying coarse mesh. These views are not new source photos
and must not be used as independent evidence for validating hidden geometry.

## Material limitations

A single photo does not establish hidden surfaces, true scale, fine panel gaps,
spoke geometry, intrinsic paint/lighting or transparent interior structure.
Projected radiance preserves visible *appearance*, not geometric detail or PBR.
Another viewing angle can expose projection distortion and incomplete geometry.
The learned car surface remains coarse and is not production-ready CAD.

COLMAP currently exports sparse structure, not a dense watertight surface. No
claim is made that VGGT, MapAnything, automatic semantic part splitting, dense
fusion, generic NURBS fitting or the full original reconstruction specification
is finished. Gated licenses/accounts have not been accepted on the user's behalf.
All model binaries and optional providers remain outside the core distributable.

Upstream projects: [TripoSR](https://github.com/VAST-AI-Research/TripoSR),
[PyCOLMAP](https://colmap.github.io/pycolmap/pycolmap.html),
[Open3D](https://github.com/isl-org/Open3D),
[Trimesh](https://github.com/mikedh/trimesh),
[scikit-image](https://github.com/scikit-image/scikit-image),
[Mitsuba](https://github.com/mitsuba-renderer/mitsuba3),
[rembg](https://github.com/danielgatis/rembg).
