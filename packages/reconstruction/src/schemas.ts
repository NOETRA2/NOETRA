import { z } from 'zod';
const Path = z.string().min(1).max(4096);
const RunId = z.string().uuid();
const Id = z.string().regex(/^[a-z][a-z0-9-]{0,63}$/);
const ObjectName = z.string().min(1).max(160);
const Point3=z.tuple([z.number().min(-1000).max(1000),z.number().min(-1000).max(1000),z.number().min(-1000).max(1000)]);
const Cubic=z.array(Point3).length(4);
const Color=z.tuple([z.number().min(0).max(1),z.number().min(0).max(1),z.number().min(0).max(1)]);
const PaintRegion=z.object({shape:z.enum(['ellipsoid','box']).default('ellipsoid'),center:Point3,radii:z.tuple([z.number().positive().max(100),z.number().positive().max(100),z.number().positive().max(100)]),feather:z.number().min(.01).max(.5).default(.2),provenance:z.string().min(1).max(1000)}).strict();
const MaterialDesign=z.object({baseSRGB:Color,baseRoughness:z.number().min(.05).max(1),resolution:z.union([z.literal(1024),z.literal(2048)]).default(2048),
  layers:z.array(z.object({id:Id,region:PaintRegion,colorSRGB:Color,roughness:z.number().min(.05).max(1),opacity:z.number().min(0).max(1).default(1),verticalFiber:z.number().min(0).max(1).default(0),
    gradient:z.object({axis:z.enum(['X','Y','Z']),minimum:z.number().min(-1000).max(1000),maximum:z.number().min(-1000).max(1000),colorSRGB:Color}).strict().refine(x=>x.maximum>x.minimum,'Gradient maximum must exceed minimum').optional(),
    provenance:z.string().min(1).max(1000)}).strict()).min(1).max(32),provenance:z.string().min(1).max(2000)}).strict();
