# ADF · one-pager

[English](ONEPAGER.md) · **Português (Brasil)**

**Segurança de efeitos para coding agents: negar e provar leituras sensíveis no notebook do desenvolvedor.**

## Problema

Coding agents (Claude Code, Codex, peers A2A) rodam com as permissões do desenvolvedor. Eles leem
`.env`, chaves privadas e diretórios de segredos tão facilmente quanto leem o README. A allowlist do
IDE pede confirmação mas não deixa prova; a ferramenta de observabilidade mostra o que aconteceu, mas
não impediu nada. Times de AppSec e Platform não têm um ponto de enforcement nem evidência para auditar.

## Como funciona

```text
agente ──▶ borda (hook Read · cat allowlisted · A2A HTTP + bearer)
            │
            ▼
          PDP  (determinístico, policy pinada pelo host)  ──deny──▶ Evidence Bundle
            │ admit_read
            ▼
          PEP  (revalida run, snapshot, principal no instante do efeito) ──deny──▶ Evidence Bundle
            │
            ▼
          runtime de leitura confinado (snapshot Git, sem symlink, budget, paths sensíveis)
            │
            ▼
          conteúdo marcado não confiável + Evidence Bundle (verificação offline)
```

## Wedge v1

- Policy pack [`effect-security-read-v0`](../../ai-development-framework/policy-packs/effect-security-read-v0/README.md):
  allowlist exata pinada por SHA-256, recusa `.env*`, `*.pem`, `*.key`, `secrets/`, credenciais de nuvem e SSH.
- Bordas reais: Claude Code `Read`, Codex `cat`, A2A loopback.
- Prova: cada decisão vira um bundle que um auditor verifica offline, sem LLM e sem serviço externo.
- Ativação por host: um clone, um hook global, N projetos ligados por allowlist (`~/.adf/enabled-projects`);
  evidência fora do repo do cliente. Nada é decidido fora da lista.
- Risco residual declarado na [matriz de suporte](BOUNDARY.pt-BR.md#matriz-de-suporte).

## Operação para partner (um projeto, 5 passos)

1. **Ligar o projeto:** `make project-enable PROJECT=/abs/raiz/do/repo` (uma vez, após registrar o hook global
   conforme [trials.md](../../ai-development-framework/docs/trials.pt-BR.md#vários-projetos-com-um-hook-só-req-mp-01)).
2. **Ver o deny:** peça ao agente para ler `config/.env`. O `Read` (Claude) ou `cat` (Codex) volta
   `deny invalid_scope` e o conteúdo não chega ao modelo.
3. **Ver o allow:** peça para ler `README.md`. Entregue, com bundle.
4. **Onde está a prova:** `~/.adf/evidence/<projeto>-<hash>/<AAAA-MM-DD>/<session>/*.json`; cada bundle verifica
   offline (`verify_offline`); `make project-reasons` dá as contagens por projeto.
5. **O que fica de fora:** `Bash`/`Grep`/`Glob` no Claude e tudo além de `cat PATH` no Codex; o agente pode
   editar a lista de projetos; arquivo não commitado, binário ou acima do budget é negado.

## Demo (5 minutos)

```bash
make install-dev
make local-evidence-trial TRIAL_ID="demo-$(date -u +%Y%m%dT%H%M%SZ)"   # deny sensível, allow comum, verify
```

Opcional: o trial A2A ao vivo com spans no Jaeger
([relatório](../../ai-development-framework/docs/observability/trials/a2a-live/README.md)).

## Open core e oferta para times (futuro)

| Open core (MIT, neste repo) | Para times (futuro, sem código de billing aqui) |
| --- | --- |
| PDP, PEP, runtime, contratos, evidência, verificação offline | Policy packs mantidos por stack e linguagem |
| Bordas Claude / Codex / A2A, export OTel redigido | Trial reports conduzidos com o time de AppSec |
| Policy pack v0, trials repetíveis | Runbooks JWKS/IdP para piloto enterprise |
| | Suporte a design partners |

## O que não é

UI de orquestração, substituto do Langfuse, gateway MCP/A2A em nuvem, sandbox de host, cobertura total de
`Bash`, efeito de escrita, certificação de compliance. Não há métricas de clientes publicadas: os números do repo vêm de trials locais e
sequenciais, não de produção.

## Contato

Issues: <https://github.com/Joaolucas2210/agent-effect-security/issues> · Vulnerabilidades: reporte em privado em <https://github.com/Joaolucas2210/agent-effect-security/security/advisories/new>, nunca numa issue pública.
