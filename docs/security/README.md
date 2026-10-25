# Security model and release gaps

- Trusted local host/operator, local process permissions. No network listener or
  remote authentication service is exposed; stdio is the only shipped transport.
- Core has no arbitrary shell, generated-code evaluator, autonomous installer,
  credential reader, telemetry sender or model-provider API. No personal browser
  profile is accessed. Text/REA evidence cannot change integrations or invoke code.
- REA launch comes only from reviewed local configuration and the official
  package's public bin. Process args are arrays, not a generated shell command.
  External subprocesses get the SDK's safe environment allowlist, not all secrets.
- Zod strict inputs; bounded strings/collections/transport, two concurrent core
  operations, at most 64 rule rounds, bounded planner graph, lazy Z3 workers with
  solver and wall-clock timeouts. Only validated integer constraints reach Z3.
- SQLite uses parameter bindings and project-qualified queries. It is plaintext,
  not a cryptographic vault or tenant-authentication boundary. OS encryption and
  access control remain important. Backups/export are the operator's responsibility.
- Evidence statuses preserve epistemic scope. Formal proof is conditional; model
  agreement is never empirical verification. No confidence percentages are invented.
- Visual-design accepts bounded, project-local immutable PNGs, validates their
  container and hashes, and stores attributed reviews. It has no image decoder,
  semantic vision model, automatic provider request or assurance of exact object
  identity. A trusted host chooses whether to upload a reference to its editor.
- Optional reconstruction is disabled by default. A trusted operator selects
  absolute Python/Blender runtimes and separately approves fixed-template Blender
  execution. MCP callers cannot grant that permission, choose arbitrary script
  paths or submit code. Originals and spatial/render evidence are hashed and
  rechecked; dense arrays stay local. A fresh process is not an OS sandbox for
  arbitrary untrusted code. No remote model adapter or private-image upload ships.
- Setup defaults to preview, requires explicit apply confirmation, keeps backups
  and checks for changed settings. It has no silent host registration. Codex
  setup is manually reviewed in the alpha. Rollback refuses intervening changes.
- The optional REA subprocess is not an OS sandbox. NOETRA narrows the callable
  tool surface and canonical file scope, but an operator must trust the installed
  REA distribution. Do not point it at secrets or unauthorized software. Native
  binary execution, generic execution tools and internet browsing are not enabled.

Before public release: independent security review, broader adversarial/resource
tests, dependency/license audit, signed/versioned release process, stronger
operation-specific output contracts, installer cross-platform validation and a
real end-user host reconnect check. Checksums detect accidental corruption; they
are not signatures or publisher identity verification. No administrator rights
should normally be needed for the user-local install.
