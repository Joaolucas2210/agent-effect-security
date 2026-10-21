# Plano de implementação: agent effect security

[English](IMPLEMENTATION_PLAN.md) · **Português (Brasil)**

Atualizado: 2026-10-21 · Escopo: wedge v1 (negar e provar leituras sensíveis) · Fronteira: [BOUNDARY](BOUNDARY.pt-BR.md)

Regras que valem para todos os pacotes:

- Nenhum effect class novo (escrita, rede) sem ADR `Accepted` próprio **e** demanda de design partner
  registrada na tabela [Demanda registrada](#demanda-registrada).
- Código só onde serve ao wedge. Gate que não rodou é *skipped*, nunca verde.
- Gates de todo PR: `make install-dev`, `bash ai-development-framework/hooks/test-a2a-gateway.sh`,
  `bash ai-development-framework/hooks/test-local-read-adapter.sh`, `make quality-check`, `make eval-required`.
- Toda descrição de PR responde: qual dor de mercado? qual effect? qual residual fica?

## Sequência

```text
WP0 ─▶ WP1 ─▶ WP2 ─▶ WP3          (Now)
         └─▶ WP1b ✓  WP4 ✓ WP5 ✓   (Next concluído)
MP-01 ✓ ─▶ MP-02 ✓ MP-03 ✓ A2A-6b ✓ (2026-10-20)
A2A-8 ─▶ MP-04 ─▶ MP-05 ─▶ A2A-9 · MP-06   (Next em PR, 2026-10-21: credencial fora do modelo → principal → policy por principal → medição)
WP6, WP7                           (Later, com gate de ADR)
```

## WP0: posicionamento e matriz de suporte (docs)

- **Dor:** o comprador de AppSec/Platform não sabe o que é coberto; o termo "framework" vendia a coisa errada.
- **Objetivo:** README, BOUNDARY, ONEPAGER e ROADMAP mostram categoria, wedge, fora de escopo, demo e residual.
- **Arquivos:** `README.md`, `docs/product/{BOUNDARY,ONEPAGER,ROADMAP,IMPLEMENTATION_PLAN}.md`.
- **Testes:** `make quality-check`, `make eval-required`.
- **Pronto quando:** a primeira tela do README tem categoria, problema, solução, demo, fora de escopo e
  honestidade; a matriz cobre Claude `Read`, Codex `cat` e os modos de AuthN do A2A.
- **Fora de escopo:** renomear o diretório `ai-development-framework/` (quebraria instalações existentes).

## WP1: policy pack `effect-security-read-v0`

- **Dor:** agentes leem `.env`, chaves e segredos; o time precisa de uma policy pronta, pinada e revisável.
- **Objetivo:** gerar a host policy existente (ADR 0011) a partir de uma allowlist exata, recusando paths
  de segredo. Sem engine paralela: o runtime continua aplicando `sensitive-path-policy-v1`.
- **Arquivos:** `ai-development-framework/policy-packs/effect-security-read-v0/{pack.json,build.py,README.md}`,
  `ai-development-framework/hooks/test-policy-pack.{sh,py}`.
- **Testes:** `bash ai-development-framework/hooks/test-policy-pack.sh`.
- **Pronto quando:** a saída carrega com `load_host_policy` e o pin impresso; o gate Claude `Read` entrega o
  README e nega `.env`, `config/.env` e `secrets/…` com o `reason_code` de cada camada; a denylist do pack
  contém a do runtime; um segredo que escapou do builder ainda é negado no runtime.
- **Fora de escopo:** wildcard/DSL na policy (o ADR 0011 proíbe), mudar a denylist do runtime.

## WP1b: denies do PDP anteriores ao scope verificáveis (**Done**, 2026-10-19)

- **Dor:** `invalid_scope`, `invalid_arguments` e `sensitive_argument_rejected` geram bundle com
  `effective_scope: null`. O schema do `EvidenceBundle` exige objeto, então o bundle não verifica offline.
  Claude/Codex contam esses casos em `evidence_bundle_invalid_total`; o A2A responde 500
  `a2a_evidence_failed` (exemplo: `config/.env`). É fail-closed, mas o deny não fica provado.
- **Objetivo:** aceitar `effective_scope: null` no schema do bundle, alinhado ao `AdmissionDecision`, que já
  permite `null`. Um admit com `null` continua falhando em `verify_offline`, porque o receipt exige scope.
- **Arquivos:** `integration/v1/schemas/evidence-bundle.schema.json`, `hooks/test-local-evidence-bundle.py`,
  as contagens fixadas em `hooks/test-local-evidence-trial.py`, `docs/CONTROL_PLANE.md` (limites e
  interpretação), e o caso T5d de `hooks/run-a2a-live-trial.py` (passa a esperar 200 `invalid_scope`).
- **Testes:** suites de bundle, local-evidence-trial, a2a-gateway e a2a-live-trial.
- **Pronto quando:** o deny de `config/.env` verifica nas três bordas e a mudança nas métricas da suite fixa
  (`evidence_bundle_invalid_total` 1 → 0) aparece documentada no PR.
- **Status:** aprovado pelo mantenedor e entregue. Métricas da suite fixa mudam: `evidence_bundle_invalid_total`
  1 → 0, `deny_total` 0 → 1, `binding_mismatch_total` 1 → 2, `decisions_total` 3 → 4. Não compare com trials anteriores.
- **Fora de escopo:** gerar bundle para denies de contrato (a request nunca validou).

## WP2: trial A2A ao vivo repetível

- **Dor:** um único trial manual não convence AppSec; precisa ser reproduzível no SHA deles.
- **Objetivo:** `make a2a-live-trial` sobe o gateway real em loopback com fixture hermética, policy do pack e
  segredo HS256 só em memória, e executa a matriz: 401 (sem token, assinatura inválida, expirado),
  403 (scope, skill), deny da policy, path fora do workspace, `.env` na raiz e aninhado, allow do README,
  pausa `input-required` → confirmação humana.
- **Arquivos:** `ai-development-framework/hooks/run-a2a-live-trial.py`, `hooks/test-a2a-live-trial.{sh,py}`,
  `Makefile`, `docs/observability/trials/a2a-live/README.md`.
- **Testes:** `bash ai-development-framework/hooks/test-a2a-live-trial.sh`; `make a2a-live-trial`.
- **Pronto quando:** sai com código diferente de 0 se algum caso divergir, se um record falhar em
  `verify_record` ou se o relatório tiver token, segredo, path absoluto ou conteúdo; nunca sobrescreve um trial.
- **Fora de escopo:** consulta automática ao Jaeger, benchmark de latência, RS256 com IdP real.

## WP3: docs do contrato 200 + deny e da contagem A2A

- **Dor:** cliente que lê só o status HTTP trata um deny como sucesso; agregados misturados enganam AppSec.
- **Objetivo:** documentar que 200 pode trazer `outcome=deny` e que `make local-evidence-trial` não conta
  records A2A. O `summary.json` do WP2 é o agregador A2A enxuto.
- **Arquivos:** `docs/product/BOUNDARY.md`, `docs/observability/trials/a2a-live/README.md`.
- **Testes:** `make quality-check`.
- **Pronto quando:** as duas regras aparecem na fronteira e no README dos trials A2A.
- **Fora de escopo:** um agregador A2A versionado com schema próprio (só quando um partner precisar).

## WP4: runbook RS256/JWKS ("piloto enterprise") (**Done**, 2026-10-19)

- **Dor:** HS256 não serve para IdP real; um partner enterprise precisa de um caminho dourado.
- **Objetivo:** runbook passo a passo: exportar a JWKS do IdP, calcular o pin, configurar `iss`/`aud`, girar a
  chave (novo pin entre sessões), validar com um token real, e um trial A2A com `auth_mode: rs256_jwks`.
- **Arquivos:** `ai-development-framework/docs/runbooks/a2a-rs256-jwks.md` (novo); talvez uma opção
  `--jwks` no runner do WP2.
- **Testes:** `test-a2a-gateway.sh` (o RS256 já tem mutação e oráculo `openssl`).
- **Pronto quando:** um partner executa o runbook sem ler código e obtém um trial A2A em RS256.
- **Fora de escopo:** fetch/rotação automática de JWKS, emissão de token pelo gateway.
- **Entregue:** [`docs/runbooks/a2a-rs256-jwks.md`](../../ai-development-framework/docs/runbooks/a2a-rs256-jwks.pt-BR.md) e
  `make a2a-live-trial AUTH=rs256` (IdP de teste via `openssl`, gateway só com a JWKS pública pinada). O trial com
  IdP real é o smoke manual do runbook: um IdP real não emite os tokens adversariais da matriz.

## WP5: spans OTel nas bordas locais (**Done**, 2026-10-20; [ADR 0021](../../ai-development-framework/docs/architecture-decision-records/0021-local-edge-otel-spans.md) Accepted)

- **Dor:** decisões de Claude/Codex não aparecem na mesma tela que as do A2A.
- **Objetivo:** um span `adf.local_read.request` por decisão de cada borda local (Claude `Read`, Codex `cat`,
  MCP), emitido na borda e não no adapter (o A2A continua com um span só). Usa a allowlist do ADR 0020 mais
  `adf.edge`, um flush com teto nos hooks e nenhum stderr no hook.
- **Arquivos:** `hooks/claude-code-read-gate.py`, `hooks/codex-bash-read-gate.py`, `integration/mcp_read_server.py`,
  `integration/otel_export.py`, `hooks/test-otel-export.py`.
- **Testes:** `test-otel-export.sh`, `test-local-read-adapter.sh`, `test-a2a-gateway.sh`.
- **Pronto quando:** o ADR 0021 está `Accepted` e a matriz de validação dele passa: span único por borda,
  sem path/`command`/`session_id` no payload, decisão idêntica com o collector fora, flush dentro do teto.
- **Fora de escopo:** fazer do span uma evidência; spans filhos PDP/PEP; qualquer atributo além de `adf.edge`.

## WP6: effect de escrita/edição (Later, gate de ADR)

- **Dor:** agentes também editam arquivos sensíveis (CI, configs de deploy).
- **Gate:** ADR `Accepted` + demanda de pelo menos um design partner registrada abaixo.
- **Esboço:** um novo effect class no PDP, um PEP com escrita atômica no worktree, um receipt com
  digest antes/depois, e as bordas Claude `Edit`/`Write`.
- **Fora de escopo até o gate:** qualquer código.

## WP7: DPoP/mTLS, Agent Card assinado, Token Exchange com AS externo (Later, gate de ADR)

- **Dor:** um bearer roubado vale até `exp`; peers remotos pedem prova de posse.
- **Gate:** ADR próprio (o 0019 adiou o endpoint de exchange) + demanda registrada.
- **Fora de escopo até o gate:** endpoint de Token Exchange, DPoP, bind fora de loopback.

## REQ-MP-01: ativação multi-projeto no host (**Done**, 2026-10-20)

- **Dor:** o ADF só funcionava bem no próprio clone; um hook global sem configuração por projeto negaria tudo.
- **Entregue:** `hooks/adf-read-hook.py` (registro global único, lista `~/.adf/enabled-projects`, evidência em
  `~/.adf/evidence/`), `hooks/test-adf-read-hook.{sh,py}`, seção em `docs/trials.md`.
- **Fora do MVP:** auto-descoberta de repos, policy pack automático por projeto, proteção da lista contra edição
  via `Bash`. O wrapper Codex virou MP-03.

## REQ-MP-02: UX de portfólio (PR `feat/portfolio-projects-cli`, 2026-10-20)

- **Dor:** ativar projetos só editando `~/.adf/enabled-projects` à mão; nenhuma visão do que foi negado por projeto.
- **Entregue:** `hooks/adf-projects.py` (`list | enable | disable | reasons`) e `make projects` / `project-enable` /
  `project-disable` / `project-reasons`. Mesmas regras do hook (absoluto, normalizado, sem `..`; symlink vira path
  real; fora de git aceita com aviso); escrita atômica `0600`; `reasons` agrega `reason_code` por projeto
  (receipt primeiro), só contagens.
- **Testes:** `bash ai-development-framework/hooks/test-adf-projects.sh`.
- **Residual:** o agente pode rodar o CLI ou editar o arquivo via `Bash`; a lista não é protegida.

## REQ-MP-03: Codex pelo mesmo hook global (PR `feat/mp01-codex-symmetry`, 2026-10-20)

- **Dor:** o allowlist do host só cobria o `Read` do Claude; Codex exigia variáveis por shell.
- **Entregue:** `adf-read-hook.py` despacha `Read` → gate Claude e `Bash` → gate Codex P4; projeto vem de
  `CLAUDE_PROJECT_DIR` ou do `cwd` do payload (ambos do host). Mesma lista, raiz git e pasta de evidência.
  Projeto ativado com tool desconhecida ou payload malformado → deny.
- **Testes:** `bash ai-development-framework/hooks/test-adf-read-hook.sh` (casos Codex).
- **Residual:** só `cat PATH`; hook global do Codex validado pelo contrato de payload, não em trial (`na`).

## A2A-6b: `effect_binding` (PR `feat/a2a-effect-binding`, ADR 0022 Accepted, mergeado em #84, 2026-10-20)

- **Dor:** a retomada já é vinculada a `sub`/skill/`path` (ADRs 0016/0018), mas o record da pausa não carrega o
  descritor, então o auditor confia no gateway.
- **Entregue:** `effect_binding` = digest de `sub` + skill + `path` na pausa, na retomada confirmada e no deny de
  retomada; `confirmation` exige o campo no schema.
- **Testes:** `bash ai-development-framework/hooks/test-a2a-gateway.sh`, `test-a2a-live-trial.sh`.
- **Status:** ADR 0022 aceito pelo mantenedor em 2026-10-20; entregue.

## A2A-8: cliente A2A no host (PR `feat/mcp-a2a-client`, 2026-10-21)

- **Dor:** o piloto colou um JWT no prompt para o peer ler pelo gateway; credencial no contexto do modelo.
- **Entregue:** `integration/mcp_a2a_client.py`, servidor MCP stdio com uma tool `read_via_adf(path)`; token em
  `ADF_A2A_TOKEN_FILE` (absoluto, regular, `0600`), URL só em loopback; deny/pausa/401/transporte viram reason codes;
  sem tool de confirmação por desenho.
- **Testes:** `bash ai-development-framework/hooks/test-mcp-a2a-client.sh`.
- **Residual:** um agente a quem alguém der um token ainda pode usar `curl` por `Bash`.

## MP-04: principal local derivado do harness (PR `feat/local-principal`, ADR 0023 Accepted, 2026-10-21)

- **Dor:** três subagentes em paralelo e a evidência não dizia quem leu o quê.
- **Entregue:** `local_principal(payload, edge)` monta um `CallerPrincipal` (`claude:<agent_type>`, `host_harness`) a
  partir do payload do hook, verificado empiricamente; vai ao PDP/PEP, ao journal (`principal_sub`) e ao span
  (`adf.agent_type`). `agent_type` malformado nega. Bundle inalterado.
- **Testes:** `test-local-edge-otel.sh`, `test-adf-read-hook.sh`.
- **Status:** ADR 0023 aceita pelo mantenedor em 2026-10-21; entregue.

## MP-05: `principal_rules` na policy pinada (PR `feat/principal-policy`, ADR 0024 Accepted, 2026-10-21)

- **Dor:** todo principal com `workspace:read` tinha a mesma autoridade; least privilege por agente não existia no PDP.
- **Entregue:** `principal_rules` opcional no `PolicyBundle`, coberto pelo pin; PDP fechado a quem não é nomeado
  (`principal_required`, `principal_not_allowlisted`, `scope_not_allowlisted_for_principal`); a lista do host continua
  o teto. `build.py --principal SUB=PATH[,PATH]`.
- **Testes:** `bash ai-development-framework/hooks/test-principal-policy.sh` (PDP, builder, A2A ponta a ponta, adapter).
- **Status:** ADR 0024 aceita pelo mantenedor em 2026-10-21; entregue. Depende de MP-04 para valer nas bordas locais; sem ele, policy com
  `principal_rules` nega as bordas locais (`principal_required`), por desenho.

## A2A-9: `mint --ttl` (PR `feat/mint-ttl`, 2026-10-21)

- **Dor:** token de 5 min venceu três confirmações humanas no piloto.
- **Entregue:** padrão 1 h, `--ttl` até 86400, só no dublê de IdP; o gateway continua sem emitir.

## MP-06: `project-reasons` com journal e principais (PR `feat/project-reasons-principals`, 2026-10-21)

- **Dor:** o `.env` da raiz (deny de contrato, sem bundle) não aparecia no agregado; nada media privilégio por agente.
- **Entregue:** linha `attempts=` do journal; linhas `principal=` com attempts/delivered/denied/paths_read; `POLICY=` dá
  `granted`/`unused` por principal. Só contagens, nunca paths.
- **Testes:** `bash ai-development-framework/hooks/test-adf-projects.sh`.

## Explicitamente não faremos

UI de grafo de agentes no repo; Langfuse self-hosted como core; bind público sem ADR; billing;
telemetria phone-home ligada por padrão; UI de orquestração; orquestrador que distribui tokens; ADF como
OAuth AS ou endpoint de Token Exchange; UI ou registry de agentes; token gerido pelo LLM.

## Demanda registrada

| Data | Partner | Pedido | WP |
| --- | --- | --- | --- |
| — | — | Nenhuma registrada ainda | — |
