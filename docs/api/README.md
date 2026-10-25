# Public API — alpha

Every tool returns this validated envelope:

```ts
{
  ok: boolean;
  status: 'OBSERVED' | 'DERIVED' | 'HYPOTHESIS' | 'VERIFIED' | 'CONTRADICTED' | 'UNKNOWN';
  data: Record<string, unknown>;
  limitations: string[];
  error?: { code: string; message: string };
}
```

Most successful outputs contain `data.record` with `project`, `id`, `kind`,
`revision`, `createdAt`, `expiresAt` and the operation's `value`. Records are
immutable revisions. The output envelope is machine-validated; operation-specific
payload types are still alpha and are not a stable versioned API. Full validated
input contracts are exported as `schemas` and advertised through MCP tools/list.
Unknown input properties are rejected. Project scope is fixed by engine startup,
not caller-controlled project IDs.

| Operation | Inputs | Payload / permission |
| --- | --- | --- |
| analyze_problem | text, optional attributed assertions, hypotheses | World record, created hypothesis records, REA enabled flag; local writes |
| build_world_model | world, optional id + expectedRevision | Validated graph revision; references/IDs checked; local writes |
| check_logic | world | Deduction closure, rule premises, assumptions, contradictions, completeness and optional Z3 consistency/model; local writes |
| explore_possibilities | candidates, requirements, maxCost | Ranked structured candidates with unmet requirements and estimated-budget fit; local writes |
| create_plan | goal, actions, available, optional id + expectedRevision | Order, blocked reasons, cycles, failed tasks, predicted available facts; local writes |
| verify_claim | premises[], claim | Z3 consistency, entailment/counterexample, method, scope and next experiment; local writes |
| investigate_software | target, scope, authorization, sourcePaths | Scoped REA evidence record; separately enabled trusted package/roots required |
| record_evidence | claim, origin, method, observation, optional limitations/expiry | Attributed untrusted evidence with SHA-256 digest; cannot set VERIFIED |
| revise_hypothesis | id, expectedRevision, conclusion, outcome, evidenceIds, reason | New hypothesis revision plus history; referenced evidence must exist/unexpired |
| get_reasoning_report | optional id or limit | Read-only project records/history, integration state and interpretation limits |
| design_visual | action: create / anchor / prepare / attach-output / review / status | Reference-locked visual state; bounded project-local PNG reads and versioned local writes; does not invoke a generator |

All names are prefixed `noetra.` in MCP. `outcome` is supported/refuted/unresolved;
support never auto-promotes a hypothesis to VERIFIED. `classification` is
premise/assumption/unknown; no premise is automatically a factual truth.

Alpha.3 also exports six optional reconstruction schemas. They are advertised by
MCP only when the operator explicitly supplies a reconstruction runtime config;
direct SDK calls without configuration fail with RECONSTRUCTION_DISABLED. See
[reconstruction](../RECONSTRUCTION.md) for actual inputs, consent, limits and
the planar-grid-only scope. Proposed but unimplemented tools are not advertised.

Typed formal constraints are bounded sums of integer variables with constant
coefficients, relation eq/ne/lt/le/gt/ge and an integer constant. Arbitrary code,
SMT-LIB, nonlinear expressions and unbounded recursion are not accepted.

```ts
import { NoetraEngine } from 'noetra';
const engine = new NoetraEngine({ projectRoot: '/absolute/authorized/project' });
try {
  const result = await engine.call('noetra.verify_claim', {
    premises: [{ id: 'p', terms: [{ variable: 'x', coefficient: 1 }], relation: 'ge', value: 2 }],
    claim: { id: 'c', terms: [{ variable: 'x', coefficient: 1 }], relation: 'ge', value: 1 }
  });
  // VERIFIED here means implication within the supplied integer model.
} finally { engine.close(); }
```

Additional SDK exports: `Memory`, `deduce`, `solve`, `createPlan`, `intervene`,
`rankCandidates`, `compareExperiment`, shared Zod schemas/types and ModelAdapter
interface. These do not expose arbitrary shell/code execution. Cancellation is
accepted through `AbortSignal` on engine/solver/investigation operations.

`design_visual` uses `{ action: { kind: '...', ... } }`. Mutations after create
require `designId` and `expectedRevision`; status requires only `designId`.
Prepare mode is detail-edit, turnaround, or 3d-brief. Reference PNGs must be
regular files inside the active project (no junction/symlink traversal); later
operations recheck the recorded bytes. Attach-output requires the prepared job's
exact reference IDs. Reviews must cite those references and per-feature findings.
Only attributed assessments are recorded; a reviewer calling something a match
does not establish independent visual verification. Numeric contradictions and
unknown/missing observations cannot pass a gate. See [visual upgrade](../VISUAL-UPGRADE.md).

Errors include VALIDATION_ERROR, INPUT_LIMIT, BUSY, REVISION_CONFLICT,
MISSING_EVIDENCE, NOT_FOUND, REA_DISABLED, TARGET_NOT_AUTHORIZED,
REA_UNAVAILABLE, REA_CAPABILITY_MISSING and REA_TOOL_FAILED. Failures are UNKNOWN
with `ok:false`; raw external errors/source text are not diagnostic logs.
