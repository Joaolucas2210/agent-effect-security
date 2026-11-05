<!-- ADF is a security control: evidence over claims. "n/a" is a valid answer; a guess is not. See CONTRIBUTING.md. -->

## Why

<!-- The pain this addresses, and the issue or ADR it follows. -->

## Effect and boundary

<!-- Which effect, edge or contract this touches (read, a hook, the PDP, evidence, CI, docs only).
     A change to the authorization boundary needs an ADR. Which residual risk remains? -->

## Gates

| Gate | Result |
| --- | --- |
| `make test` | <!-- pass / fail; list every skipped gate by name --> |
| `make eval-required` | |
| `make e2e` (contracts, hooks, CLI, packaging) | |
| `make demo` (user-facing behaviour) | |

<!-- A gate that could not run is "skipped", never green. Bilingual doc changed? Change X.pt-BR.md in this PR. -->

## Risks and follow-ups
