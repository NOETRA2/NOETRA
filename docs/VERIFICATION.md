# NOETRA alpha verification — 24 October 2026

## Outcome

A separate working Node.js/TypeScript project and one-package distribution were
created. No existing Nexa application source, Android install, Firebase/Supabase
configuration or real AI-client registration was changed. REA was reused, not
reinstalled. A source checkpoint was saved before subsequent engine revisions.

Environment actually tested: Windows, Node.js 26.3.0, npm 11.16.0. Linux, macOS
and Node 24 support are intended and have a CI matrix, but those matrix jobs have
not been run in this session.

## Completed checks

| Check | Observed result |
| --- | --- |
| Strict TypeScript check | Passed |
| Production compilation | Passed |
| Automated suite | 29 tests passed across 6 files |
| Real NOETRA stdio connection | Official MCP SDK client handshake, 10 tools discovered, validated calls |
| SQLite persistence | Survived engine close and MCP reconnect; project isolation and immutable revisions passed |
| Actual Z3 | Inconsistent energy constraints, scoped implication, counterexample and inconsistent-premise rejection passed |
| Planning | Missing rig, prerequisite ordering, cycles and failed dependencies passed |
| Hypothesis revision | Contradictory observation retained with prior revision and evidence |
| Imported hostile text | Retained as untrusted data; no command execution/config/source mutation |
| Setup | Disposable JSON configs only; exact backups, preservation, conflict checks and rollback passed |
| REA unavailable/scope limits | Core remained functional; out-of-root/parent traversal/oversized-source/missing-package checks passed |
| Existing REA connection | Official 6.7.0 package, MIT metadata, live version match, 207 tools discovered |
| Real REA fixture investigation | Static Electron summary and source-fact view captured with IDs and limitations |
| Package installation | Tarball installed in an empty output directory; only NOETRA appeared as the root installed product |
| Packaged CLI self-test | Passed live MCP/SQLite/Z3 test from that independent installation |
| Runtime npm audit | Registry audit reported zero known runtime vulnerabilities; not a security certification |

The first restricted-sandbox runs failed temporary source-transfer access in REA
and temporary config renames in setup tests. The same scoped tests passed in the
approved normal execution environment. No browser security settings, OS policy,
existing client config or file permissions were weakened to make them pass.

## Actual software-investigation evidence

Target: NOETRA-owned synthetic `examples/software-investigation/electron-sample`.
Selected sources: package.json, main.js, preload.js. The HTML was unselected.
No Electron installation, target execution, real account or personal software
inspection was required.

- REA observed one BrowserWindow, one preload entrypoint, one context-bridge API,
  one renderer transmission and one main handler.
- Selected source facts recorded `invoke` on `navigation:open` in preload.js and
  `handle` on `navigation:go` in main.js. There were zero paired transmissions
  and one unpaired literal transmission in the selected static analysis.
- A mismatched static channel boundary is a derived finding, not proof of all
  runtime behavior. The fixture intentionally contains that defect.
- Parent evidence:
  `ev_008650c7ace66757a64c2afdef19f8eadb9727a0e871ba616f53ed91dd9c130d`.
- Summary evidence:
  `ev_435efb65df70265cf7bab43fff1a30c5fb7aecaa924815f9cf4bbfa9783dd9e2`.
- Coverage explicitly remained partial for the application and unknown for some
  semantic relationships. One application unknown and 34 semantic unknowns were
  retained by REA. These were not presented as complete analysis.

`scripts/verify-rea.mjs` validates the finding against the actual returned facts,
builds an attributed world model and prerequisite plan, and saves the workflow
under `.noetra/verification/`. The independent URL boundary example has executable
tests for HTTPS normalization and rejecting file/script/credential-bearing URLs.
That is not an Electron runtime/UI reconstruction or runtime navigation test.
Raw local evidence and databases are excluded from distribution.

## Files and boundaries

All new source is under `noetra/`. Main groups:

- `apps/cli/src`: commands, safe JSON setup/rollback, protocol self-test.
- `packages/shared-types`, `core`: schemas, status/error contracts and orchestration.
- `packages/cognition`, `world-model`, `memory`: attribution, graph validation,
  SQLite revisions/expiry/export/deletion.
- `packages/logic`, `planner`, `causality`, `imagination`, `verification`:
  deterministic reasoning, Z3 worker, planning, predictions and scoped checks.
- `packages/mcp-server`, `mcp-client`, `integrations/rea`, `sdk`: agent interfaces,
  approved subprocess bridge and the public library.
- `tests/`, `examples/`, `docs/`, `scripts/`, `.github/workflows/`: executable checks,
  authorized fixtures, documentation and release tooling.

Output checkpoints, disposable clean installs and standalone/source archives are
kept separately under the enclosing workspace's `output/` directory. They do not
modify sibling project source.

## Not finished / not claimed

- A real Codex/Claude/Cursor UI/model reconnect has not been tested. The successful
  test uses the official protocol client, not an LLM host. Actual registration
  remains opt-in; Codex TOML auto-editing is not implemented.
- Generic natural-language/vision perception, original generative imagination,
  explicit provider implementations, token/cost-budgeted model calls, a full
  autonomous investigation/experiment/replanning loop and execution sandboxes are
  not implemented. Hosts supply structured interpretations/candidates.
- Causal links are supplied hypotheses, not learned causal truth. The planner
  handles monotonic prerequisites/effects, not general resource-consuming plans.
- Optional REA auto-download, Python/browser/Blender/native-binary integrations,
  broad client discovery and fully typed per-operation output payload contracts
  remain future work. No placeholder tool reports these as working.
- Imported observations are not automatically authenticated. SQLite is plaintext.
  Package metadata validation is not signature verification or an OS sandbox.
- No host-with/without-NOETRA A/B benchmark has been run. No claim of improved
  general intelligence, human-like cognition or subjective aesthetic proof.
- No npm/GitHub publication, signing, security audit or store release occurred.

The attached full specification is a roadmap. This deliverable is an independently
installable, tested **developer alpha foundation**, not completion of every phase.
