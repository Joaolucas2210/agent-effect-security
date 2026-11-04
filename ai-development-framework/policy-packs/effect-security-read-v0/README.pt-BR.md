# Policy pack `effect-security-read-v0`

[English](README.md) · **Português (Brasil)**

Este builder cria uma **policy de leitura exata, vinculada à sessão e controlada pelo host** para o PDP e PEP existentes ([ADR 0011](../../docs/architecture-decision-records/0011-pinned-host-read-policy.md)). Não adiciona efeito nem engine de execução. O runtime continua aplicando a [policy de paths sensíveis v2](../../runtime/v1/policies/sensitive-path-policy-v2.json) no momento da leitura. O ADF só decide pedidos observados em [bordas instaladas](../../../docs/product/BOUNDARY.pt-BR.md#matriz-de-suporte).

## O que verifica

`adf policy build` recebe `--run-id`, um ou mais paths exatos em `--allow` e o arquivo de saída. Recusa paths cobertos pela policy do runtime ou pelas regras extras de [`pack.json`](pack.json), depois recarrega a policy gerada antes de imprimir seu pin. Wildcards e uma DSL de policy livre não são suportados. Um path negado pode ser barrado pelo PDP (`invalid_scope` ou `scope_not_allowlisted`) antes do runtime. Nem o pack nem um trial local bem-sucedido provam que o host instalou e revisou essa policy.

## Gere e pine para uma sessão real

Depois da [instalação local](../../../docs/product/QUICKSTART.pt-BR.md), no clone do ADF:

```bash
adf policy build --run-id '<client-session-id>' --allow README.md --out /absolute/host-policy.json
# imprime: export ADF_READ_POLICY_FILE=/absolute/host-policy.json ADF_READ_POLICY_SHA256=<pin>
```

O host deve definir `ADF_READ_POLICY_FILE` e `ADF_READ_POLICY_SHA256` no ambiente do hook para a sessão, revisar o arquivo e guardar o pin SHA-256 impresso. O `run_id` da policy precisa corresponder ao ID da sessão do cliente. Mantenha o pin fixo durante a sessão; revise qualquer nova allowlist entre sessões. Sem policy configurada, a demo de referência pode sintetizar um grant para o path solicitado; isso não é uma allowlist revisada pelo host. Um pin configurado ausente, incompleto ou incorreto resulta em `host_policy_invalid`, sem cair no modo demo. [Ativação no host e trials](../../docs/trials.pt-BR.md#vários-projetos-com-um-hook-só-req-mp-01).

## Paths por principal

```bash
adf policy build --run-id '<client-session-id>' --allow README.md --allow src/app.py \
  --principal claude:main=README.md \
  --principal claude:backend-reviewer=src/app.py \
  --out /absolute/host-policy.json
```

Nomear qualquer principal fecha a policy para principals não nomeados. Cada principal nomeado recebe somente seus paths, dentro do teto global de `--allow`; `--max-act-depth` também pode limitar a profundidade de delegação ([ADRs 0024](../../docs/architecture-decision-records/0024-principal-rules-in-pinned-policy.md) e [0033](../../docs/architecture-decision-records/0033-subagent-principal-propagation.md)). O hook local afirma `claude:<agent_type>` a partir do payload do cliente; não é identidade do sistema operacional.

## Motivos esperados e limites

| Pedido | Reason code esperado | Etapa / registro |
| --- | --- | --- |
| `README.md` na allowlist | `read_delivered` | Leitura composta; bundle |
| `.env` na raiz ou aninhado | `invalid_scope` | Deny do PDP; bundle desde a ADR 0036 |
| Path válido fora da allowlist | `scope_not_allowlisted` | Deny do PDP; bundle |
| Policy editada à mão com pin errado | `host_policy_invalid` | Rejeição do adapter; journal de tentativa, sem fallback |
| Traversal inválido (`..`) | `invalid_referenced_contract` | Rejeição de contrato; journal de tentativa, sem bundle |
| Principal não listado | `principal_not_allowlisted` | Deny do PDP; bundle |

Um path admitido ainda pode ser negado pelo runtime com `sensitive_path_denied`. O `delivery_mode` do bundle importa: `gate_only` em ferramenta nativa não prova os bytes entregues; `mediated` devolve bytes controlados do snapshot. Veja a [fronteira da evidência](../../../docs/product/BOUNDARY.pt-BR.md#evidência-é-o-registro-telemetria-só-visualiza). O pack não intercepta scripts, Bash arbitrário ou processos fora da borda instalada. Teste: `bash ai-development-framework/hooks/test-policy-pack.sh`.
