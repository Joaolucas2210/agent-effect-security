# OSPS Baseline 2026.08.28: autoavaliação com evidências

[English](OSPS-BASELINE-2026-08-28.md) · **Português (Brasil)**

Data da avaliação: 2026-11-04. Fonte: [OpenSSF OSPS Baseline, versão 2026.08.28](https://baseline.openssf.org/versions/2026-08-28). Esta é uma **autoavaliação local**, não badge OpenSSF, certificação nem alegação de conformidade completa. “Adotado” significa que o artefato citado foi inspecionado no repositório; não afirma configurações do GitHub que não foram observadas. “Parcial” significa que há evidência útil, mas o controle completo não foi verificado. “Pendente” significa falta de evidência adequada aqui. “N/A” traz o motivo. O Nível 1 foi avaliado controle por controle; alguns controles de Nível 2 aparecem como melhorias voluntárias para este projeto de um mantenedor.

## Controles de Nível 1

| Controle | Estado | Evidência ou lacuna |
| --- | --- | --- |
| OSPS-AC-01.01 | Pendente | MFA dos colaboradores é configuração do GitHub; não é visível neste checkout. |
| OSPS-AC-02.01 | Pendente | Permissões padrão de novos colaboradores não foram inspecionadas. |
| OSPS-AC-03.01 | Pendente | Regras de branch que impeçam commits diretos em `main` não foram inspecionadas. CI sozinho não é regra de branch. |
| OSPS-AC-03.02 | Pendente | Proteção contra exclusão do branch principal não foi inspecionada. |
| OSPS-BR-01.01 | Parcial | O [guard do workflow](../../.github/workflows/quality-gates.yml) valida contagem e paths alterados; todos os usos de metadados não confiáveis de issue/PR ainda precisam de revisão. |
| OSPS-BR-01.03 | Parcial | O job de gates pede `contents: read` e checkout desativa credenciais persistidas; todos os jobs e eventos ainda precisam de revisão dos ativos privilegiados. |
| OSPS-BR-03.01 | Parcial | Links oficiais do GitHub no [README](../../README.pt-BR.md) usam HTTPS; exclusividade do canal não foi auditada. |
| OSPS-BR-03.02 | Pendente | Não há avaliação registrada do transporte do canal de distribuição. |
| OSPS-BR-07.01 | Parcial | CI executa imagem Gitleaks pinada no histórico e um guard de mudanças; não está estabelecida prevenção de todo commit de segredo não criptografado. |
| OSPS-DO-01.01 | Parcial | [Início rápido](../product/QUICKSTART.pt-BR.md), [trials](../../ai-development-framework/docs/trials.pt-BR.md) e [boundary](../product/BOUNDARY.pt-BR.md) cobrem fluxos centrais; não foi auditada a completude para toda feature lançada. |
| OSPS-DO-02.01 | Adotado | [Guia de contribuição](../../CONTRIBUTING.pt-BR.md) e template GitHub de bug descrevem o reporte de defeitos. |
| OSPS-GV-02.01 | Adotado | [Issues](https://github.com/Joaolucas2210/agent-effect-security/issues) e PRs públicos aparecem no repositório público. |
| OSPS-GV-03.01 | Adotado | [CONTRIBUTING](../../CONTRIBUTING.pt-BR.md) explica o processo de contribuição. |
| OSPS-LE-02.01 | Adotado | O código-fonte tem [licença MIT](../../LICENSE). |
| OSPS-LE-02.02 | Pendente | Licença de cada asset publicado em release não foi conferida. |
| OSPS-LE-03.01 | Adotado | [LICENSE](../../LICENSE) está na raiz do código-fonte. |
| OSPS-LE-03.02 | Pendente | Inclusão da licença junto de cada asset de release não foi conferida. |
| OSPS-QA-01.01 | Adotado | O [repositório público](https://github.com/Joaolucas2210/agent-effect-security) é legível em URL HTTPS estável. |
| OSPS-QA-01.02 | Adotado | O repositório público expõe histórico Git com autoria e data. |
| OSPS-QA-02.01 | Adotado | Dependências Python diretas estão em [`pyproject.toml`](../../ai-development-framework/pyproject.toml) e pins de teste em [`requirements-test.txt`](../../ai-development-framework/requirements-test.txt). |
| OSPS-QA-04.01 | N/A | O ADF é apresentado como um único repositório; nenhum codebase oficial separado foi declarado. Reavaliar se mudar. |
| OSPS-QA-05.01 | Adotado | Nenhum formato binário executável gerado foi encontrado entre arquivos versionados neste checkout. Repetir no release. |
| OSPS-QA-05.02 | Parcial | O GIF de demo e o PNG social têm [geradores e proveniência](../assets/README.pt-BR.md); revisão completa dos assets binários não foi feita. |
| OSPS-VM-02.01 | Adotado | [SECURITY](../../SECURITY.pt-BR.md) informa canal privado do GitHub e metas de resposta. |

## Controles selecionados do Nível 2

| Controle | Estado | Evidência ou lacuna |
| --- | --- | --- |
| OSPS-AC-04.01 | Parcial | O job de gates usa `contents: read`; permissões padrão de todos os workflows não foram auditadas. |
| OSPS-BR-02.01 | Adotado | [`VERSION`](../../VERSION) e [CHANGELOG](../../CHANGELOG.md) identificam o release 0.1.0 neste checkout. |
| OSPS-BR-04.01 | Parcial | O changelog registra mudanças; completude para todos os assets de release não foi conferida. |
| OSPS-BR-06.01 | Pendente | Nenhum manifesto assinado de release ou inventário assinado de assets foi verificado. |
| OSPS-DO-07.01 | Adotado | [Início rápido](../product/QUICKSTART.pt-BR.md) e [CONTRIBUTING](../../CONTRIBUTING.pt-BR.md) trazem requisitos e comandos de build. |
| OSPS-SA-03.01 | Parcial | [ADR 0026](../../ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md) e [cobertura de incidentes](../knowledge/coverage.md) avaliam ameaças prováveis; não se alega avaliação independente. |
| OSPS-VM-01.01 / VM-03.01 | Adotado | [SECURITY](../../SECURITY.pt-BR.md) define metas de divulgação coordenada e rota privada de reporte. |

## Próxima verificação

O mantenedor deve inspecionar as configurações de MFA/colaboradores e branches no GitHub, permissões de todos os workflows, assets de release e a rota privada de reporte no repositório ativo. Registre data e evidência antes de elevar qualquer controle pendente. Não infira conformidade do badge de CI nem desta tabela.
