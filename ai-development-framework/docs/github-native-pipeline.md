# GitHub-native pipeline

Install the core workflows with `make ci`, then commit the generated root
`.github/workflows/*.yml`. The versions under `ai-development-framework/.github/` are the
source of truth; regenerate root copies instead of editing them.

```text
Issue + agent:spec or /agent proceed
  → draft Spec PR
  → /approve-plan by an authorized repository actor
  → merge Spec PR
  → draft Implementation PR
  → /agent implement
  → Builder work, quality gates, reviews, /ship
```

The workflow creates only the small docs skeletons. It never claims to implement a feature or
make an architectural decision. The command check establishes repository association, not human
identity; repository rules and reviewers retain the human approval/taste boundary.

## Controls

- Workflow writes are limited to the three pipeline jobs; ordinary gates have `contents: read`.
- A separate trusted `workflow_run` workflow validates the gate-run artifact before posting the
  actual token/success/cost/switch summary; it never checks out untrusted PR code.
- Commands are accepted only from `OWNER`, `MEMBER`, or `COLLABORATOR` commenters.
- The gate rejects more than 30 changed files, `.env`/key material, and obvious private-key or
  AWS-access-key additions. It also runs quality gates, MCP/skill/graph audits, Ponytail review,
  and an observability summary.
- There is no new MCP server or runtime dependency. GitHub-hosted `gh` and `GITHUB_TOKEN` are
  used with job-level least-privilege permissions.

## Required repository settings

This workflow cannot protect its own YAML or a PR's checked-out gate code. Repository
maintainers must require pull-request review with stale-review dismissal and CODEOWNERS/ruleset
protection for `.github/workflows/**`, `ai-development-framework/hooks/**`,
`ai-development-framework/skills/**`, `Makefile`, and policy docs. Choose the real team or
users in repository settings; the framework intentionally does not invent an owner allowlist.

For model token/cost data, record it from the agent runtime using `make observability-complete`.
GitHub Actions cannot infer provider token accounting and reports it as `na`.
