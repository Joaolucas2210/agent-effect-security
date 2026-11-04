# Knowledge base

Records that feed architecture decisions and public positioning. Governed by
[ADR 0035](../../ai-development-framework/docs/architecture-decision-records/0035-knowledge-base-as-decision-input.md);
the reference model is [ADR 0026](../../ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md).
English only; these are records, not user-facing documents, so they have no pt-BR sibling.

| Folder | Id | Content |
| --- | --- | --- |
| [threats/](threats/README.md) | `THR-NN` | Abstract threat classes ADF decides about |
| [incidents/](incidents/) | `INC-NN` | Real cases, one file each, with ADF status and eval id |
| [papers/](papers/README.md) | `PAP-NN` | Papers and surveys, with why each matters for ADF |
| [coverage.md](coverage.md) | — | The single table used in public material |

Rules: an ADR that adds an effect or moves the boundary cites ≥ 1 `THR-`. An `INC-` marked `covered` names a
green eval. ⚠ marks an unverified CVE id or date: not citable publicly until verified.

Status vocabulary: `covered` (ADF denies or proves it on a covered edge, eval green) · `residual` (ADF sees
part of the path; documented gap) · `out_of_scope` (outside the ADR 0026 boundary by design).
