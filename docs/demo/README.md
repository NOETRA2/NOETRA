# Try the actual core, without a GPU

From a source checkout with a supported Node.js version:

```sh
npm ci --ignore-scripts
npm run demo
```

Open http://127.0.0.1:7860 and stop with Ctrl+C. From an installed tarball,
run its `noetra demo` binary instead; `--port 7861` selects another local port.
The CLI serves loopback only. The dedicated Docker Space entrypoint can bind
publicly through its hosting proxy; do not expose your own development server
to the internet without appropriate controls.

## Guided walkthrough (60 seconds)

1. 0–10s: What NOETRA is: a local toolkit, not a foundation model.
2. 10–20s: Run the integer example with premise 2 and claim 1: `VERIFIED`.
3. 20–30s: Change the claim to 5: inspect the counterexample.
4. 30–40s: Plan a release with the test prerequisite missing: blocked.
5. 40–50s: Supply that prerequisite: the three actions can be ordered.
6. 50–60s: Record a fixed observation: `OBSERVED`, untrusted, with a digest.

The video presents the [actual captured results](results.json) as six ten-second
cards. It is not a browser recording; see [provenance](PROVENANCE.md).
The running demo computes every result through the real engine. It does
not use an LLM, arbitrary text interpretation, model downloads or a GPU.

## Data and limits

The API accepts only an enumerated example plus bounded numeric/boolean controls.
It never accepts file paths, arbitrary tool names, uploaded images or commands.
Each run starts with separate SQLite `:memory:` storage and closes it afterward.
Nothing can query another visitor's history. No body logging or analytics is
implemented; a hosting provider may still log request/network metadata.

The public demo allows two concurrent runs, limits request size and constrains
solver work. Formal proofs concern supplied premises. The planner does not
perform the actions it orders. A recorded observation is not established truth.

Tests exercise the actual built HTTP app, Z3 entailment/counterexample, planning
with/without a prerequisite, evidence isolation, blocked arbitrary tool inputs,
origin/content-type checks, request-size limits and the static asset allowlist.
