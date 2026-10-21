#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for workflow in "$ROOT/.github/workflows/maintenance-routines.yml"; do
  grep -Fxq '        run: python -m pip install --disable-pip-version-check -e ai-development-framework -r ai-development-framework/requirements-test.txt' "$workflow"
done
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/framework/hooks" "$tmp/bin" "$tmp/graphify-out"
cp "$ROOT/hooks/maintenance-routine.sh" "$ROOT/hooks/observability.sh" "$tmp/framework/hooks/"

cat > "$tmp/bin/make" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$MAKE_LOG"
EOF
chmod +x "$tmp/bin/make"
cat > "$tmp/graphify-out/graph.json" <<'EOF'
{"nodes":[{"id":"called","label":"called()","norm_label":"called","_callable":true,"source_file":"src/a.js","source_location":"L1"},{"id":"unused","label":"unused()","norm_label":"unused","_callable":true,"source_file":"src/b.js","source_location":"L2"},{"id":"duplicate","label":"calledAgain()","norm_label":"called","_callable":true,"source_file":"src/c.js","source_location":"L3"}],"links":[{"source":"caller","target":"called","relation":"calls"}]}
EOF

jq_bin="$(command -v jq)"
run() {
  (cd "$tmp" && PATH="$tmp/bin:/usr/bin:/bin" MAKE_LOG="$tmp/make.log" ADF="$tmp/framework" \
    GRAPH_PATH="$tmp/graphify-out/graph.json" JQ="$jq_bin" DRY_RUN="${2:-1}" \
    bash "$tmp/framework/hooks/maintenance-routine.sh" "$1")
}

dead="$(run dead-code)"
[[ "$dead" == *"unused()"* ]]
grep -qx -- '-s quality' "$tmp/make.log"
grep -qx -- '-s mcp-audit' "$tmp/make.log"
grep -qx -- '-s skill-audit' "$tmp/make.log"
grep -qx -- '-s graph-check' "$tmp/make.log"

abstractions="$(run abstractions)"
[[ "$abstractions" == *"src/a.js:L1 called()"* && "$abstractions" == *"src/c.js:L3 calledAgain()"* ]]
run graph 0 >/dev/null
grep -q '"outcome":"success"' "$tmp/framework/docs/observability/events.jsonl"
[ -f "$tmp/framework/docs/observability/trajectories/routine-dead-code.trajectory.md" ]

if run unknown >/dev/null 2>&1; then
  echo "✗ accepted an unknown routine" >&2
  exit 1
fi
echo "✓ maintenance routine self-test"
