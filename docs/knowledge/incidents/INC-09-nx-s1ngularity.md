# INC-09: Nx "s1ngularity" supply-chain attack

- **Date / source:** 2025-08 · Nx advisory; multiple vendor analyses
- **Threat:** THR-07, THR-04 · **Legs:** — (host compromise) · **OWASP:** ASI04
- **Status:** out_of_scope · **Eval:** —

## Vector

Malicious `nx` npm releases ran a postinstall that invoked locally installed Claude Code, Gemini CLI and
Amazon Q with permission-skipping flags to enumerate and exfiltrate secrets, then pushed them to public
repositories under the victim's account.

## Lesson

Once arbitrary code runs as the user, the agent is just another tool for the attacker. Permission flags are
not a security boundary when the caller is hostile.

## ADF

Out of the ADR 0026 boundary (host compromise). ADF hooks are per-session configuration; a process that
starts the agent with its own settings never passes through them. ADR 0027 would at most record that the
pinned hook was absent. Cite to state the limit.
