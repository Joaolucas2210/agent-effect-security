# INC-08: GitHub Copilot agent writes `.vscode/settings.json` to enable auto-approve (CVE-2025-53773)

- **Date / source:** 2025-08 · Embrace The Red ("ZombAI"); Microsoft advisory
- **Threat:** THR-02, THR-04 · **Legs:** 2 → execution · **OWASP:** ASI03, ASI05
- **Status:** out_of_scope → covered after ADR 0028 · **Eval:** `eval-inc-08` (red)

## Vector

Prompt injection makes the agent edit the workspace `.vscode/settings.json`, setting
`chat.tools.autoApprove: true`; from then on every tool call runs without confirmation — RCE and a wormable
pattern across repositories.

## Lesson

The agent's own permission configuration is the first thing an injected agent will edit. Native approval
prompts are a control the agent can switch off.

## ADF

After ADR 0028: writes to `.vscode/settings.json`, `.claude/`, `.codex/` denied
(`uncovered_write_denied_agent_config`); ADR 0027 records tampering with ADF's own registration. The
canonical case for the `agent_config_policy_v1` list.
