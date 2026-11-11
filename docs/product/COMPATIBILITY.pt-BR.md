# Compatibilidade e evidências

[English](COMPATIBILITY.md) · **Português (Brasil)**

Quais bordas funcionam, em quais versões e **como sabemos**. Uma linha vale o seu nível de evidência
mais fraco. Nada aqui é "validado" sem uma execução registrada que você possa abrir.
A [matriz de suporte do BOUNDARY](BOUNDARY.pt-BR.md#matriz-de-suporte) lista o que cada borda não cobre.

## Níveis de evidência

| Nível | Significado | Onde roda |
| --- | --- | --- |
| **C — contrato** | Um teste entrega ao hook ou gateway real um payload sintético, no formato do cliente, e confere a decisão | `make quality` e o workflow `ci` |
| **E — clone limpo** | `make e2e` clona a árvore commitada, cria uma venv nova e aciona o CLI `adf` real com payloads sintéticos em um `ADF_HOME` isolado | localmente e no workflow `ci` |
| **R — cliente real** | O próprio processo do cliente chamou o hook durante uma sessão, e o registro informa a versão do cliente | um piloto no host, relatado em `docs/product/PILOT-*` |

C e E provam o lado do ADF no contrato. Só R prova que uma versão do cliente de fato chama o hook
com aquele payload. Uma atualização do cliente pode mudar o payload; a versão do cliente faz parte da afirmação.

## Matriz

Estado em `0.2.0`. `na` significa não registrado, nunca "provavelmente funciona".

| Borda | C | E | R — versão do cliente | Resultado | Evidência |
| --- | :-: | :-: | --- | --- | --- |
| Gate `Read` do Claude Code | ✓ | ✓ | observado, versão `na` | permite README; nega `.env` e `config/.env` com bundle; `cat` composto negado | [teste do read hook](../../ai-development-framework/hooks/test-adf-read-hook.py), [e2e](../../ai-development-framework/e2e/quickstart.sh), [piloto 2026-10-20, sessões 2–4](PILOT-20261020.pt-BR.md#o-que-foi-feito-em-ordem) |
| Gates deny-only do Claude Code (`Grep`, `Glob`, `Edit`, `Write`, `WebFetch`, `Bash` selecionado) | ✓ | — | `na` | negados em paths sensíveis e de configuração do agente; entrada no journal, sem bundle | [teste do deny gate](../../ai-development-framework/hooks/test-adf-deny-gate.py), [gramática Bash](../../ai-development-framework/hooks/test-bash-read-grammar.py); o smoke do piloto 2026-11-04 usou payloads sintéticos ([relatório](PILOT-20261104.pt-BR.md)) |
| Codex CLI `Bash` com um único `cat PATH` | ✓ | ✓ | `na` (path de configuração documentado para 0.157.0) | `cat README.md` passa, `cat config/.env` negado, `cat` composto negado | [teste do gate Codex](../../ai-development-framework/hooks/test-codex-bash-read-gate.py), [e2e](../../ai-development-framework/e2e/quickstart.sh) |
| Gateway A2A em loopback | ✓ | ✓ | n/a — gateway e cliente de teste do próprio ADF | decisões vinculadas ao efeito via HTTP em `127.0.0.1`; HS256 de piloto e RS256 + JWKS pinado | [teste do gateway](../../ai-development-framework/hooks/test-a2a-gateway.py), [relatórios dos trials ao vivo](../../ai-development-framework/docs/observability/trials/a2a-live/README.md) |
| Leitura mediada MCP stdio | ✓ | — | `na` (sem execução em cliente Claude/Codex real) | o ADF devolve os bytes do snapshot, `delivery_mode=mediated` | [teste cliente MCP ↔ A2A](../../ai-development-framework/hooks/test-mcp-a2a-client.py) |
| Gate de registro MCP (Claude Code) | ✓ | — | `na`; probe conferido só contra o servidor do próprio ADF | servidor/ferramenta não registrado ou com drift é negado | [teste do registro](../../ai-development-framework/hooks/test-mcp-registry-2.py), [idade do probe](../../ai-development-framework/hooks/test-mcp-probe-age.py) |
| Cursor | — | — | — | sem adaptador | — |

O GIF do `make demo` é nível C: CLI e hook reais, payloads sintéticos, rotulados como tal.

## Garantia Community por integração

O que a edição Community (MIT) garante, borda a borda. **Não há enforcement global**: cada linha vale só enquanto a
ativação no host vale (hook registrado e invocado, executável presente, projeto listado em
`~/.adf/enabled-projects`; [ADR 0026](../../ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md)).

| Status | Significado |
| --- | --- |
| **enforced** | Toda chamada que chega a esta borda recebe uma decisão do ADF antes do efeito; um teste de contrato prova isso |
| **partial** | Só nega, ou só alguns formatos recebem decisão; o resto passa **sem decisão** |
| **unsupported** | O ADF não decide; valem as permissões do próprio cliente |
| **unverified** | Implementado e testado em contrato, mas nenhuma execução registrada em cliente real (nível R) mostra o cliente chamando |

| Integração | Status | Mecanismo | Policy de leitura | Teste |
| --- | --- | --- | --- | --- |
| Claude Code `Read` | enforced (`gate_only`) | `adf-read-hook.py` → `claude-code-read-gate.py` → PDP, PEP, leitura do snapshot; bundle | policy do host pinada, senão a demo de referência | [teste do hook de leitura](../../ai-development-framework/hooks/test-adf-read-hook.py), [teste do adaptador](../../ai-development-framework/hooks/test-local-read-adapter.py) |
| Gate de negação Claude Code `Grep`/`Glob`/`Edit`/`Write` | partial (só nega) | `adf-deny-gate.py`: paths sensíveis e de configuração do agente negados, nunca um allow; `Grep`/`Glob` sem `path` não cobertos; journal, sem bundle | nenhuma: policy fixa de paths sensíveis | [teste do deny gate](../../ai-development-framework/hooks/test-adf-deny-gate.py), [teste do journal](../../ai-development-framework/hooks/test-deny-gate-journal.py) |
| Claude Code `Bash` | partial | `cat PATH` único decidido como no Codex; equivalentes de leitura listados sobre paths sensíveis e rede após tentativa sensível negados (ADR 0028 1b/1c); outros formatos sem decisão | `cat`: pinada ou demo; regras só-nega: nenhuma | [gramática Bash](../../ai-development-framework/hooks/test-bash-read-grammar.py), [gramática 2](../../ai-development-framework/hooks/test-bash-grammar-2.py) |
| Codex CLI `cat PATH` | enforced (`gate_only`) | `codex-bash-read-gate.py`: um `cat` na allowlist → adaptador; bundle. Registro não pinado pelo `adf doctor` | policy do host pinada, senão a demo de referência | [teste do gate Codex](../../ai-development-framework/hooks/test-codex-bash-read-gate.py) |
| Codex CLI outros comandos de shell | partial (só nega) | mesma gramática só-nega do `Bash` do Claude; scripts, interpretadores e binários não listados ficam sem decisão | nenhuma | [gramática Bash](../../ai-development-framework/hooks/test-bash-read-grammar.py) |
| Servidor MCP stdio de leitura | unverified | `mcp_read_server.py` devolve os bytes do snapshot do adaptador, `delivery_mode=mediated`; sem execução em cliente real | policy do host pinada, senão a demo de referência | [teste cliente MCP ↔ A2A](../../ai-development-framework/hooks/test-mcp-a2a-client.py) |
| Gateway A2A loopback | enforced (só loopback) | bearer verificado no transporte e revalidado no efeito; não executa leituras sem policy pinada válida | **somente** policy do host pinada, nunca a demo | [teste do gateway](../../ai-development-framework/hooks/test-a2a-gateway.py) (`test_missing_or_tampered_host_policy_fails_closed_without_demo_grants`) |
| Subagentes do Claude Code | partial | mesmo hook e mesmos gates da thread principal; principal `claude:<agent_type>` afirmado pelo harness, não autenticado (ADR 0023, 0033) | a da borda que o subagente usa | [teste de principal de subagente](../../ai-development-framework/hooks/test-subagent-principal.py) |
| Hook não registrado, ou falha de bootstrap | unsupported | o wrapper e o `adf hook` saem com 0 sem decisão; não existe registro do ADF | — | [teste de semântica de falha](../../ai-development-framework/hooks/test-hook-failure-semantics.py), [teste da CLI](../../ai-development-framework/hooks/test-adf-cli.py) |

**Demo de referência vs policy pinada.** Sem `ADF_READ_POLICY_FILE` nem `ADF_READ_POLICY_SHA256` no ambiente do
hook, as bordas de leitura marcadas acima rodam a **demo de referência**: ela concede cada path não sensível
solicitado. Paths sensíveis continuam negados, mas não é uma allowlist revisada. Só uma das duas variáveis, valor
vazio, path relativo, arquivo ausente ou malformado, ou pin divergente nega toda leitura com
`host_policy_invalid`; nunca cai para a demo. `adf doctor`, `adf hook-snippet` e
`adf projects enable` dizem qual está em vigor ([teste](../../ai-development-framework/hooks/test-demo-policy-defaults.py)).
Os bundles registram `policy_sha256`, não se a policy veio da demo.

**Escopo do `gate_only`.** Nas bordas `gate_only` (Claude `Read`, Codex `cat`) o ADF decide sobre o snapshot Git e a
ferramenta nativa do cliente lê depois a working tree viva. O bundle prova a decisão e uma leitura confinada do
snapshot, nunca os bytes que a ferramenta nativa entregou (ADR 0026, claim C5). Quando os bytes entregues precisam
ser os decididos, use uma borda mediada.

**Princípio (intenção).** Os defaults da Community nunca são mais fracos que qualquer pack pago. Uma oferta paga
futura pode acrescentar conteúdo mantido ou serviços. Ela não muda o que as bordas Community decidem para a mesma entrada.

## Reproduza

Níveis C e E, a partir de um clone, sem tocar nas configurações de nenhum cliente:

```bash
python3 -m venv .venv && source .venv/bin/activate && make install-dev
make demo          # três decisões + verificação offline (C)
make e2e           # clone limpo, as duas bordas de hook, os dois trials (E)
```

## Registre uma observação em cliente real (nível R)

Faça isto em um host cujas configurações de cliente sejam suas, em um repositório descartável com um `.env` falso.

1. Registre as versões: `claude --version` ou `codex --version`, e `git -C /caminho/do/adf rev-parse HEAD`.
2. Registre o hook a partir de `adf hook-snippet claude|codex` ([ativação](QUICKSTART.pt-BR.md#ative-um-cliente-real-depois)), reinicie o cliente, `adf projects enable /abs/descartavel`, `adf doctor --pin`; `make doctor` precisa sair com 0.
3. Em uma sessão nova do cliente, peça `README.md` e depois `.env`.
4. `adf projects reasons` precisa contar um `delivered/read_delivered` e um `invalid_scope`; `adf verify BUNDLE --key ~/.adf/evidence.key` precisa informar `authenticity=valid`.
5. Acrescente uma linha a um relatório `PILOT-*` datado com as versões, os prompts e as contagens. Só então troque o `na` acima por essa versão.

Nenhum registro do ADF após o passo 3 significa que o cliente não chamou o hook: **sem decisão**, não um deny.
