# Threat classes

Attacker model: [ADR 0026](../../../ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md).
Trifecta legs: **1** private data · **2** untrusted content · **3** exfiltration channel.

| Id | Threat | Legs | OWASP ASI | ADF mechanism | Status | Incidents |
| --- | --- | --- | --- | --- | --- | --- |
| THR-01 | **Read-equivalent bypass**: the agent reads a sensitive file through a tool the gate does not see (`Grep`, `Glob`, Bash `head`/`sed`/`rg`, subprocess) | 1 | ASI02 | Covered edges only; ADR 0028 deny-only | residual | INC-06, INC-07, INC-09 |
| THR-02 | **Config-as-code execution**: untrusted content makes the agent write an agent/IDE/CI config that later executes or widens permissions (`.vscode/settings.json`, `.cursor/mcp.json`, `.claude/`, hooks, workflows) | 2 → execution | ASI05, ASI01 | None today; ADR 0028 `agent_config_policy_v1`, ADR 0032 | out_of_scope → covered after 0028 | INC-01, INC-05, INC-08, INC-10, INC-11 |
| THR-03 | **Exfiltration channel**: after a sensitive read, data leaves via `WebFetch`, `curl`, a PR/issue, an MCP write tool | 3 | ASI02 | None; ADR 0028 run-scoped deny of network tools after a sensitive-adjacent read | residual | INC-02, INC-03, INC-07 |
| THR-04 | **Control-plane tampering**: the agent edits ADF's own hook registration, project list, policy or scripts, silencing evidence | — | ASI03, ASI10 | ADR 0027 pins + `control_plane_tampered`; ADR 0030 key | residual → covered after 0027 | INC-08, INC-09 |
| THR-05 | **Evidence over-claim / forgery**: a bundle that verifies but was not issued by ADF, or proves the decision while readers assume it proves the bytes | — | ASI10 | ADR 0029 `delivery_mode`, ADR 0030 signature | residual | — |
| THR-06 | **Tool poisoning / rug-pull**: MCP tool descriptions or tool lists change after approval; repo ships its own MCP config | 2 | ASI04 | `cannot_authorize` on descriptions; ADR 0031 registry pin | out_of_scope → covered after 0031 | INC-02, INC-05, INC-11 |
| THR-07 | **Host or vendor compromise**: malicious agent update, postinstall driving the agent CLI, root | — | ASI04 | None by design | out_of_scope | INC-04, INC-09 |
| THR-08 | **Destructive effect without gate**: `rm`, DB drop, force push | execution | ASI02 | None by design (anti-goal) | out_of_scope | INC-12 |
