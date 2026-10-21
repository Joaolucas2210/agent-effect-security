# Instalar em outros repositórios e coletar trials

[English](trials.md) · **Português (Brasil)**

Este guia separa três fontes: o teste de instalação (`fixed_suite`), os bundles de uma
sessão real (`persisted_evidence`) e os eventos de trabalho (`make metrics`). São sinais
diferentes. Nenhum deles, sozinho, mede produtividade, economia de tokens ou segurança do host.

![Fluxo de coleta: instalar, fixar revisão, capturar, agregar e comparar](images/trial-lifecycle.svg)

## 1. Instalar a ferramenta no repositório de destino

No clone do ADF:

```bash
make install-metrics DEST=/caminho/absoluto/outro-repositorio
```

O comando copia `ai-development-framework/` e cria `Makefile.adf`. Preserva `Makefile`,
`AGENTS.md`, `.gitignore`, `VERSION`, `LICENSE`, ambientes Python e configurações de agentes
do destino. Não instala dependências, não ativa hooks, não faz commits e não acessa a rede.
Eventos, bundles, trials, caches, arquivos `.env*`, propostas antigas e linhas históricas
dos CSVs não são levados para o novo projeto. A licença MIT do ADF fica dentro do core;
a licença do projeto de destino permanece a mesma.

O destino precisa existir e ficar fora do clone ADF. Uma instalação existente ou symlink
em `ai-development-framework` ou `Makefile.adf` causa erro antes da cópia. Atualizações
devem ser revisadas como diff; o comando não sobrescreve uma instalação anterior.
`install-into` continua sendo a instalação completa do harness, mas agora recusa conflitos
com arquivos do projeto. Para coletar métricas em um repo existente, use `install-metrics`.

No destino, prepare um ambiente separado do ambiente da aplicação:

```bash
cd /caminho/absoluto/outro-repositorio
python3 -m venv .venv-adf
export ADF_CONTRACTS_PYTHON="$PWD/.venv-adf/bin/python3"
make -f Makefile.adf install-dev
"$ADF_CONTRACTS_PYTHON" -c 'import tools, runtime, integration; print("ok")'
```

Alternativa com uv: `uv venv --python python3 .venv-adf`, seguida de
`uv pip install --python .venv-adf/bin/python3 -e ./ai-development-framework -r ai-development-framework/requirements-test.txt`.
Exporte `ADF_CONTRACTS_PYTHON` como acima para os comandos seguintes.
Python 3.10+, Git e Make são necessários; os pins exatos de dependência ficam em `ai-development-framework/requirements-test.txt`.
Bash 4+ é necessário para os gates completos, não para o runner Python de trial.

### Validar a instalação portátil

No destino, execute `make -f Makefile.adf quality` e `make -f Makefile.adf eval`
com `ADF_CONTRACTS_PYTHON` apontando para `.venv-adf/bin/python3`. Para os gates
da aplicação, mantenha o ambiente dela no `PATH` e configure suas dependências
de teste, incluindo um banco isolado quando necessário. Use Bash 4+ no `PATH`.
`ADF_EVAL_WRITE=0` preserva os resultados históricos enquanto executa os checks.

Os self-tests do core sempre executam e qualquer falha bloqueia o gate. Specs
necessárias aos oráculos acompanham a cópia em `ai-development-framework/docs/specs/`.
Testes usam `Makefile.adf` para evitar depender dos targets do Makefile da aplicação;
a licença ADF é verificada separadamente da licença do destino.

A presença de um `Makefile.adf` regular identifica a instalação portátil para
a checagem de deployment. Hooks Codex e workflows ADF não instalados ficam
explicitamente `skipped`, sem contar como checks verdes. Arquivos presentes
inválidos, workflows divergentes do template e templates ausentes no pacote
continuam falhando. No clone de origem, sem `Makefile.adf`, a ausência da
configuração de deployment continua sendo falha. `make test-all` (ou
`make -f Makefile.adf test-all`) também executa essa checagem separada.
Nenhum desses comandos instala hooks ou workflows automaticamente, nem prova
captura dentro de um cliente real.

