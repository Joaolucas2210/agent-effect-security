# Coverage map

Updated: 2026-11-04 · Model: [ADR 0026](../../ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md) · Status vocabulary in [README](README.md).

"Today" is `main` at the date above. "After" names the Proposed ADR that changes the status; nothing in
that column is delivered. Eval ids are placeholders until the case exists in `docs/evals`.

| Incident | Threat | Legs | Today | After | Eval |
| --- | --- | --- | --- | --- | --- |
| [INC-01](incidents/INC-01-rules-file-backdoor.md) Rules File Backdoor | THR-02 | 2 | covered (write) since 0028 1a | — | `test-adf-deny-gate.sh` |
| [INC-02](incidents/INC-02-github-mcp-exfil.md) GitHub MCP exfil | THR-03, THR-06 | 1,2,3 | residual (server must be registered; exfil via an MCP *write* tool after a sensitive attempt is not yet denied) | 1c extension to MCP write tools | `eval-inc-02` |
| [INC-03](incidents/INC-03-supabase-mcp-sql-exfil.md) Supabase MCP SQL exfil | THR-03 | 1,2,3 | out_of_scope | out_of_scope (demand needed) | — |
| [INC-04](incidents/INC-04-amazon-q-extension.md) Amazon Q extension | THR-07 | — | out_of_scope | out_of_scope | — |
| [INC-05](incidents/INC-05-cursor-curxecute-mcpoison.md) CurXecute / MCPoison | THR-02, THR-06 | 2 | covered since 0028 1a + 0031 1 (config write denied; unregistered server/tool denied) | — | `test-adf-deny-gate.sh`, `test-mcp-registry.sh` |
| [INC-06](incidents/INC-06-claude-code-path-bypass.md) Claude Code path bypass | THR-01 | 1 | covered (`Read`) | covered | `eval-inc-06` |
| [INC-07](incidents/INC-07-gemini-cli-allowlist-bypass.md) Gemini CLI allowlist bypass | THR-01, THR-03 | 1,2,3 | covered since 0028 1b + 1c (whitespace/separator smuggling → `uncovered_bash_ambiguous` or sensitive deny; exfil after a sensitive attempt denied) | — | `test-bash-read-grammar.sh`, `test-deny-gate-journal.sh` |
| [INC-08](incidents/INC-08-copilot-settings-autoapprove.md) Copilot settings auto-approve | THR-02, THR-04 | 2 | covered since 0028 1a + 0027 (config write denied; ADF's own registration/list/policy tamper denied) | — | `test-adf-deny-gate.sh`, `test-control-plane-pins.sh` |
| [INC-09](incidents/INC-09-nx-s1ngularity.md) Nx s1ngularity | THR-07, THR-04 | — | out_of_scope (host compromise); 0027 detects tamper of ADF's files only | — | `test-control-plane-pins.sh` |
| [INC-10](incidents/INC-10-idesaster.md) IDEsaster | THR-01, THR-02 | 1,2 | covered subset since 0028 1a-1c (context-file reads of secrets, config writes, exfil after a sensitive attempt) on supported edges; per-CVE mapping pending verified ids | — | `test-adf-deny-gate.sh`, `test-bash-read-grammar.sh` |
| [INC-11](incidents/INC-11-codex-mcp-config-loading.md) Codex MCP config loading | THR-02, THR-06 | 2 | covered since 0031 1 (unregistered server denied at the call; the client's own server *start* stays residual) | — | `test-mcp-registry.sh` |
| [INC-12](incidents/INC-12-replit-prod-db-deletion.md) Replit prod DB deletion | THR-08 | execution | out_of_scope | out_of_scope (anti-goal) | — |

Totals today (0027, 0028 complete, 0029, 0030, 0031 slice 1 delivered): covered 7 · residual 1 (INC-02) · out_of_scope 4.

`covered` here means the Claude Code edge with the project enabled; Codex sees only `Bash` and is not
covered by slice 1a.
