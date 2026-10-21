# ADR 0011: policy de leitura fixada pelo host

> **English summary.** The adapter's demo mode synthesizes scope and budgets from the requested path, so no organization-configured authorization applies. The proposal adds an opt-in host policy: a closed JSON envelope loaded once per instance and pinned by a mandatory canonical SHA-256 (`ADF_READ_POLICY_FILE`, `ADF_READ_POLICY_SHA256`); any partial, invalid or divergent configuration returns `host_policy_invalid` before any read, and the absence of both keeps the demo mode. Status: Accepted by the maintainer on 2026-10-21 (release 0.1.0 preparation); the host policy remains opt-in. Residual risk: whoever can replace the host configuration and pin changes the authority (hashes only detect divergence), the gates remain `gate_only` because the native tool still delivers bytes outside the snapshot, and the reported coverage (97.87% of changed executable lines) and mutation results are targeted, not full scores. The full record below is in Portuguese.

- **Status:** Accepted — aceite humano em 2026-10-21 (mantenedor, preparação do release 0.1.0); antes: Proposed — implementação opt-in na branch para revisão humana.
- **Date:** 2026-09-26
- **Depends on:** ADRs 0007–0010.
- **Scope:** P0-B da [pesquisa de evolução](../research/2026-09-26-product-evolution.md).

## Context and proposed decision

O modo demonstrativo do adapter cria scope e budgets para o path solicitado.
Preservar esse modo ajuda a compatibilidade, mas ele não aplica autorização
organizacional previamente configurada. Acrescentar opção explícita de carregar
um JSON do host antes das intenções, com pin SHA-256 canônico obrigatório.

O envelope fechado 1.0 contém apenas `schema_version`, `profiles`, `policy`,
`context`. Reutiliza os contratos v1 e suporta um profile/uma operação. Validar
shape, schemas, pin externo e hashes internos no carregamento. Não reparar
artefato, hash, permissão ou binding inconsistente. PDP/PEP continuam decidindo
scope exato, efeitos read-only, run ID e menor teto; pedido acima do teto é negado.

`LocalReadAdapter` aceita keywords `host_policy_path` e `host_policy_sha256`.
O host dos gates fornece `ADF_READ_POLICY_FILE` absoluto e
`ADF_READ_POLICY_SHA256`, sem usar campos do payload. Qualquer configuração
parcial, inválida ou divergente retorna `host_policy_invalid`, sem preparar
workspace, fazer a leitura ou expor erro cru; o journal registra essa negação.
Ambas ausentes mantêm o demo anterior, identificado como tal na documentação.

## Session and trust boundaries

Carregar uma vez por instância e copiar os artefatos por intenção. O context
fornecido pelo host já deve vincular o run ID ao session ID do harness. Não
reescrever esse binding com dados do pedido. Um adapter não aceita alterações
posteriores no arquivo; outro processo verifica o mesmo pin fornecido pelo host.
O host deve manter o pin fixo durante a sessão e revisar novas versões entre sessões.

Não há store central de sessão ou autenticação do emissor. Quem pode substituir
configuração e pin do host altera a autoridade; hashes só detectam divergência.
Os gates continuam `gate_only`: a tool nativa entrega bytes fora do snapshot.
Não adicionar wildcard/DSL, providers remotos, cache ou efeitos novos.

## Validation and rollback

Testes primeiro: path fora da allowlist não chega ao runtime; run ID divergente;
budget acima do teto; pin e hash interno errados; versões/campos extras; configuração
parcial; policy trocada após construção e entre processos; payload tentando
sobrescrever policy; ausência de configuração conserva demo. Reutilizar o teste
existente do adapter para exercitar gates Claude e Codex.

Executar suites adapter/Codex/trial, `make quality`, `make eval`, `make graph-check`
e revisões de segurança/compatibilidade. Skips e medições limitadas devem ser
reportados como tal. Rollback: remover ambas as opções do host para voltar ao
modo de demonstração, sem apresentá-lo como policy organizacional, ou revert
revisado da implementação. Manter evidências históricas; ADR continua Proposed.

Na branch, 2026-09-26: 20 testes do adapter, 2 do gate Codex, 4 de trial,
`make quality` (26 self-tests), `make eval`, `make eval-required` e
`make graph-check` passaram. Backend/segurança: pass; QA: pass no escopo direcionado.
Trace da stdlib: 138/141 linhas executáveis alteradas exercitadas (97,87%);
13/13 mutações direcionadas mortas, sem sobreviventes. Isso não é score completo
de coverage/mutation. O teste protege contratos internos inválidos mesmo com
hashes recalculados, além de adulteração schema-valid sem rehash no journal.

Coverage/mutation completos, CCN e lint Python não executados por indisponibilidade
de ferramentas; checks opcionais JS de coverage/ciclos/mutation e um teste independente
de JSON Schema também skipped. Um gate de estabilidade do checkout falhou durante
refresh concorrente do grafo; refresh terminou e o gate serial passou sem relaxar
o teste. Grafo final: 3.701 nós/4.947 arestas; tokens e custo de execução indisponíveis (`na`).
