# Install & Distribution

The framework is one core (`ai-development-framework/`) plus thin per-tool adapters wired by
symlink. Activation links the local core into `.claude/`, `.codex/`, `.cursor/`.

## Install metrics into an existing repository

From the ADF clone:

```bash
make install-metrics DEST=/absolute/path/to/another-repository
```

This copies a clean core and `Makefile.adf`, preserving the destination's Makefile,
AGENTS.md, license, environments and agent settings. It excludes captured evidence,
events, trials, caches and old CSV rows. Conflicts fail instead of overwriting an
installation. No hooks or dependencies are installed automatically.
The ADF license and version travel inside the core, without replacing host files.

In the destination, use `make -f Makefile.adf install-dev` with an explicit
`ADF_CONTRACTS_PYTHON` pointing to a dedicated virtual environment. Follow the
[complete trial protocol](trials.md) for environment setup, agent hooks and session capture.
`make install-into` remains the full harness installer; it now refuses file conflicts.

## Install

```bash
./setup-adf.sh all        # Claude + Codex + Cursor + hooks + Graphify + RTK (default)
./setup-adf.sh claude     # one platform only
./setup-adf.sh --doctor   # health check: tools + read-only gates, no changes
./setup-adf.sh --version  # print VERSION
```

`make setup` / `make adf-claude` / `make check` are equivalents (see `make help`).

## Control-plane packages (local, editable)

`tools/` (PDP), `runtime/` (PEP, confined read) and `integration/` (evidence, adapter) are one
installable package, `adf-control-plane`, so hooks/tests import them without `sys.path` hacks:

```bash
make install-dev   # python3 -m pip install -e ./ai-development-framework -r .../requirements-test.txt
```

Needs pip ≥ 21.3 (PEP 660). Ubuntu 22.04's patched system pip 22.0 rejects the editable hook, so use a
venv there (`python3 -m venv .venv && . .venv/bin/activate`), or point `ADF_CONTRACTS_PYTHON` at one.
Editable install from this clone only. Nothing is published to PyPI or npm and there is no
console script (README non-goals, ADR 0008). `hooks/test-packaging.sh` fails CI if the install
path stops resolving the imports or `pyproject.toml` drifts from `VERSION`.

## Clean install (temp dir)

Prove a from-scratch install without touching your repo:

```bash
tmp=$(mktemp -d); git clone . "$tmp"; cd "$tmp"
./setup-adf.sh all && ./setup-adf.sh --doctor
```

## Idempotency

Re-running is safe. `link()` replaces stale symlinks and **skips real files** with a warning
(`setup-adf.sh:36-37`) — running `setup-adf.sh all` twice re-points the same links and changes
no real file. Verify:

```bash
./setup-adf.sh all >/dev/null && a=$(find .claude .codex .cursor -type l | sort)
./setup-adf.sh all >/dev/null && b=$(find .claude .codex .cursor -type l | sort)
[ "$a" = "$b" ] && echo "idempotent" || echo "DRIFT"
```

## Rollback

For activation, inspect the links created by setup and remove only those links.
Do not clean entire agent configuration directories: they can contain host files.
For a metrics installation, review `Makefile.adf` and `ai-development-framework/`
against your Git diff before removing the added files. Preserve captured data locally
if it is needed for diagnosis. Setup and the metrics installer preserve existing host files.

## Platform compatibility

| Platform | Wiring | Commands surface | Notes |
| --- | --- | --- | --- |
| Claude Code | `agents/`, `commands/`, `skills/` → `.claude/` | `/spec /plan /build /review /ship /graphify` | primary target; hooks active |
| Codex | `skills/` → `.codex/skills`, `commands/` → `.codex/prompts` | prompts | conflicting files skipped, not overwritten |
| Cursor | `commands/` → `.cursor/commands`; `AGENTS.md` read natively | commands | AGENTS.md at repo root |

## Versioning & releases

`VERSION` (repo root) is the single source of truth; `./setup-adf.sh --version` reads it.
Bump it in the same PR as a breaking change to the core contract (gates, skill schema, hook API).

`install-metrics` carries a copy of `VERSION` inside the core, independently of the host
repository's version file. Installation updates are reviewed manually; there is no release
or migration automation. Record the ADF source SHA alongside each trial to distinguish copies
that share the same package version.
