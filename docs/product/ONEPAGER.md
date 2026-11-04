# ADF · one-pager

**English** · [Português (Brasil)](ONEPAGER.pt-BR.md)

**A local decision point and bounded evidence for reads through installed agent edges.**

## Problem

Coding agents (Claude Code, Codex, A2A peers) can request `.env`, private keys and secrets directories
while working on ordinary files. Prompts and traces help review a session; ADF adds a host-owned decision
and an evidence path for the specific edges that are installed. Other routes to the same file remain a risk.

## How it works

```text
agent ──▶ edge (Read hook · allowlisted cat · A2A HTTP + bearer)
            │
            ├── pre-adapter deny ──▶ attempt journal (no bundle)
            ▼
          PDP  (deterministic, policy pinned by the host)  ──deny──▶ Evidence Bundle
            │ admit_read
            ▼
          PEP  (revalidates run, snapshot, principal at the moment of the effect) ──deny──▶ Evidence Bundle
            │
            ▼
          confined read runtime (Git snapshot, no symlink, budget, sensitive paths)
            │
            ▼
          content marked untrusted + Evidence Bundle (offline verification)
```

## Wedge v1

- Policy pack [`effect-security-read-v0`](../../ai-development-framework/policy-packs/effect-security-read-v0/README.md):
  exact allowlist pinned by SHA-256, refuses `.env*`, `*.pem`, `*.key`, `secrets/`, cloud and SSH credentials.
- Implemented edges: Claude Code `Read`, Codex `cat`, A2A loopback; real-client versions and host activation vary.
- Proof: composed decisions have a bundle; earlier observed denies have a journal entry. Offline integrity
  checks need no service; HMAC authenticity needs the host's shared key and is not public verification.
- Host activation: one clone, one global hook, N projects enabled by allowlist (`~/.adf/enabled-projects`);
  evidence outside the project repository. Nothing is decided outside the list.
- Residual risk declared in the [support matrix](BOUNDARY.md#support-matrix).

## Partner operation (one project, 5 steps)

1. **Enable the project:** `make project-enable PROJECT=/abs/repo/root` (once, after registering the global hook
   as described in [trials.md](../../ai-development-framework/docs/trials.md#many-projects-one-hook-req-mp-01)).
2. **See the deny:** in the local hook fixture, `config/.env` returns `deny invalid_scope` and ADF returns
   no content. A real client's handling of the hook must be checked on its installed version.
3. **See the allow:** ask it to read `README.md`. Delivered, with a bundle.
4. **Where the proof is:** `~/.adf/evidence/<project>-<hash>/<YYYY-MM-DD>/<session>/*.json`; each bundle verifies
   offline (`verify_offline`); `make project-reasons` gives the counts per project.
5. **What stays out:** scripts and interpreter reads outside the hook grammar, unobserved MCP tools and other
   routes to disk; the agent can edit the project list through an unobserved route. An uncommitted file, a
   binary or a file over the budget is denied when the read reaches the controlled runtime.

## Local fixture demo

```bash
make install-dev
make local-evidence-trial TRIAL_ID="demo-$(date -u +%Y%m%dT%H%M%SZ)"   # sensitive deny, common allow, verify
```

Optional: the live A2A trial with spans in Jaeger
([report](../../ai-development-framework/docs/observability/trials/a2a-live/README.md)).

## Open core and team offering (future)

| Open core (MIT, in this repo) | For teams (future, no billing code here) |
| --- | --- |
| PDP, PEP, runtime, contracts, evidence, offline verification | Policy packs maintained per stack and language |
| Claude / Codex / A2A edges, redacted OTel export | Trial reports conducted with the AppSec team |
| Policy pack v0, repeatable trials | JWKS/IdP runbooks for a pilot |
| | Design partner support |

## What it is not

Orchestration UI, Langfuse replacement, cloud MCP/A2A gateway, host sandbox, full `Bash` coverage,
write effect, compliance certification. There are no published customer metrics: the numbers in the repo
come from local, sequential trials, not from production.

## Contact

Issues: <https://github.com/Joaolucas2210/agent-effect-security/issues> · Vulnerabilities: report privately at <https://github.com/Joaolucas2210/agent-effect-security/security/advisories/new>, never in a public issue.
