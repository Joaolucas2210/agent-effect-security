#!/usr/bin/env bash
# P1: the control plane is a locally installable package (`make install-dev`), never a registry release.
# Imports must resolve from a neutral cwd with no sys.path folklore; package version tracks VERSION.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
version_file="$ROOT/VERSION" # vendored installation; otherwise the source clone's canonical VERSION
[ -f "$version_file" ] || version_file="$ROOT/../VERSION"
version="$(tr -d '[:space:]' < "$version_file")"
grep -q "^version = \"$version\"" "$ROOT/pyproject.toml" || { echo "pyproject version != VERSION ($version)"; exit 1; }
grep -Eq 'twine|npm publish' "$ROOT/pyproject.toml" && { echo "publish configuration is out of scope"; exit 1; }
# ADR 0025: exactly one console script, the `adf` dispatcher; anything else is a new public surface.
scripts="$(awk '/^\[project.scripts\]/{on=1; next} /^\[/{on=0} on && NF' "$ROOT/pyproject.toml")"
[ -z "$scripts" ] || [ "$scripts" = 'adf = "integration.cli:main"' ] || { echo "only the adf console script is allowed (ADR 0025): $scripts"; exit 1; }
( cd "$(mktemp -d)" && "$PYTHON" -c 'import tools.pdp, runtime.pep, runtime.local_read_runtime, integration.local_evidence_bundle, integration.local_read_adapter' ) \
  || { echo "control-plane packages not importable from a neutral cwd — run: make install-dev"; exit 1; }
echo "✓ packaging: editable install imports tools/runtime/integration; version $version"
