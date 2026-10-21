# Releasing ADF

**English** · [Português (Brasil)](RELEASING.pt-BR.md)

This is the maintainer's checklist for a release, and for the first public one in particular. Part 1 is mechanical
and anyone can run it. Part 2 lists the decisions that belong to a human: the project's rule is that agents propose
and the maintainer decides architecture, scope, history and publication.

## 1. Verify the tree

Run on the exact commit you will tag, from a clean clone:

```bash
make install-dev
make quality-check          # every self-test and stack gate (42 at 0.1.0); skips are listed, never green
make eval-required          # evaluation coverage of the diff
make e2e                    # fresh clone, new venv, adf CLI, both edges, both trials, hygiene checks
make a2a-live-trial TRIAL_ID="release-$(date -u +%Y%m%dT%H%M%SZ)"   # keep the redacted report as release evidence
bash ai-development-framework/hooks/test-docs.sh   # links, anchors, English/Portuguese parity
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.18.4 detect --source /repo --config /repo/.gitleaks.toml --log-opts=--all --redact --no-banner
```

Known skips at 0.1.0: JavaScript coverage, `madge` and `stryker` for the `sandbox/` fixture. They are reported as
skipped by design and say nothing about the Python control plane.

## 2. Human decisions before going public

| # | Decision | Why it is yours | How |
| --- | --- | --- | --- |
| 1 | Accept or reject ADRs 0010, 0011, 0012, 0023, 0024, 0025 | Done for 0.1.0: the maintainer accepted all six on 2026-10-21. A public reader reads status as truth, so a future `Proposed` ADR that the code relies on blocks a release | Edit each status line, keeping the previous wording |
| 2 | Rewrite history, or publish a fresh repository | Decided for 0.1.0: a fresh repository. Older commits of the private repository still carry two anonymized project names and a home path (7 paths, 2 commit bodies) | See [History](#history) |
| 3 | Accept the secret-scan result | Done on 2026-10-21 over 48 branches and 220 commits: trufflehog found 0 verified and 0 unverified secrets in 2,164 chunks; gitleaks found only the contract value `bearer_jwt_hs256`, now allowlisted in `.gitleaks.toml`. CI runs gitleaks on every PR. A scan finds known patterns; it is not proof of absence | Re-run the gitleaks line of part 1 on the release commit |
| 4 | Repository name | Decided for 0.1.0: `agent-effect-security`, a fresh public repository; every public URL points to it | For a future rename, update the URLs in README, SECURITY, CONTRIBUTING, ONEPAGER, CITATION.cff, CHANGELOG and the issue forms |
| 5 | A public contact for the Code of Conduct | The CoC points to the contact on the maintainer's GitHub profile | Add a public email to the profile, or a dedicated address in CODE_OF_CONDUCT |
| 6 | Repository settings | Settings are not in git | Description and topics; branch protection on `main` requiring `gates` and `e2e`; private vulnerability reporting; secret scanning with push protection; Dependabot alerts; CodeQL default setup |
| 7 | Delete stale branches | Deleting is irreversible for anyone without a local copy. On 2026-10-21, 36 of 40 remote branches had every changed file identical in `main`; `feat/adr-0008-pep-local-read-runtime` holds a superseded ADR 0008 proposal | Run the [branch check](#branch-check), review its list, then delete |
| 8 | Release date and tag | Decided for 0.1.0: 2026-06-04, the project's first commit | Tag `v0.1.0` on the published commit and create the GitHub Release from the CHANGELOG entry |
| 9 | Flip visibility | Irreversible in practice: forks and caches keep what was public | Only after 1 to 8 |

### History

Every commit is public once the repository is. Two options:

- **Fresh repository (chosen for 0.1.0).** Create an empty public repository, then publish the release tree of
  `main` as three import commits. Three, not one: the CI evidence pilot reads `HEAD`, `HEAD~1` and `HEAD~2`, and the
  push-time change guard measures only the last commit, which must stay under 30 files. The private repository
  keeps the full history.

  ```bash
  git -C <private-clone> fetch origin && tree=$(git -C <private-clone> rev-parse origin/main^{tree})
  mkdir adf-public && git -C <private-clone> archive "$tree" | tar -x -C adf-public && cd adf-public && git init -q -b main
  export GIT_AUTHOR_NAME="<name>" GIT_AUTHOR_EMAIL="<id>+<user>@users.noreply.github.com"
  export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"   # never a personal or work address
  meta="README.md README.pt-BR.md CONTRIBUTING.md CONTRIBUTING.pt-BR.md SECURITY.md SECURITY.pt-BR.md CODE_OF_CONDUCT.md CODE_OF_CONDUCT.pt-BR.md"
  git add -A -f . && git reset -q -- $meta CHANGELOG.md CITATION.cff .gitleaks.toml docs .github ai-development-framework/docs
  git commit -qm "Import the ADF 0.1.0 control plane"
  git add -A -f $meta docs ai-development-framework/docs && git commit -qm "Add the documentation, English first with Portuguese siblings"
  git add -A -f . && git commit -qm "Add CI, community health files and release checks"
  [ "$(git rev-parse HEAD^{tree})" = "$tree" ] && echo "tree identical to main"   # -f: some tracked paths are gitignored
  docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.18.4 detect --source /repo --config /repo/.gitleaks.toml --log-opts=--all --redact --no-banner
  make e2e                                       # in the snapshot, before the first push
  git remote add origin git@github.com:<user>/<new-repo>.git && git push -u origin main
  ```
- **Rewrite in place.** On a mirror clone, never on your working clone:

  ```bash
  git clone --mirror git@github.com:<user>/<private-repo>.git adf-mirror.git && cd adf-mirror.git
  $EDITOR ../replacements.txt   # one 'old==>new' per line for each name to remove; keep this file out of every repository
  git filter-repo --replace-text ../replacements.txt --replace-message ../replacements.txt \
    --path-rename <old-research-note-path>:ai-development-framework/docs/research/2026-10-04-external-validation.md
  git log --all -S '<old name>' --oneline | wc -l   # expect 0 for each name
  git push --force --mirror                     # rewrites every branch and tag; collaborators must re-clone
  ```

  Rewriting changes every commit SHA: links to old commits and pull requests in docs stop resolving.

### Branch check

A branch is safe to delete when every file it changed is already byte-identical in `main` (squash merges leave no
ancestry to compare). This check is conservative: a later change in `main` makes a branch look unabsorbed, never the
opposite.

```bash
git fetch --prune origin
for b in $(git branch -r --format='%(refname:lstrip=3)' | grep -v -x -e HEAD -e main); do
  files=$(git diff --name-only origin/main...origin/$b)
  [ -z "$files" ] || [ -z "$(git diff origin/main origin/$b -- $files)" ] && echo "$b"
done                                   # review the list, then: git push origin --delete <branch> ...
```

## 3. Publish

1. Set the date in `CHANGELOG.md`, merge it, and tag the merge commit: `git tag -s v0.1.0 -m "ADF 0.1.0"`.
2. Push the tag and create the GitHub Release from the CHANGELOG entry. Attach the redacted A2A trial report.
3. Bump `VERSION` and `ai-development-framework/pyproject.toml` together for the next cycle; `test-packaging.sh`
   checks that they match.
