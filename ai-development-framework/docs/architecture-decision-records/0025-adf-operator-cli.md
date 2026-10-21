# ADR 0025: one operator CLI, `adf`

- **Status:** Accepted — human acceptance on 2026-10-21 (maintainer, release 0.1.0 preparation); previously Proposed.
- **Date:** 2026-10-21
- **Depends on:** ADR 0008 (editable install only, no registry release).
- **Scope:** packaging and operator ergonomics. No new effect, no new decision path.

## Problem

Operating the control plane meant knowing six entry points with different shapes: `make project-*`, a
hook script with a dash in its name, `python -m integration.a2a_gateway`, the policy pack's `build.py`,
and no command at all to verify a bundle offline. The 2026-10-20 pilot also showed the hook registration
line is easy to break by hand. The README and `test-packaging.sh` said "no public runtime CLI" to keep the
surface closed; that left operators with more surface, not less.

## Decision

- One console script, `adf = "integration.cli:main"`, installed by `make install-dev` (editable only).
- `adf` is a thin dispatcher: `projects`, `hook`, `hook-snippet`, `policy build`, `a2a`, `verify`,
  `version`. Arguments after the command go to the existing script unchanged; no command decides anything
  the script did not already decide.
- `adf hook` keeps the hook's rule: any ADF failure is "no decision" (exit 0, no output), never a blocked
  tool. `adf hook-snippet` prints the registration with the fail-safe (`[ -x "$A" ] || exit 0`).
- `adf verify` is the only new behaviour: `verify_offline` for a bundle, `verify_record` for an A2A record
  with its bundle located next to it. Read-only, offline, exit 0/1/2.
- `test-packaging.sh` allows exactly this one script and still refuses publish configuration.

## Not decided here

Publishing to PyPI or npm, a daemon, a TUI, or any command that writes outside `~/.adf` and the chosen
output file. Each would need its own ADR.

## Residual risk

`adf` is on the agent's PATH if the venv is: an agent with `Bash` can run `adf projects enable` exactly as it
could run the script or edit the list before. Same residual as REQ-MP-02, now one command shorter.

## Rollback

Remove `[project.scripts]` and `integration/cli.py`; the scripts and `make` targets keep working.
