# OSPS Baseline 2026.08.28: evidence-led self-assessment

**English** · [Português (Brasil)](OSPS-BASELINE-2026-08-28.pt-BR.md)

Assessment date: 2026-11-04. Source: [OpenSSF OSPS Baseline, version 2026.08.28](https://baseline.openssf.org/versions/2026-08-28). This is a **local self-assessment**, not an OpenSSF badge, certification or claim of full conformance. “Adopted” means the stated repository artifact was inspected; it does not assert unobserved GitHub settings. “Partial” means useful evidence exists but the full control has not been verified. “Pending” means no adequate evidence here. “N/A” gives a reason. Level 1 is assessed control by control; selected Level 2 controls are listed as voluntary improvements for this single-maintainer project.

## Level 1 controls

| Control | State | Evidence or gap |
| --- | --- | --- |
| OSPS-AC-01.01 | Pending | Repository collaborator MFA enforcement is a GitHub setting; not visible in this checkout. |
| OSPS-AC-02.01 | Pending | Default collaborator permissions were not inspected. |
| OSPS-AC-03.01 | Pending | Branch rules preventing direct commits to `main` were not inspected. CI alone is not a branch rule. |
| OSPS-AC-03.02 | Pending | Primary-branch deletion protection was not inspected. |
| OSPS-BR-01.01 | Partial | [Workflow guard](../../.github/workflows/ci.yml) validates changed-file count and paths; all untrusted issue/PR metadata uses need review. |
| OSPS-BR-01.03 | Partial | Gates job requests `contents: read` and checkout disables persisted credentials; all jobs and event paths still need a privileged-asset review. |
| OSPS-BR-03.01 | Partial | Official GitHub links in [README](../../README.md) use HTTPS; exclusive channel delivery was not audited. |
| OSPS-BR-03.02 | Pending | No release-channel transport assessment was recorded. |
| OSPS-BR-07.01 | Partial | CI runs a pinned Gitleaks image over history and a change guard; prevention of every unencrypted secret commit is not established. |
| OSPS-DO-01.01 | Partial | [Quickstart](../product/QUICKSTART.md), [trials](../../ai-development-framework/docs/trials.md) and [boundary](../product/BOUNDARY.md) cover core flows; completeness across every released feature was not audited. |
| OSPS-DO-02.01 | Adopted | [Contribution guide](../../CONTRIBUTING.md) and GitHub bug-report template describe defect reporting. |
| OSPS-GV-02.01 | Adopted | Public [Issues](https://github.com/Joaolucas2210/agent-effect-security/issues) and PRs are listed on the public repository. |
| OSPS-GV-03.01 | Adopted | [CONTRIBUTING](../../CONTRIBUTING.md) explains the contribution process. |
| OSPS-LE-02.01 | Adopted | Source has an [MIT license](../../LICENSE). |
| OSPS-LE-02.02 | Pending | Licensing of every published release asset was not checked. |
| OSPS-LE-03.01 | Adopted | [LICENSE](../../LICENSE) is in the source root. |
| OSPS-LE-03.02 | Pending | License inclusion alongside each release asset was not checked. |
| OSPS-QA-01.01 | Adopted | [Public source repository](https://github.com/Joaolucas2210/agent-effect-security) is readable at a stable HTTPS URL. |
| OSPS-QA-01.02 | Adopted | The public repository exposes Git history with author and date. |
| OSPS-QA-02.01 | Adopted | Direct Python dependencies are in [`pyproject.toml`](../../ai-development-framework/pyproject.toml) and test pins in [`requirements-test.txt`](../../ai-development-framework/requirements-test.txt). |
| OSPS-QA-04.01 | N/A | ADF is presented here as one project repository; no separate official codebase is declared. Reassess if that changes. |
| OSPS-QA-05.01 | Adopted | No generated executable binary format was found among tracked files in this checkout. Recheck at release. |
| OSPS-QA-05.02 | Partial | The demo GIF and social PNG have [generators and provenance](../assets/README.md); a complete binary-asset review was not done. |
| OSPS-VM-02.01 | Adopted | [SECURITY](../../SECURITY.md) names the private GitHub reporting channel and response targets. |

## Selected Level 2 controls

| Control | State | Evidence or gap |
| --- | --- | --- |
| OSPS-AC-04.01 | Partial | The gates job uses `contents: read`; permission defaults across all workflows were not audited. |
| OSPS-BR-02.01 | Adopted | [`VERSION`](../../VERSION) and [CHANGELOG](../../CHANGELOG.md) identify the 0.1.0 release in this checkout. |
| OSPS-BR-04.01 | Partial | The changelog records changes; completeness against every release asset was not checked. |
| OSPS-BR-06.01 | Pending | No signed release manifest or signed asset inventory was verified. |
| OSPS-DO-07.01 | Adopted | [Quickstart](../product/QUICKSTART.md) and [CONTRIBUTING](../../CONTRIBUTING.md) give build requirements and commands. |
| OSPS-SA-03.01 | Partial | [ADR 0026](../../ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md) and [incident coverage](../knowledge/coverage.md) assess likely threats; no independent assessment is claimed. |
| OSPS-VM-01.01 / VM-03.01 | Adopted | [SECURITY](../../SECURITY.md) sets coordinated disclosure targets and a private reporting path. |

## Next verification

A maintainer should inspect GitHub MFA/collaborator and branch settings, all workflow permissions, release assets and the private reporting route in the live repository. Record date and evidence before upgrading any pending control. Do not infer compliance from the CI badge or this table.
