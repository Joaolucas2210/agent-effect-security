# ADF · Agent Effect Security

[English](README.md) · **Português (Brasil)**

![Símbolo ADF: um pedido do agente atravessa uma fronteira de decisão e deixa um registro separado](docs/assets/brand/adf-mark.svg)

**Decisões na fronteira.** Um control plane local para leituras nas bordas de agentes suportadas e instaladas. Versão experimental `0.x`; este checkout informa a versão em [`VERSION`](VERSION).

[![Workflow de CI](https://github.com/Joaolucas2210/agent-effect-security/actions/workflows/quality-gates.yml/badge.svg)](https://github.com/Joaolucas2210/agent-effect-security/actions/workflows/quality-gates.yml) [![Release mais recente](https://img.shields.io/github/v/release/Joaolucas2210/agent-effect-security)](https://github.com/Joaolucas2210/agent-effect-security/releases) [![Licença MIT](https://img.shields.io/badge/license-MIT-263548)](LICENSE)

[Teste uma decisão isolada](#início-rápido) · [Veja a cobertura](#cobertura-atual) · [Audite a fronteira](docs/product/BOUNDARY.pt-BR.md) · [Reporte uma vulnerabilidade em privado](SECURITY.pt-BR.md)

![Diagrama conceitual: uma intenção do agente chega à fronteira da policy, uma decisão permite a leitura e a evidência é registrada separadamente](docs/assets/brand/adf-hero.svg)

## Por que isso existe

Um agente de código pode pedir para ler `.env` durante o trabalho comum em um repositório. Prompts e traces ajudam a entender a sessão, mas não são a autoridade para esse acesso. O ADF coloca uma decisão determinística em **bordas específicas instaladas**: uma policy controlada pelo host limita quais leituras podem prosseguir, e o resultado tem um caminho de evidência explícito. O operador do host, o código ADF instalado e o registro do hook continuam confiáveis. [Modelo de ameaças e seis claims limitados](ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md).

## Veja funcionar

Na fixture sintética desta demo, `Read README.md` é permitido e `Read .env` é negado com `invalid_scope`. Ambos os pedidos chegam ao adapter e produzem Evidence Bundles. Uma negação por gate deny-only ou contrato inválido pode deixar **só uma entrada no journal**. O GIF captura CLI e hook reais em um repositório descartável; os caminhos mostrados são substituídos, e isso não representa uma sessão de cliente real. [Como reproduzir](docs/assets/README.md).

![Sessão sintética gravada: leitura de README permitida, leitura de .env negada, HMAC conferido com a chave do host da demo e contagens por motivo](docs/assets/adf-demo.gif)

## Início rápido

**Primeiro, sem configurar agentes:** siga o [início rápido isolado](docs/product/QUICKSTART.pt-BR.md). Ele cria uma fixture Git e um `ADF_HOME` temporários, instala o pacote editável em um venv, chama o `adf hook` real com dois pedidos sintéticos e verifica um bundle com chave temporária. Requisitos: Git, Make e Python 3.10+ com `venv`. Não presume instalação pública por PyPI.

```bash
python3 -m venv .venv
source .venv/bin/activate
make install-dev
adf version
# Continue com a fixture sintética e a verificação em docs/product/QUICKSTART.pt-BR.md
```

**Depois, habilite um cliente real:** `adf hook-snippet claude` ou `adf hook-snippet codex` imprime JSON. Revise e mescle as entradas `hooks.PreToolUse` nas configurações do cliente, preservando hooks existentes; reinicie o cliente; habilite um repositório com `adf projects enable /caminho/absoluto/do/repo`; então execute `adf doctor --pin` depois do registro. Para uma allowlist real, gere e pine uma policy de sessão com `ADF_READ_POLICY_FILE` e `ADF_READ_POLICY_SHA256`. [Passos completos e reversão](docs/product/QUICKSTART.pt-BR.md#ative-um-cliente-real-depois).

`make e2e` executa separadamente uma fixture em clone fresco, bordas locais e trials. É um teste de contrato, não prova de que uma versão específica do cliente instalado chamou o hook.

## Como funciona

![Arquitetura ADF: uma borda suportada envia a intenção pelo PDP, PEP e leitura confinada do snapshot; negações precoces vão ao journal e decisões compostas ao bundle](docs/assets/brand/adf-architecture.svg)

A borda traduz um pedido observado. O **PDP** decide conforme a policy pinada pelo host. O **PEP** revalida os vínculos no momento do efeito e consome a decisão uma vez. O runtime de leitura abre um arquivo regular em um snapshot Git preparado pelo host, com teto de bytes e regra de caminhos sensíveis. [Arquitetura](ai-development-framework/docs/CONTROL_PLANE.pt-BR.md) · [policy pack](ai-development-framework/policy-packs/effect-security-read-v0/README.md).

`gate_only` (Claude `Read`, hooks de `cat` suportados) significa que o ADF decide e verifica um snapshot, enquanto a ferramenta nativa entrega os bytes. O bundle **não** prova esses bytes nativos. `mediated` (leitura MCP stdio do ADF e caminho A2A suportado) significa que o ADF devolve bytes da leitura controlada. Nenhum modo cobre um pedido que não entra em uma borda instalada.

## Cobertura atual

Esta é a superfície implementada neste checkout; testes locais com fixtures e observações em cliente real são níveis diferentes de evidência. Consulte a [matriz de suporte da BOUNDARY](docs/product/BOUNDARY.pt-BR.md#matriz-de-suporte) para gramática, versões e exceções.

| Borda | Caminho implementado | Principal risco residual |
| --- | --- | --- |
| Claude Code | Gate de `Read`; leituras `Bash` selecionadas; gates deny-only para chamadas selecionadas de leitura, escrita, rede e MCP pinado | Outras rotas Bash/script/interpretador e tools de subagente não observadas; versão do cliente não registrada nos trials |
| Codex CLI | Hook para um único `cat PATH` suportado; negações Bash selecionadas | Outros comandos e chamadas MCP fora do hook; versão do cliente com hook global `na` |
| A2A | Gateway em loopback com `read_workspace_file`, validação de bearer e decisões vinculadas ao efeito | Bearer roubado vale até expirar; sem gateway público nem DPoP/mTLS |
| MCP | Leitura mediada via stdio ADF; gate de registry/definition no hook Claude | Servers sem hook, drift da lista entre probes e output não observado |

Não há alegação de sandbox de SO ou interceptação universal de Bash. Um agente com outra rota para o disco pode contornar esses gates. [Mapa de cobertura de incidentes](docs/knowledge/coverage.md).

## O que a evidência comprova

![Três resultados de evidência: bundle gate-only não prova bytes nativos; bundle mediado vincula a leitura controlada; negação precoce deixa entrada no journal](docs/assets/brand/adf-evidence-flow.svg)

- **Evidence Bundle:** decisão composta, vínculos e receipt de leitura, sem conteúdo do arquivo. `delivery_mode` indica se o ADF entregou bytes (`mediated`) ou apenas fez o gate de uma ferramenta nativa (`gate_only`). Um pedido negado antes da composição pode não ter bundle.
- **Journal de tentativas:** registro local encadeado por hash para tentativas pré-adapter e deny-only. Registra um motivo, não um receipt de leitura verificado; sem hook, não há registro ADF.
- **OpenTelemetry:** visualização opcional e redigida para correlação. A falta de um span não muda a admissão, e um span não é evidência de autorização.

`adf verify ARQUIVO` confere estrutura e digests offline e informa `authenticity=not_checked`. `adf verify ARQUIVO --key CHAVE_DO_HOST` confere também um **HMAC de segredo compartilhado**. Isso autentica em relação à chave do host, não perante um verificador público independente; não compartilhe a chave com auditor externo. A evidência ainda pode expor metadados, como IDs e scopes relativos ao repositório; revise antes de compartilhar. [Fronteira da evidência](docs/product/BOUNDARY.pt-BR.md#evidência-é-o-registro-telemetria-só-visualiza) · [decisão sobre HMAC](ai-development-framework/docs/architecture-decision-records/0030-evidence-authenticity-host-key.md).

## Fronteira de segurança

O operador do host precisa proteger o registro do hook, a lista de projetos habilitados, os pins de policy e a chave de evidência. Se o wrapper fornecido não encontrar o executável `adf`, ele sai **sem decisão**; `adf hook` também suprime exceções inesperadas. O cliente pode então prosseguir com as próprias permissões. O ADF não alega fail-closed global. Mesmo a negação dentro do processo de um projeto habilitado não contém código arbitrário fora da borda observada. [Modelo de ameaças](ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md) · [fronteira e premissas de confiança](docs/product/BOUNDARY.pt-BR.md) · [divulgação privada](SECURITY.pt-BR.md).

## Status e próximos passos

O repositório é experimental `0.x`. O efeito de leitura e gates deny-only selecionados estão implementados; o piloto no host do mantenedor é experimental, e o efeito de escrita continua uma [proposta bloqueada](ai-development-framework/docs/architecture-decision-records/0032-write-effect-admit-path.md) à espera de demanda de design partner. O harness de desenvolvimento em `ai-development-framework/` ajuda a construir o ADF, mas fica fora da fronteira de enforcement. [Roadmap](docs/product/ROADMAP.pt-BR.md) · [changelog](CHANGELOG.md).

## Documentação e contribuição

- **Integre:** [início rápido isolado](docs/product/QUICKSTART.pt-BR.md), [guia de host/trials](ai-development-framework/docs/trials.pt-BR.md), [policy pack](ai-development-framework/policy-packs/effect-security-read-v0/README.md).
- **Opere e verifique:** [boundary](docs/product/BOUNDARY.pt-BR.md), [control plane](ai-development-framework/docs/CONTROL_PLANE.pt-BR.md), [ameaças e claims](ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md).
- **Contribua:** [CONTRIBUTING](CONTRIBUTING.pt-BR.md), [Código de Conduta](CODE_OF_CONDUCT.pt-BR.md), [Licença MIT](LICENSE), [assets da marca](docs/brand/BRAND_GUIDELINES.pt-BR.md).
- **Reporte falha:** use o [canal privado de segurança](SECURITY.pt-BR.md); não abra issue pública com segredos.
