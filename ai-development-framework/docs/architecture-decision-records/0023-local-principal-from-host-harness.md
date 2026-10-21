# ADR 0023: principal local derivado do harness do host

> **English summary.** ADR 0014 left local edges with `principal=None`, and in the 2026-10-20 pilot three parallel subagents produced evidence that did not say which one read what. The proposal adds `local_principal(payload, edge)`, which builds a `CallerPrincipal` 1.0 from the harness-supplied `agent_type` (`sub = <edge>:<agent_type>` or `<edge>:main`, `scopes = ["workspace:read"]`, `authn_method = host_harness`, `expires_at` now plus 3600 s), denies a malformed `agent_type` with `invalid_principal`, and adds `principal_sub` to the `started` journal event and `adf.agent_type` to the OTel allowlist; decisions and bundles do not change, and MCP stdio stays without a principal. Status: Accepted by the maintainer on 2026-10-21 (release 0.1.0 preparation). Residual risk: `agent_type` is asserted by the harness, so a compromised harness can assert anything, and the local principal authorizes nothing by itself. The full record below is in Portuguese.

- **Status:** Accepted — aceite humano em 2026-10-21 (mantenedor, preparação do release 0.1.0); antes: Proposed — aguarda aceite humano.
- **Date:** 2026-10-21
- **Depends on:** ADRs 0010, 0014, 0021 (emenda aditiva às três).
- **Scope:** bordas locais Claude `Read`/`Bash` e Codex `cat`. Sem token, sem IdP, sem efeito novo.

## Problema

A ADR 0014 deixou as bordas locais passarem `principal=None`: o host é confiável e não havia como
distinguir quem pedia. O piloto de 2026-10-20 rodou três subagentes em paralelo no mesmo projeto e a
evidência não dizia qual deles leu o quê. Sem principal local, a policy por principal (próxima ADR)
não tem a quem se aplicar nas bordas que mais importam no dia a dia.

Verificação empírica (2026-10-21, Claude Code headless com um subagente): dentro de um subagente o
payload do `PreToolUse` traz `agent_id` e `agent_type`; na thread principal os dois estão ausentes e o
`session_id` é o mesmo. É informação do harness, não do `tool_input`.

## Decisão

- `local_principal(payload, edge)` em `integration/read_gate_host.py` monta um `CallerPrincipal` 1.0:
  `sub = <edge>:<agent_type>` (`claude:security-reviewer`), ou `<edge>:main` quando o campo não existe;
  `scopes = ["workspace:read"]`, `act = []`, `token_aud = local-host`, `authn_method = host_harness`
  (valor novo no enum), `expires_at = agora + 3600 s` (o PEP continua checando).
- `agent_type` malformado (não string, fora de `[A-Za-z0-9][A-Za-z0-9_.-]{0,119}`) é `deny
  invalid_principal` antes do adapter: o harness é a raiz de confiança, um valor estranho é falha.
- O principal chega ao PDP e ao PEP pelo caminho que a ADR 0014 já abriu. Decisão e bundle não mudam:
  o PDP v1 não usa campos do principal; esta ADR só o torna presente.
- O journal de tentativa (ADR 0010) ganha `principal_sub` opcional no payload de `started`. Vale para
  todas as bordas, inclusive A2A, que já tinha principal. O bundle continua sem principal.
- O span `adf.local_read.request` ganha `adf.agent_type` (emenda à allowlist da ADR 0021). `agent_id`
  não entra em lugar nenhum fora do payload do hook.
- MCP stdio (`mcp_read_server.py`) continua sem principal: o servidor não recebe payload de hook.

## Contratos

Aditivos: `host_harness` no enum `authn_method` do `CallerPrincipal`; `principal_sub` opcional no
payload `started` do `AdapterAttemptEvent`; `adf.agent_type` na allowlist OTel. `ToolCallIntent`,
`EvidenceBundle` e `AdmissionDecision` inalterados.

## Risco residual

O `agent_type` é afirmado pelo harness; um harness comprometido afirma o que quiser, o que já valia
para tudo o que o hook recebe. O principal local não autoriza nada por si (mesmo scope para todos
até a ADR de policy por principal). `expires_at` fixo em 1 h é um teto, não uma sessão.

## Reversão

Remover a chamada a `local_principal` nas duas bordas volta a `None`. Journals com `principal_sub` e
spans com `adf.agent_type` continuam válidos como histórico.
