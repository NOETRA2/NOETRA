# Installation, configuration and removal

The standalone Windows bundle contains one NOETRA tarball and a confirmation-based
PowerShell installer. It checks an existing supported Node.js installation,
checks the tarball digest, and installs only that tarball and its runtime npm
dependencies under `%LOCALAPPDATA%/Programs/NOETRA` (or your explicit directory).
It does not change PATH, install Node, install REA, register an AI client, create
a cloud account or install another Nexa product. Internet access is needed for
npm libraries. No npm lifecycle scripts are enabled.

For Linux/macOS or a custom local installation:

```sh
npm install --prefix ./noetra-tools --ignore-scripts --no-audit --no-fund ./noetra-0.1.0-alpha.3.tgz
./noetra-tools/node_modules/.bin/noetra test
```

Use the explicit binary path or add your chosen bin directory to PATH yourself.
No global install is necessary.

## Host setup

Run `noetra setup --client cursor|claude|codex --project /absolute/project`.
Default scope is project-local. Setup is a preview unless `--apply --yes` is
specified. It does not infer permission from a detected client.

- Cursor: project/user `.cursor/mcp.json`.
- Claude: project `.mcp.json`, or user `.claude.json`.
- Codex: project/user `.codex/config.toml`; **snippet only, manual review/apply**.

An existing different `mcpServers.noetra` entry blocks automatic setup. Other
entries are preserved. Configuration backups/receipts may contain credentials
from existing client settings: keep them private and do not upload them.

After a Cursor/Claude apply, the output gives the exact rollback receipt. Use:

```sh
noetra setup --client cursor --project /absolute/project --rollback /absolute/receipt.json --yes
```

Rollback requires the current file to match the installed digest. If other
settings changed afterward, it refuses and you should remove only the NOETRA
entry manually. A newly created config is removed by rollback; prior config
bytes are restored from their backup. Keep backup files until you have confirmed
the host connects. Reconnect the host after registration/removal.

REA is enabled separately using a reviewed existing official package:

```sh
noetra integrations rea --project /absolute/project --package /path/to/node_modules/rea-agents --allow-root /authorized/sample
# Review the plan, then repeat with --apply --yes to write project-local integration settings.
```

Remove that project's `.noetra/integrations.json` to disable REA; this does not
uninstall or modify the existing REA package. No automatic REA installer exists
in this alpha. Review/install the official pinned package separately if needed.

## Memory export/deletion

Use the local SDK's `engine.memory.export()` to retrieve that project's records;
write/export sensitive results only when authorized. `deleteProject()` requires
the exact active project ID. `purgeExpired()` physically removes expired records
and prevents older revisions from resurfacing. Logical deletion is not a promise
of forensic erasure from SSDs, backups or WAL files. Project memory is unencrypted
by default: use OS disk encryption and appropriate file permissions.

To remove the installed tool, first disconnect it from the host, then remove
only the dedicated NOETRA installation directory you chose. Do not delete a
project's `.noetra` memory unless you intend to remove its local evidence too.
