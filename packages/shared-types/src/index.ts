import { z } from 'zod';

export const VERSION = '0.1.0-alpha.4';
export function supportedNode(version = process.versions.node): boolean {
  const [major = 0, minor = 0] = version.replace(/^v/, '').split('.').map(Number);
  return major >= 26 || (major === 24 && minor >= 11);
}
export const Id = z.string().min(1).max(100).regex(/^[a-zA-Z0-9_.:-]+$/);
export const Text = z.string().min(1).max(8000);
export const Status = z.enum(['OBSERVED', 'DERIVED', 'HYPOTHESIS', 'VERIFIED', 'CONTRADICTED', 'UNKNOWN']);
export type Status = z.infer<typeof Status>;
export const Origin = z.object({
  kind: z.enum(['user', 'host-model', 'tool', 'formal-check']),
  reference: Text,
  timestamp: z.iso.datetime()
}).strict();
export const Assertion = z.object({
  id: Id, proposition: Text, negated: z.boolean().default(false),
  classification: z.enum(['premise', 'assumption', 'unknown']).default('assumption'),
  origin: Origin, evidenceIds: z.array(Id).max(100).default([])
}).strict();
export type Assertion = z.infer<typeof Assertion>;
export const Rule = z.object({ id: Id, when: z.array(Id).min(1).max(32), then: Id }).strict();
export type Rule = z.infer<typeof Rule>;
export const Constraint = z.object({
  id: Id,
  terms: z.array(z.object({ variable: Id, coefficient: z.number().int().min(-1000000).max(1000000) }).strict()).min(1).max(32),
  relation: z.enum(['eq', 'ne', 'lt', 'le', 'gt', 'ge']),
  value: z.number().int().min(-1000000000).max(1000000000)
}).strict();
export type Constraint = z.infer<typeof Constraint>;
export const Entity = z.object({ id: Id, type: Id, properties: z.record(Id, z.union([z.string().max(4000), z.number().finite(), z.boolean(), z.null()])).default({}) }).strict();
export const Relation = z.object({ from: Id, to: Id, kind: Id, evidenceIds: z.array(Id).max(32).default([]) }).strict();
export const World = z.object({
  goal: Text,
  entities: z.array(Entity).max(300).default([]),
  relations: z.array(Relation).max(1000).default([]),
  assertions: z.array(Assertion).max(500).default([]),
  rules: z.array(Rule).max(200).default([]),
  constraints: z.array(Constraint).max(128).default([]),
  unknowns: z.array(Text).max(100).default([])
}).strict();
export type World = z.infer<typeof World>;
export const Action = z.object({
  id: Id, description: Text,
  dependsOn: z.array(Id).max(100).default([]),
  requires: z.array(Id).max(100).default([]),
  provides: z.array(Id).max(100).default([]),
  state: z.enum(['pending', 'completed', 'failed']).default('pending')
}).strict();
export type Action = z.infer<typeof Action>;
export const Candidate = z.object({
  id: Id, concept: Text, origin: Origin,
  components: z.array(Text).max(30),
  satisfies: z.array(Id).max(50),
  estimatedCost: z.number().nonnegative().max(1e9),
  risks: z.array(Text).max(30),
  testPlan: z.array(Text).min(1).max(30)
}).strict();
export type Candidate = z.infer<typeof Candidate>;
export const EvidenceInput = z.object({
  claim: Text, origin: Origin, method: Text,
  observation: z.string().min(1).max(65536),
  limitations: z.array(Text).max(100).default([]),
  expiresAt: z.iso.datetime().optional()
}).strict();
export type EvidenceInput = z.infer<typeof EvidenceInput>;
export interface Evidence extends EvidenceInput {
  id: string; status: Status; untrusted: true; digest: string;
}
export const Result = z.object({
  ok: z.boolean(), status: Status,
  data: z.record(z.string(), z.unknown()),
  limitations: z.array(z.string()),
  error: z.object({ code: z.string(), message: z.string() }).optional()
});
export type Result = z.infer<typeof Result>;
export class NoetraError extends Error {
  constructor(public readonly code: string, message: string) { super(message); this.name = 'NoetraError'; }
}
export function fail(code: string, message: string): never { throw new NoetraError(code, message); }
export function uniqueIds(items: ReadonlyArray<{ id: string }>): void {
  if (new Set(items.map(x => x.id)).size !== items.length) fail('DUPLICATE_ID', 'Identifiers must be unique within a collection.');
}
export function success(data: Record<string, unknown>, status: Status = 'DERIVED', limitations: string[] = []): Result {
  return { ok: true, status, data, limitations };
}
