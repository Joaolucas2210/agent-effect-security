# Como fazer um release do ADF

[English](RELEASING.md) · **Português (Brasil)**

Este é o checklist do mantenedor para um release, e em especial para o primeiro público. A parte 1 é mecânica e
qualquer pessoa pode rodá-la. A parte 2 lista as decisões que cabem a um humano: a regra do projeto é que agentes
propõem e o mantenedor decide arquitetura, escopo, histórico e publicação.

## 1. Verificar a árvore

Rode no commit exato que vai receber a tag, a partir de um clone limpo:

```bash
make install-dev
make quality-check          # todos os self-tests e gates de stack (42 no 0.1.0); skips aparecem listados, nunca verdes
make eval-required          # cobertura de eval do diff
make e2e                    # clone novo, venv nova, CLI adf, as duas bordas, os dois trials, checagens de higiene
make a2a-live-trial TRIAL_ID="release-$(date -u +%Y%m%dT%H%M%SZ)"   # guarde o relatório redigido como evidência do release
bash ai-development-framework/hooks/test-docs.sh   # links, âncoras, paridade inglês/português
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.18.4 detect --source /repo --config /repo/.gitleaks.toml --log-opts=--all --redact --no-banner
```

Skips conhecidos no 0.1.0: cobertura JavaScript, `madge` e `stryker` da fixture `sandbox/`. São reportados como
skipped por desenho e não dizem nada sobre o control plane em Python.

## 2. Decisões humanas antes de abrir o repositório

