# Optional reconstruction proof — alpha.3

This document describes the original **limited planar-target proof**. The newer
[local photo pipeline](PHOTO-PIPELINE.md) adds learned single-photo meshes,
multi-photo COLMAP and real Open3D/Mitsuba/Blender processing. Neither delivers
the complete high-fidelity reconstruction specification or a production-ready vision system.
No model weights, pretrained assets, car meshes or photograph dataset are bundled.
The default core remains CPU-only and does not require Python, Blender or a GPU.

## What actually works

- Project-local PNG/JPEG originals preserved byte-for-byte with SHA-256 identity,
  dimensions, image mode, EXIF-orientation status and unchanged original metadata.
- Full-resolution RGB/alpha, Sobel gradients and Canny edges in compressed binary
  arrays; prompts receive compact metadata and paths, not millions of pixels.
- Exact duplicate detection, perceptual-hash observations, blur variance and
  observed luminance/color statistics. These are not calibrated quality scores.
- A known rectangular calibration-grid detector supplies semantic target identity.
  Its observed cell-color boundaries and Canny edges are separately identified as
  geometric/image structure. They are not falsely labelled physical creases.
- OpenCV intrinsics/distortion estimation and nonlinear calibration on training
  stereo pairs; stereo extrinsics; a separate pair for reconstruction; checked
  triangulation, cheirality/parallax/reprojection filtering and planar fitting.
- A versioned spatial representation with persistent sheet/tile IDs, source-image
  regions, camera matrices, sparse 3D observations, editable parameters, appearance
  observations and unknown geometry. Camera-ready references are undistorted at
  full original resolution; originals are never resampled or overwritten.
- A fixed Blender adapter builds separate editable sheet components, driver-backed
  width/height parameters, matched cameras, materials, BLEND and GLB files.
- Bounded finite-difference parameter fitting followed by **actual Blender renders**.
  Acceptance requires both views' landmark and boundary errors not to regress,
  and a measurable validation-view silhouette gain. Otherwise the initial scene
  remains best. Checkpoints, predictions, proposals, renders and decisions remain.
- Per-part landmark boundary errors, silhouette IoU, symmetric boundary distance,
  apparent edge distance, view-specific RGB error and difference overlays.
- Geometry-derived depth/normal arrays and actual rendered multilayer EXR passes.
  Neither is represented as a physical depth measurement of the photograph.
- Bicubic controlled-patch evaluation, tangent normals and differential curvature
  are implemented and numerically tested. They are **not yet automatically fitted
  to arbitrary object photographs**.

## The first real-photo demonstration

The fixture is 26 small public grayscale calibration photographs from OpenCV's
official stereo example. A separate explicit downloader preserves originals and
upstream license in a workspace proof folder; it is never invoked by MCP/core.
The output reconstructs **only the inner 9-by-6 corner grid / 40 painted cells**,
not the whole board, person, room, thickness, exterior frame or hidden back.

Twelve stereo pairs calibrate the cameras; one pair is excluded from calibration.
The experiment deliberately initializes width at 0.82 and height at 1.18 of the
triangulation-derived sheet. It is a controlled correction test, not a claim that
the initial reconstruction naturally had this error or a test of arbitrary 3D
generation. Scale fitting uses left-image landmarks; right-image renders validate
the candidate. The right image was used earlier for triangulation/plane pose, so
this validation is **not a wholly independent dataset split**.

Observed first-pass results (separate full final report accompanies the proof):

| Right view | Before | Corrected |
| --- | ---: | ---: |
| Inner-grid silhouette IoU | 0.71198 | 0.98983 |
| Landmark RMSE, pixels | 18.8539 | 0.3366 |
| Mean symmetric boundary distance, pixels | 17.1300 | 0.2763 |

Stereo calibration RMS was 0.20254 px. All 54 triangulated points passed checks;
minimum parallax was 10.56 degrees. These numbers measure this known-pattern,
planar, image-space proof, **not 99% fidelity for general objects or a car**.
Square size is not known; dimensions are relative checker-square units. A supplied
squareSizeMetres establishes a caller-provided scale, not verified measurement.

## Enable deliberately

Python dependencies are optional and independently installed: NumPy, SciPy,
OpenCV and Pillow. Tested here: Python 3.14.5, NumPy 2.4.6, SciPy 1.18.0,
OpenCV 5.0.0, Pillow 12.2.0, Blender 5.2.2 LTS. Optional installed psutil reports
worker RSS/peak memory; its measurements exclude the Blender child. No packages
or model weights are downloaded automatically. The Blender adapter is tested on
5.2; other versions are not certified.

Create a reviewed **local operator config**, outside untrusted image content:

```json
{
  "pythonExecutable": "C:/absolute/path/to/python.exe",
  "blenderExecutable": "C:/absolute/path/to/blender.exe",
  "allowBlenderExecution": false
}
```

```text
noetra mcp --project ABSOLUTE_DEDICATED_PROJECT --reconstruction-config ABSOLUTE_CONFIG_JSON
```

Without that flag, MCP advertises the original eleven tools. With the config,
twenty-three optional tools are added (thirty-four total). Separately configuring
the Ghidra native route adds one more. The original six proof
operations are listed below; newer operations are documented in
[part correction and outline construction](PART-CORRECTION.md), the [photo pipeline](PHOTO-PIPELINE.md), [calibrated all-side views](CALIBRATED-VIEWS.md), [surface painting](SURFACE-PAINT.md) and [automatic appearance analysis](APPEARANCE-ANALYSIS.md).

