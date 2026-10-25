# NOETRA standalone alpha

This ZIP installs **NOETRA only**, not Nexa Chat, Browser, TV or any other app.
NOETRA is a command-line tool, MCP server and developer SDK; it is not a GUI app.

## Windows

1. Extract the entire ZIP into a folder.
2. Have Node.js 24.11+ (24.x) or 26+ and npm installed. Get Node only from
   https://nodejs.org/ if it is missing; this installer will not download it.
3. Open `Install-NOETRA.cmd`. It runs the included readable PowerShell script.
4. Review the directory and type `INSTALL` to consent. Internet is required for
   NOETRA's npm libraries. No administrator rights should normally be needed.
5. The installer prints the full `noetra.cmd` path. Use that path with `help`,
   `doctor`, `test` or `setup`. It does not register your AI host automatically.

If your PowerShell execution policy blocks a downloaded script, do not disable
machine security settings. Review the script and use your organization's approved
method, or install the tarball directly with npm as below.

## Direct local install (Windows, Linux, macOS)

From the extracted directory:

```sh
npm install --prefix ./noetra-tools --ignore-scripts --no-audit --no-fund ./noetra-0.1.0-alpha.3.tgz
```

Executable: `noetra-tools/node_modules/.bin/noetra` (`noetra.cmd` on Windows).
Run `noetra test` through that executable for a real MCP/SQLite/Z3 check.
`noetra setup` previews configuration; it does not alter clients without consent.
REA is optional and not bundled/downloaded. Existing REA installs can be enabled
later for authorized local software investigation.

The installed package includes architecture, installation, security, API and
verification documentation under `node_modules/noetra/docs/`.

This is a tested developer **alpha**, not the entire finished specification.
Alpha.2 adds a reference-locked visual-design workflow. Read VISUAL-UPGRADE.md:
actual image editing still requires an image-capable host, and visual reviews
are attributed assessments rather than independently verified pixel matching.
Alpha.3 adds a deliberately enabled, limited planar reconstruction proof. Read
RECONSTRUCTION.md. Optional Python/Blender libraries are NOT installed by this
bundle; the default core still needs only Node and its npm runtime libraries.
Host-model understanding/idea generation, generic execution adapters and the
full autonomous experimental loop remain unfinished. It has not been published
to npm or GitHub; do not install an unrelated registry package by name.

Checksums detect corruption, not publisher authenticity. Keep the bundle from a
trusted source. To remove, first disconnect any host registration, then remove
only the dedicated installation directory. Project memory is separate and should
not be deleted unless you want to remove that project's evidence.
