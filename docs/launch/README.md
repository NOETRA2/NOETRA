# NOETRA launch preparation

Prepared 25 October 2026. The goal is **10 independent developers who can install
and use one core tool**. No users, stars, downloads, testimonials or accuracy
numbers are invented. Installation tests on the maintainer's computer are not
independent user adoption.

## Current status

| Channel | Status | Next step |
| --- | --- | --- |
| GitHub | Public source, real mesh examples and ten discovery topics applied | Read the quickstart, try the CPU demo, report an issue |
| Core package | `0.1.0-alpha.4` tarball prepared and tested locally | Create/sign into the owner's npm account before publication |
| npm | Not published; `noetra` is a proposed, unreserved name | Recheck the name; use an owned scope if needed |
| Official MCP Registry | `server.json` prepared, official JSON Schema validated locally | Publish npm first, then authenticate as NOETRA2 and validate/publish through the official publisher |
| Glama | An index entry was externally readable on 25 October 2026 | Link the existing listing; no duplicate submission |
| Hugging Face | CPU Docker Space bundle prepared | Create an account/Space and verify the actual build before claiming a live demo |
| Show HN / Product Hunt | Drafts only, not posted | Wait for stable installation and a working public demo |

GitHub topics applied on 25 October 2026: `mcp`, `model-context-protocol`, `ai-agents`,
`reasoning-engine`, `evidence-tracking`, `formal-verification`, `z3`, `planning`,
`local-first`, `typescript`. These describe implemented core capabilities;
discoverability does not guarantee that any AI assistant will know the project.

[Local preparation verification](VERIFICATION.md) distinguishes completed checks
from account-dependent publication and visual/hosting checks still pending.

## First publication: owner-operated steps

1. Create your npm account and enable its required publishing authentication.
   Sign in directly using `npm login`; never paste tokens/passwords in issues,
   source code or this project's docs.
2. Recheck `npm view noetra`. A not-found response is not a reservation. If the
   name cannot be used, select a scope you own and update `package.json`, the
   lockfile, `server.json`, examples and docs together; rerun the artifact test.
3. Run `npm ci --ignore-scripts`, `npm run check`, `npm run test:package` and inspect
   `npm pack --dry-run`. Review the actual artifact's contents and licence notices.
4. Publish the alpha deliberately: `npm publish --access public --tag alpha`.
   Do not use the `latest` tag for this developer alpha. Confirm the exact package,
   owner, version and install command on npm afterward.
5. Only **after** successful npm publication, test `npx noetra@alpha --version`
   and `npx noetra@alpha test` on a fresh machine. These are **future commands**,
   not working registry installs today. `npx noetra@alpha setup` previews host
   settings; for durable registration use a project-local installed package rather
   than relying on an npm temporary cache path.

For later CI publication, npm supports repository/workflow-bound trusted
publishers. Set that up in npm only after reviewing its access. No publishing
workflow, stored token or account permission is enabled by this preparation.

## Official MCP Registry

This registry holds metadata, not NOETRA's executable. The npm package must be
publicly available before its package entry can be published. The package's
`mcpName` and `server.json` name match: `io.github.NOETRA2/noetra`.

Install the official `mcp-publisher` from the registry project's releases, review
the binary/source as appropriate, then run these **manually after npm**:

```sh
mcp-publisher validate
mcp-publisher login github
mcp-publisher publish
```

Authenticate as **NOETRA2** to verify the namespace. Registry-side package/name
ownership checks have not run merely because local JSON Schema validation passed.
`packageArguments` explicitly launch `mcp` with a selected project directory.
The browser demo is not a remote MCP endpoint and is not advertised as one.

## Hugging Face demo

```sh
npm run build
node scripts/prepare-space.mjs ../NOETRA-space
```

The destination must be a new directory. The script copies only the built
runtime, its dependency metadata and Docker Space files; it does not copy
`.git`, private settings, local SQLite data, models or development dependencies.
Create a **Docker** Space and upload that generated folder's contents. It is
configured for CPU on port 7860 and a non-root user. No API key or GPU is needed.

The demo accepts fixed, bounded structured examples, uses isolated in-memory
databases and never exposes arbitrary MCP tools, filesystem access or model
execution to visitors. Public hosting still needs ordinary deployment/network
abuse controls and an actual hosted smoke test. It is not a production service.

## First 30 days

| Week | Work | Evidence of completion |
| --- | --- | --- |
| 1 | Package, quickstart and CPU demo | A fresh install runs the MCP/SQLite/Z3 self-test |
| 2 | npm, registry, GitHub metadata and existing directory listing | Public URLs resolve and exact-version installs work |
| 3 | Real examples, walkthrough and reproducible 3D report | Source, method and limits accompany every claimed result |
| 4 | Small community introduction and onboarding fixes | Independent installation reports, actionable issues and contributor feedback |

Use the [installation report template](../../.github/ISSUE_TEMPLATE/installation.yml)
to collect OS, Node/npm versions, command, sanitized output and whether a core
operation succeeded. Do not enable tracking or collect private identifiers.

## Sources checked for this preparation

- [Official MCP publishing quickstart](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/quickstart.mdx)
- [npm public package publishing](https://docs.npmjs.com/creating-and-publishing-scoped-public-packages/)
- [npm trusted publishing](https://docs.npmjs.com/trusted-publishers/)
- [Hugging Face Docker Spaces](https://huggingface.co/docs/hub/spaces-sdks-docker)
- [Space metadata reference](https://huggingface.co/docs/hub/spaces-config-reference)
- [Existing Glama listing](https://glama.ai/mcp/servers/NOETRA2/NOETRA)
