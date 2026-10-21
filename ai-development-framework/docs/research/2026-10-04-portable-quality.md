# Gates portáteis: core obrigatório e deployment separado

> **English summary.** This record (2026-10-04) fixes the portable quality gate that failed in the previous `project-b` validation, where core self-tests mixed package integrity with host configuration. Core self-tests now run in their own fixture, and a separate `check-host-deployment.py` returns 0 when its three checks pass, 77 when only optional deployments are missing in a portable install, and 1 for invalid configuration, drift, a missing template or a missing deployment in the source clone; code 77 is accepted only from that check and no skip counts as a green gate. After the update, `make quality` passed in the ADF clone with 29 self-tests and four gates, and `make -f Makefile.adf quality` passed in `project-b` with the 71 PostgreSQL application tests, 29 self-tests and three gates, with the listed skips. It does not complete real-client capture or external P0-D task evaluation, and an older install must receive the checker, tests, `Makefile.adf` and packaged specs together. The full record below is in Portuguese.

Data: **2026-10-04**. Base ADF: `1a2d7ce`, com mudanças locais anteriores.
Destino: `project-b`, revisão `ca5239c`. Modo: **Maintainer → Builder**.
Esta entrega resolve o gate portátil que falhou na revisão anterior; não
conclui a captura em cliente real ou a avaliação externa de tarefas P0-D.

## Problema e implementação

Os self-tests confundiam integridade do pacote com configuração do host:
exigiam `.codex/hooks.json`, workflows ativos do clone, specs fora do core,
targets no Makefile da aplicação e a licença da aplicação como licença ADF.
Os testes de regressão reproduziram essas dependências antes da correção.

Os testes do core agora executam o wrapper em fixture própria e verificam os
templates canônicos empacotados. Quando o hook está configurado, seu comando
também é exercitado e precisa persistir evidência; devolver JSON vazio não
é suficiente para passar. As duas specs acompanham a instalação em
`ai-development-framework/docs/specs/`, preservando os oráculos normativos.
Os testes escolhem `Makefile.adf` no destino e mantêm separadas as licenças
do ADF e da aplicação. Nenhum schema ou hash v1 foi alterado nesta fatia.

`check-host-deployment.py` verifica a configuração Codex e a identidade dos
workflows ativos com os templates. Retorna 0 quando os três checks passam,
77 quando somente deployments opcionais estão ausentes numa instalação
portátil, e 1 para configuração inválida, drift, template ausente ou deployment
ausente no clone de origem. Um `Makefile.adf` regular identifica o contexto
portátil; essa classificação serve aos checks de instalação e não participa
de PDP/PEP, autorização ou policy do runtime.

`make quality` e `make test-all` executam a checagem separadamente. O código
77 só é aceito dessa checagem de deployment; uma falha de self-test do core
continua bloqueando. Nenhum skip entra na contagem de gates verdes. Os cinco
testes novos cobrem ausência em clone/instalação portátil, configuração
inválida, drift e template ausente. O teste de CI confirma que falha no core
não pode ser convertida em skip. A regressão de instalação executa testes
de contrato, wrapper, templates e eventos em um destino sem hooks.

## Atualização e validação

O core do `project-b` foi atualizado seletivamente com backup. Os arquivos
existentes foram comparados ao baseline conhecido antes de sobrescrever;
as 27 evidências e registros preexistentes foram preservados por hashes.
A licença, Makefile e configurações da aplicação não foram substituídos.

- Clone ADF: `make quality` passou com 29 self-tests e quatro gates; a
  configuração de deployment do clone passou. `make eval` e `eval-required`
  passaram, cobrindo os hooks novos e alterados. `make graph-check` e diff
  check passaram; o graph-check compara com `HEAD`, sem claim de reindexação
  dos arquivos novos.
- `project-b`: `make -f Makefile.adf quality` passou com os 71 testes
  PostgreSQL da aplicação, 29 self-tests e três gates. `make -f Makefile.adf
  eval` passou. O teste portátil de licença expôs uma comparação indevida
  com a licença do host; ela foi corrigida antes da execução final.
- A primeira execução no destino não acessou PostgreSQL pelo sandbox;
  a repetição autorizada fora dele executou todos os testes de banco. Evals
  usaram `ADF_EVAL_WRITE=0`, sem reescrever o histórico.
- Ruff passou nos dois arquivos Python novos. As limitações de lint
  preexistentes dos arquivos ADF anteriores permanecem; nenhum claim de
  lint integral, cobertura ou mutação Python do ADF é feito.
- **Skipped no destino:** três deployments não instalados (hook Codex e
  dois workflows), cobertura Python por ausência de pytest-cov, complexidade
  Python por ausência de Lizard e mutação por ausência de mutmut. Uma
  validação independente opcional de JSON Schema foi pulada nos self-tests.
- **Skipped no clone:** cobertura JS, ciclos Madge, mutação Stryker e uma
  validação independente opcional de JSON Schema. Captura e timings reais
  do cliente, MCP em produto e resultado de tarefa seguem pendentes.

## Risco e continuidade

Uma instalação antiga precisa receber o checker, testes, Makefile ADF e
specs empacotadas juntos; atualizar apenas o gate não basta. Os scripts não
instalam hooks nem workflows, não aceitam ADRs e não alteram a autorização.
O próximo passo é conferir a configuração do cliente real usado pelo
mantenedor e coletar uma tarefa com versão, SHA e critério de aceite fixados.

Referências: [validação anterior](2026-10-04-external-validation.md),
[guia portátil](../trials.md#validar-a-instalação-portátil),
[spec P0-D](../../../docs/specs/p0d-trial-sessions.md).
