# Contributing to ADF

**English** · [Português (Brasil)](CONTRIBUTING.pt-BR.md)

Thanks for helping. ADF is a security control, so the bar is evidence: every change says which market pain it
addresses, which effect it touches, and which residual risk remains.

## Before you start

- Read the [boundary](docs/product/BOUNDARY.md) and the [roadmap](docs/product/ROADMAP.md). Items under
  *Later* and *Not doing* need an accepted ADR and recorded design-partner demand before any code.
- Open an issue first for anything bigger than a small fix. Changes to the authorization boundary (a new effect,
  a new edge, a contract change) need an ADR in
  [`ai-development-framework/docs/architecture-decision-records/`](ai-development-framework/docs/architecture-decision-records/).
- Report vulnerabilities privately, as described in [SECURITY.md](SECURITY.md). Never in a public issue.

## Development setup

Requirements: Git, Make, Python 3.10+ and Bash 4+ (on macOS, Homebrew's `bash` first on `PATH`).

```bash
git clone https://github.com/Joaolucas2210/agent-effect-security.git && cd agent-effect-security
python3 -m venv .venv && source .venv/bin/activate
export ADF_CONTRACTS_PYTHON="$PWD/.venv/bin/python3"
make install-dev          # editable install; creates the `adf` command
adf version
```

## Workflow

1. Issue, then a spec or plan in the PR description, then the implementation. Keep PRs small: the CI change-safety
   guard rejects a PR that touches more than 30 files.
2. Security-sensitive changes are test-first: write the negative test (the deny, the tampered bundle, the
   forged token) and watch it fail before the fix.
3. A new or changed hook, skill or command needs an eval case, a `hooks/test-*.sh` self-test that mentions it, or a
   dated waiver in `ai-development-framework/docs/evals/waivers.md`. `make eval-required` is the gate.
4. Run the gates before pushing:

   ```bash
   make quality-check     # every self-test and stack gate, without persisting eval evidence
   make eval-required     # evaluation coverage of the diff
   ```

   A gate that cannot run is reported as **skipped**, never as passing. Say so in the PR.
5. The PR description answers: market pain, effect, residual risk, gates run (with skips listed).

## Conventions

- **Commits:** Conventional Commits with a scope, as in the history (`feat(pdp): ...`, `fix(eval): ...`,
  `docs(product): ...`). The body explains why, not only what.
- **Code:** the least code that works; stdlib first; no new dependency for what a few lines do. Contracts are
  closed JSON Schemas (`additionalProperties: false`); a new field needs a schema change, a normative oracle and
  a negative test.
- **Evidence and telemetry:** never put file content, absolute paths, tokens or secrets in bundles, records, logs
  or spans. OpenTelemetry is a view, never the authority.
- **Docs:** English is the primary language. A user-facing document has a Portuguese sibling `X.pt-BR.md` with the
  same headings and a language switcher on line 3; the docs self-test checks links, anchors and that parity. ADRs
  are records: new ones are written in English; older Portuguese ADRs carry an English summary.

## License

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
Please follow the [Code of Conduct](CODE_OF_CONDUCT.md).
