# ADR 0021: Spans OTel nas bordas locais (emenda ao ADR 0020)

> **English summary.** Local-edge decisions (Claude `Read`, Codex `cat`, MCP stdio) did not appear in the tracing UI; hooks are short-lived processes whose daemon export thread would die, hook stderr can reach the user or the model, and local payloads carry sensitive paths and session IDs. The decision emits one `adf.local_read.request` span at each local edge after the adapter result (not inside `LocalReadAdapter`, so A2A keeps exactly one span), adds only the closed-enum attribute `adf.edge` to the allowlist, forbids `tool_input`, `file_path`, `command`, `session_id`/`run_id` and similar fields, waits in hooks with a capped flush (`ADF_OTEL_FLUSH_MS`, default 300 ms, cap 2000 ms), and keeps hook stderr silent on export failure. Status: Accepted, human merge of PR #77 on 2026-10-19; implemented on 2026-10-20 (WP5). Consequence: with OTel on, a slow collector adds up to the flush cap per read, a hook span can still be lost, and traces remain outside the evidence. The full record below is in Portuguese.

- **Status:** Accepted — merge humano do PR #77 em 2026-10-19; implementado em 2026-10-20 (WP5).
- **Date:** 2026-10-19
- **Amends:** [ADR 0020](0020-control-plane-otel-export.md) (Accepted), que restringe o export à borda A2A
  e registra "`local_read` não instrumentado".
- **Depends on:** ADRs 0009, 0010, 0011, 0020.
- **Scope:** WP5 do [plano de implementação](../../../docs/product/IMPLEMENTATION_PLAN.md): um span por
  decisão das bordas locais (Claude `Read`, Codex `cat`, MCP stdio), só para visualização.
  Não muda AuthN, PDP, PEP, runtime, evidência nem contratos.

## Problema

As decisões da borda A2A aparecem no Jaeger/Langfuse; as das bordas locais, não. Elas são o caso
principal do wedge (coding agent no notebook lendo `.env`). Hoje AppSec precisa abrir bundles ou rodar
`make local-evidence-trial` para ver um deny de Claude ou Codex, enquanto o mesmo deny via A2A aparece
na UI. A tela de "o que o agente fez" (Langfuse) e a de "o que o ADF permitiu" ficam assimétricas.

## Restrições que mudam em relação ao ADR 0020

1. **O A2A também passa pelo `LocalReadAdapter`.** Instrumentar o adapter geraria dois spans por leitura
   A2A e acoplaria o núcleo ao exporter.
2. **Os hooks são processos curtos.** O gate imprime a decisão e sai. O exporter do ADR 0020 envia numa
   thread daemon, que morre com o processo, então o span se perderia quase sempre.
3. **O stderr do hook não é um canal neutro.** Claude Code e Codex podem mostrar o stderr do hook ao
   usuário ou ao modelo. A linha de erro do exporter ("otel export skipped: …") não pode sair dali.
4. **O payload local carrega dados sensíveis:** `tool_input.file_path`, o `command` do Codex (contém o path),
   `session_id`, a raiz do repositório.

## Opções

1. **Span dentro do `LocalReadAdapter.read`.** Um ponto só, cobre as três bordas. Duplica o span do A2A
   (exige um flag para suprimir) e põe o export no núcleo, contra a regra do ADR 0020 de exportar na borda.
2. **Span em cada borda local, depois da decisão final.** É o mesmo desenho do ADR 0020 (`handle` do
   A2A): os gates e o servidor MCP chamam `emit_span` com o resultado do adapter. Nos hooks, um *flush*
   com teto de tempo espera o envio antes de o processo sair.
3. **Não fazer.** A evidência e o agregado de trial já existem; perde-se só a visualização local.

## Decisão proposta

Opção 2.

- **Onde:** `hooks/claude-code-read-gate.py`, `hooks/codex-bash-read-gate.py` e
  `integration/mcp_read_server.py`, depois de `read_adapter(...)` devolver o resultado. O
  `LocalReadAdapter` continua sem export; a borda A2A continua com exatamente um span por request.
