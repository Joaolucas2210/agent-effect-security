#!/usr/bin/env bash
# End-to-end release check: what a stranger does with a fresh clone, on the committed tree only.
#
#   clone (no local hardlinks) -> new venv -> make install-dev -> adf CLI
#   -> enable a fixture project on an isolated ADF_HOME -> Claude Read and Codex cat through `adf hook`
#   -> subagent principal in the journal -> per-principal policy -> `adf verify` (and a tampered copy)
#   -> `adf projects reasons` -> make local-evidence-trial -> make a2a-live-trial
#   -> no secret in any evidence, nothing written into the project's working tree.
#
# Usage: bash ai-development-framework/e2e/quickstart.sh       (E2E_KEEP=1 keeps the temp dir)
# Needs: git, make, python3 (3.10+) with venv, network or a pip cache for jsonschema and mcp.
set -euo pipefail

REPO="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
WORK="$(mktemp -d)"
SECRET="AKIA-e2e-fake-secret-$$"
STEP=""
trap 'status=$?; [ "$status" -eq 0 ] || echo "✗ e2e failed at: $STEP" >&2; [ "${E2E_KEEP:-0}" = 1 ] && echo "kept: $WORK" || rm -rf "$WORK"' EXIT

step() { STEP="$1"; echo "▶ $1"; }
ok() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1" >&2; exit 1; }
expect() { case "$2" in *"$3"*) ok "$1";; *) fail "$1: expected '$3' in: $2";; esac; }

payload_read() {  # path [agent_type]
  printf '{"hook_event_name":"PreToolUse","tool_name":"Read","session_id":"e2e-session","tool_input":{"file_path":"%s"}%s}' \
    "$PROJECT/$1" "${2:+,\"agent_id\":\"e2e\",\"agent_type\":\"$2\"}"
}

payload_cat() {  # command
  printf '{"hook_event_name":"PreToolUse","tool_name":"Bash","session_id":"e2e-session","cwd":"%s","tool_input":{"command":"%s"}}' "$PROJECT" "$1"
}

claude_hook() { CLAUDE_PROJECT_DIR="$PROJECT" adf hook; }
codex_hook() { (cd "$PROJECT" && env -u CLAUDE_PROJECT_DIR adf hook); }

install_clone() {
  step "fresh clone and editable install"
  git clone --quiet --no-local "$REPO" "$WORK/adf"
  cd "$WORK/adf"
  python3 -m venv .venv
  export ADF_CONTRACTS_PYTHON="$PWD/.venv/bin/python3" PATH="$PWD/.venv/bin:$PATH"
  make -s install-dev >/dev/null
  [ "$(adf version)" = "$(tr -d '[:space:]' < VERSION)" ] || fail "adf version != VERSION"
  ok "adf $(adf version) on $(git rev-parse --short HEAD)"
}

fixture_project() {
  step "enable a fixture project on an isolated host"
  export ADF_HOME="$WORK/adf-home"
  PROJECT="$WORK/project"
  mkdir -p "$PROJECT/config"
  echo "public readme" > "$PROJECT/README.md"; echo "$SECRET" > "$PROJECT/config/.env"; echo "$SECRET" > "$PROJECT/.env"
  git -C "$PROJECT" init -q && git -C "$PROJECT" add -f . \
    && git -C "$PROJECT" -c user.email=e2e@example.invalid -c user.name=e2e commit -qm fixture
  adf projects enable "$PROJECT" >/dev/null
  expect "listed as git root" "$(adf projects list)" "[git-root]"
}

