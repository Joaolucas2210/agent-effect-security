# Início rápido: decisão de leitura isolada

[English](QUICKSTART.md) · **Português (Brasil)**

Esta demo chama a entrada `PreToolUse` real do ADF com payloads sintéticos. Ela não registra hook no cliente, não toca nas configurações do agente e não afirma ter testado uma sessão real do Claude Code. Requisitos: Git, Make, Python 3.10+ com `venv` e um clone local. `make install-dev` instala o pacote editável no venv ativo; o ADF não é publicado no PyPI. Use um shell e diretório descartáveis.

## 1. Instale e prepare um projeto sintético

No clone do ADF:

```bash
python3 -m venv .venv
source .venv/bin/activate
make install-dev
adf version                         # deve corresponder ao VERSION deste clone

DEMO_ROOT="$(mktemp -d)"
mkdir -p "$DEMO_ROOT/project" "$DEMO_ROOT/home"
export ADF_HOME="$DEMO_ROOT/home/.adf"
export ADF_EVIDENCE_KEY_FILE="$ADF_HOME/evidence.key"
printf 'public demo\n' > "$DEMO_ROOT/project/README.md"
printf 'synthetic only\n' > "$DEMO_ROOT/project/.env"
git -C "$DEMO_ROOT/project" init -q
git -C "$DEMO_ROOT/project" add README.md .env
git -C "$DEMO_ROOT/project" -c user.name=Demo -c user.email=demo@example.invalid commit -qm fixture
adf key init "$ADF_EVIDENCE_KEY_FILE"
adf projects enable "$DEMO_ROOT/project"
```

A fixture não contém credencial real. Esta demo de referência gera a allowlist para cada path solicitado; ela **não** é uma policy revisada e controlada pelo host. Para um projeto real, gere e pine uma allowlist exata com [`adf policy build`](../../ai-development-framework/policy-packs/effect-security-read-v0/README.md) e defina `ADF_READ_POLICY_FILE` e `ADF_READ_POLICY_SHA256` para a sessão.

## 2. Peça duas decisões à borda instalada

```bash
printf '{"hook_event_name":"PreToolUse","tool_name":"Read","session_id":"demo","tool_input":{"file_path":"%s"}}' "$DEMO_ROOT/project/README.md" | CLAUDE_PROJECT_DIR="$DEMO_ROOT/project" adf hook
printf '{"hook_event_name":"PreToolUse","tool_name":"Read","session_id":"demo","tool_input":{"file_path":"%s"}}' "$DEMO_ROOT/project/.env" | CLAUDE_PROJECT_DIR="$DEMO_ROOT/project" adf hook
```

Espere `allow` com `delivered/read_delivered` para `README.md` e `deny/invalid_scope` para `.env`. Nesta fixture, ambos chegam ao adapter e produzem bundles. O pedido passa pelo hook, PDP, PEP e leitura do snapshot reais, mas nenhuma leitura nativa do cliente ocorre aqui. O modo resultante é `gate_only`: a decisão e a checagem do snapshot pelo ADF não provam os bytes que uma ferramenta nativa entregaria. Falhas de contrato e de gates deny-only podem deixar somente uma entrada no journal.

## 3. Verifique e encerre

```bash
find "$ADF_HOME/evidence" -name '*.json' -not -path '*/_attempts/*' -print
adf verify "$(find "$ADF_HOME/evidence" -name '*.json' -not -path '*/_attempts/*' -print -quit)" --key "$ADF_EVIDENCE_KEY_FILE"
adf projects reasons
```

Espere `verified ... authenticity=valid ... delivery_mode=gate_only`. `--key` verifica um HMAC com o mesmo segredo que emitiu o registro; não é verificação pública independente. Sem `--key`, o resultado é `authenticity=not_checked`. Mantenha a chave no host; não a entregue a um auditor externo. O diretório da demo pode ser removido após a inspeção. Veja [o que a evidência comprova](BOUNDARY.pt-BR.md#evidência-é-o-registro-telemetria-só-visualiza).

## Ative um cliente real depois

`adf hook-snippet claude` ou `adf hook-snippet codex` **imprime JSON; não instala nada**. Revise e mescle as entradas `hooks.PreToolUse` emitidas nas configurações do cliente sem substituir hooks existentes. Reinicie o cliente para carregar o novo registro. Então execute `adf projects enable /caminho/absoluto/do/repositorio` e `adf doctor --pin` no host **depois** que o registro estiver no lugar. O comando do hook exporta o path da chave de evidência somente se uma chave existia ao imprimir o snippet; gere e revise o snippet novamente após criar a chave. Uma allowlist real é vinculada à sessão e precisa ser pinada separadamente. Leia o [guia de instalação e trials](../../ai-development-framework/docs/trials.pt-BR.md#vários-projetos-com-um-hook-só-req-mp-01) e a [matriz de suporte](BOUNDARY.pt-BR.md#matriz-de-suporte) antes de habilitar um repositório de trabalho.

Para desabilitar um projeto, execute `adf projects disable /caminho/absoluto/do/repositorio`. Para remover a integração, retire apenas as entradas do ADF, preserve os outros hooks, reinicie o cliente e peça ao host que revise o pin. Se o executável ADF não estiver disponível ou falhar antes de uma decisão, o wrapper fornecido sai sem decidir; o cliente pode continuar com as próprias permissões. Não há fail-closed global.
