# Task evaluation — 2026-10-04

Delivered a separate versioned external assessment contract rather than changing
session-report v2's `task_outcome: null`. The API binds the verified session hash,
trial/task/session IDs, acceptance hash and initial revision. It records the
evaluated revision and an assessor-declared outcome. Executed outcomes require
a result artifact SHA-256; skipped outcomes require null. This is integrity,
not assessor authentication or independent proof of task success.

Four focused tests cover outcome semantics, immutability, forged bindings with
recomputed hashes, closed inputs and a static normative oracle. The source
quality gate passed 30 self-tests and four gates. JS coverage, cycle detection
and mutation tooling were skipped. An initial concurrent eval run invalidated
the checkout-immutability test; an isolated quality run passed.

The selective portable update in project-b passed quality (30 framework
self-tests plus application tests, three executed gates) and eval. Host
deployments, Python coverage, complexity and mutation tooling remained skipped.
All 27 observability files were preserved by digest during the update; the
existing host probe still verifies. Source eval, focused Ruff and diff checks
passed. Graph freshness checked HEAD, without reindexing this uncommitted slice.

No real coding-agent session or task outcome has been added to the project-b
trial. A host integration probe remains distinct from an external task trial.
Next: run a chosen client against a revision-pinned task and acceptance criterion,
retain its external test result, and pair its evaluation with the v2 session.
