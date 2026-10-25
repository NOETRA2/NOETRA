# Launch preparation verification

25 October 2026 · `0.1.0-alpha.4` · local Windows / Node.js 26.3.0.

| Check | Result |
| --- | --- |
| TypeScript and production build | Passed |
| Node regression suite | 71 tests passed in nine files |
| Packaged artifact in a fresh local install | Passed; no repository workspace dependencies used |
| Installed MCP / SQLite / Z3 self-test | Passed |
| Cursor setup against dummy settings | Preview made no changes; apply preserved an existing REA entry; rollback restored exact original bytes |
| Windows bundle installer | Passed into a new dedicated directory; no global install, PATH change or real client registration |
| Actual demo outputs | Entailment, counterexample, blocked plan, feasible plan and attributed observation captured |
| HTTP demo behavior | Built server tested, including input bounds, cross-origin rejection, fixed routes and independent evidence runs |
| MCP metadata | Validated against official 2025-12-11 JSON Schema; identifiers/versions match package metadata |
| Hugging Face bundle | Exported; runtime-only dependency install, protocol self-test and a real formal example passed outside the source checkout |
| Docker image / live Space | Not tested: Docker daemon unavailable; no Hugging Face account supplied |
| Browser layout and interactive visual check | Pending: browser use remained disabled in Work settings |
| Walkthrough | 60.000-second silent presentation of real captured results; result cards, not browser footage |
| npm / official registry publication | Not performed; owner accounts/authentication and registry-side ownership validation pending |
| Product Hunt / Show HN | Drafts prepared; not posted |
| Independent developer adoption | Not measured; local maintainer test installs are not counted as users |

The original reconstruction's Python test results and mesh comparisons are
separate historical evidence; the launch changes do not improve or retrain the
underlying reconstruction models. No new 3D accuracy claim is made.

## Reproduce

```sh
npm ci --ignore-scripts
npm run check
npm run test:package
node scripts/capture-demo.mjs ../demo-results
node scripts/prepare-space.mjs ../NOETRA-space
```

`test:package` builds/packs NOETRA, installs the tarball in a fresh temporary
folder and runs the installed CLI. It uses fixture client settings only. Its
report gives the local artifact directory for inspection. It never publishes.

JSON Schema validation does not prove ownership, publication or a connected AI
host. The package name remains proposed until npm accepts the owner's publish.