| # | Decisão | Por que é sua | Como |
| --- | --- | --- | --- |
| 1 | Aceitar ou rejeitar as ADRs 0010, 0011, 0012, 0023, 0024, 0025 | Feito para o 0.1.0: o mantenedor aceitou as seis em 2026-10-21. Um leitor público lê o status como verdade, então uma ADR futura `Proposed` da qual o código depende bloqueia o release | Editar a linha de status, mantendo o texto anterior |
| 2 | Reescrever o histórico ou publicar um repositório novo | Decidido para o 0.1.0: repositório novo. Commits antigos do repositório privado ainda têm dois nomes de projeto anonimizados e um caminho de home (7 caminhos, 2 corpos de commit) | Veja [Histórico](#histórico) |
| 3 | Aceitar o resultado da varredura de segredos | Feita em 2026-10-21 em 48 branches e 220 commits: o trufflehog achou 0 segredos verificados e 0 não verificados em 2.164 chunks; o gitleaks achou só o valor de contrato `bearer_jwt_hs256`, agora na allowlist do `.gitleaks.toml`. O CI roda o gitleaks em todo PR. Uma varredura acha padrões conhecidos; não prova ausência | Rodar de novo a linha do gitleaks da parte 1 no commit do release |
| 4 | Nome do repositório | Decidido para o 0.1.0: `agent-effect-security`, um repositório público novo; toda URL pública aponta para ele | Num rename futuro, atualizar as URLs em README, SECURITY, CONTRIBUTING, ONEPAGER, CITATION.cff, CHANGELOG e issue forms |
| 5 | Um contato público para o Código de Conduta | O CoC aponta para o contato no perfil do GitHub do mantenedor | Colocar um e-mail público no perfil ou um endereço dedicado no CODE_OF_CONDUCT |
| 6 | Configurações do repositório | Configurações não ficam no git | Descrição e topics; proteção do `main` exigindo `gates` e `e2e`; reporte privado de vulnerabilidades; secret scanning com push protection; alertas do Dependabot; CodeQL default setup |
| 7 | Apagar branches antigas | Apagar é irreversível para quem não tem cópia local. Em 2026-10-21, 36 de 40 branches remotas tinham todos os arquivos alterados idênticos no `main`; `feat/adr-0008-pep-local-read-runtime` guarda uma proposta superada da ADR 0008 | Rodar a [checagem de branches](#checagem-de-branches), revisar a lista e então apagar |
| 8 | Data e tag do release | Decidido para o 0.1.0: 2026-06-04, o primeiro commit do projeto | Criar a tag `v0.1.0` no commit publicado e o GitHub Release a partir da entrada do CHANGELOG |
| 9 | Mudar a visibilidade | Na prática irreversível: forks e caches guardam o que foi público | Só depois de 1 a 8 |

### Histórico

Todo commit fica público junto com o repositório. Duas opções:

- **Repositório novo (escolhido para o 0.1.0).** Crie um repositório público vazio e publique a árvore de release do
  `main` como três commits de importação. Três, não um: o pilot de evidência do CI lê `HEAD`, `HEAD~1` e `HEAD~2`, e o
  guard de mudança no push mede só o último commit, que precisa ficar abaixo de 30 arquivos. O repositório privado
  guarda o histórico completo.

  ```bash
  git -C <clone-privado> fetch origin && tree=$(git -C <clone-privado> rev-parse origin/main^{tree})
  mkdir adf-public && git -C <clone-privado> archive "$tree" | tar -x -C adf-public && cd adf-public && git init -q -b main
  export GIT_AUTHOR_NAME="<nome>" GIT_AUTHOR_EMAIL="<id>+<usuario>@users.noreply.github.com"
  export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"   # nunca um e-mail pessoal ou de trabalho
  meta="README.md README.pt-BR.md CONTRIBUTING.md CONTRIBUTING.pt-BR.md SECURITY.md SECURITY.pt-BR.md CODE_OF_CONDUCT.md CODE_OF_CONDUCT.pt-BR.md"
  git add -A -f . && git reset -q -- $meta CHANGELOG.md CITATION.cff .gitleaks.toml docs .github ai-development-framework/docs
  git commit -qm "Import the ADF 0.1.0 control plane"
  git add -A -f $meta docs ai-development-framework/docs && git commit -qm "Add the documentation, English first with Portuguese siblings"
  git add -A -f . && git commit -qm "Add CI, community health files and release checks"
  [ "$(git rev-parse HEAD^{tree})" = "$tree" ] && echo "árvore idêntica ao main"   # -f: alguns caminhos versionados estão no gitignore
  docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.18.4 detect --source /repo --config /repo/.gitleaks.toml --log-opts=--all --redact --no-banner
  make e2e                                       # no snapshot, antes do primeiro push
  git remote add origin git@github.com:<usuario>/<repo-novo>.git && git push -u origin main
  ```
- **Reescrever no lugar.** Num clone espelho, nunca no seu clone de trabalho:

  ```bash
  git clone --mirror git@github.com:<usuario>/<repo-privado>.git adf-mirror.git && cd adf-mirror.git
  $EDITOR ../replacements.txt   # uma linha 'antigo==>novo' por nome a remover; mantenha este arquivo fora de qualquer repositório
  git filter-repo --replace-text ../replacements.txt --replace-message ../replacements.txt \
    --path-rename <old-research-note-path>:ai-development-framework/docs/research/2026-10-04-external-validation.md
  git log --all -S '<nome antigo>' --oneline | wc -l   # esperado 0 para cada nome
  git push --force --mirror                     # reescreve todas as branches e tags; colaboradores precisam clonar de novo
  ```

  Reescrever muda o SHA de todo commit: links para commits e pull requests antigos nas docs param de resolver.

### Checagem de branches

Uma branch pode ser apagada quando todo arquivo que ela alterou já está idêntico, byte a byte, no `main` (squash
merge não deixa ancestralidade para comparar). A checagem é conservadora: uma mudança posterior no `main` faz uma
branch parecer não absorvida, nunca o contrário.

```bash
git fetch --prune origin
for b in $(git branch -r --format='%(refname:lstrip=3)' | grep -v -x -e HEAD -e main); do
  files=$(git diff --name-only origin/main...origin/$b)
  [ -z "$files" ] || [ -z "$(git diff origin/main origin/$b -- $files)" ] && echo "$b"
done                                   # revise a lista e então: git push origin --delete <branch> ...
```

## 3. Publicar

1. Ponha a data no `CHANGELOG.md`, faça o merge e crie a tag no commit de merge: `git tag -s v0.1.0 -m "ADF 0.1.0"`.
2. Envie a tag e crie o GitHub Release a partir da entrada do CHANGELOG. Anexe o relatório redigido do trial A2A.
3. Atualize `VERSION` e `ai-development-framework/pyproject.toml` juntos para o próximo ciclo; o `test-packaging.sh`
   confere que batem.
