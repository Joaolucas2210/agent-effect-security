# ADF · one-pager

[English](ONEPAGER.md) · **Português (Brasil)**

**Decisão local e evidência limitada para leituras nas bordas de agente instaladas.**

## Problema

Coding agents (Claude Code, Codex, peers A2A) podem pedir `.env`, chaves privadas e diretórios de segredos
durante o trabalho com arquivos comuns. Prompts e traces ajudam a revisar a sessão; o ADF acrescenta uma
decisão controlada pelo host e um caminho de evidência nas bordas específicas instaladas. Outras rotas para o
mesmo arquivo continuam sendo um risco.

## Como funciona

```text
agente ──▶ borda (hook Read · cat allowlisted · A2A HTTP + bearer)
            │
            ├── deny pré-adapter ──▶ journal de tentativas (sem bundle)
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
- Bordas implementadas: Claude Code `Read`, Codex `cat`, A2A loopback; versões de cliente real e ativação no host variam.
- Prova: decisões compostas têm bundle; negações observadas antes têm entrada no journal. A checagem de
  integridade offline dispensa serviço; autenticidade HMAC exige a chave compartilhada do host e não é pública.
- Ativação por host: um clone, um hook global, N projetos ligados por allowlist (`~/.adf/enabled-projects`);
  evidência fora do repo do cliente. Nada é decidido fora da lista.
- Risco residual declarado na [matriz de suporte](BOUNDARY.pt-BR.md#matriz-de-suporte).

## Operação para partner (um projeto, 5 passos)

1. **Ligar o projeto:** `make project-enable PROJECT=/abs/raiz/do/repo` (uma vez, após registrar o hook global
   conforme [trials.md](../../ai-development-framework/docs/trials.pt-BR.md#vários-projetos-com-um-hook-só-req-mp-01)).
2. **Ver o deny:** na fixture local do hook, `config/.env` retorna `deny invalid_scope` e o ADF não devolve
   conteúdo. O tratamento do hook por um cliente real deve ser conferido na versão instalada.
3. **Ver o allow:** peça para ler `README.md`. Entregue, com bundle.
4. **Onde está a prova:** `~/.adf/evidence/<projeto>-<hash>/<AAAA-MM-DD>/<session>/*.json`; cada bundle verifica
   offline (`verify_offline`); `make project-reasons` dá as contagens por projeto.
5. **O que fica de fora:** leituras por scripts e interpretadores fora da gramática do hook, tools MCP não
   observadas e outras rotas ao disco; o agente pode editar a lista de projetos por uma rota não observada.
   Arquivo não commitado, binário ou acima do budget é negado quando a leitura chega ao runtime controlado.

## Demo com fixture local

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
| Policy pack v0, trials repetíveis | Runbooks JWKS/IdP para piloto |
| | Suporte a design partners |

## O que não é

UI de orquestração, substituto do Langfuse, gateway MCP/A2A em nuvem, sandbox de host, cobertura total de
`Bash`, efeito de escrita, certificação de compliance. Não há métricas de clientes publicadas: os números do repo vêm de trials locais e
sequenciais, não de produção.

## Contato

Issues: <https://github.com/Joaolucas2210/agent-effect-security/issues> · Vulnerabilidades: reporte em privado em <https://github.com/Joaolucas2210/agent-effect-security/security/advisories/new>, nunca numa issue pública.
