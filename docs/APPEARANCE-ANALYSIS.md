# Automatic reference appearance analysis

`noetra.analyze_reference_appearance({images, colourFamilies: 8})` runs the same
object-agnostic analysis on any 1–8 project-local PNG/JPEG references. It accepts
no intended colours, body-part names, hand-painted masks, mesh or executable
code. It preserves source bytes and operates in the configured CPU Python. No
Blender, model download, GPU, external account or cloud image upload is used.

The actual implementation performs source-alpha / white-border foreground
estimation; deterministic farthest-first CIELab median clustering; connected
spatial colour regions; contour extraction; local chroma/lightness gradients;
and structure-tensor texture-line directions. Output swatches are actual source
pixels. Every region has pixel and normalized bounds, boundary contours,
texture statistics and an explicit unknown anatomical identity and depth.
Numeric label PNGs, measurements NPZ, diagrams and JSON are saved in a new run.
No mesh is read, modified or replaced.

## Analysis is not yet autonomous anatomical design

Colour clusters can merge a dark eye with a dark mane or split one leg into lit
and shaded areas. Region outlines follow quantized appearance, not verified
anatomical boundaries. Texture direction measures local image lines; it does
not recover fur strands or normals. Brightness differences cannot separate
intrinsic material, lighting and shape. Metric and relative depth remain null.
Independent generated views are not automatically consistent calibrated views.

The resulting `design-gate.json` therefore sets both automatic texturing and
geometry design to false. It lists missing anatomical segmentation,
semantic-to-mesh correspondence, light/albedo separation and depth evidence.
The gate is a recorded readiness decision; no automatic material-application
stage is implemented by this tool. Existing explicitly authored paint operations
remain distinct. The system must preserve the current mesh rather than pretend
this analysis has completed anatomy or paste the reference onto its surface.

This is working automatic observed-colour analysis, not a claim of a completed
automatic photo-to-3D material system. Future stages must provide and validate
the missing evidence before automatic application can be enabled.

## Explicit measured-palette preview

`noetra.paint_appearance_preview({analysisRunId, meshRunId, layout,
mode: "unverified-preview"})` connects the measurements to the existing local
Blender/xatlas painter without pretending automatic placement has been solved.
It requires a project-local data-only previously authored layout. Software
replaces every base/layer/gradient colour endpoint with the nearest actual source
pixel swatch in CIELab; it records each assignment, previous colour distance,
source analysis hashes and layout provenance. No photographic image is connected
to the shader. Roughness, procedural grain and spatial placement remain authored
hypotheses, not measured intrinsic material or automatically inferred anatomy.

The preview exports a separate geometry-preserving BLEND/GLB, PBR maps and eight
renders. It never changes the analysis gate, the accepted model or input layout.
This is an explicit experimental paint pass, not autonomous verified design.

For the largest attributed fibre region, the preview can fit material weights to
normal-projected surface roughness inside a bounded expansion of its old mask.
Graph smoothing avoids a straight primitive-mask cut across detailed geometry.
This is a geometric hypothesis, not semantic segmentation; source geometry is
unchanged. Atlas reuse separately requires identical positions, face indices,
resolution and padding plus rechecked source artifact hashes. A mismatch runs
fresh xatlas rather than transferring UVs to different geometry.
