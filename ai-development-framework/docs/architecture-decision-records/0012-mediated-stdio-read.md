# ADR 0012: uma leitura mediada via MCP local

> **English summary.** The Claude `Read` and Codex `cat` gates let the native tool deliver bytes, so the snapshot the adapter read and the checkout can diverge. The proposal adds a single local stdio MCP tool `read_snapshot(path)`, built on the pinned official MCP Python SDK 2.2.0 as an optional extra, that returns the adapter's text directly after revalidating the bundle and matching SHA-256 and size against the receipt; every host parameter must be present and valid, with no fallback to demo mode, and a denial returns a `ToolError` with a stable reason code and no text. Status: Accepted by the maintainer on 2026-10-21 (release 0.1.0 preparation); the MCP read server remains opt-in and validated only in tests. Limits: the journal does not confirm that a model consumed the result, an agent with another read tool can bypass the MCP path, hashes do not authenticate origin against the same UID, and the result does not extend to real Claude or Codex installations without an end-to-end trial. The full record below is in Portuguese.

- **Status:** Accepted — aceite humano em 2026-10-21 (mantenedor, preparação do release 0.1.0); antes: Proposed — experimento opt-in em branch separada; exige revisão humana.
- **Date:** 2026-09-29
- **Depends on:** ADRs 0007–0011.
- **Scope:** P0-C da [pesquisa de evolução](../research/2026-09-26-product-evolution.md).

## Problema e decisão proposta

Os gates Claude `Read` e Codex `cat` deixam a tool nativa entregar bytes;
o snapshot lido pelo adapter e o checkout podem divergir. Introduzir uma
única tool MCP local `read_snapshot(path)` que retorna diretamente o texto
UTF-8 produzido pelo adapter para o cliente. Revalidar bundle e comparar
SHA-256/tamanho do texto com o receipt imediatamente antes do retorno.
Denial usa `ToolError` com reason code estável; nenhum texto é retornado.

Usar o SDK MCP Python oficial 2.2.0 pinado como extra opcional para stdio,
schema de entrada e erro de tool; não escrever transporte ou parser próprio.
O cliente só envia `path`. O host fixa root, revision, evidence, orçamento,
run ID e policy externa com pin via ambiente ao iniciar o servidor. Todos
devem estar presentes e válidos; ausentes não caem no modo demo. PDP/PEP e
runtime continuam decidindo e lendo o snapshot. A tool é apenas o adaptador
de entrega. A annotation `readOnlyHint` é metadata, não autorização.

O teste com cliente SDK em memória e em subprocesso stdio observa o conteúdo
que o cliente recebeu. Sua igualdade com o hash do receipt liga os bytes do
teste à mesma execução. O journal ainda não confirma que um modelo consumiu
o resultado; falha de transporte após o retorno do servidor pode interromper
essa entrega. Não estender essa afirmação aos hooks ou a instalações reais
do Claude/Codex sem ensaio end-to-end. A [matriz P0-C](../integrations/coverage-2026-09-29.md)
usa `mediated`, `gate_only`, `uncovered` e `unsupported` somente como diagnóstico.

## Fronteiras e reversão

Transporte somente stdio, sem endpoint HTTP, socket ou efeito de escrita de
workspace. Evidência local continua efeito existente. O servidor só lê paths
exatos autorizados por policy do host. O cliente e seu uso posterior do texto
permanecem fora dessa contenção; um agente com outra tool de leitura pode
contornar o caminho MCP. O host deve configurar o servidor em ambiente
controlado e manter seus parâmetros inacessíveis ao agente. Hashes não
autenticam origem contra o mesmo UID. SDK traz dependências transitivas;
revisar atualização antes de mudar o pin e não habilitar transporte HTTP
por conveniência.

Remover a configuração MCP e o extra opcional reverte o experimento; os
gates atuais e bundles v1 continuam disponíveis. Não apagar journals/bundles
anteriores nem marcar os gates como `mediated`. A ADR 0011 do PR #47 também
permanece Proposed até revisão humana.

## Aceite e validação

Teste primeiro: checkout com edição não commitada; resultado do cliente igual
ao snapshot e hash/tamanho do receipt; path fora da allowlist nega sem bytes;
bundle adulterado nega; ambiente incompleto nega; descoberta e chamada stdio
reais. Rodar `make quality`, `make eval`, `make mcp-audit`, `make graph-check`,
testes do adapter/transportes e revisão de dependência/privacidade. Gates
indisponíveis são skipped e relatados; nenhum CI remoto é inferido de teste local.

Fontes: [MCP 2026-07-28 stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports),
[SDK Python v2](https://py.sdk.modelcontextprotocol.io/get-started/),
[MCP SDK ToolError](https://py.sdk.modelcontextprotocol.io/servers/handling-errors/),
[PyPI 2.2.0](https://pypi.org/project/mcp/2.2.0/). O pin 2.2.0 inclui as correções
para [validação de `$ref` remoto](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-rwrf-2pqf-9j8j)
e [redirecionamento OAuth de credenciais](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-qx49-fqc8-xw99),
publicadas em 2026-09-28. Este experimento usa stdio e não usa OAuth.