| Tool | Validated input |
| --- | --- |
| noetra.inspect_image_structure | images: 1–32 absolute project-local PNG/JPEG paths |
| noetra.reconstruct_multiview | pairs: 4–16 left/right paths; pattern [columns, rows]; holdoutPair; optional squareSizeMetres; initialScale |
| noetra.generate_3d_construction | runId; prepares a fixed script but does not execute it |
| noetra.optimize_reconstruction | runId; maxEvaluations 4–40; trusted operator execution consent required |
| noetra.compare_reference_render | runId; actual render comparison, no silent resizing |
| noetra.export_reconstruction_report | runId; compact summary and local artifact paths |

New operations: `build_outline_model`, `prepare_part_correction`, `correct_parts`
and `inspect_part_correction`. They use real Blender geometry/renders and
attributed outline/part observations. The photo pipeline separately adds COLMAP,
TripoSR and foreground estimation. VGGT/MapAnything, automatic semantic part
reconstruction and complete detailed car reconstruction remain unfinished.

For the proof, at least six detected training pairs plus one detected held-out
pair are required; the demonstration uses twelve plus one. All views must have
the same resolution and unrotated EXIF orientation. Inputs are limited to 24 MiB,
24 megapixels and an 8192-pixel edge. Analysis is bounded to 64 local runs per
dedicated project. Clean up only explicitly selected experiment folders yourself.

Execution permission is **not an MCP input field**. Set allowBlenderExecution=true
only after the human approves that local experiment. No arbitrary source string
is accepted; the runner executes a hash-checked fixed adapter, with JSON geometry
data, in a fresh background Blender process. The Python worker has a 180-second
wall limit and Blender a 110-second limit. Child processes use argument arrays,
hidden Windows windows, a reduced environment, cancellation and owned-process
termination. Blender's user-resource directory is redirected to the experiment,
not the operator's existing Blender settings. Source-image changes, changed spatial data and changed construction
scripts are rejected. A fresh process is **not an OS security sandbox**: generic
untrusted code generation/execution remains unsupported, not declared safe.

## Important unfinished capabilities

- Exact single-view 3D recovery, semantic part detection, tracking video and dense
  multi-view surface fusion. Learned single-view inference and sparse multi-view
  SfM are now implemented separately; neither establishes exact physical shape.
- Automatic NURBS/surface fitting, topology reconstruction, real panel-gap
  detection, reflection/ridge disambiguation and car-specific geometry recovery.
- Intrinsic PBR/lighting recovery, transparency analysis and calibrated confidence.
- VGGT and MapAnything runtime adapters/checkpoints remain unimplemented.
  PyCOLMAP, Open3D and Mitsuba are now locally installed and executed through
  the photo pipeline. No private images were transmitted.
- A fully autonomous multi-object correction loop or complete eight-object
  end-to-end benchmark. This proof performs a bounded two-parameter experiment.
- Remote services, cloud transmission consent flow and a generic script sandbox.
- Public npm/GitHub publication, signed releases and independent security review.

The proposed segment_parts, analyze_surface_geometry and estimate_camera_geometry
tool names are not advertised as placeholder capabilities. Calibration currently
runs inside the specialized, implemented reconstruct_multiview operation.
REA remains an independent, unchanged software-investigation option; it was not
used as photogrammetry or automatically invoked for an uploaded image.

## Test coverage scope

The Node suite covers original features plus optional configuration, strict
schemas, missing dependencies and disabled-by-default behavior. Python tests
cover an eight-corner metric-box triangulation with known synthetic 3D truth,
bad matches, zero baseline, behind-camera/nonfinite data, camera validity,
bicubic flat/raised/concave surfaces, degenerate patches, bounded optimization,
mask metrics, path scope, original RGB/alpha integrity, source mutation and
execution consent. Synthetic mathematical tests are not misreported as full
photographic reconstructions of those objects.

| Requested object family | Current evidence |
| --- | --- |
| Known-dimension box | Synthetic multi-view triangulation against 3D ground truth |
| Curved manufactured object / creased hood | Controlled bicubic geometry math tests only |
| Bumper with recessed intakes | Not yet an automated reconstruction benchmark |
| Chair, complete multi-view car, organic character | Not implemented as end-to-end benchmarks |
| Glossy/reflective object | Unsupported for intrinsic geometry/material disambiguation |
| Simple manufactured planar grid | Real photographs, cameras, editable geometry, actual renders and measured correction |

## Primary references

- [OpenCV calibration guide](https://docs.opencv.org/4.13.0/dc/dbb/tutorial_py_calibration.html)
- [Official stereo-calibration sample](https://github.com/opencv/opencv/blob/4.x/samples/cpp/stereo_calib.cpp)
- [Official sample image list](https://github.com/opencv/opencv/blob/4.x/samples/data/stereo_calib.xml)
- [PyCOLMAP interface](https://colmap.github.io/pycolmap/index.html)
- [VGGT official repository and license notes](https://github.com/facebookresearch/vggt)
- [MapAnything official repository](https://github.com/facebookresearch/map-anything)
- [Open3D surface reconstruction](https://www.open3d.org/docs/release/tutorial/geometry/surface_reconstruction.html)
- [Mitsuba inverse rendering](https://mitsuba.readthedocs.io/en/stable/src/inverse_rendering/gradient_based_opt.html)

OpenCV calls were also checked against installed Python docstrings. Blender
camera/export/pass settings were inspected in the installed Blender runtime and
its bundled official API manual, including the 5.2 media_type change for EXR.
