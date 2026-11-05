<a id="top"></a>

[English](README.md) · **Português (Brasil)**

<p align="center">
  <img src="docs/assets/brand/adf-mark.svg" alt="Símbolo ADF: uma linha de requisição encontra uma fronteira aberta, passa por um losango de decisão e deixa um quadrado de evidência separado" width="72" height="72">
</p>

<h1 align="center">ADF</h1>

<p align="center"><b>Agent Effect Security</b></p>

<p align="center">
  <b>Decisões na fronteira. Evidências com limites explícitos.</b><br>
  Decisões determinísticas de leitura nas bordas instaladas e suportadas de ferramentas de agentes de código.
</p>

<p align="center">
  <a href="#teste-com-segurança">Início rápido</a> · <a href="#cobertura-e-exclusões">Cobertura</a> · <a href="#modelo-de-confiança-maturidade-e-contribuição">Fronteira de segurança</a>
  <br>
  <sub>experimental <code>0.x</code> — veja <a href="VERSION"><code>VERSION</code></a></sub>
</p>

<p align="center">
  <a href="https://github.com/Joaolucas2210/agent-effect-security/actions/workflows/quality-gates.yml"><img src="https://github.com/Joaolucas2210/agent-effect-security/actions/workflows/quality-gates.yml/badge.svg" alt="Status do workflow de CI"></a>
  <a href="https://github.com/Joaolucas2210/agent-effect-security/releases"><img src="https://img.shields.io/github/v/release/Joaolucas2210/agent-effect-security" alt="Release mais recente no GitHub"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-263548" alt="Licença MIT"></a>
</p>

O ADF protege **leituras que passam por uma borda suportada que você instalou** — um hook de cliente, a tool de leitura MCP do ADF ou o seu gateway A2A em loopback. Ele não observa o host inteiro e não é um sandbox de sistema operacional.

## O problema

Um agente de código que pode ler `README.md` pode, com a mesma facilidade, pedir para ler `.env`. Prompts de permissão perguntam a uma pessoa a cada vez; traces mostram o que aconteceu depois. Nenhum dos dois é uma autoridade determinística sobre esse acesso a arquivo, e nenhum deixa um registro que se possa conferir sem confiar na ferramenta que o escreveu.

O ADF coloca uma decisão determinística em **bordas instaladas específicas**: uma policy do host decide quais leituras podem seguir, a decisão é reconferida no momento da leitura e o resultado tem um caminho de evidência explícito. O operador do host, o código instalado do ADF e o registro do hook continuam sendo confiáveis. [Modelo de ameaças e suas seis claims delimitadas](ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md).

## Veja uma decisão

<p align="center">
  <img src="docs/assets/adf-demo.gif" alt="Gravação de terminal numa fixture sintética: um Read de README.md é permitido, um Read de .env é negado com invalid_scope, adf verify confere o bundle da negação com uma chave temporária do host e adf projects reasons conta as duas decisões" width="900">
  <br>
  <sub>Fixture sintética, CLI e hook reais do <code>adf</code> — não é uma sessão de cliente ao vivo. <a href="docs/assets/README.pt-BR.md">Como é gravado</a>.</sub>
</p>

| Requisição na fixture do GIF | Decisão | Artefato | O que prova |
| --- | --- | --- | --- |
| `Read README.md` | `allow` — `delivered/read_delivered` | Evidence Bundle, `delivery_mode=gate_only` | O ADF admitiu a leitura e conferiu o snapshot; não os bytes que uma ferramenta nativa devolveria |
| `Read .env` | `deny` — `invalid_scope` | Evidence Bundle | A policy recusou o path antes de qualquer leitura |

## Teste com segurança

`make demo` roda o hook real contra uma fixture Git temporária, um `HOME` temporário e um `ADF_HOME` temporário. Ele não mexe nas configurações do seu agente, no seu `~/.adf` nem em segredo real algum, e reporta uma decisão ausente como "no decision", nunca como deny. Requisitos: Git, Make, Python 3.10+ com `venv`. O ADF não é publicado no PyPI.

```bash
python3 -m venv .venv && source .venv/bin/activate
make install-dev          # instalação editável neste venv; cria o `adf`
make demo                 # três decisões reais numa fixture descartável, depois verificação offline
```

