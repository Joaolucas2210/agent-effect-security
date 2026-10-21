# ADR 0010: lifecycle de tentativa do adapter

> **English summary.** An attempt can fail before an `EvidenceBundle` exists, and a `delivered` receipt does not prove the adapter finished successfully. The proposal adds `AdapterAttemptEvent` 1.0, an exclusive per-call journal under `_attempts/` with fsynced `started` and `completed` events, cleanup in `finally`, closed reason codes and a pure `verify_attempt` that returns `complete`, `incomplete` or `invalid`; if the journal write fails, the adapter returns `deny/attempt_evidence_failed` and no content. Status: Accepted by the maintainer on 2026-10-21 (release 0.1.0 preparation), after running on `main`; it does not change earlier acceptances. Residual limits: `complete` does not mean success or confirmed delivery to the harness, there is no transactional guarantee between journal and bundle, and if both the final fsync and its rollback fail, a `delivered` result may remain on disk despite the deny. The full record below is in Portuguese.

- **Status:** Accepted — aceite humano em 2026-10-21 (mantenedor, preparação do release 0.1.0); antes: Proposed — implementação na branch para revisão; não muda os aceites anteriores.
- **Date:** 2026-09-26
- **Depends on:** ADRs 0007–0009 e adapter local read-only.
- **Scope:** P0-A da [pesquisa de evolução](../research/2026-09-26-product-evolution.md).

## Context

Uma tentativa pode falhar antes de produzir `EvidenceBundle`. O bundle atual também
é persistido antes de cleanup: um receipt `delivered` não prova que o adapter
terminou com sucesso. `RunEvent` v1 só descreve o eval gate; reutilizá-lo para
leituras exigiria mudar os payloads e a semântica de um contrato fechado.

## Decision proposed for review

Acrescentar `AdapterAttemptEvent` 1.0, sem modificar bundles, receipts ou RunEvent.
Cada chamada de `LocalReadAdapter.read` cria um journal exclusivo em
`<evidence_dir>/_attempts/<attempt_id>.jsonl`. O nome reservado não pode colidir
com `run_id` válido; o ID é aleatório e não deriva dos argumentos.

1. Persistir e fazer fsync de `started` antes de validar a chamada/preparar workspace.
2. Preservar PDP, PEP e composição de bundle existentes.
3. Executar cleanup em `finally`, inclusive quando a composição é interrompida.
4. Persistir e fazer fsync de `completed` com resultado calculado pós-cleanup e pré-retorno, reason code fechado,
   bundle ID opcional e cleanup `not_attempted`, `succeeded` ou `failed`.
5. Entregar conteúdo somente se a gravação final tiver sucesso. Falha de journal
   retorna `deny/attempt_evidence_failed`; nunca retorna conteúdo.

Eventos guardam somente versão, canonicalização, IDs, timestamp, hashes e os
quatro campos de término. ID de run inválido é `null`: nenhuma representação,
hash ou fragmento dos argumentos inválidos é persistido. Reason codes são enum
fechado; exceções cruas não são evidência. Diretórios/arquivos novos usam 0700/0600;
raiz e filho `_attempts` recusam symlinks; arquivo exclusivo, identidade e nlink
são conferidos antes de cada append. Prefixos da raiz configurada pelo host
continuam sob responsabilidade do host; isso não contém outro processo do mesmo usuário.

O digest usa SHA-256 sobre JSON canônico `json-c14n-v1` de
`{"domain":"adapter-attempt-event-v1","event":<evento sem event_sha256>}`.
O término referencia o digest do início e mantém `attempt_id`, `adapter_id` e
`run_id`. Não existe resume, reaproveitamento de ID ou overwrite. Duplicação,
reordenação, contrato inválido ou binding divergente são inválidos.

`verify_attempt(events, schema)` é puro, sem I/O ou referências remotas. Retorna
`complete`, `incomplete` ou `invalid`; `complete` inclui negações e **não** significa
sucesso. Validar o bundle continua exigindo `verify_offline`. Ambos são checks de
integridade, não autenticação do emissor, autorização ou prova dos bytes da tool nativa.
O payload também não confirma que o harness recebeu conteúdo: é calculado antes
da persistência final e do retorno. Confirmação de entrega requer observação independente do consumidor.

## Limits and compatibility

- Captura somente chamadas que chegam ao adapter. Rejeições anteriores dos gates,
  tools não cobertas e indisponibilidade da própria evidência não têm captura garantida.
- Interrupção ou falha de append pode deixar apenas o início; captura vazia/truncada
  nunca é sucesso. Não há garantia transacional entre journal e bundle nem de
  recuperação após falha de energia, escrita indisponível ou término forçado.
- Se fsync final e seu rollback via ftruncate falharem, dois eventos estruturalmente
  válidos podem permanecer com resultado calculado `delivered`, apesar do retorno
  `deny/attempt_evidence_failed`. Sua durabilidade não foi confirmada. Nem
  `complete` nem esse payload comprovam retorno bem-sucedido ou entrega ao harness.
- `run-local-evidence-trial` v1 ingere somente `*.json`; journals `*.jsonl` não alteram
  seus contadores. Esse relatório continua medindo bundles, não término do adapter.
- Novo reason code em falha de journal é mudança de comportamento fail-closed.
  Não há flag de fallback que permita leitura sem o registro inicial/final.
- Sem alteração em PDP/PEP/runtime, efeitos, policy, network, modelo ou licença.

## Validation and rollback

Testes em `hooks/test-local-read-adapter.py`: falha pré-admissão, cleanup, persistência,
interrupção, dupla falha de fsync/rollback, adulteração schema-valid sem rehash,
adulteração mesmo com rehash, duplicação, schema fechado, symlink,
colisão, troca de inode e ausência de conteúdo/inputs crus no journal. Executar o
teste do adapter, os trials, `make quality` e `make eval`; skips explícitos.

Na primeira validação da branch, em 2026-09-26: 16 testes do adapter, 4 testes de trials, `make quality`
(26 self-tests), `make eval`, `make graph-check`, links locais e whitespace passaram.
Evals rodaram com `ADF_EVAL_WRITE=0`. Skips: coverage/ciclos/mutation JS sem
configuração/ferramentas; uma checagem opcional independente de JSON Schema no
teste de eventos. Coverage, mutation e lint Python não foram executados porque
`coverage`, `mutmut` e `ruff` não estão instalados; não se declara score dessas métricas.

Rollback por revert revisado da implementação; manter journals históricos ignorados
pelo Git. Não remover evidência para ajustar métricas. A próxima fatia de métricas
deve distinguir resultado calculado, durabilidade e entrega observada pelo consumidor,
sem reinterpretar bundles v1 ou contar `complete` como confirmação de entrega.
