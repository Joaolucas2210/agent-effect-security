# ADR 0005: evolução incremental para Agent Development Harness

> **English summary.** The framework has documentation-only archetype modes but no isolated runtime, versioned run contracts, per-operation authorization or model trials, and it must compare agent configurations without rewriting the project. The decision is to evolve the existing core incrementally through versioned contracts and slices: one main agent by default with modes selecting policies, an Agent Harness separate from an Evaluation Harness, tool authorization before any effect, human gates for sensitive operations, and suggest-only learning. Status: Accepted on 2026-09-17 (Proposed to Accepted by explicit human approval), authorizing only H1-01 as the first Implementation PR. The main costs and risks are keeping legacy and new formats side by side and reducing review without a reliable classifier; any reviewer-policy change is deferred to an approved H6 and no reviewer is removed. The full record below is in Portuguese.

- **Status:** Accepted
- **Date:** 2026-09-17
- **Deciders:** João Lucas
- **Aprovado por:** João Lucas
- **Data da decisão:** 2026-09-17
- **Revisão aprovada:** `bd9fb74ffc93160a708722fe6fe72ce016e30cd6`
- **Escopo inicial autorizado:** H1-01
- **Spec:** [arquitetura, gaps e plano H0–H7](../../../docs/specs/agent-development-harness.md).
- **Baseline:** `f13e147` (`feat/evaluation-driven-development`).

## Registro de aprovação

A arquitetura foi revisada e aceita por João Lucas em 2026-09-17, tendo como referência a revisão `bd9fb74ffc93160a708722fe6fe72ce016e30cd6`.

A aprovação autoriza a evolução incremental descrita nesta decisão. A primeira Implementation PR autorizada é a H1-01. Operações sensíveis, fases posteriores e efeitos protegidos continuam submetidos aos human gates definidos na Spec.

Histórico de status: Proposed → Accepted em 2026-09-17, conforme aprovação humana expressa de João Lucas. O conteúdo original abaixo foi preservado como registro da proposta e de suas condições de aprovação à época.

## Context

`ai-development-framework/` já é core compartilhado: `setup-adf.sh` instala links para Claude,
Codex e Cursor; Makefile e hooks executam gates, fixtures, observabilidade e learning. Os cinco
archetypes já são modos documentais. Não existem runtime isolado, contratos versionados de runs,
autorização geral por operação nem trials de modelos. Os CSVs atuais medem reexecuções dos testes
de duas soluções, não comparação de agentes. As evidências e limitações estão na Spec, §§2–4.

O pedido exige comparar configurações sem reescrever o projeto, preservar adapters e separar
execução de avaliação. Também propõe substituir o painel amplo de reviewers por seleção por
risco; isso conflita com `commands/review.md`, `skills/pr-review` e a Definition of Done atual.
Essa mudança requer revisão explícita, não edição silenciosa de instruções.

## Options considered

1. **Manter somente instruções e scripts atuais.** Menor custo imediato; não resolve enforcement,
   correlação entre runs nem comparação experimental. Manter como modo legado durante migração.
2. **Evoluir o core existente, com contratos e slices.** Reutiliza hooks e wiring, acrescentando
   políticas executáveis e providers quando houver callers/testes. Custo: compatibilidade de
   formatos e coexistência temporária de dois caminhos de observabilidade.
3. **Reorganizar toda a árvore ou adotar framework agentic.** Aumenta migração e dependências sem
   evidência de ganho. Rejeitado para este plano.

## Proposed decision

Adotar a opção 2, condicionada à aprovação humana:

- Um agente principal por padrão; modos selecionam políticas, não agentes. Delegação/review
  independente apenas com motivo por paralelismo, especialidade, risco, contexto ou eval.
- Agent Harness executa uma task/run. Evaluation Harness controla dataset/configurações/trials,
  aplica graders protegidos e compara evidências. O regression runner existente é preservado.
- Contratos de dados versionados; eventos por run, estado explícito e métricas ausentes null.
  JSONL/CSV atuais e interfaces dos hooks permanecem compatíveis.
- Tools passam por autorização antes do efeito. Human gates protegem produção, destruição,
  segredos, migração irreversível, contrato público, arquitetura de alto impacto, risco de
  segurança aceito e escrita externa sensível. Um adapter não declara enforcement inexistente.
- Runtime local/worktree para código confiável; Docker como segundo provider com limites
  testados. Worktree não é fronteira de segurança. Core não depende de provider/infraestrutura.
- Verificação determinística antecede LLM review e aceite; gate obrigatório skipped bloqueia.
  A migração de política de reviewers ocorre somente em H6 aprovada, preservando regras até lá.
- Learning continua suggest-only, com evidências identificáveis e alteração estrutural por PR
  humana; nunca escreve automaticamente AGENTS, skills, policies, gates ou permissões.
- Sem mudança em massa de diretórios. Novos módulos ficam sob ADF, próximos do core distribuível;
  root Makefile, loops, links e template CI canônico permanecem pontos de integração.

Primeira implementação proposta: instrumentar opt-in um gate real do runner atual com RunEvent
e GateResult, provar pass/fail/skip/erro de trace e compatibilidade legada. Os demais contratos
vêm na PR seguinte; runtimes, providers e benchmarks não pertencem ao primeiro slice.

## Consequences

- Positiva: transição revisável, nenhuma dependência de serviço/provider no primeiro slice;
  comparação futura baseada em trials identificados, não em rótulos de modelos em Markdown.
- Custo: manter projeção legada e formato novo até migração deliberada dos consumidores.
- Limite: neutralidade de instruções já existe; neutralidade de enforcement exige capability
  probes e testes de conformidade. Não há evidência atual para escolher modelo vencedor.
- Risco: diminuir review sem classificador/gates confiáveis. A mudança fica dependente de H6
  e de aprovação própria; nenhum reviewer é removido nesta entrega.
- Reversibilidade: desabilitar caminho novo, preservar artifacts/histórico e retornar ao legado
  apenas em escopos permitidos. Nunca contornar uma negação de política como rollback.

## Metrics impact

H1 mede integridade/completude de eventos e preservação dos resultados legados; não promete
economia de tokens. H4 mede sucesso/first-pass, review humano, retrabalho, chamadas, tokens,
tempo, custo estimado, gates e defeitos pós-aceite. H5 compara providers de contexto; H6 mede
custo e defeitos da revisão. Ganho exige baseline pareada e incerteza reportada; código escrito
ou apagado não é métrica de produtividade.

## Approval and follow-up

A aprovação humana deve apontar para a revisão desta Spec/ADR. Registros complementares de
contratos, runtime/políticas, protocolo experimental e review são aprovados antes da ativação
das respectivas fases. Este ADR não modifica automaticamente ADRs 0001–0004 e não autoriza
deploy, segredo, operação destrutiva ou implementação de todas as fases.