Instalações anteriores precisam receber os arquivos revisados e as duas specs
empacotadas antes de rodar esses gates. Preserve as evidências e configurações
locais ao atualizar; `install-metrics` continua recusando sobrescrita.

Se for versionar a instalação, inclua somente os arquivos revisados. Acrescente
`.venv-adf/` à política de ignore do destino antes de preparar qualquer commit.
O `.gitignore` dentro do core já exclui bundles, eventos, trajectories e trials.

## 2. Confirmar a instalação com a suite fixa

O destino deve ser um repositório Git com pelo menos um commit e `README.md` rastreado
na revisão `HEAD`. O runner prepara snapshots dessa revisão; arquivos não commitados
não entram na leitura controlada. Se seu README tem outro nome, rode o teste no clone
ADF e use a captura real no destino, sem interpretar essa diferença como falha do gate.

```bash
make -f Makefile.adf local-evidence-trial \
  TRIAL_ID="smoke-$(date -u +%Y%m%dT%H%M%SZ)"
```

Resultado esperado na suite 1.0:

| Caso | Resultado |
| --- | --- |
| Leitura de README | `delivered/read_delivered` |
| Caminho sensível | `deny/sensitive_path_denied` |
| Traversal | `deny/invalid_referenced_contract` |
| Binding diferente no PDP | `deny/run_binding_mismatch` |
| Binding diferente no PEP | `deny/task_ref_mismatch` |

São **5 tentativas, 4 bundles, 3 bundles válidos e 1 inválido**. O bundle inválido do
caso PDP é esperado: a negação ocorre antes de haver `effective_scope`. O traversal
não produz bundle. Portanto, `decisions_total=3`, `admit_read_total=3` e `deny_total=0`
não significam que as quatro negações deixaram de ocorrer. Leia também `reason_codes`.
Os casos de binding mismatch são injetados pelo teste; não são incidentes de produção.

A suite usa um diretório de evidências próprio do runner. Não agregue esse diretório
como se fosse uma sessão de usuário. Uma falha de expectativa retorna erro; preserve
o relatório para diagnóstico. IDs repetidos não sobrescrevem relatórios.

## 3. Preparar uma captura real

Use uma tarefa identificada por código, sem nomes de pessoas, clientes ou prompts.
Para cada sessão, execute no destino, no mesmo terminal que iniciará o agente:

```bash
export ADF_CONTRACTS_PYTHON="$PWD/.venv-adf/bin/python3"
export ADF_TRUSTED_REPOSITORY="$(pwd -P)"
export ADF_TRUSTED_REVISION="$(git rev-parse HEAD)"
export ADF_MAX_OUTPUT_BYTES=1048576
export TRIAL_ID="session-$(date -u +%Y%m%dT%H%M%SZ)-01"
export ADF_EVIDENCE_DIR="$ADF_TRUSTED_REPOSITORY/ai-development-framework/docs/observability/evidence/$TRIAL_ID"
umask 077
mkdir -p "$(dirname "$ADF_EVIDENCE_DIR")"
mkdir "$ADF_EVIDENCE_DIR"
```

O último `mkdir` deve ter sucesso: se o diretório já existe, escolha outro ID antes
de iniciar. Não use `mkdir -p` para reaproveitar a pasta da sessão. Fixar o SHA evita
que o significado de `HEAD` mude durante a coleta. O gate controla uma leitura do
snapshot fixado; a leitura nativa seguinte do agente pode observar o working tree.
Mantenha a revisão e o arquivo de teste estáveis durante a verificação inicial.

Registre junto aos resultados o SHA da revisão alvo, SHA/versão do ADF usado, versão
do agente, modelo, configuração, código da tarefa, horário e critérios de sucesso.
O relatório agregado **não inclui todos esses metadados**. Guarde esse registro à
parte, localmente, sem paths físicos, conteúdo de arquivos, prompts ou credenciais.
Em comparações, mantenha tarefa e snapshot iguais e registre qualquer mudança.

