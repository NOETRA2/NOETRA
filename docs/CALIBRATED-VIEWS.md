# Calibrated all-side images to a visual hull

`noetra.reconstruct_calibrated_views({manifest:absolutePath})` builds a new mesh
from at least three calibrated views. It reads images, masks and camera data;
it cannot read a source mesh or execute caller-supplied code. It is separate
from the older planar checker-grid proof and single-image learned pipeline.

Enable the optional reconstruction module with the existing trusted local
operator configuration and its `vision.pythonExecutable` (NumPy, OpenCV, Pillow,
SciPy, scikit-image and trimesh). `allowBlenderExecution:true` additionally runs
the fixed Blender exporter and matched-camera comparisons. No weights or network
connection are required by this operation. Inference does not download anything.

The project-local JSON manifest is strict:

```json
{
  "schemaVersion": 1,
  "provenance": "Describe the source and scope of this dataset",
  "bounds": {"minimum": [-2,-1,-1], "maximum": [2,1,1]},
  "grid": 160,
  "views": [{
    "id": "front",
    "image": {"path": "ABSOLUTE_PROJECT_IMAGE.png", "sha256": "64 lowercase hex digits"},
    "mask": {"path": "ABSOLUTE_PROJECT_MASK.png", "sha256": "64 lowercase hex digits"},
    "camera": {
      "convention": "opencv-world-to-camera-x-right-y-down-z-forward",
      "K": [[800,0,320],[0,800,320],[0,0,1]],
      "R": [[1,0,0],[0,1,0],[0,0,1]],
      "t": [0,0,5],
      "uncertaintyPx": 0,
      "provenance": "How this camera was calibrated"
    },
    "origin": {"kind": "rendered", "captureId": "front", "provenance": "Producer scene identity"}
  }]
}
```

The excerpt shows one view; supply 3–16 views with distinct camera centres.
All paths must be absolute and inside the selected project. Cameras must use
one coordinate system and scale. Masks must be same-sized binary PNGs with
foreground 255. Grid resolution is bounded to 16–192 samples per axis. The
object must fit inside the supplied bounds; occupied boundary samples fail.
Camera positions are not recovered by this operation. For uncalibrated real
photos, estimate cameras first; do not invent calibration and claim it measured.

Origins can be `actual_photo`, `reference_artwork` or `rendered`. Rendered views
preserve their derived status. Reconstructing them does not independently
validate their producer. All input bytes and hashes are preserved. Saved-run
inspection rechecks the images, manifest and output artifacts.

The solver intersects bilinearly sampled silhouette distance cones, extracts
their zero surface with marching cubes, checks closedness and consistent winding,
and exports PLY/GLB. Optional Blender export creates a fresh scene and renders the
actual mesh through the supplied cameras. It records camera projection error,
silhouette IoU and symmetric boundary distance. Source models are never opened.

Silhouettes constrain only the visual hull: recessed surfaces, spokes hidden
inside an outer wheel outline, panel gaps and materials are not recovered.
Sampling and input resolution limit fine detail. High silhouette IoU is not a
percentage of overall 3D fidelity. Retain a more detailed existing model; this
coarse reconstruction does not automatically supersede it.

The local car test used ten 640px rendered views and 160³ sampling. The signed
distance extraction improved mean fitting-view IoU from 98.730% to 99.089%, with
explicit subpixel non-regression tolerances. All views were derived from the
same authored hypothesis; there was no independent photographic ground truth.
The detailed car reconstruction remains unfinished.