- **Span:** `adf.local_read.request`, com atributos tirados só do resultado do adapter:

| Atributo | Origem |
| --- | --- |
| `adf.edge` (**novo**, enum fechado: `claude_read`, `codex_bash`, `mcp_read`) | constante da borda |
| `adf.outcome`, `adf.reason_code` | resultado do adapter |
| `adf.bundle_id` | resultado do adapter (correlação com o bundle e `verify_offline`) |
| `adf.duration_ms` | relógio da borda |

  `adf.edge` entra na allowlist do exporter; nenhum outro atributo novo. `decision_id` fica de fora: o
  adapter não o devolve, e ler o bundle só para isso custaria I/O no caminho da leitura.
- **Proibido, além da lista do ADR 0020:** `tool_input`, `file_path`, `command`, `session_id`/`run_id`,
  raiz do repositório, revisão, conteúdo, policy e pin.
- **Processo curto:** `emit_span` passa a devolver a thread de envio (ou `None`), e a borda faz
  `join(timeout)` com `ADF_OTEL_FLUSH_MS` (padrão 300 ms, teto 2000 ms). Desligado, não há thread nem espera.
  Collector lento custa no máximo o teto por leitura, **só com OTel ligado**. O MCP é um processo longo e
  não espera.
- **Silêncio no hook:** nas bordas de hook, falha de export não escreve no stderr (a falha é descartada).
  A borda A2A mantém a linha de stderr do ADR 0020.
- **Fail open / fail closed:** como no ADR 0020. A decisão do gate é a mesma com export ligado, desligado
  ou com collector fora; um valor com forma de credencial descarta o span inteiro.

## Validação (testes primeiro)

- Desligado por padrão: nenhum socket, nenhuma thread, nenhuma espera (o tempo do gate não muda).
- Cada borda local emite exatamente um span com `adf.edge` correto; uma leitura A2A continua emitindo
  exatamente um span (`adf.a2a.request`).
- Vazamento: com um path sentinela, o `command` do Codex e o `session_id`, nada disso aparece no payload
  OTLP serializado.
- A permissão de cada gate (`allow`/`deny` + `reason_code`) é idêntica com o collector ligado, desligado,
  ou num endpoint que não responde.
- O flush respeita o teto: um endpoint que não responde não segura o hook além de `ADF_OTEL_FLUSH_MS` + margem.
- O stderr do hook fica vazio quando o export falha.
- Gates: `test-otel-export.sh`, `test-local-read-adapter.sh`, `test-a2a-gateway.sh`, `make quality-check`,
  `make eval-required`.

## Consequências

- Positivo: os denies de `.env`/segredos de Claude e Codex aparecem na mesma UI que os do A2A, com
  `bundle_id` para chegar à prova offline. Nenhuma dependência nova.
- Negativo: com OTel ligado, até `ADF_OTEL_FLUSH_MS` de latência extra por leitura quando o collector está
  lento. Um span de hook ainda pode se perder (processo morto, teto estourado). `ponytail:` uma conexão
  por span; um exporter em lote ou um agente local só se a taxa justificar.
- Trace continua não sendo evidência: a fonte de verdade é o Evidence Bundle + `verify_offline`.
- Reversibilidade: barata. Remover a chamada nas três bordas e o valor `adf.edge` da allowlist.

## Contratos

Nenhum. Bundles, journal, `ToolCallIntent` v1 e o payload dos hooks ficam inalterados. A allowlist do
exporter ganha uma chave (`adf.edge`) com valor de enum fechado.

## Perguntas para o revisor (resolvidas com os defaults desta proposta)

1. **`session_id` como atributo?** Ligaria o span do ADF ao trace do agente no Langfuse (a "segunda tela"),
   mas é um identificador estável de sessão do usuário. Esta proposta deixa de fora; a correlação fica por
   `bundle_id`.
2. **Teto do flush:** 300 ms por padrão é aceitável para um `Read` interativo?
3. **Emendar o 0020 na aceitação:** ao aceitar, acrescentar ao 0020 uma linha "Amended by ADR 0021", sem
   reescrever o texto aceito.
