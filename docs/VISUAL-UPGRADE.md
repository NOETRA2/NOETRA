# Reference-locked visual design — 0.1.0-alpha.2

Purpose: avoid silently turning a concept into a different object while adding
detail or handing it to a modeller. This is workflow enforcement, not a newly
trained image model, automatic vision system, or proof of visual identity.

## Workflow

1. Create explicit immutable identity criteria and requested detail criteria.
2. Anchor one real project-local PNG; its exact bytes and dimensions are recorded.
3. Prepare a same-view detail edit or a proposed turnaround. The packet contains
   actual reference paths, hashes, a hierarchy of details, and a review checklist.
4. The host must pass those references to a real reference-capable image editor.
   A text-only generator is not an identity-preserving fallback.
5. Attach the actual output and declared reference provenance to its bounded job.
6. Review that exact output against its exact references, recording match,
   mismatch or unknown per feature. Missing findings never silently pass.
   A subsequent bounded detail-edit packet includes prior non-matching findings
   as attributed correction requests, while retaining the original anchor.
7. Request a 3D brief only after the latest outputs for every required view have
   been reviewed. One attractive perspective is insufficient. A real modeller
   and same-camera render comparisons are still required afterward.

Silhouette/proportions precede parts, materials and microdetail. Detail-edit
aspect-ratio changes over 2% relative to the anchor block the review gate.
Counts and scalar tolerances can be checked deterministically when a reviewer
actually supplies measurements. The appearance findings themselves remain
attributed to a human, host model or separately implemented vision adapter.
There is no invented quality score, independent semantic verification, or claim
that model self-review equals proof. Unseen geometry remains proposed/unknown.

## Safety and limits

- Existing project revisions remain intact; the first anchor cannot be replaced.
- Changes to registered image bytes invalidate subsequent operations, not merely
  their displayed filename. Anchor and output SHA-256 hashes are separate from
  semantic claims about the pixels.
- PNG-only input: 24 MiB, 8192-pixel edge, 24 megapixels, bounded chunk count,
  checked container signatures/CRC/IHDR, no animation or trailing data. This is
  container validation, **not full pixel decoding or malware scanning**. IHDR
  rules follow the [W3C PNG specification](https://www.w3.org/TR/png-3/#11IHDR).
- Only explicitly supplied files beneath the engine's dedicated project root
  are accepted. Broad home/drive roots and symlink/junction traversal are refused.
- No image upload, network request, provider key, shell execution or new model is
  bundled. Preparing a packet does not generate an image. The optional SDK adapter
  interface requires edit/reference capabilities, passes a cancellation signal,
  and stops waiting after 120 seconds. A provider ignoring cancellation may keep
  running; NOETRA cannot guarantee external cost cancellation.
- References are declared by the trusted host. NOETRA cannot prove a remote
  provider consumed them. Host configuration is not changed by this upgrade.
- The reference-edit prompt mitigates identity drift; it cannot guarantee exact
  component preservation. Review and rejection remain necessary.

## Verification

`npm run check`: TypeScript check and production build pass; **47 tests pass**.
The 18 added tests cover immutable references, revision conflicts, path boundaries,
image mutation, wrong references, duplicate outputs, missing/numeric findings,
aspect drift, latest-view gates, attempt budgets, PNG corruption, persistence,
untrusted goal text, bounded repair feedback, unsupported adapters and pre-cancelled execution. Existing
MCP, SQLite, formal reasoning, integration and installer tests remain passing.

The end-to-end MCP test advertises eleven operations and calls the new operation
through the official MCP client. Real-car editing is a separate host-assisted
demonstration; fixture tests do not prove photorealism or exact 3D reconstruction.

Historical foundation results remain in VERIFICATION.md and describe alpha.1.
Do not reinterpret that earlier report as completion of the full project.
