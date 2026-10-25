# REA integration

Official upstream: https://github.com/morluto/rea, npm `rea-agents` 6.7.0 (MIT).
NOETRA reuses the public launcher declared by the installed package, running its
`mcp` command through Node without a shell. It validates package metadata and the
launcher location, then compares the live MCP version. Metadata checks are not a
substitute for installing from a trusted registry/integrity-checked distribution.

The bridge lazily connects, dynamically discovers schemas, and selects the actual
`analyze_javascript_application` capability. It never exposes REA's entire tool
catalog as public NOETRA operations. The verified package advertised 207 tools;
its full-schema catalog needs about 9.1 MB, so the internal transport is capped at
12 MiB. Full nested schemas are inspected internally, not sent to the host.
Public NOETRA keeps eleven default operations; the separately configured local
reconstruction runtime adds ten operations. The internal REA catalog is not
advertised as image-to-3D functionality.

Scope is operator-configured in project-local `.noetra/integrations.json`.
Public investigation inputs cannot change the launcher, integration settings,
allowed roots or tool allowlist. An authorization reference and exact source-path
list are required. Canonical paths must stay inside approved roots. Home/drive
roots, symlink/junction-containing targets, nonregular files and oversized
inventories are refused. The public authorization text is a record of consent,
not a security credential; the independently configured filesystem scope is the
enforced boundary. Only connect trusted MCP hosts.

Current supported targets: extracted JavaScript/Electron directories and ASAR
archives. No target program is executed. Bounds: 5,000 entries / 100 MiB inventory,
16 selected files, 2 MiB per selected directory source, 256 MiB analyzer old-space,
10 seconds per-source analysis, 60-second integration deadline, one concurrent
investigation. Initial connection can retry once; analysis calls are not replayed.

The bridge captures the summary, source-evidence identifiers, upstream coverage
limitations and a bounded `inspect_analysis_view` fact view before closing the
connection. Returned source facts are static observations/inferences, not proof
of runtime reachability or security enforcement. Complete retained parent graphs
expire on disconnect; only captured views survive in NOETRA memory. Source views
may omit facts outside their selected kinds/paths/limit. Absence in a projection
is not proof of absence from the app. No pseudocode is labeled original source.

Local evidence contract includes investigation ID, target/scope, authorization
reference, tool/version, timestamp, static observation type, upstream evidence
IDs/locations, raw digest, interpretation/rationale, limitations and status.
Raw outputs remain untrusted and are never evaluated. No external raw stderr
is forwarded or logged. Protocol errors produce bounded structured failures.

Run the actual integration check against the synthetic authorized fixture:

```sh
npm run build
npm run test:rea -- /path/to/already-installed/rea-agents
```

No REA download or global MCP registration occurs. Evidence is saved under
`.noetra/verification/rea-investigation.json`; it is excluded from npm packaging.
On restricted sandboxes, REA's temporary source-transfer worker may be denied
filesystem access. Report that restriction rather than claiming analysis worked.

REA is an integrated software-investigation subsystem. Its lazy connection avoids
running irrelevant software investigations on every image. REA does not infer
depth, recover car surfaces or generate a mesh from a photograph. The current
NOETRA bridge supports the scoped JavaScript/ASAR route above and the bounded
Ghidra native-PE route below; upstream native tools are not all automatically
exposed by this bridge. Image structure,
geometry, rendering and correction belong to the reconstruction subsystem.

## Integrated Ghidra native analysis

Configure an existing official Ghidra 12.1.4 installation and full JDK 21 in the
same project-local integration config, or use the CLI:

```text
noetra integrations rea --project PROJECT --package REA_PACKAGE --allow-root AUTHORIZED_FIXTURE --ghidra-dir GHIDRA_ROOT --java-home JDK_ROOT
```

Review the printed config, then apply with `--apply --yes`. Existing Ghidra
settings are preserved if later updating the REA package/allowlist without those
flags. No global Java, REA registration or system PATH change is required. REA
does not install Ghidra; the core does not bundle it.

When configured, `noetra.investigate_native` accepts `target`, `scope`,
`authorization` and 1–3 `procedures`. The bridge exposes only static selected
procedure pseudocode, not an unrestricted REA proxy. PE EXE/DLL targets are
allowlisted and limited to 50 MiB; Ghidra/REA performs format/architecture
admission. Calls bind provider `ghidra`, verify returned source identity, preserve
the original file digest and request explicit session close. Imported text is
untrusted attributed evidence, never original source or proof of runtime behavior.

Ghidra/JDK environment and temporary folders belong to the integration process.
Other REA sessions and applications are not reconfigured. Windows support follows
REA's experimental read-only native-PE boundary; GUI/database editing and other
formats are not implied. If a call fails, bounded upstream tool diagnostics are
saved locally as `rea-state/native/native-failure.json`; raw process stderr is
discarded. The MCP native tool is advertised only when the trusted local Ghidra
configuration is present. Default unconfigured core tool counts remain unchanged.
