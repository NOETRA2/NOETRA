import { z } from 'zod';
import { Id } from '../../shared-types/src/index.js';

export const View = z.enum(['front-three-quarter', 'rear-three-quarter', 'front', 'rear', 'side', 'top', 'detail']);
export type View = z.infer<typeof View>;
const Short = z.string().min(1).max(600);
export const Feature = z.object({
  id: Id, description: Short,
  layer: z.enum(['silhouette', 'proportions', 'parts', 'materials', 'microdetail']),
  importance: z.enum(['critical', 'important']),
  views: z.array(View).min(1).max(7),
  measure: z.discriminatedUnion('kind', [
    z.object({ kind: z.literal('appearance') }).strict(),
    z.object({ kind: z.literal('count'), expected: z.number().int().nonnegative().max(1000) }).strict(),
    z.object({ kind: z.literal('scalar'), expected: z.number().finite(), tolerance: z.number().nonnegative().finite(), unit: z.string().min(1).max(40) }).strict()
  ])
}).strict();
export type Feature = z.infer<typeof Feature>;
export const VisualBrief = z.object({
  subject: z.string().min(1).max(400),
  goal: z.string().min(1).max(1200),
  identityFeatures: z.array(Feature).min(1).max(24),
  detailFeatures: z.array(Feature).min(1).max(24),
  required3dViews: z.array(View).min(3).max(7).default(['front', 'side', 'rear']),
  maxImageAttempts: z.number().int().min(1).max(8).default(3)
}).strict();
export type VisualBrief = z.infer<typeof VisualBrief>;
export const Observation = z.object({
  featureId: Id, finding: z.enum(['match', 'mismatch', 'unknown']),
  measuredValue: z.number().finite().optional(),
  note: Short
}).strict();
export type Observation = z.infer<typeof Observation>;
export const VisualRequest = z.object({ action: z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('create'), brief: VisualBrief }).strict(),
  z.object({ kind: z.literal('anchor'), designId: Id, expectedRevision: z.number().int().positive(), path: z.string().min(1).max(4096), view: View }).strict(),
  z.object({ kind: z.literal('prepare'), designId: Id, expectedRevision: z.number().int().positive(), mode: z.enum(['detail-edit', 'turnaround', '3d-brief']), view: View }).strict(),
  z.object({ kind: z.literal('attach-output'), designId: Id, expectedRevision: z.number().int().positive(), jobId: Id,
    path: z.string().min(1).max(4096), sourceReferenceIds: z.array(Id).min(1).max(8), generator: Short }).strict(),
  z.object({ kind: z.literal('review'), designId: Id, expectedRevision: z.number().int().positive(), assetId: Id,
    referenceIds: z.array(Id).min(1).max(8), reviewer: z.enum(['human', 'host-model', 'vision-adapter']),
    method: Short, observations: z.array(Observation).min(1).max(48) }).strict(),
  z.object({ kind: z.literal('status'), designId: Id, assetId: Id.optional() }).strict()
]) }).strict();
export type VisualRequest = z.infer<typeof VisualRequest>;
export interface VisualAsset {
  id: string; role: 'anchor' | 'candidate'; path: string; sha256: string;
  width: number; height: number; bytes: number; view: View; registeredAt: string;
  jobId?: string; sourceReferenceIds: string[]; generator?: string;
}
export interface VisualJob {
  id: string; designRevision: number; mode: 'detail-edit' | 'turnaround'; view: View;
  referenceIds: string[]; prompt: string; createdAt: string;
}
export interface VisualReview {
  id: string; assetId: string; assetSha256: string; referenceIds: string[];
  reviewer: 'human' | 'host-model' | 'vision-adapter'; method: string;
  observations: Observation[]; createdAt: string;
}
export interface VisualState {
  contractVersion: 1; brief: VisualBrief; assets: VisualAsset[]; jobs: VisualJob[]; reviews: VisualReview[];
}
