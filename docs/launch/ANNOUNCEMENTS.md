# Launch drafts — not posted

Use after the owner has tested installation and a real public demo. Replace
future demo links only with URLs that actually work. Never imply benchmark
accuracy, independent adoption or hosted availability that has not been measured.

## Show HN

**Title:** Show HN: NOETRA – local evidence, Z3 checks and planning tools for AI agents

I’m building NOETRA, an open-source MCP server, CLI and TypeScript SDK that gives
an AI host a structured record of evidence, assumptions and formal checks.

The core works on a CPU. It stores project-local evidence in SQLite, checks
supplied integer constraints with Z3 and orders actions around explicit
dependencies. It doesn’t silently call an AI API, prove arbitrary natural
language or certify that a premise is true.

There’s a small demo for entailment, counterexamples, blocked prerequisites and
evidence provenance. Experimental image-to-3D integrations are separate and
unfinished; the repository includes actual mesh comparisons and their limits.

Source and current installation instructions: https://github.com/NOETRA2/NOETRA

I’d welcome installation reports and feedback on which evidence/checking tools
you would actually use. This is a developer alpha, not a finished general
cognitive system.

## Product Hunt

**Name:** NOETRA

**Tagline:** Local evidence, logic checks and plans for AI agents

**Description:** An open-source MCP server, CLI and SDK for evidence tracking,
formal integer checks with Z3 and prerequisite planning. Core tools run locally
without a GPU or model API key. Includes a small real demo and optional,
experimental 3D workflows with reproducible methods and stated limitations.

**Maker comment:** We’re looking for our first independent installation reports.
The goal is a tool people can inspect and use—not unmeasured claims of stronger
AI. Please share your OS, Node version and the first core operation you tried,
without private configuration or credentials.
