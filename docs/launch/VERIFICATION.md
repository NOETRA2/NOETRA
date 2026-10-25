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
| MCP metadata | Official JSON Schema and official publisher/server validation passed; identifiers/versions match the public npm package |
| Hugging Face bundle | Exported; runtime-only dependency install, protocol self-test and a real formal example passed outside the source checkout |
| Docker image | Not tested: local Docker startup failed; Hub Docker hosting requires PRO for this account; no paid plan was purchased |
| Free static Space | Uploaded under NOETRA2; public deployment reports RUNNING; contains recorded results, not a remote engine |
| Public preview browser QA | Remote browser checked all five tabs, result inspection, pinned commands, install links, video and poster; passed with no reported layout issues |
| Local demo browser layout | Local browser access remained disabled in Work settings; its HTTP behavior was tested separately |
| Walkthrough | 60.000-second silent presentation of real captured results; result cards, not browser footage |
| npm publication | `noetra@0.1.0-alpha.4` public, publisher harshavardhan2; registry integrity exactly matches reviewed artifact; fresh anonymous install passed the protocol/solver self-test |
| Official MCP Registry publication | Published `io.github.NOETRA2/noetra@0.1.0-alpha.4`; public listing independently checked against the npm package identifier and version |
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
host. The npm publication and exact-version install were verified separately.
