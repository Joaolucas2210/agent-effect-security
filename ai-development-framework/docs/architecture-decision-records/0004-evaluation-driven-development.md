# 4. Evaluation-Driven Development and a real complexity gate for shell

- Status: accepted
- Date: 2026-08-24

## Context

Two holes made `make quality` optimistic:

1. **Shell was never measured.** The complexity gate only existed in the Python arm (`lizard`),
   and `lizard`/`radon` do not parse bash. This framework is ~1.2k lines of shell across 15
   hooks — the language it is written in was the one language it never gated. On this repo the
   whole wall reported `✓ 1 gate(s) green` (a `npm test` on a sandbox fixture).
2. **Evals were optional and invisible to CI.** `eval-agent-flow.sh` existed, but nothing ran it
   on a change and nothing required a new skill/command/hook to be evaluated at all.

The stack arms were also mutually exclusive (`if/elif`), so a polyglot repo was gated on the
first stack found and silently not on the rest.

## Decision

**Shell complexity is a first-class gate.** `hooks/shell-complexity.sh` + `shell-complexity.awk`
count `CCN = 1 + (if|elif|while|until|for) + && + || + case branches`, per function and for the
script's top-level body, with no new dependency. Thresholds are parsed from
`rules/quality-thresholds.md` by `hooks/thresholds.sh` — one source of truth, no hardcoded copies.

Two numbers, deliberately:

- **Functions ≤ 10** — the same number every other language gets. Reusable units get no discount.
- **Script top-level body ≤ 20** — a linear entry point where each `cmd || fail` guard is a real
  branch. This is a **ratchet**, not an exemption: the target is 10, reached by extracting bodies
  into functions. It may be lowered as that happens, never raised to make a red gate green.

Landing it required refactoring what it found: `setup-adf.sh` (3 functions), `skill-audit.sh`,
`observability.sh`, and `ci-quality-gates.sh` itself.

**Evaluation-Driven Development is enforced.** `hooks/eval-required.sh` fails when a changed
`skills/`, `commands/` or `hooks/` file has no eval case (`covers:` in a fixture's `task.md`), no
`hooks/test-*.sh`, and no dated waiver in `docs/evals/waivers.md`. `make eval` runs every case,
the coverage gate, and the diagnosis; both are inside `make quality` and CI, so a regressed case
blocks a merge instead of being noticed later.

**Every self-test is a contract.** `make quality` runs all `hooks/test-*.sh`; contracts are not
counted as stack gates, so `gates_run == 0` still means "nothing about this code was measured"
and remains a hard failure in CI.

## Consequences

- `make quality` on this repo went from **1 gate** to **4** (JS tests, shell complexity, eval
  cases, eval coverage) plus 8 contracts; every skipped gate is named in the output.
- Writing this PR produced three real findings from its own gates: `eval-agent-flow.sh` never
  propagated `ADF_DIR`; `shell-complexity.sh` reported "all green" when its analyser was missing;
  `skill-audit.sh` flagged `hooks/test-*.sh` in prose as a broken ref. All three now have tests.
- Cost: a new skill or command that genuinely cannot be evaluated needs a waiver line. That
  friction is the point — `waivers.md` is short, dated, and read in review.
- Ceilings (documented in `shell-complexity.awk`): a `}` in column 0 closes a function; decision
  keywords inside single-line quoted strings still count (heredoc bodies do not). The upgrade
  path is a real bash parser, not more regex.
