#!/usr/bin/env bash
# MCP security audit — no MCP server enters the framework without a declared allowlist.
# "MCP with security by default" (root CLAUDE.md, principle 4): private data + untrusted
# content + external communication is a human-review boundary, not an automatic yes.
# HARD (exit 1): no allow{} block, command not in allow.commands, broad shell interpreter,
#   shell metachar/wildcard in args, secret-like env not in allow.env, hardcoded secret value,
#   lethal trifecta (private_data+untrusted_content+external_comms) without human_reviewed:true.
# WARN (advisory): missing/ambiguous description, no trust{} classification.
# Usage: mcp-audit.sh [SERVERS_JSON]   (default: ai-development-framework/mcp/servers.json)
# Threat model & schema: ai-development-framework/docs/mcp-security.md
set -uo pipefail

ADF="ai-development-framework"
file="${1:-$ADF/mcp/servers.json}"

command -v jq >/dev/null 2>&1 || { echo "✗ mcp-audit: jq required (apt/brew install jq)"; exit 1; }
[ -f "$file" ] || { echo "✗ mcp-audit: $file missing"; exit 1; }
jq -e . "$file" >/dev/null 2>&1 || { echo "✗ mcp-audit: $file is not valid JSON"; exit 1; }

echo "▶ mcp-audit ($file)"

# All rules live in jq — one FAIL/WARN line per finding, tab-separated: LEVEL<TAB>server<TAB>reason.
# (No single quotes inside messages: the program is bash-single-quoted and jq lacks a \x27 escape.)
findings="$(jq -r '
.servers // {} | to_entries[] | .key as $n | .value as $s | [

  (if ($s.allow | type) != "object"
     then "FAIL\t\($n)\tno allow{} block — undeclared server surface" else empty end),

  (if ($s.command // "") != "" and (($s.allow.commands // []) | index($s.command) | not)
     then "FAIL\t\($n)\tcommand [\($s.command)] not in allow.commands" else empty end),

  (if ($s.command // "") | test("^(sh|bash|zsh|dash|env|eval|python|node)$")
     then "FAIL\t\($n)\tbroad interpreter as command: [\($s.command)] (wrap in a fixed binary)" else empty end),

  (($s.args // [])[] | select(type=="string" and test("[;|&$`><]|\\*"))
     | "FAIL\t\($n)\tshell metachar/wildcard in arg: [\(.)]"),

  (($s.env // {}) | to_entries[] | .key as $k | .value as $v |
     ( if ($k | test("SECRET|TOKEN|KEY|PASSWORD|PASSWD|CREDENTIAL"; "i"))
            and (($s.allow.env // []) | index($k) | not)
          then "FAIL\t\($n)\tsecret-like env [\($k)] not in allow.env" else empty end ),
     ( if ($k | test("SECRET|TOKEN|KEY|PASSWORD|PASSWD|CREDENTIAL"; "i"))
            and ($v | type=="string") and ($v != "")
            and (($v | test("^\\$\\{?[A-Za-z0-9_]+\\}?$")) | not)
          then "FAIL\t\($n)\thardcoded secret value in env [\($k)] (use a ${VAR} ref)" else empty end )),

  (if ($s.trust.private_data == true and $s.trust.untrusted_content == true and $s.trust.external_comms == true)
        and ($s.human_reviewed != true)
     then "FAIL\t\($n)\tlethal trifecta (private_data+untrusted_content+external_comms) without human_reviewed:true" else empty end),

  (if (($s.description // "") | length) < 20
     then "WARN\t\($n)\tdescription missing/ambiguous (<20 chars)" else empty end),

  (if ($s.trust | type) != "object"
     then "WARN\t\($n)\tno trust{} classification (private_data/untrusted_content/external_comms)" else empty end)

] | .[]' "$file")" || { echo "✗ mcp-audit: audit program failed (jq error above)"; exit 1; }

count=$(jq '.servers // {} | length' "$file")
fails=0; warns=0
if [ -n "$findings" ]; then
  while IFS=$'\t' read -r lvl name msg; do
    [ -n "$lvl" ] || continue
    if [ "$lvl" = "FAIL" ]; then echo "✗ $name: $msg"; fails=$((fails+1));
    else echo "⚠ $name: $msg"; warns=$((warns+1)); fi
  done <<< "$findings"
fi

echo
echo "servers: $count · hard fails: $fails · warnings: $warns"
[ "$fails" -eq 0 ] || { echo "✗ mcp-audit: $fails hard failure(s) — see docs/mcp-security.md"; exit 1; }
echo "✓ mcp-audit passed ($warns warning(s))"
