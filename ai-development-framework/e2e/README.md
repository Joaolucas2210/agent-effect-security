# End-to-end release check

`make e2e` (or `bash ai-development-framework/e2e/quickstart.sh`) does what a stranger does with this repository,
on the **committed** tree only, and fails at the first step that differs from the docs:

| Step | What it proves |
| --- | --- |
| Fresh clone (`--no-local`), new venv, `make install-dev` | The quickstart works from nothing; `adf version` matches `VERSION` |
| Enable a fixture project on an isolated `ADF_HOME` | Host activation (REQ-MP-01) through `adf projects` |
| Claude `Read` and Codex `cat` through `adf hook` | Allow, `invalid_scope` with a bundle, `invalid_referenced_contract`, `unsafe_read_command`; no decision for a project that is not enabled |
| Subagent payload (`agent_type`) | The local principal of ADR 0023 reaches the journal |
| Per-principal policy | ADR 0024: the named principal reads, an unnamed one gets `principal_not_allowlisted` |
| `adf verify` on every bundle, then on a tampered copy | Offline verification goes green and red |
| `adf projects reasons` | The aggregate counts denies, journal-only contract denies and principals |
| `make local-evidence-trial`, `make a2a-live-trial` | Both fixed suites pass in the clone |
| Hygiene | The fixture secret appears in no evidence or report; the project's working tree and worktree list are unchanged |

It needs `git`, `make`, Python 3.10+ with `venv`, and network access or a pip cache (it installs the pinned
`jsonschema` and `mcp`). It is not part of `make quality` because it is slow and needs the network; CI runs it as
its own job. `E2E_KEEP=1` keeps the temporary directory for inspection.
