# Skill Governance

Skills only help when they are specialized, valid, and non-redundant. Extra generic skills
raise context cost and can lower pass rate (SWE-Skills-Bench). This is the contract and the
gate: `make skill-audit` (`hooks/skill-audit.sh`).

## Mandatory metadata

Every `skills/<name>/SKILL.md` frontmatter must have:

| Field | Meaning | Enforcement |
| --- | --- | --- |
| `name` | must equal the directory name | **hard** — audit fails |
| `description` | objective **and** when to use (a "Use for …/when …" clause) | **hard** — audit fails if missing |

Body should also carry:
- **When NOT to use** — the anti-redundancy signal. Currently a **warning** (ratcheting to hard
  once all skills comply), because forcing it retroactively risks filler over signal.
- **Validation / Quality gates** — how you know the skill did its job.

## Audit checks

**Hard (blocks — exit 1):** no `SKILL.md`; missing `name`/`description`; `name` ≠ directory;
broken internal file reference (framework-relative paths only — example paths in code blocks
are ignored).

**Advisory (warns):** file over 80 lines (bloat); no "when NOT to use" guidance; a keyword
appearing in ≥4 skill descriptions (redundancy candidate).

Run against a fixture dir: `hooks/skill-audit.sh sandbox/skill-audit-fixture` (proves it fails).

## Deprecation policy

A generic skill with no measured gain becomes a common rule (`rules/`) or is removed:
1. Audit flags it (persistent keyword overlap, or it duplicates a `rules/*.md`).
2. Check `docs/metrics/` for evidence it changed an outcome. No evidence ⇒ candidate.
3. Fold its unique content into a `rules/` file or a sibling skill; delete the directory.
4. Record the removal in an ADR (`docs/architecture-decision-records/`).

## Not here yet

Behavioral smoke prompts (does the skill produce the expected output when invoked) belong to
the Phase 4 eval loop (`docs/evals/`) — doc-based skills have no runtime, so this audit only
verifies they load and are well-formed.
