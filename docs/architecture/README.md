# Architecture and boundaries

One root npm artifact contains the compiled private workspace modules. It has no
relative dependency on any sibling Nexa project.

```text
AI host / TypeScript consumer
       -> NOETRA MCP server / SDK
       -> validated core operations
          cognition (attribution, not hidden semantic invention)
          world model -> immutable SQLite revisions
          logic -> deduction + bounded Z3 worker
          planner -> dependency/precondition ordering
          imagination -> host-supplied structured candidate evaluation
          verification -> formal entailment and attributed observations
          visual-design -> reference lock, bounded host-edit packet, attributed review gates
       -> optional reconstruction -> fixed local Python geometry worker -> approved fixed Blender adapter
          causality -> explicit intervention helper (SDK)
       -> optional REA MCP client -> official REA subprocess
```

`apps/cli` owns setup/diagnostics and stdio lifecycle. `packages/shared-types`
owns shared Zod contracts. `core` coordinates operations. Visual-design builds
explicit reference-edit prompts for a host; it has no bundled model/provider.
`memory` uses parameterized SQL, WAL, project-qualified
queries, append-only revisions and optimistic revision checks. Identifiers are
namespaces, not authentication: the trusted local process user can access local
files. For stronger tenant isolation, use separate OS accounts and databases.

Default memory path: `<explicit project>/.noetra/memory.sqlite`. Project IDs
default to a SHA-256-derived identifier of the supplied absolute project path.
CLI resolves the path canonically. The SDK accepts a project identifier/path so
applications can define stable project identity. Moving a project can change its
default identity; export records first or configure an explicit SDK project ID.

No outbound network requests are made by core reasoning. Initial npm installation
requires package-registry access; enabled external providers may have their own
network behavior. No model provider is configured by default.

## Evidence policy

OBSERVED records the receipt of an attributed observation, not the truth of its
claim. DERIVED means a deterministic conclusion conditional on premises.
HYPOTHESIS is a proposed interpretation. VERIFIED is issued only by the scoped
formal entailment operation. CONTRADICTED marks a discovered inconsistency or
attributed refutation. UNKNOWN means unsupported, unavailable or resource-limited.

Hypothesis updates require supporting record IDs and expected revision. Earlier
revisions are kept. The public observation schema cannot set a verification
status. Imported model output and REA text are never executed.

## Extension boundary

`ModelAdapter` specifies an optional explicit model adapter contract, but no
provider is shipped. Hosts generate concepts and pass typed candidates. A future
adapter must enforce token/cost/time budgets, consent and privacy. Python,
generic external-tool execution, vision and full autonomous experimentation are
not implemented; there are no placeholder tools claiming otherwise.

Alpha.3's optional reconstruction worker is deliberately narrower than generic
Python/vision execution: fixed schemas, fixed packaged source, project-local
image/array/scene data, known calibration-grid geometry and operator-approved
Blender rendering. No LLM-generated code string is evaluated. See RECONSTRUCTION.md.
