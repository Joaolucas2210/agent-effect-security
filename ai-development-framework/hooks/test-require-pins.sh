#!/usr/bin/env bash
# hooks/require_pins.py: the single source of the exact dependency pins (requirements-test.txt), green and red.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
installed="$("$PYTHON" -c 'from importlib.metadata import version; print(version("jsonschema"))')"
printf 'jsonschema==%s\nmcp[cli]==0.0.1\n# comment\n' "$installed" > "$tmp/ok.txt"
"$PYTHON" "$ROOT/hooks/require_pins.py" --requirements "$tmp/ok.txt" jsonschema >/dev/null
printf 'jsonschema==0.0.1\n' > "$tmp/bad.txt"
out="$("$PYTHON" "$ROOT/hooks/require_pins.py" --requirements "$tmp/bad.txt" jsonschema)" && { echo "✗ wrong version passed"; exit 1; }
grep -q "jsonschema==0.0.1 is required (installed: $installed)" <<< "$out"
"$PYTHON" "$ROOT/hooks/require_pins.py" --requirements "$tmp/ok.txt" not-pinned >/dev/null && { echo "✗ unpinned name passed"; exit 1; }
"$PYTHON" "$ROOT/hooks/require_pins.py" --requirements "$tmp/ok.txt" mcp >/dev/null && { echo "✗ extras pin not compared"; exit 1; }
rc=0; "$PYTHON" "$ROOT/hooks/require_pins.py" 2>/dev/null || rc=$?; [ "$rc" = 2 ] || { echo "✗ usage must exit 2"; exit 1; }
# The package metadata and the test requirements pin the same versions (one bump, both files).
for name in jsonschema mcp; do
  req="$(sed -n "s/^$name\(\[[^]]*\]\)\{0,1\}==//p" "$ROOT/requirements-test.txt")"
  grep -q "\"$name\(\[[^]]*\]\)\{0,1\}==$req\"" "$ROOT/pyproject.toml" || { echo "✗ $name pin differs between pyproject.toml and requirements-test.txt"; exit 1; }
done
"$PYTHON" "$ROOT/hooks/require_pins.py" jsonschema
echo "✓ require-pins: exact pins read from requirements-test.txt; pyproject agrees"
