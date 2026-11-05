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

Three workflows, split by what they may write:

| Workflow | Runs on | Permissions | State |
| --- | --- | --- | --- |
| `ci.yml` — quality gates, fresh-clone e2e, gitleaks | PR, push to `main`, manual | `contents: read` only | active once merged |
| `agentic-automation.yml` — the Spec/Implementation PR flow below | labels, commands, merged Spec PRs | job-level `contents`/`issues`/`pull-requests: write` | inert until the owner sets the Actions variable `ADF_AGENTIC_AUTOMATION=true` |
| `post-observability.yml` — posts the validated `ci` summary on the PR | `workflow_run` of `ci` | `actions: read`, `pull-requests: write`; never checks out PR code | owner enables it |
| `maintenance-routines.yml` — scheduled Maintainer loops, `DRY_RUN=1` | schedule, manual | `contents: read` | owner enables it |

`hooks/test-workflow-permissions.sh` fails if `ci.yml` gains a write scope or a secret, or if an
automation job's condition is not wholly guarded by the opt-in variable.

The automation creates only the small docs skeletons. It never claims to implement a feature or
make an architectural decision. The command check establishes repository association, not human
identity; repository rules and reviewers retain the human approval/taste boundary.

## Controls

- Workflow writes are limited to `agentic-automation.yml` and the PR comment poster; gates have `contents: read`.
- A separate trusted `workflow_run` workflow validates the gate-run artifact before posting the
  actual token/success/cost/switch summary; it never checks out untrusted PR code.
- Commands are accepted only from `OWNER`, `MEMBER`, or `COLLABORATOR` commenters.
- The `ci` gate rejects more than 30 changed files, `.env`/key material, and obvious private-key or
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