export const StructuralPriorSpec=z.object({
  blend:Path,collection:ObjectName,reference:Path,floor:ObjectName,
  wheels:z.array(ObjectName).min(1).max(16),wheelAxis:z.number().int().min(0).max(2).default(1),
  forward:Point3.default([-1,0,0]),referenceTarget:Point3,
  groundClearance:z.number().positive().max(.1).default(.003),
  patches:z.array(z.object({object:ObjectName,curves:z.object({left:Cubic,right:Cubic,bottom:Cubic,top:Cubic}).strict(),
    resolution:z.number().int().min(4).max(64).default(24),provenance:z.string().min(1).max(1000)}).strict()).max(16),
  recesses:z.array(z.object({object:ObjectName,guide:ObjectName,outward:Point3,depth:z.number().positive().max(.1),
    clearance:z.number().positive().max(.05),provenance:z.string().min(1).max(1000)}).strict()).max(8).default([]),
  fairing:z.array(z.object({object:ObjectName,minimum:Point3,maximum:Point3,axis:z.enum(['X','Y','Z']),
    iterations:z.number().int().min(1).max(24),strength:z.number().positive().max(.5),maxDisplacement:z.number().positive().max(.05)}).strict()).max(8).default([]),
  provenance:z.string().min(1).max(2000)
}).strict();
const Pixel = z.tuple([z.number().min(0).max(8192),z.number().min(0).max(8192)]);
const Binding = z.object({
  id: Id, partId: Id, kind: z.enum(['translate','mesh_offset','curve_offset']),
  axis: z.enum(['X','Y','Z']), object: ObjectName.optional(),
  indices: z.array(z.number().int().min(0).max(2000000)).min(1).max(4096).optional(),
  spline: z.number().int().min(0).max(256).optional(),
  minimum: z.number().min(-10).max(0), maximum: z.number().min(0).max(10),
  step: z.number().positive().max(1)
}).strict();
export const PartCorrectionSpec = z.object({
  blend: Path, collection: ObjectName,
  parts: z.array(z.object({id:Id,objects:z.array(ObjectName).min(1).max(512)}).strict()).min(1).max(24),
  parameters: z.array(Binding).min(1).max(12),
  views: z.array(z.object({
    id:Id,camera:ObjectName,reference:Path,
    annotations:z.array(z.object({partId:Id,polygon:z.array(Pixel).min(3).max(512),
      provenance:z.string().min(1).max(1000)}).strict()).min(1).max(24)
  }).strict()).min(1).max(3),
  influencePaddingPixels:z.number().int().min(0).max(32).default(8),
  minimumLossImprovement:z.number().min(.000001).max(.1).default(.0001)
}).strict();
export const OutlineSpec = z.object({
  reference:Path, outlinePx:z.array(Pixel).min(3).max(512).optional(),foregroundMask:Path.optional(),
  provenance:z.string().min(1).max(1000),cameraAssumption:z.literal('front-orthographic'),
  frontWidthUnits:z.number().positive().max(100).default(2),
  proposedDepthRatio:z.number().min(.05).max(5).default(.75),
  proposedSections:z.array(z.object({t:z.number().min(0).max(1),scaleX:z.number().min(.05).max(1),scaleZ:z.number().min(.05).max(1)}).strict()).min(2).max(8)
    .default([{t:0,scaleX:1,scaleZ:1},{t:.3,scaleX:.95,scaleZ:.95},{t:1,scaleX:.8,scaleZ:.8}])
}).strict().refine(x=>(x.outlinePx===undefined)!==(x.foregroundMask===undefined),'Supply exactly one attributed outline or foreground mask.');
export const ReconstructionConfig = z.object({
  pythonExecutable: Path,
  blenderExecutable: Path.optional(),
  allowBlenderExecution: z.boolean().default(false),
  vision:z.object({
    pythonExecutable:Path,sourceDirectory:Path,modelManifest:Path,sourceManifest:Path,
    allowModelExecution:z.boolean().default(false),
    cpuPrecision:z.enum(['float32','int8']).default('float32'),
    maxResolution:z.number().int().min(64).max(256).default(192),
    hunyuan:z.object({
      pythonExecutable:Path,sourceDirectory:Path,assetDirectory:Path,
      device:z.enum(['cuda','cpu']).default('cuda'),steps:z.number().int().min(1).max(30).default(8),
      seed:z.number().int().min(0).max(2147483647).default(12345),
      timeoutSeconds:z.number().int().min(30).max(1000).default(900),
      numChunks:z.number().int().min(256).max(8192).default(1024),
      cpuThreads:z.number().int().min(1).max(4).default(4),
      experimentalLowRam:z.boolean().default(false)
    }).strict().optional()
  }).strict().optional()
}).strict();
export type ReconstructionConfig = z.infer<typeof ReconstructionConfig>;
export const reconstructionSchemas = {
  'noetra.paint_appearance_preview':z.object({analysisRunId:RunId,meshRunId:RunId,layout:Path,mode:z.literal('unverified-preview')}).strict(),
  'noetra.analyze_reference_appearance':z.object({images:z.array(Path).min(1).max(8),colourFamilies:z.number().int().min(3).max(12).default(8)}).strict(),
  'noetra.refine_base_surface':z.object({runId:RunId,references:z.array(Path).min(1).max(8),design:MaterialDesign,
    refinement:z.object({maximumDisplacement:z.number().positive().max(.025),deformations:z.array(z.object({id:Id,region:PaintRegion,direction:Point3,distance:z.number().min(-.025).max(.025)}).strict()).min(1).max(16),provenance:z.string().min(1).max(2000)}).strict()
  }).strict(),
  'noetra.paint_surface_material':z.object({runId:RunId,references:z.array(Path).max(8).default([]),design:MaterialDesign}).strict(),
  'noetra.refine_learned_surface':z.object({runId:RunId,resolution:z.number().int().min(128).max(256).default(256)}).strict(),
  'noetra.colorize_reconstruction':z.object({runId:RunId,
    views:z.array(z.object({id:Id,image:Path,direction:Point3,up:Point3.default([0,0,1]),weight:z.number().positive().max(4).default(1),
      controlPoints:z.array(z.object({modelPixel:Pixel,referencePixel:Pixel}).strict()).min(3).max(64).optional(),
      region:z.object({center:Point3,radii:z.tuple([z.number().positive().max(100),z.number().positive().max(100),z.number().positive().max(100)]),feather:z.number().min(.01).max(.5).default(.2),provenance:z.string().min(1).max(1000)}).strict().optional(),
      provenance:z.string().min(1).max(1000)}).strict()).min(1).max(12),
    mappingMode:z.enum(['multi-view','primary-view']).default('multi-view'),
    textureResolution:z.number().int().min(512).max(2048).optional(),
    symmetryPlane:z.object({normal:Point3,offset:z.number().min(-1000).max(1000),maxDistanceFraction:z.number().positive().max(.1).default(.035),provenance:z.string().min(1).max(1000)}).strict().optional(),
    fallbackSRGB:z.tuple([z.number().min(0).max(1),z.number().min(0).max(1),z.number().min(0).max(1)]).default([.65,.4,.18]),
    provenance:z.string().min(1).max(2000)
  }).strict(),
  'noetra.reconstruct_calibrated_views':z.object({manifest:Path}).strict(),
  'noetra.inspect_image_structure': z.object({ images: z.array(Path).min(1).max(32) }).strict(),
  'noetra.reconstruct_multiview': z.object({
    pairs: z.array(z.object({ left: Path, right: Path }).strict()).min(4).max(16),
    pattern: z.tuple([z.number().int().min(4).max(15),z.number().int().min(4).max(12)]).default([9,6]),
    squareSizeMetres: z.number().positive().max(10).optional(),
    holdoutPair: z.number().int().min(0).max(15).default(0),
    initialScale: z.tuple([z.number().min(.5).max(1.5),z.number().min(.5).max(1.5)]).default([1,1])
  }).strict(),
  'noetra.generate_3d_construction': z.object({ runId: RunId }).strict(),
  'noetra.optimize_reconstruction': z.object({ runId: RunId, maxEvaluations: z.number().int().min(4).max(40).default(24) }).strict(),
  'noetra.compare_reference_render': z.object({ runId: RunId }).strict(),
  'noetra.export_reconstruction_report': z.object({ runId: RunId }).strict(),
  'noetra.prepare_part_correction': PartCorrectionSpec,
  'noetra.correct_parts': z.object({runId:RunId,maxCandidates:z.number().int().min(1).max(6).default(4)}).strict(),
  'noetra.inspect_part_correction': z.object({runId:RunId}).strict(),
  'noetra.build_outline_model':OutlineSpec,
  'noetra.reconstruction_backends':z.object({}).strict(),
  'noetra.refine_photo_appearance':z.object({runId:RunId}).strict(),
  'noetra.fit_photo_outline':z.object({runId:RunId}).strict(),
  'noetra.repair_photo_surface':z.object({runId:RunId}).strict(),
  'noetra.complete_from_prior':StructuralPriorSpec,
  'noetra.reconstruct_photos':z.object({
    images:z.array(Path).min(1).max(16),backend:z.enum(['triposr','colmap','hunyuan-mini']),
    quality:z.enum(['preview','standard','high']).default('standard'),
    foregroundMask:Path.optional()
  }).strict()
};
export type ReconstructionTool = keyof typeof reconstructionSchemas;
export const reconstructionDescriptions: Record<ReconstructionTool,string> = {
  'noetra.paint_appearance_preview':'Paint a separate geometry-preserving preview using actual source-pixel palette measurements from an appearance-analysis run and an existing explicitly authored project-local material layout. Software replaces colour choices with nearest measured Lab swatches; it does not infer anatomical placement or override analysis readiness. Requires mode unverified-preview, trusted local Blender/vision execution and bounded data-only layout. Produces PBR maps, BLEND/GLB and real renders; never projects photographs or replaces an accepted model.',
  'noetra.analyze_reference_appearance':'Automatically analyze project-local references without designing or changing a mesh: deterministic observed-colour families, spatial colour components, pixel boundaries, colour/lightness transitions and local texture directions. Preserve source hashes and output masks, diagrams and a reconstruction gate. Colour components are not anatomical parts; metric depth, intrinsic albedo and semantic-to-mesh correspondence remain unknown and block automatic material application. No model download, uploaded image, supplied paint masks or generic code execution.',
  'noetra.refine_base_surface':'Refine the existing base mesh inside explicitly authored small surface masks and assign authored surface materials. Preserve original topology, exact vertices outside the masks and prior checkpoints. Add no objects, photographic projections or overlay parts. Bounded deformations are checked for face reversal and backtracked; anatomical likeness is not established by these checks. Requires trusted Blender and vision runtimes, no caller code.',
  'noetra.paint_surface_material':'Paint an existing mesh with explicitly authored surface masks, palette gradients and procedural fine fur detail. Use real local xatlas UV generation and Blender baking to export packed sRGB base color, Non-Color roughness and tangent-normal maps, BLEND/GLB and eight actual renders. Preserve all geometry; no AI material recovery or exact photograph match is claimed. Requires trusted local vision and Blender runtimes; no caller scripts or automatic dependency installation.',
  'noetra.refine_learned_surface':'Re-extract a cached learned shape at a bounded surface resolution using only its pinned VAE decoder. Preserve the original latent identity, source images and earlier meshes; no new image conditioning or random shape sampling. Requires an existing safetensors shape checkpoint and trusted local provider/Blender configuration. Higher resolution cannot establish correct anatomy; visual acceptance remains required.',
  'noetra.colorize_reconstruction':'Create an immutable colored version of an existing mesh using attributed reference pictures and explicit approximate view directions. Transfer visible reference radiance into portable vertex colors with occlusion checks, matte materials and a declared fallback. Preserve every vertex and face, export colored BLEND/GLB and eight actual renders. This estimates alignment and appearance, not intrinsic PBR or exact textures; requires trusted Blender execution.',
  'noetra.reconstruct_calibrated_views':'Fuse three or more attributed calibrated silhouettes into a local visual-hull mesh, preserving original image bytes and exact camera/mask hashes. Requires a project-local data-only manifest and configured local vision environment. Rendered views remain derived hypotheses; silhouettes cannot recover hidden concavities, textures or physical truth. No source mesh is read by this reconstruction operation.',
  'noetra.inspect_image_structure':'Opt-in local OpenCV inspector: preserves original PNG/JPEG bytes; lossless full-resolution RGB arrays, blur/lighting statistics and geometric Canny edges. No automatic general semantic, depth or material inference.',
  'noetra.reconstruct_multiview':'Opt-in limited planar calibration-grid proof: detect known grid correspondences in stereo photographs, calibrate cameras on training pairs, triangulate a held-out pair and fit an editable sheet. Not general object/car reconstruction; physical scale needs a supplied measurement.',
  'noetra.generate_3d_construction':'Prepare a reproducible, fixed Blender construction adapter and spatial model for a reconstruction run. Preparing does not execute code or guarantee fidelity.',
  'noetra.optimize_reconstruction':'Bounded finite-difference sheet-scale experiment using observed landmarks and fixed recovered cameras; accept only after real matched-camera render validation. Blender execution needs separate trusted operator configuration, never caller-supplied permission.',
  'noetra.compare_reference_render':'Read actual before/candidate matched-camera renders and compare observed grid masks, boundaries, internal edges, landmarks and appearance; preserve unknown physical geometry/material scope.',
  'noetra.export_reconstruction_report':'Read a bounded compact reconstruction report and artifact paths after rechecking preserved source bytes. Does not serialize dense pixel arrays into prompts.',
  'noetra.prepare_part_correction':'Checkpoint a project-local existing Blender scene and attributed polygon observations; render per-part visibility masks and fingerprint geometry/cameras. Requires trusted local Blender execution consent. No automatic semantic segmentation or initial object inference.',
  'noetra.correct_parts':'Reusable bounded coordinate search: edit declared mesh/curve controls or translate one part; render and compare all annotated views, reject protected-geometry/camera changes and visual regressions. Preserve every candidate and the accepted best. Not universal image-to-3D reconstruction.',
  'noetra.inspect_part_correction':'Read measured per-part boundary/overlap errors, accepted/rejected correction history, preserved object fingerprints and checkpoint paths; recheck original scene, reference and artifact hashes.',
  'noetra.build_outline_model':'Build an editable 3D loft from an attributed front-view polygon or binary foreground mask; preserve the visible contour and explicitly label proposed depth/sides/rear. Render and measure the front silhouette. Requires an explicit front-orthographic assumption and trusted local Blender execution consent. Not general single-photo 3D inference.',
  'noetra.reconstruction_backends':'Inspect the explicitly configured local vision environment and library/model availability without inference, model download or image upload.',
  'noetra.refine_photo_appearance':'Project original observed image appearance onto visible faces of a validated local photo mesh. Preserve geometry/cameras and prior checkpoints; unseen faces retain learned appearance. This is view-dependent observed radiance, not intrinsic PBR or recovered geometric detail. Requires local Blender consent.',
  'noetra.fit_photo_outline':'Bounded near-contour camera-plane deformation of an existing single-photo mesh against its attributed foreground estimate. Preserve topology, camera, depth and distant interior vertices; accept only after actual Blender silhouette/boundary improvement. Not measured physical depth or hidden-shape recovery.',
  'noetra.repair_photo_surface':'Repair only the fixed contour neighbourhood of an existing generated photo mesh with bounded fairing, orientation checks and actual Blender silhouette/roughness acceptance. Preserve distant vertices, cameras and topology; export seven real viewpoints and neutral geometry inspections of the same mesh. No new inference, cloud upload or claimed hidden-shape truth.',
  'noetra.complete_from_prior':'Complete a project-local explicit geometric prior using attributed boundary-constrained patches and bounded local fairing. Protect undeclared parts, verify complete circular wheels, set ground clearance and frame every model vertex safely in seven real views. Requires a supplied trusted template and authored constraints; not automatic image-to-3D or recovered hidden geometry.',
  'noetra.reconstruct_photos':'Run an explicitly configured local backend: single-image TripoSR, staged isolated Hunyuan3D-2mini Turbo, or multi-photo CPU COLMAP structure-from-motion. Preserve source bytes, attributed masks, provider identity and exports. Hunyuan accepts one image, not multi-view fusion; source-detail fidelity, hidden surfaces and scale remain unverified. No automatic downloads or cloud transmission.'
};
export function isReconstructionTool(name: string): name is ReconstructionTool { return Object.hasOwn(reconstructionSchemas,name); }