local_edges() {
  step "Claude Read and Codex cat through adf hook"
  expect "Read README.md is allowed" "$(payload_read README.md | claude_hook)" '"permissionDecision":"allow"'
  expect "Read config/.env is denied with a bundle" "$(payload_read config/.env | claude_hook)" "deny/invalid_scope bundle="
  expect "Read .env is denied by the contract" "$(payload_read .env | claude_hook)" "deny/invalid_referenced_contract"
  expect "cat README.md is not blocked" "$(payload_cat 'cat README.md' | codex_hook)" "{}"
  expect "cat config/.env is denied" "$(payload_cat 'cat config/.env' | codex_hook)" "invalid_scope"
  expect "a composed cat is denied" "$(payload_cat 'cat README.md; cat .env' | codex_hook)" "unsafe_read_command"
  expect "a subagent is a principal" "$(payload_read README.md security-reviewer | claude_hook)" '"permissionDecision":"allow"'
  [ -z "$(payload_read config/.env | ADF_HOME="$WORK/elsewhere" CLAUDE_PROJECT_DIR="$PROJECT" adf hook)" ] || fail "a project that is not enabled got a decision"
  ok "a project that is not enabled gets no decision"
}

principal_policy() {
  step "per-principal policy (ADR 0024)"
  local exports; exports="$(adf policy build --run-id e2e-session --allow README.md --principal claude:main=README.md --out "$WORK/policy.json")"
  eval "$exports"
  export ADF_READ_POLICY_FILE ADF_READ_POLICY_SHA256
  expect "the named principal reads" "$(payload_read README.md | claude_hook)" '"permissionDecision":"allow"'
  expect "an unnamed subagent is denied" "$(payload_read README.md backend-reviewer | claude_hook)" "principal_not_allowlisted"
  unset ADF_READ_POLICY_FILE ADF_READ_POLICY_SHA256
}

verify_evidence() {
  step "offline verification and the aggregate"
  local bundles; mapfile -t bundles < <(find "$ADF_HOME/evidence" -name '*.json' -not -path '*/_attempts/*' | sort)
  [ "${#bundles[@]}" -ge 5 ] || fail "expected at least 5 bundles, got ${#bundles[@]}"
  for bundle in "${bundles[@]}"; do adf verify "$bundle" >/dev/null || fail "bundle does not verify: $bundle"; done
  ok "${#bundles[@]} bundles verify offline"
  python3 - "${bundles[0]}" "$WORK/tampered.json" <<'PY'
import json, sys
bundle = json.load(open(sys.argv[1])); bundle["reason_code"] = "tampered"; json.dump(bundle, open(sys.argv[2], "w"))
PY
  if adf verify "$WORK/tampered.json" >/dev/null; then fail "a tampered bundle verified"; fi
  ok "a tampered bundle does not verify"
  local reasons; reasons="$(adf projects reasons)"
  expect "aggregate counts the deny" "$reasons" "invalid_scope="
  expect "aggregate counts contract denies from the journal" "$reasons" "invalid_referenced_contract="
  expect "aggregate names the subagent" "$reasons" "principal=claude:security-reviewer"
}

trials() {
  step "fixed local trial and A2A live trial"
  make -s local-evidence-trial TRIAL_ID="e2e-local-$$" >/dev/null && ok "local-evidence-trial"
  make -s a2a-live-trial TRIAL_ID="e2e-a2a-$$" >/dev/null && ok "a2a-live-trial: every case as expected, records verify"
}

hygiene() {
  step "no secret in evidence, project untouched"
  if grep -rq "$SECRET" "$ADF_HOME" "$WORK/adf/ai-development-framework/docs/observability" 2>/dev/null; then fail "the fixture secret leaked into evidence"; fi
  ok "the fixture secret appears in no evidence or report"
  [ -z "$(git -C "$PROJECT" status --porcelain --ignored)" ] || fail "something was written inside the project"
  [ "$(git -C "$PROJECT" worktree list | wc -l)" -eq 1 ] || fail "a snapshot worktree was left behind"
  ok "the project's working tree and worktree list are unchanged"
}

install_clone
fixture_project
local_edges
principal_policy
verify_evidence
trials
hygiene
echo "✓ e2e: release quickstart passed"
