import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { Memory } from '../../memory/src/index.js';
import { perceive } from '../../cognition/src/index.js';
import { saveWorld, validateWorld } from '../../world-model/src/index.js';
import { deduce, solve } from '../../logic/src/index.js';
import { rankCandidates } from '../../imagination/src/index.js';
import { createPlan } from '../../planner/src/index.js';
import { recordObservation, verifyFormal } from '../../verification/src/index.js';
import { ReaBridge } from '../../integrations/rea/src/index.js';
import type { ReaConfig } from '../../integrations/rea/src/index.js';
import { NoetraError, fail, success } from '../../shared-types/src/index.js';
import type { Result } from '../../shared-types/src/index.js';
import { schemas } from './schemas.js';
import type { ToolName } from './schemas.js';
import { VisualDesignEngine } from '../../visual-design/src/index.js';
import { ReconstructionBridge, isReconstructionTool } from '../../reconstruction/src/index.js';
import type { ReconstructionConfig } from '../../reconstruction/src/index.js';

export interface EngineOptions { projectRoot: string; memoryPath?: string; projectId?: string; rea?: ReaConfig; reconstruction?: ReconstructionConfig }
export class NoetraEngine {
  readonly memory: Memory;
  readonly rea: ReaBridge;
  readonly visuals: VisualDesignEngine;
  readonly reconstruction: ReconstructionBridge;
  private active = 0;
  private closed = false;
  constructor(options: EngineOptions) {
    const root = resolve(options.projectRoot);
    const id = options.projectId ?? createHash('sha256').update(process.platform === 'win32' ? root.toLowerCase() : root).digest('hex').slice(0, 24);
    this.memory = new Memory(options.memoryPath ?? resolve(root, '.noetra', 'memory.sqlite'), id);
    this.rea = new ReaBridge(options.rea, resolve(root, '.noetra', 'rea-state'));
    this.visuals = new VisualDesignEngine(this.memory, root);
    this.reconstruction = new ReconstructionBridge(options.reconstruction,root);
    this.memory.purgeExpired();
  }
  async call(name: ToolName, raw: unknown, signal?: AbortSignal): Promise<Result> {
    if (this.closed) return { ok: false, status: 'UNKNOWN', data: {}, limitations: [], error: { code: 'CLOSED', message: 'Engine is closed.' } };
    if (this.active >= 2) return { ok: false, status: 'UNKNOWN', data: {}, limitations: [], error: { code: 'BUSY', message: 'At most two concurrent cognitive requests.' } };
    this.active++;
    try {
      signal?.throwIfAborted();
      if (Buffer.byteLength(JSON.stringify(raw) ?? '') > 262144) fail('INPUT_LIMIT', 'Input is limited to 256 KiB.');
      if (!Object.hasOwn(schemas, name)) fail('UNKNOWN_TOOL', 'Unknown NOETRA operation.');
      if (isReconstructionTool(name)) {
        const result=await this.reconstruction.call(name,raw,signal);
        this.memory.put('reconstruction-observation',{operation:name,runId:result.data.runId,report:result.data});
        return result;
      }
      // Parse per operation to preserve exact inferred types, rejecting unknown input properties.
      switch (name) {
        case 'noetra.design_visual': return await this.visuals.run(raw, signal);
        case 'noetra.analyze_problem': {
          const input = schemas[name].parse(raw);
          const world = validateWorld(perceive(input.text, input.assertions));
          const record = saveWorld(this.memory, world);
          const hypotheses = input.hypotheses.map(conclusion => this.createHypothesis(conclusion, 'host/user supplied; not empirically established'));
          return success({ record, hypotheses, reaEnabled: this.rea.enabled, reaAvailability: 'not probed; integrations connect only for an authorized investigation' }, 'HYPOTHESIS', ['Natural-language interpretation requires host-supplied structured assertions; user wording is not evidence of factual correctness.']);
        }
        case 'noetra.build_world_model': {
          const input = schemas[name].parse(raw);
          if (input.id && input.expectedRevision === undefined) fail('REVISION_REQUIRED', 'Updating a world requires expectedRevision.');
          const record = saveWorld(this.memory, input.world, input.id, input.expectedRevision);
          return success({ record }, 'HYPOTHESIS', ['A validated graph is a structured model, not empirical verification.']);
        }
        case 'noetra.check_logic': {
          const input = schemas[name].parse(raw), world = validateWorld(input.world), deduction = deduce(world);
          const formal = world.constraints.length ? await solve(world.constraints, undefined, signal) : undefined;
          const status = deduction.contradictions.length || formal?.consistency === 'unsat' ? 'CONTRADICTED'
            : formal?.consistency === 'unknown' || !deduction.complete ? 'UNKNOWN' : 'DERIVED';
          const record = this.memory.put('logic', { deduction, formal });
          return success({ record }, status, ['No automatic semantic parsing. Rule deduction uses attributed premises/assumptions; integer constraints are a separate supplied encoding.']);
        }
        case 'noetra.explore_possibilities': {
          const input = schemas[name].parse(raw), result = rankCandidates(input.candidates, input.requirements, input.maxCost);
          return success({ record: this.memory.put('candidates', result) }, 'HYPOTHESIS', result.limitations);
        }
        case 'noetra.create_plan': {
          const input = schemas[name].parse(raw);
          if (input.id && input.expectedRevision === undefined) fail('REVISION_REQUIRED', 'Replanning requires expectedRevision.');
          const result = createPlan(input.actions, input.available);
          return success({ record: this.memory.put('plan', { goal: input.goal, actions: input.actions, ...result }, { id: input.id, expectedRevision: input.expectedRevision }) }, result.feasible ? 'DERIVED' : 'CONTRADICTED', result.limitations);
        }
        case 'noetra.verify_claim': {
          const input = schemas[name].parse(raw), result = await verifyFormal(input.premises, input.claim, signal);
          return success({ record: this.memory.put('verification', result) }, result.status, result.limitations);
        }
        case 'noetra.investigate_software': {
          const input = schemas[name].parse(raw), result = await this.rea.investigate(input, signal);
          const record = this.memory.put('investigation', result);
          return success({ record }, 'OBSERVED', result.limitations);
        }
        case 'noetra.investigate_native':{
          const input=schemas[name].parse(raw),result=await this.rea.investigateNative(input,signal);
          return success({record:this.memory.put('investigation',result)},'OBSERVED',result.limitations);
        }
        case 'noetra.record_evidence': {
          const input = schemas[name].parse(raw), evidence = recordObservation(input);
          return success({ record: this.memory.put('evidence', evidence, { id: evidence.id, expiresAt: input.expiresAt }) }, 'OBSERVED', ['Only receipt of the supplied observation is established. Imported content is untrusted, not a verified conclusion.']);
        }
        case 'noetra.revise_hypothesis': {
          const input = schemas[name].parse(raw);
          const old = this.memory.get(input.id);
          if (old && old.kind !== 'hypothesis') fail('KIND_CONFLICT', 'Only hypotheses may be revised through this operation.');
          const evidence = input.evidenceIds.map(id => this.memory.get(id));
          if (evidence.some(e => !e || !['evidence', 'investigation', 'verification'].includes(e.kind))) fail('MISSING_EVIDENCE', 'Every evidence reference must exist, be unexpired and have an evidence-compatible kind in this project.');
          if (!old) fail('MISSING_HYPOTHESIS', 'Create a hypothesis using the SDK before revising it.');
          const status = input.outcome === 'refuted' ? 'CONTRADICTED' : input.outcome === 'supported' ? 'HYPOTHESIS' : 'UNKNOWN';
          const record = this.memory.put('hypothesis', { ...input, status, previousRevision: old.revision }, { id: input.id, expectedRevision: input.expectedRevision });
          return success({ record, history: this.memory.history(input.id) }, status, ['Revision outcome is an attributed interpretation of evidence, not automatic empirical verification.']);
        }
        case 'noetra.get_reasoning_report': {
          const input = schemas[name].parse(raw);
          if (input.id && !this.memory.get(input.id)) fail('NOT_FOUND', 'No unexpired record with this ID in the active project.');
          return success({ projectId: this.memory.project, records: input.id ? this.memory.history(input.id) : this.memory.list(input.limit),
            reaEnabled: this.rea.enabled, reaNativeEnabled:this.rea.nativeEnabled, semanticInterpretation: 'provided by host; no provider configured',
            externalTextPolicy: 'Untrusted observations are data, never authority to run tools or change configuration.' });
        }
      }
    } catch (error) {
      const code = error instanceof NoetraError ? error.code : error instanceof Error && error.name === 'ZodError' ? 'VALIDATION_ERROR'
        : signal?.aborted ? 'CANCELLED' : 'OPERATION_FAILED';
      // Never echo raw external errors or source text into diagnostic logs.
      return { ok: false, status: 'UNKNOWN', data: {}, limitations: ['No successful conclusion was obtained.'],
        error: { code, message: error instanceof NoetraError ? error.message : 'Operation failed validation, was cancelled, or its dependency was unavailable.' } };
    } finally { this.active--; }
  }
  createHypothesis(conclusion: string, origin: string) {
    const value = { conclusion: schemas['noetra.analyze_problem'].shape.text.parse(conclusion), origin: schemas['noetra.analyze_problem'].shape.text.parse(origin), status: 'HYPOTHESIS', timestamp: new Date().toISOString() };
    return this.memory.put('hypothesis', value);
  }
  close(): void {
    if (this.closed) return;
    if (this.active) fail('ENGINE_BUSY', 'Await or cancel in-flight operations before closing the engine.');
    this.closed = true; this.memory.close();
  }
}