```text
  ✓ Read README.md               allow delivered/read_delivered                 Evidence Bundle
  ✓ Read .env                    deny  deny/invalid_scope                       Evidence Bundle
  ✓ Edit .claude/settings.json   deny  uncovered_write_denied_agent_config      attempt journal only
  ✓ adf verify (no key)          verified                                       authenticity=not_checked
  ✓ adf verify (demo host key)   verified                                       authenticity=valid
demo passed
```

A terceira decisão é um gate deny-only: deixa **só uma entrada no journal de tentativas**, sem bundle. A fixture, o `.env` falso e o `ADF_HOME` temporário são removidos ao final (`DEMO_KEEP=1` os mantém). A versão passo a passo, com os payloads crus do hook, é o [início rápido isolado](docs/product/QUICKSTART.pt-BR.md).

**Ativar um cliente real é um passo separado e opt-in.** `adf hook-snippet claude` ou `adf hook-snippet codex` **imprime** JSON; não instala nada. Revise e mescle as entradas `hooks.PreToolUse` nas configurações do cliente, preservando os hooks existentes; reinicie o cliente; rode `adf projects enable /caminho/absoluto/do/repo`; depois `adf doctor --pin`, com o registro já feito. Para uma allowlist revisada, gere uma policy da sessão e pine-a com `ADF_READ_POLICY_FILE` e `ADF_READ_POLICY_SHA256`. [Ativação e reversão](docs/product/QUICKSTART.pt-BR.md#ative-um-cliente-real-depois). `make e2e` roda uma checagem de contrato em clone fresco das bordas locais e dos trials; não prova que uma versão específica de cliente chamou o hook.

## Como funciona

1. **Borda** — um hook ou gateway suportado traduz o pedido do agente num intent fechado. Ela nunca decide.
2. **PDP** — uma função pura decide contra uma policy pinada pelo host: default deny, reason codes estáveis, sem relógio, sem I/O, sem LLM.
3. **PEP e runtime** — no momento da leitura, os bindings são reconferidos e a decisão é consumida uma vez; um único arquivo regular é aberto por handle a partir de um snapshot Git preparado pelo host, com teto de bytes e regra de paths sensíveis.
4. **Evidência** — a decisão composta vira um Evidence Bundle; uma tentativa recusada antes da composição fica registrada no journal de tentativas.

![Caminho de leitura do ADF: um intent do agente chega a uma borda instalada, depois ao PDP, ao PEP e a uma leitura confinada do snapshot. Negações precoces seguem para uma entrada de journal, decisões compostas para um bundle, e só leituras mediadas devolvem bytes do snapshot](docs/assets/brand/adf-architecture.svg)

`gate_only` (Claude `Read`, hooks de `cat` suportados): o ADF decide e confere um snapshot, depois a ferramenta nativa entrega os próprios bytes — o bundle **não** prova esses bytes. `mediated` (leitura MCP stdio do ADF e o caminho A2A): o ADF devolve bytes da sua própria leitura controlada. Nenhum dos dois cobre um pedido que nunca chega a uma borda instalada. [Control plane em detalhe](ai-development-framework/docs/CONTROL_PLANE.pt-BR.md) · [policy pack](ai-development-framework/policy-packs/effect-security-read-v0/README.md).

## Cobertura e exclusões

A superfície implementada neste checkout. Testes de fixture local e observações em cliente real são níveis diferentes de evidência; a [matriz de suporte do BOUNDARY](docs/product/BOUNDARY.pt-BR.md#matriz-de-suporte) lista gramáticas, versões e exceções.

| Borda | Caminho implementado | O que ainda passa |
| --- | --- | --- |
| Claude Code | Gate de `Read`; leituras `Bash` selecionadas; gates deny-only em chamadas selecionadas de leitura, escrita, rede e MCP pinado | Outras rotas por Bash, script ou interpretador; tools de subagente fora desses gates; versão do cliente não registrada nos trials |
| Codex CLI | Hook para um único `cat PATH` suportado; negações Bash selecionadas | Outros comandos; chamadas MCP (o Codex não as envia a hooks); versão do cliente no hook global `na` |
| A2A | Gateway `read_workspace_file` em loopback com validação de bearer e decisões amarradas ao efeito | Um bearer roubado vale até expirar; sem gateway público, sem DPoP/mTLS |
| MCP | Leitura mediada stdio do ADF; gate deny de registry e definição no hook do Claude | Servers sem hook, mudança na lista de tools entre probes, o output do próprio server |

Não há claim de sandbox de SO nem de interceptação universal de Bash. Um agente com outra rota até o disco passa por fora desses gates. [Doze incidentes reais mapeados como cobertos, residuais ou fora de escopo](docs/knowledge/coverage.md).

## O que a evidência comprova — e não comprova

![Três desfechos de evidência: um bundle gate-only não prova os bytes nativos; um bundle mediado amarra uma leitura controlada; uma negação precoce deixa só uma entrada de journal](docs/assets/brand/adf-evidence-flow.svg)

| Registro | Comprova | Não comprova |
| --- | --- | --- |
| **Evidence Bundle** | Uma decisão composta, seus bindings e o recibo da leitura; `delivery_mode` diz se o ADF entregou os bytes (`mediated`) ou só fez o gate de uma ferramenta nativa (`gate_only`) | Os bytes que uma ferramenta nativa devolveu em `gate_only`; qualquer coisa que nunca chegou à borda |
| **Journal de tentativas** | Um registro local, encadeado por hash, de que uma tentativa chegou ao ADF e de por que foi recusada | Uma leitura verificada; um hook ausente **não** deixa registro algum do ADF |
| **Span OpenTelemetry** (opcional) | Correlação redigida para dashboards | Nada: um span nunca é evidência de autorização e sua ausência não muda decisão alguma |

`adf verify ARQUIVO` confere estrutura e digests offline e reporta `authenticity=not_checked`. `adf verify ARQUIVO --key CHAVE_DO_HOST` também confere um **HMAC de segredo compartilhado**: autentica contra a chave daquele host, não perante um verificador público independente. Mantenha a chave no host; não a entregue a um auditor externo. Um bundle guarda IDs e escopos relativos ao repositório, mas nunca conteúdo de arquivo — revise-o antes de compartilhar. [Fronteira da evidência](docs/product/BOUNDARY.pt-BR.md#evidência-é-o-registro-telemetria-só-visualiza) · [decisão sobre o HMAC](ai-development-framework/docs/architecture-decision-records/0030-evidence-authenticity-host-key.md).

## Modelo de confiança, maturidade e contribuição

**Modelo de confiança.** O operador do host precisa proteger o registro do hook, a lista de projetos habilitados, os pins de policy e a chave de evidência. Se o wrapper fornecido não encontra o executável `adf`, ele sai **sem decisão**; `adf hook` também não devolve decisão se não consegue carregar o script do hook ou falha antes de saber se o projeto está habilitado. O cliente então segue com as próprias permissões. Dentro de um projeto habilitado, uma falha do adapter é um deny. O ADF não alega comportamento fail-closed global, e um deny em processo não contém código que roda fora da borda observada. [Modelo de ameaças](ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md) · [fronteira e premissas de confiança](docs/product/BOUNDARY.pt-BR.md).

**Maturidade.** Experimental `0.x`. O efeito de leitura e gates deny-only selecionados estão implementados; um piloto no host está em curso; o efeito de escrita é uma [proposta bloqueada](ai-development-framework/docs/architecture-decision-records/0032-write-effect-admit-path.md) à espera de demanda de design partner. `ai-development-framework/` é o harness de desenvolvimento usado para construir o ADF, não faz parte da sua fronteira de enforcement. [Roadmap](docs/product/ROADMAP.pt-BR.md) · [changelog](CHANGELOG.md).

**Contribuição.** Comece por [CONTRIBUTING](CONTRIBUTING.pt-BR.md) e pelo [Código de Conduta](CODE_OF_CONDUCT.pt-BR.md). Reporte vulnerabilidades pela [rota privada do SECURITY](SECURITY.pt-BR.md), nunca em issue pública. Leituras adicionais: [guia de host e trials](ai-development-framework/docs/trials.pt-BR.md), [autoavaliação OSPS Baseline](docs/security/OSPS-BASELINE-2026-08-28.md), [assets de marca](docs/brand/BRAND_GUIDELINES.pt-BR.md). Distribuído sob a [Licença MIT](LICENSE).
