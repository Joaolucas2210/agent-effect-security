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