## 4. Habilitar o hook de leitura

`install-metrics` não altera configurações do agente. Mescle um dos blocos abaixo
na configuração existente; preserve os outros hooks. Troque `ABS_DEST` pelo caminho
absoluto do destino. Caminhos com espaços devem permanecer entre aspas no comando.
Reinicie o agente a partir do terminal que contém os exports da etapa anterior.

### Claude Code

Em `.claude/settings.local.json`, use o matcher `Read`:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Read",
      "hooks": [{
        "type": "command",
        "command": "\"ABS_DEST/.venv-adf/bin/python3\" \"ABS_DEST/ai-development-framework/hooks/claude-code-read-gate.py\""
      }]
    }]
  }
}
```

### Codex

Em `.codex/hooks.json`, use o contrato de hook P4 testado neste projeto:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "^Bash$",
      "hooks": [{
        "type": "command",
        "command": "\"ABS_DEST/.venv-adf/bin/python3\" \"ABS_DEST/ai-development-framework/hooks/codex-bash-read-gate.py\"",
        "timeout": 30,
        "statusMessage": "Checking ADF read policy"
      }]
    }]
  }
}
```

Revise/confie no hook em `/hooks` antes de coletar. Usamos o Python diretamente porque
o wrapper do clone espera `.venv`, enquanto este guia usa `.venv-adf`.
O suporte depende da versão do agente; os limites P4 estão em
[CONTROL_PLANE](CONTROL_PLANE.pt-BR.md#codex-bash-read-equivalent-p4).
**Só um `cat arquivo` allowlisted é medido no Codex.** `rg`, Python, comandos compostos
e outras tools não têm essa cobertura. Cursor recebe o harness, mas não tem adapter
de evidência implementado aqui.

### Vários projetos com um hook só (REQ-MP-01)

Para usar o gate em outros repositórios sem instalar o ADF em cada um (e sem instalar na pasta pai:
o Claude Code não herda `.claude/` de pastas pai e `install-metrics` recusa um destino que contém
o clone), registre **uma vez** o wrapper no settings global e ative projetos numa lista do host:

```jsonc
// ~/.claude/settings.json — acrescente ao array hooks.PreToolUse; os outros hooks continuam (eles somam)
{ "matcher": "Read", "hooks": [{ "type": "command", "timeout": 30,
  "command": "H=/abs/agent-effect-security/ai-development-framework/hooks/adf-read-hook.py; P=/abs/agent-effect-security/.venv/bin/python3; [ -f \"$H\" ] && [ -x \"$P\" ] || exit 0; exec \"$P\" \"$H\"" }] }
```

Mais simples: `adf hook-snippet claude` (ou `codex`) imprime esse bloco já com os caminhos deste clone e o
fail-safe, nos matchers `Read` e `Bash` ([ADR 0025](architecture-decision-records/0025-adf-operator-cli.md)).

O teste `[ -f … ] || exit 0` é obrigatório: se o clone mudar para uma branch sem o wrapper, o Python sai com
código 2, e no `PreToolUse` código 2 **bloqueia** a tool, ou seja, todo `Read` em todos os projetos.

O mesmo wrapper atende o Codex: registre-o no arquivo de hooks global do Codex (`~/.codex/hooks.json` na
0.157.0; confirme o caminho na versão instalada, `na` nos trials) com `matcher: "^Bash$"` e a mesma linha de
comando com fail-safe. O hook identifica o projeto pelo `cwd` que o Codex envia no payload (Claude exporta
`CLAUDE_PROJECT_DIR`) e aplica o gate P4: só `cat PATH` allowlisted decide (`{}` = entregue, deny com
`reason_code`); qualquer outro comando devolve `{}` e segue a política do Codex. Mesma lista, mesma raiz
git, mesma pasta de evidência que o Claude. Codex não é cobertura de todo acesso a arquivo: `head`, `sed`,
`rg`, pipes e redirecionamentos ficam fora, como no P4.

```bash
make project-enable PROJECT=/home/voce/dev/MEU_PROJETO   # caminho absoluto canônico; raiz git recomendada
make projects                                             # lista cada entrada e como o hook vai tratá-la
make project-disable PROJECT=/home/voce/dev/MEU_PROJETO
make project-reasons                                      # por projeto: bundles, tentativas do journal (inclui denies de contrato sem bundle) e, por principal, attempts/delivered/denied/paths_read
make project-reasons POLICY=/abs/host-policy.json         # acrescenta granted/unused por principal a partir da policy pinada (ADR 0024)
```

Os targets chamam `hooks/adf-projects.py`, que aplica as mesmas regras do hook: path relativo, com `..`,
`//`, `/` no fim ou que não é diretório é recusado (exit 1) e a lista não muda; symlink é gravado pelo
path real; projeto fora de git é aceito com aviso, porque o gate vai negar lá (`project_not_git`). Linhas
escritas à mão que não são canônicas ficam no arquivo e aparecem como `ignored`. Editar o arquivo
diretamente continua válido (uma linha por path absoluto).

| Situação | Comportamento |
| --- | --- |
| Projeto fora da lista, lista ausente ou ilegível, sem `CLAUDE_PROJECT_DIR` nem `cwd` no payload | Nenhuma decisão: o agente segue as permissões normais |
| Linha relativa, com `..`, `//` ou `/` no fim | Ignorada (não ativa nada) |
| Projeto listado e repositório git (inclusive aberto numa subpasta) | Gate do clone, com raiz = topo git do projeto; um `ADF_TRUSTED_REPOSITORY` exportado para outro repo é sobrescrito |
| Projeto listado sem git | `deny project_not_git` (o gate só lê snapshot git) |
| Projeto listado e falha interna, payload malformado ou tool fora de `Read`/`Bash` | `deny adapter_failed` / `unsupported_tool` (fail closed) |

A evidência vai para `~/.adf/evidence/<projeto>-<hash>/<AAAA-MM-DD>/<session_id>/`, fora do repo
do cliente. Revisão, budget, policy pinada (`ADF_READ_POLICY_*`) e OTel (`ADF_OTEL_*`) vêm do ambiente
de onde o Claude foi aberto, se exportados; senão `HEAD`, 1 MiB, modo demo e OTel desligado. O hook só vale
para sessões abertas depois do registro. Cada leitura registra e remove um worktree temporário em
`.git/worktrees/` do cliente; nenhum arquivo do working tree é tocado.

Residuais: o agente pode editar `~/.adf/enabled-projects` via `Bash` ou rodar `make project-enable` (a lista só
tira o interruptor do workspace; não é protegida); num projeto ativado valem os limites do gate (arquivo não
commitado, binário ou acima do budget é negado; no Claude `Bash`/`Grep`/`Glob` ficam fora; no Codex só `cat PATH`
é decidido).

### Quem leu: subagentes na evidência (ADR 0023)

Dentro de um subagente do Claude Code o hook recebe `agent_type`; o gate deriva daí um principal local
(`claude:security-reviewer`, ou `claude:main` na thread principal; `codex:…` no Codex) que vai ao PDP e ao
PEP, ao journal `_attempts` (`principal_sub`) e ao span (`adf.agent_type`). O bundle não muda. `agent_type`
malformado é `deny invalid_principal`. Sozinho é rótulo; a policy por principal é a próxima fatia.

### Token no processo do host, nunca no prompt (cliente A2A)

Para um agente que precisa ler pela borda A2A, não cole o bearer no prompt nem o exporte onde o agente rode
`echo`. Registre o cliente MCP `integration/mcp_a2a_client.py` como servidor stdio do agente: ele guarda o token e
expõe uma única tool, `read_via_adf(path)`. O modelo vê só o path e o resultado; AuthN, AuthZ, PDP, PEP e evidência
continuam no gateway.

```jsonc
// servidor MCP no Claude/Codex; o ambiente é do host, o agente não o vê
{ "command": "/abs/agent-effect-security/.venv/bin/mcp", "args": ["run", "/abs/agent-effect-security/ai-development-framework/integration/mcp_a2a_client.py:mcp", "--transport", "stdio"],
  "env": { "ADF_A2A_URL": "http://127.0.0.1:8765/", "ADF_A2A_TOKEN_FILE": "/home/USER/.adf/pilot/token-agent.txt" } }
```

Regras do cliente: `ADF_A2A_TOKEN_FILE` absoluto, arquivo regular, modo `0600` (grupo/outros legíveis ou symlink →
`host_configuration_invalid`); `ADF_A2A_URL` só em `127.0.0.1` (TLS é por proxy do host, A2A-8a). Entregue devolve
o texto; deny devolve `ToolError(reason_code)`; pausa devolve `input_required task=<id> effect_binding=<digest>` e
**não existe tool de confirmação**: o humano confirma com um token `human:confirm` que esse processo nunca tem.
Residual: um agente a quem alguém der um token ainda pode usar `curl` por `Bash`; o cliente tira a necessidade do
anti-padrão, não a possibilidade. Teste: `bash ai-development-framework/hooks/test-mcp-a2a-client.sh`.

## 5. Verificar a captura e executar a tarefa

Faça uma leitura de um arquivo público, rastreado e estável: `Read` no Claude ou
`cat README.md` no Codex. Deve aparecer um JSON de bundle sob `ADF_EVIDENCE_DIR`.
Uma permissão concedida pelo agente sem bundle não comprova instrumentação.
Não teste com segredos reais. Faça a verificação inicial em uma sessão separada e
abra um novo diretório/ID para a tarefa medida, para não contaminar suas contagens.

Durante a tarefa, registre os hand-offs do trabalho separadamente:

```bash
make -f Makefile.adf observability-record \
  TASK="$TRIAL_ID" ARCHETYPE=Builder PHASE=build \
  TOKENS_IN=na TOKENS_OUT=na BUDGET_REMAINING=na DURATION_SECONDS=na

# Execute a tarefa no agente e os testes relevantes do projeto.
# Ao terminar, use o resultado observado: success, failure ou skipped.
make -f Makefile.adf observability-complete \
  TASK="$TRIAL_ID" ARCHETYPE=Builder PHASE=review OUTCOME=success \
  TOKENS_IN=na TOKENS_OUT=na BUDGET_REMAINING=na DURATION_SECONDS=na
make -f Makefile.adf metrics
```

Troque `na` por números somente quando houver contagem do runtime. Conte cada intervalo
uma vez; não repita o total acumulado em todos os hand-offs. Duração e custo são valores
fornecidos pelo coletor, não medidos automaticamente por esses comandos. `make metrics`
resume todo o histórico local, enquanto o relatório de trial agrega só a pasta escolhida.
RTK pode fornecer seu relatório separado via `rtk gain`, mas o histórico global da
ferramenta não deve ser atribuído automaticamente a esta tarefa.

## 6. Agregar exclusivamente a sessão encerrada

Encerre a sessão do agente antes de agregar; evite novos bundles durante a leitura
do diretório. No mesmo terminal, confirme que a pasta contém JSONs:

```bash
"$ADF_CONTRACTS_PYTHON" -c 'import os; from pathlib import Path; count = len(list(Path(os.environ["ADF_EVIDENCE_DIR"]).rglob("*.json"))); print("bundles:", count); assert count > 0, "captura vazia"'
make -f Makefile.adf local-evidence-trial \
  EVIDENCE_DIR="$ADF_EVIDENCE_DIR" TRIAL_ID="$TRIAL_ID"
```

O relatório fica em `ai-development-framework/docs/observability/trials/$TRIAL_ID.json`.
Essa fonte deve ter `source.kind=persisted_evidence` e `source.latency_recorded=false`.
A saída CLI é um resumo; o JSON guarda o agregado verificado e seu `report_sha256`.
Uma captura vazia pode produzir um agregado válido; o `assert` acima impede interpretá-la
como trial executado. O agregado não reconstrói tentativas que falharam antes de persistir
um bundle; mantenha também um registro local da contagem de falhas de instrumentação.

### Compartilhar somente o agregado em outra branch

No repositório em que o trial foi executado, depois de encerrar a sessão e
gerar o relatório acima, revise o JSON localmente. Use um `TRIAL_ID` sem nomes
de pessoas, clientes ou outras informações privadas. Os relatórios gerados em
`docs/observability/trials/` são ignorados pelo Git; copie **apenas o agregado**
para uma pasta rastreável e publique uma branch própria:

```bash
git status --short
git switch -c "trial/$TRIAL_ID"
mkdir -p docs/trial-results
cp "ai-development-framework/docs/observability/trials/$TRIAL_ID.json" "docs/trial-results/$TRIAL_ID.json"
git add "docs/trial-results/$TRIAL_ID.json"
git diff --cached --check
git commit -m "data(trial): add aggregate $TRIAL_ID"
git push -u origin "trial/$TRIAL_ID"
```

Se a instalação está em outro repositório, a branch acima pertence **àquele**
repositório. Para compartilhar no repositório do ADF, copie o JSON agregado
para um clone do ADF e crie a branch nele. Revise os metadados e o diff antes
do push; não versione `evidence/`, `_attempts/`, logs, prompts, `.env` ou
conteúdo lido. O relatório v1 de `persisted_evidence` contém zeros de
preenchimento em `metrics.decision_latency_ms`; `source.latency_recorded=false`
significa que essas latências **não foram medidas**. O contrato P0-D
[aprovado](../../docs/specs/p0d-trial-sessions.md) corrige isso sem alterar
os arquivos v1.

### Relatório de sessão P0-D (v2)

Com a versão P0-D instalada, informe o `session_id` do agente (o mesmo
`run_id` nos journals P0-A; ele pode diferir de `TRIAL_ID`) e um código de
tarefa sem PII. A sessão deve estar encerrada:

```bash
make -f Makefile.adf local-session-trial EVIDENCE_DIR="$ADF_EVIDENCE_DIR" \
  TRIAL_ID="$TRIAL_ID" TASK_ID="task-01" SESSION_ID="$SESSION_ID"
```

No clone ADF, use `make local-session-trial` com os mesmos parâmetros. O
relatório agregado fica em
`ai-development-framework/docs/observability/trials/$TRIAL_ID-$SESSION_ID.v2.json`.
Para publicá-lo, copie **esse arquivo** em vez do `.json` v1 nos comandos acima.
O v2 distingue tentativas, bundles e sessão; durações de evidência histórica
permanecem `null`, e `task_outcome` permanece
`null` até avaliação externa. `coverage=unknown` significa que nenhum início
verificável foi observado, não que ocorreram zero tentativas.

O diretório `_attempts` é compartilhado entre sessões. No v2 atual,
`journal_other_session_total` conta journals íntegros de outras sessões;
`journal_duplicates_total` e `bundle_duplicates_total` contam cópias verificadas
sem aumentar tentativas ou decisões. Bindings inválidos continuam inválidos.
Journals conflitantes para a mesma tentativa tornam sua captura `invalid`,
independentemente da ordem dos arquivos. `journal_files_total` inclui os arquivos
inspecionados de todas as sessões, por isso não é o denominador de tentativas.
`decisions.total` conta bundles distintos verificados, inclusive órfãos;
`decisions.runtime_delivered`/`runtime_denied` descrevem receipts, sem provar
retorno após cleanup ou sucesso da tarefa. Os novos campos são opcionais para
preservar leitura de v2 anteriores; ausência de `decisions` significa desconhecido.
Para obter essas classificações em capturas antigas, gere outro relatório com
um `TRIAL_ID` novo; o coletor nunca sobrescreve relatórios existentes.

### Registrar proveniência do trial

Para novos trials, forneça os quatro campos de proveniência juntos:

```bash
make -f Makefile.adf local-session-trial EVIDENCE_DIR="$ADF_EVIDENCE_DIR" \
  TRIAL_ID="$TRIAL_ID" TASK_ID="task-01" SESSION_ID="$SESSION_ID" \
  AGENT_NAME="codex" AGENT_VERSION="$AGENT_VERSION" \
  REVISION_SHA="$ADF_WORKSPACE_REVISION" ACCEPTANCE_SHA256="$ACCEPTANCE_SHA256"
```

`AGENT_NAME` aceita `claude`, `codex`, `cursor` ou `other`; a versão deve ser
um identificador sem espaços ou paths, com até 128 caracteres. Use a versão
real do cliente, não a do modelo. `REVISION_SHA` é o SHA Git completo de 40
caracteres minúsculos usado pelo host na captura, não `HEAD` ou nome de branch.
`ACCEPTANCE_SHA256` é o SHA-256 dos bytes do documento de aceite ou teste
reproduzível, definido antes da tarefa e mantido separadamente pelo avaliador.
No macOS, `shasum -a 256 arquivo-de-aceite` calcula esse hash; só o hash entra
no relatório. Não informe prompts, paths ou texto do critério nesses campos.

O CLI também aceita `--agent-name`, `--agent-version`, `--revision-sha` e
`--acceptance-sha256`. Se algum campo for informado, todos são obrigatórios;
valores inválidos falham antes de persistir o relatório. Sem os quatro, o campo
`provenance` fica ausente para preservar a ingestão de capturas antigas.
O hash do relatório cobre os metadados. São declarações do host, sem atestação
da versão, revisão ou execução do teste; não autorizam leituras nem demonstram
sucesso. `task_outcome` continua `null`: o coletor não executa a avaliação
externa. Revise os identificadores antes de compartilhar o agregado.

### Capturar tempos dos seis estágios

Na versão P0-D com instrumentação, o host pode ativar a captura antes de
iniciar o agente ou o servidor MCP:

```bash
export ADF_CAPTURE_TIMINGS=1
```

Claude `Read`, Codex `Bash` coberto pelo gate e MCP `read_snapshot` passam
pela mesma observação. A opção não vem do payload do agente. A captura grava
`_timings/<attempt_id>.json` separadamente, depois do retorno/raise do adapter;
journals e bundles v1 permanecem intactos. Desative a variável para voltar ao
comportamento anterior. O comando `local-session-trial` coleta os novos arquivos
sem argumentos adicionais, sempre com a sessão encerrada.

Na ingestão v1 (`local-evidence-trial EVIDENCE_DIR=...`), diretórios reservados
`_timings` são excluídos da seleção de bundles, inclusive em pastas de sessões
aninhadas. Seus JSONs são observações separadas P0-D, não bundles inválidos.
Arquivos inválidos fora desses diretórios continuam sendo contados. Relatórios
anteriores não são reescritos; regenere com outro trial ID se misturaram timings
e bundles. A ingestão v1 continua sem medições de latência, mesmo quando há
timings ao lado dos bundles; use v2 para essas medições.

Consulte `observations[].timing.durations_ms` e `timings.stages` no relatório.
Cada estágio tem contagem, soma, mínimo e máximo dos samples correlacionados;
`null` indica ausência e `0` medição abaixo de 1 ms. `timings.coverage=observed`
indica que há samples, sem garantir cobertura completa. `total` mede o adapter,
incluindo fechamento do journal, antes de exportar a observação; não mede
exportação, transporte MCP, modelo ou duração da sessão. O `durations_ms` no
topo continua `null`: somar tentativas não produz tempo de sessão.

Falha de exportação emite `adf: timing_evidence_failed` em stderr e mantém o
resultado de leitura. Arquivos parciais, symlinks e FIFOs são inválidos. Hash,
run/attempt ID e hash do start devem verificar antes de correlacionar tempos.
Conflitos não entram nas amostras. Receipts, timings e `returned`/`raised` não
comprovam consumo pelo cliente nem sucesso da tarefa. Veja os
[limites e o contrato](../integration/v2/README.md#monotonic-timings-p0-d-step-3-opt-in).

## 7. Interpretar e comparar sem inflar resultados

| Campo | Interpretação |
| --- | --- |
| `reads_total` | Na suite: tentativas. Na fonte persistida: JSONs encontrados, não todas as tools da sessão |
| `bundles_total` | Entradas encaminhadas à agregação, incluindo bundles inválidos |
| `evidence_bundle_valid_total` / `invalid_total` | Evidência que verifica / falha na verificação |
| `decisions_total` | Decisões dos bundles válidos; não é a contagem total de tentativas |
| `admit_read_total` / `deny_total` | Decisão do PDP; uma admissão pode ser negada pelo PEP/runtime |
| `sensitive_path_denied_total` | Negação no efeito por caminho sensível; pode coexistir com admissão do PDP |
| `binding_mismatch_total` | Mismatches contados a partir de evidência válida |
| `reason_codes` | Distribuição dos outcomes coletados, incluindo falhas da suite |
| `decision_latency_ms` | Usar somente se `latency_recorded=true`; zeros da fonte persistida são preenchimento |
| Tokens/custo `na` ou `null` | Não disponível; nunca zero ou economia comprovada |

Repita a mesma tarefa sob as mesmas condições em sessões independentes. Separe smoke,
suite fixa e trabalho real; identifique falhas, skips e mudanças de versão. Para comparar
produtividade com/sem ADF, capture também sucesso objetivo da tarefa, duração, tokens e
custo de ambas as condições; bundles de leitura não fornecem esse baseline. Reporte o
número de sessões e a dispersão, sem transformar uma única execução em ganho geral.

Compartilhe apenas agregados revisados e metadados anônimos necessários à comparação.
Não publique bundles brutos nem diretórios inteiros de observabilidade: embora não guardem
conteúdo de arquivos, os bundles podem incluir escopos com nomes relativos de arquivos.
`report_sha256` detecta alteração do agregado; não é assinatura nem autentica o coletor.

## Diagnóstico

| Sintoma | Verificação |
| --- | --- |
| Sem bundles | Exports no processo do agente, hook confiado, matcher e tool usados |
| `host_configuration_invalid` | Root/evidence absolutos, revisão válida e budget positivo |
| `workspace_revision_unavailable` | Commit existente no destino, Git acessível |
| `path_outside_trusted_root` | Arquivo dentro do repo fixado pelo host |
| `trial_evidence_dir_unavailable` | Diretório correto, com leitura permitida |
| `trial_execution_failed` ao repetir ID | Escolher ID novo; relatórios usam criação exclusiva |
| Números menores que as tentativas | Falhas sem bundle, bundles inválidos e tools fora do matcher |

Veja [limites do control plane](CONTROL_PLANE.pt-BR.md), [eventos e trajectories](observability/README.md)
e [schemas de métricas](../integration/v1/README.md). Nenhum comando deste guia faz deploy,
publicação de pacote ou envio de dados para um serviço.

## Avaliação externa da tarefa

O coletor de sessões v2 conserva `task_outcome: null`. Para registrar o resultado
de uma avaliação externa, use o contrato independente `task-evaluation` 1.0 e as
funções `build_task_evaluation` / `verify_task_evaluation` de
`integration.task_evaluation`. A sessão precisa ter proveniência completa.

O avaliador deve verificar o critério de aceitação identificado na sessão,
executar a avaliação na revisão declarada e preservar o artefato de resultado.
Passe seu SHA-256 como `result_sha256`, um identificador e versão do avaliador,
`evaluated_revision_sha`, `created_at` UTC e `task_outcome` (`success` ou
`failure`). Para uma avaliação não executada, declare `skipped` e passe
`result_sha256=None`. Guarde o registro separadamente e valide-o junto à sessão
original; nunca substitua seu relatório v2.

O registro contém hashes e identificadores, sem saída de testes, nomes pessoais
ou caminhos. A verificação confirma integridade e vínculo, não autenticidade
do avaliador ou verdade do resultado. A execução de checks e a revisão humana
permanecem externas. Não foi atribuída avaliação ao host probe de um repositório externo.
