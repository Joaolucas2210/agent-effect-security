# Contribuir com o ADF

[English](CONTRIBUTING.md) · **Português (Brasil)**

Obrigado por ajudar. O ADF é um controle de segurança, então a régua é evidência: toda mudança diz qual dor de
mercado resolve, qual effect toca e qual risco residual permanece.

## Antes de começar

- Leia a [fronteira](docs/product/BOUNDARY.pt-BR.md) e o [roadmap](docs/product/ROADMAP.pt-BR.md). Itens em
  *Later* e *Not doing* exigem ADR aceito e demanda registrada de design partner antes de qualquer código.
- Abra uma issue antes de qualquer coisa maior que uma correção pequena. Mudanças na fronteira de autorização (um
  effect novo, uma borda nova, uma mudança de contrato) exigem ADR em
  [`ai-development-framework/docs/architecture-decision-records/`](ai-development-framework/docs/architecture-decision-records/).
- Reporte vulnerabilidades em privado, como descrito em [SECURITY.pt-BR.md](SECURITY.pt-BR.md). Nunca numa issue pública.

## Ambiente de desenvolvimento

Requisitos: Git, Make, Python 3.10+ e Bash 4+ (no macOS, o `bash` do Homebrew primeiro no `PATH`).

```bash
git clone https://github.com/Joaolucas2210/agent-effect-security.git && cd agent-effect-security
make bootstrap            # .venv + instalação editável; o Makefile usa a .venv sem ativar
make test                 # os quality gates do CI
```

`make help` lista os comandos de produto e de contribuição; `make help-all` inclui o harness. Com o seu próprio
venv, ative-o e rode `make install-dev`; um `ADF_CONTRACTS_PYTHON` explícito sempre prevalece sobre a `.venv`.

## Organização do repositório

O produto e o harness que o constrói dividem este repositório. Só o primeiro grupo é o ADF.

| Caminho | O que é |
| --- | --- |
| `ai-development-framework/tools/`, `runtime/`, `integration/` | **Produto.** PDP, PEP e runtime de leitura, bordas e o CLI `adf` (os pacotes instalados) |
| `ai-development-framework/contracts/`, `policy-packs/` | **Produto.** JSON Schemas fechados e o policy pack de leitura |
| `ai-development-framework/hooks/adf-*.py`, `*-read-gate.py` | **Produto.** Os pontos de entrada de hook que um cliente chama |
| `ai-development-framework/hooks/test-*` | Self-tests de contrato; `make test` roda todos |
| `ai-development-framework/e2e/`, `docs/product/`, `docs/security/` | `make demo` e `make e2e`; documentação para usuários e de segurança |
| `ai-development-framework/docs/architecture-decision-records/` | ADRs: o registro do porquê |
| `agents/`, `commands/`, `skills/`, `rules/`, `modes/`, `loops/`, `sandbox/`, `setup-adf.sh`, `.codex/` | **Harness.** O framework de desenvolvimento com agentes usado para construir o ADF; não faz parte da fronteira de enforcement |


## Fluxo

1. Issue, depois spec ou plano na descrição do PR, depois a implementação. Mantenha PRs pequenos: o guard de
   segurança de mudança do CI recusa PR que toca mais de 30 arquivos.
2. Mudança sensível a segurança é test-first: escreva o teste negativo (o deny, o bundle adulterado, o token
   forjado) e veja-o falhar antes da correção.
3. Hook, skill ou comando novo ou alterado precisa de caso de eval, de um self-test `hooks/test-*.sh` que o
   mencione, ou de um waiver datado em `ai-development-framework/docs/evals/waivers.md`. `make eval-required` é o gate.
4. Rode os gates antes do push:

   ```bash
   make test              # todos os self-tests e gates de stack, sem persistir evidência de eval
   make eval-required     # cobertura de eval do diff
   ```

   Gate que não roda é reportado como **skipped**, nunca como aprovado. Diga isso no PR.
5. A descrição do PR responde: dor de mercado, effect, risco residual, gates rodados (com os skips listados).

## Convenções

- **Commits:** Conventional Commits com escopo, como no histórico (`feat(pdp): ...`, `fix(eval): ...`,
  `docs(product): ...`). O corpo explica o porquê, não só o quê.
- **Código:** o mínimo que funciona; stdlib primeiro; nenhuma dependência nova para o que poucas linhas resolvem.
  Contratos são JSON Schemas fechados (`additionalProperties: false`); campo novo exige mudança de schema, oráculo
  normativo e teste negativo.
- **Evidência e telemetria:** nunca coloque conteúdo de arquivo, paths absolutos, tokens ou segredos em bundles,
  records, logs ou spans. OpenTelemetry é visualização, nunca autoridade.
- **Docs:** inglês é o idioma principal. Documento voltado ao usuário tem um irmão em português `X.pt-BR.md` com os
  mesmos headings e o seletor de idioma na linha 3; o self-test de docs confere links, âncoras e essa paridade.
  ADRs são registros: os novos são escritos em inglês; ADRs antigos em português têm um resumo em inglês.

## Licença

Ao contribuir, você concorda que sua contribuição é licenciada sob a [licença MIT](LICENSE).
Siga o [Código de Conduta](CODE_OF_CONDUCT.pt-BR.md).
