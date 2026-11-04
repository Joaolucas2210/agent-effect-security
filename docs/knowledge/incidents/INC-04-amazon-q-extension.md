# INC-04: Amazon Q Developer VS Code extension v1.84

- **Date / source:** 2025-07 · public reporting on the compromised release
- **Threat:** THR-07 · **Legs:** — (supply chain of the agent itself) · **OWASP:** ASI04
- **Status:** out_of_scope · **Eval:** —

## Vector

A pull request to the extension's repository added a prompt instructing the agent to wipe the user's
machine and cloud resources; it shipped in a release.

## Lesson

The agent vendor is in the trust base. No local control plane survives a malicious agent binary.

## ADF

Declared out of the ADR 0026 boundary. ADR 0027 would detect a change to ADF's *own* scripts, not to the
agent. Cite only to state the limit honestly.
