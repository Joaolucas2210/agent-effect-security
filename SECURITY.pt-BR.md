# Política de segurança

[English](SECURITY.md) · **Português (Brasil)**

O ADF é um controle de segurança para coding agents: uma vulnerabilidade aqui pode transformar um deny em allow.
Reporte em privado e nos dê a chance de corrigir antes de ficar público.

## Versões suportadas

| Versão | Suportada |
| --- | --- |
| `main` e o release `0.x` mais recente | Sim |
| Releases `0.x` anteriores | Não; atualize antes |

O projeto é experimental (`0.x`). Contratos podem mudar entre versões minor, e as notas de release dizem quando.

## Como reportar

- Use o reporte privado do GitHub: **Security → Report a vulnerability** neste repositório
  (<https://github.com/Joaolucas2210/agent-effect-security/security/advisories/new>).
- Não abra issue, pull request ou discussion pública para uma suspeita de vulnerabilidade.
- Inclua o SHA do commit, a borda envolvida (Claude `Read`/`Bash`, Codex `cat`, A2A, MCP), a menor reprodução que
  tiver e o `reason_code` esperado versus o obtido.
- Nunca envie segredos reais, tokens, Evidence Bundles crus de repositório privado ou dados pessoais. Bundles
  redigidos e fixtures sintéticas bastam.

## O que esperar

| Etapa | Meta |
| --- | --- |
| Confirmação de recebimento | em até 3 dias úteis |
| Primeira avaliação (válido, severidade, versões afetadas) | em até 10 dias úteis |
| Correção ou mitigação de problema alto/crítico confirmado | o mais rápido possível, coordenado com você |
| Advisory público | depois de um release corrigido, com crédito a você, se quiser |

São metas de um projeto com um mantenedor, não um SLA contratual.

## Dentro do escopo

- Uma request admitida (`delivered`) que a policy pinada do host, o PDP, o PEP ou o runtime deveriam negar.
- Um deny ou allow sem Evidence Bundle ou record A2A onde a documentação diz que existe, ou um bundle ou record
  adulterado que ainda verifica offline.
- Bypass de autenticação ou autorização na borda A2A (validação de token, scopes, cadeias `act`, retomada de task,
  `human:confirm`, `effect_binding`).
- Segredos, tokens, conteúdo de arquivo ou paths absolutos vazando para evidência, logs ou spans OpenTelemetry.
- Uma falha do ADF que bloqueia as tools do agente em projetos que não estão ativados.
- Uma chamada coberta e registrada no hook que prossiga após um deny explícito do ADF, com versão do cliente e
  reprodução sintética. O [contrato de bootstrap](ai-development-framework/docs/architecture-decision-records/0037-hook-bootstrap-failure-contract.md)
  registra o que ainda não foi verificado sobre executável ausente e fallback do cliente.

## Fora do escopo

São limites documentados, não vulnerabilidades. Veja a
[matriz de suporte](docs/product/BOUNDARY.pt-BR.md#matriz-de-suporte):

- Leituras por rotas não observadas, como scripts, interpretadores arbitrários ou servidores MCP fora do hook.
  A gramática Bash nega formas selecionadas de `head`/`sed`/pipes, mas não é um sandbox.
- Um agente editando `~/.adf/enabled-projects` ou as próprias settings via `Bash`.
- Qualquer coisa que exija o segredo HS256 do piloto, ou um bearer roubado usado antes de `exp` (sem DPoP/mTLS ainda).
- Vulnerabilidades do próprio Claude Code, Codex ou outros agentes. Reporte aos fornecedores.
