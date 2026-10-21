# AI Development Framework — task runner
# `make` or `make help` lists targets. Thin wrappers over setup-adf.sh + the framework hooks.
.DEFAULT_GOAL := help
SHELL := /usr/bin/env bash
ADF   := ai-development-framework
PLATFORM ?= claude          # graphify --platform (override: make setup-graphify PLATFORM=codex)
GRAPHIFY_PKG := graphifyy    # ⚠ verify pkg name at https://github.com/safishamsi/graphify

# rtk if present, else raw. ponytail: don't force a dep that may be absent.
RTK := $(shell command -v rtk 2>/dev/null)
RUN := $(if $(RTK),rtk,)
DRY_RUN ?= 1

.PHONY: help setup install-into install-metrics install-dev adf-claude adf-codex adf-cursor setup-graphify check quality quality-check complexity graph-check metrics metrics-snapshot observability-record observability-complete test-observability test-maintenance-routine test-all local-evidence-pilot local-evidence-trial a2a-live-trial local-session-trial rtk-report graph-hit-rate skill-audit mcp-audit routine-dead-code routine-abstractions routine-security routine-graph routine-token-budget routine-governance routine-all eval eval-check eval-agent-flow eval-agent-flow-all eval-required eval-diagnose learn learn-apply test-learn test-loop hooks ci clean-links loop token-budget projects project-enable project-disable project-reasons e2e

help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' \
	  | sort

install-dev: ## Editable local install of the control-plane packages + test deps (never published to PyPI)
	@PYTHON="$${ADF_CONTRACTS_PYTHON:-python3}"; \
	  "$$PYTHON" -m pip install --disable-pip-version-check -e $(ADF) -r $(ADF)/requirements-test.txt \
	  && echo "✓ tools/runtime/integration importable from $$PYTHON (editable, local only)" \
	  || { echo "✗ editable install needs pip ≥ 21.3 (PEP 660); Ubuntu's patched system pip 22.0 rejects it — use a venv: python3 -m venv .venv && . .venv/bin/activate && make install-dev"; exit 1; }

setup: ## Full activation for Claude + Codex + Cursor (links, hooks, Graphify, RTK)
	@./setup-adf.sh all

install-metrics: export DEST := $(DEST)
install-metrics: ## Install clean metrics/trial tooling without replacing host files (DEST=/path)
	@"$${ADF_CONTRACTS_PYTHON:-python3}" $(ADF)/hooks/install-metrics.py

install-into: ## Copy the framework into another project and activate it (DEST=/path[ PLATFORM=all])
	@[ -n "$(DEST)" ] || { echo "✗ DEST required — make install-into DEST=/your/project"; exit 1; }
	@[ -d "$(DEST)" ] || { echo "✗ DEST not a directory: $(DEST)"; exit 1; }
	@[ "$$(cd "$(DEST)" && pwd)" != "$$(pwd)" ] || { echo "✗ DEST is this repo — pick another project"; exit 1; }
	@for item in $(ADF) setup-adf.sh Makefile AGENTS.md; do \
	  [ ! -e "$(DEST)/$$item" ] && [ ! -L "$(DEST)/$$item" ] \
	    || { echo "✗ destination conflict; use install-metrics to preserve host files"; exit 1; }; done
	@echo "▶ installing framework into $(DEST)"
	@cp -r $(ADF) setup-adf.sh Makefile AGENTS.md "$(DEST)/"
	@cd "$(DEST)" && ./setup-adf.sh $(PLATFORM)
	@echo "✓ installed. Next in $(DEST): /graphify .   (build the graph over your code)"

adf-claude: ## Activate framework for Claude Code (.claude/) + Graphify
	@./setup-adf.sh claude

adf-codex: ## Activate framework for Codex (.codex/) + Graphify
	@./setup-adf.sh codex

adf-cursor: ## Activate framework for Cursor (.cursor/commands/) + Graphify
	@./setup-adf.sh cursor

setup-graphify: ## Install (pip) + wire the Graphify skill (PLATFORM=claude|codex). Build the graph in-agent with /graphify .
	@echo "▶ Graphify setup (--platform $(PLATFORM))"
	@command -v graphify >/dev/null 2>&1 || { \
	  echo "  installing $(GRAPHIFY_PKG)"; \
	  (command -v pip >/dev/null 2>&1 && pip install $(GRAPHIFY_PKG)) \
	    || (command -v pip3 >/dev/null 2>&1 && pip3 install $(GRAPHIFY_PKG)) \
	    || echo "  no pip/pip3 — install Python first"; }
	@command -v graphify >/dev/null 2>&1 \
	  && { graphify install --platform $(PLATFORM) \
	       && echo "✓ graphify skill installed for $(PLATFORM)" \
	       && echo "→ build the graph in-agent:  /graphify .   (writes graphify-out/graph.json)"; } \
	  || echo "✗ graphify unavailable — see ai-development-framework/skills/graphify"

check: ## Verify tools (git/graphify/rtk) without changing anything
	@./setup-adf.sh --check

quality: ## Run the full CI quality gates locally (coverage/complexity/mutation/cycles)
	@chmod +x $(ADF)/hooks/ci-quality-gates.sh && $(ADF)/hooks/ci-quality-gates.sh

quality-check: ## Run quality gates without persisting eval evidence
	@chmod +x $(ADF)/hooks/ci-quality-gates.sh && ADF_EVAL_WRITE=0 PYTHONDONTWRITEBYTECODE=1 $(ADF)/hooks/ci-quality-gates.sh

complexity: ## Cyclomatic complexity + function length for shell (report mode: make complexity ARGS=--report)
	@$(ADF)/hooks/shell-complexity.sh $(ARGS)

test-all: ## Run every framework self-test (the contracts `make quality` enforces)
	@rc=0; for t in $(ADF)/hooks/test-*.sh; do \
	  bash "$$t" || { echo "✗ $$t"; rc=1; }; \
	done; status=0; "$${ADF_CONTRACTS_PYTHON:-python3}" $(ADF)/hooks/check-host-deployment.py $(ADF) || status=$$?; \
	[ "$$status" -eq 0 ] || [ "$$status" -eq 77 ] || rc=1; exit $$rc

local-evidence-pilot: ## Run the isolated H4 local evidence pilot and print its verified aggregate
	@PYTHON="$${ADF_CONTRACTS_PYTHON:-python3}"; \
	  "$$PYTHON" $(ADF)/hooks/require_pins.py jsonschema \
	  || exit 1; \
	  $(RUN) "$$PYTHON" $(ADF)/hooks/run-local-evidence-pilot.py

local-evidence-trial: ## P2 design-partner trial: fixed adapter suite (or EVIDENCE_DIR=<adapter evidence dir>) -> redacted aggregate in docs/observability/trials/
	@PYTHON="$${ADF_CONTRACTS_PYTHON:-python3}"; \
	  "$$PYTHON" $(ADF)/hooks/require_pins.py jsonschema \
	  || exit 1; \
	  $(RUN) "$$PYTHON" $(ADF)/hooks/run-local-evidence-trial.py $(if $(EVIDENCE_DIR),--evidence-dir "$(EVIDENCE_DIR)",) $(if $(TRIAL_ID),--trial-id "$(TRIAL_ID)",)

a2a-live-trial: ## Repeatable A2A live trial (hermetic, loopback; AUTH=hs256|rs256) -> redacted report in docs/observability/trials/a2a-live/
	@PYTHON="$${ADF_CONTRACTS_PYTHON:-python3}"; \
	  "$$PYTHON" $(ADF)/hooks/require_pins.py jsonschema \
	  || exit 1; \
	  $(RUN) "$$PYTHON" $(ADF)/hooks/run-a2a-live-trial.py $(if $(TRIAL_ID),--trial-id "$(TRIAL_ID)",) $(if $(AUTH),--auth "$(AUTH)",)

local-session-trial: ## P0-D: project one closed session; requires EVIDENCE_DIR, TRIAL_ID, TASK_ID, SESSION_ID
	@PYTHON="$${ADF_CONTRACTS_PYTHON:-python3}"; \
	  "$$PYTHON" $(ADF)/hooks/require_pins.py jsonschema \
	  || exit 1; \
	  $(RUN) "$$PYTHON" $(ADF)/hooks/run-session-trial.py --evidence-dir "$(EVIDENCE_DIR)" --trial-id "$(TRIAL_ID)" --task-id "$(TASK_ID)" --session-id "$(SESSION_ID)" --agent-name "$(AGENT_NAME)" --agent-version "$(AGENT_VERSION)" --revision-sha "$(REVISION_SHA)" --acceptance-sha256 "$(ACCEPTANCE_SHA256)"

projects: ## REQ-MP-01: list host-enabled projects (~/.adf/enabled-projects) and how the global read hook treats each
	@"$${ADF_CONTRACTS_PYTHON:-python3}" $(ADF)/hooks/adf-projects.py list

project-enable: ## Enable one project for the global ADF read hook: PROJECT=/abs/git/root (canonical path, no ..)
	@"$${ADF_CONTRACTS_PYTHON:-python3}" $(ADF)/hooks/adf-projects.py enable "$(PROJECT)"

project-disable: ## Disable one project: PROJECT=/abs/git/root
	@"$${ADF_CONTRACTS_PYTHON:-python3}" $(ADF)/hooks/adf-projects.py disable "$(PROJECT)"

project-reasons: ## reason_code counts per project and per principal from ~/.adf/evidence (counts only); POLICY=/abs/policy.json adds granted vs unused
	@"$${ADF_CONTRACTS_PYTHON:-python3}" $(ADF)/hooks/adf-projects.py reasons $(if $(POLICY),--policy "$(POLICY)",)

e2e: ## Release check: fresh clone of the committed tree, new venv, adf CLI, both edges, both trials (needs network or a pip cache)
	@bash $(ADF)/e2e/quickstart.sh

graph-check: ## Report if the knowledge graph is stale vs HEAD (tolerates topology-neutral commits)
	@chmod +x $(ADF)/hooks/graph-check.sh && $(ADF)/hooks/graph-check.sh

metrics-snapshot: ## Append this commit's metrics to docs/metrics/history.csv (idempotent per commit)
	@csv="$(ADF)/docs/metrics/history.csv"; \
	commit=$$(git rev-parse --short HEAD); \
	date=$$(git show -s --format=%cs HEAD); \
	report="graphify-out/GRAPH_REPORT.md"; graph=na; \
	if [ -f "$$report" ]; then \
	  built=$$(grep 'Built from commit' "$$report" | grep -oE '[0-9a-f]{7,40}' | head -1); \
	  if [ -n "$$built" ]; then head=$$(git rev-parse --short=$${#built} HEAD); \
	    [ "$$built" = "$$head" ] && graph=fresh || graph=stale; fi; \
	fi; \
	gain=na; command -v rtk >/dev/null 2>&1 && gain=$$(rtk gain 2>/dev/null | grep -oE '\([0-9.]+%\)' | head -1 | tr -d '()'); \
	[ -n "$$gain" ] || gain=na; \
	row="$$date,$$commit,na,na,na,na,$$graph,$$gain"; \
	tmp=$$(mktemp); grep -v ",$$commit," "$$csv" > "$$tmp" || true; mv "$$tmp" "$$csv"; \
	echo "$$row" >> "$$csv"; \
	echo "✓ snapshot: $$row"; \
	echo "  (coverage/mutation/complexity/cycles = na until a stack runner fills them — same honesty as 'make quality')"

metrics: ## Show agent-flow tokens, outcomes, estimated cost, switches, and eval runs
	@$(ADF)/hooks/observability.sh summary

observability-record: ## Record a structured archetype hand-off (TASK=... ARCHETYPE=...)
	@TASK="$(TASK)" ARCHETYPE="$(ARCHETYPE)" PHASE="$(PHASE)" TOKENS_IN="$(TOKENS_IN)" TOKENS_OUT="$(TOKENS_OUT)" BUDGET_REMAINING="$(BUDGET_REMAINING)" DURATION_SECONDS="$(DURATION_SECONDS)" COST_USD="$(COST_USD)" SWITCHED="$(SWITCHED)" TRIGGER="$(TRIGGER)" OUTCOME="$(OUTCOME)" $(ADF)/hooks/observability.sh record

observability-complete: ## Record completion and generate its trajectory (same variables as observability-record)
	@TASK="$(TASK)" ARCHETYPE="$(ARCHETYPE)" PHASE="$(PHASE)" TOKENS_IN="$(TOKENS_IN)" TOKENS_OUT="$(TOKENS_OUT)" BUDGET_REMAINING="$(BUDGET_REMAINING)" DURATION_SECONDS="$(DURATION_SECONDS)" COST_USD="$(COST_USD)" SWITCHED="$(SWITCHED)" TRIGGER="$(TRIGGER)" OUTCOME="$(OUTCOME)" $(ADF)/hooks/observability.sh complete

test-observability: ## Run the focused, dependency-free observability self-test
	@$(ADF)/hooks/test-observability.sh

test-maintenance-routine: ## Run the focused closed-maintenance routine self-test
	@bash $(ADF)/hooks/test-maintenance-routine.sh

rtk-report: ## Save RTK token-savings (global + per-command) to docs/metrics/rtk-report.txt
	@out="$(ADF)/docs/metrics/rtk-report.txt"; \
	if command -v rtk >/dev/null 2>&1; then \
	  { rtk gain; echo; rtk gain --history; } > "$$out" 2>&1 && echo "✓ rtk report → $$out"; \
	else echo "⚠ rtk absent — nothing to report (install RTK to capture token savings)"; fi

graph-hit-rate: ## Report graph-query hit rate from docs/metrics/graph-hits.log (agents append hit/miss)
	@log="$(ADF)/docs/metrics/graph-hits.log"; \
	[ -f "$$log" ] || { echo "⚠ no graph-hits log yet ($$log) — append 'hit' when a task queried the graph before reading big files, 'miss' otherwise"; exit 0; }; \
	hits=$$(grep -c '^hit' "$$log" || true); miss=$$(grep -c '^miss' "$$log" || true); total=$$((hits+miss)); \
	[ "$$total" -gt 0 ] && echo "graph-hit-rate: $$hits/$$total ($$((hits*100/total))%)" || echo "⚠ graph-hits log empty"

skill-audit: ## Audit skills: valid metadata, no broken refs, size/overlap/when-not warnings
	@chmod +x $(ADF)/hooks/skill-audit.sh && $(ADF)/hooks/skill-audit.sh

mcp-audit: ## Audit MCP inventory: allowlist, no broad shell/secrets/lethal-trifecta (mcp/servers.json)
	@chmod +x $(ADF)/hooks/mcp-audit.sh && $(ADF)/hooks/mcp-audit.sh

routine-dead-code: ## Suggest graph-backed dead-code candidates; never deletes code
	@DRY_RUN="$(DRY_RUN)" bash $(ADF)/hooks/maintenance-routine.sh dead-code

routine-abstractions: ## Suggest duplicate/leaky abstraction candidates; never unifies code
	@DRY_RUN="$(DRY_RUN)" bash $(ADF)/hooks/maintenance-routine.sh abstractions

routine-security: ## Run the Maintainer security sweep and strict shared gates
	@DRY_RUN="$(DRY_RUN)" bash $(ADF)/hooks/maintenance-routine.sh security

routine-graph: ## Check graph freshness; DRY_RUN=0 allows Graphify's incremental refresh
	@DRY_RUN="$(DRY_RUN)" bash $(ADF)/hooks/maintenance-routine.sh graph

routine-token-budget: ## Audit RTK/graph cost; DRY_RUN=0 appends the metrics snapshot
	@DRY_RUN="$(DRY_RUN)" bash $(ADF)/hooks/maintenance-routine.sh token-budget

routine-governance: ## Run the strict Skill and MCP governance audits
	@DRY_RUN="$(DRY_RUN)" bash $(ADF)/hooks/maintenance-routine.sh governance

routine-all: ## Run every closed maintenance loop in safe suggest-only mode
	@for routine in security graph token-budget governance dead-code abstractions; do \
	  $(MAKE) -s routine-$$routine DRY_RUN="$(DRY_RUN)" || exit $$?; \
	done

eval: ## Evaluation-Driven Development in one command: every case + eval coverage of the diff + diagnosis
	@chmod +x $(ADF)/hooks/eval-agent-flow.sh $(ADF)/hooks/eval-required.sh $(ADF)/hooks/eval-diagnose.sh
	@rc=0; $(ADF)/hooks/eval-agent-flow.sh --all || rc=1; \
	$(ADF)/hooks/eval-required.sh || rc=1; \
	$(ADF)/hooks/eval-diagnose.sh; \
	echo "▶ evals done — proposals in docs/traces/proposals, metrics in 'make metrics'"; exit $$rc

eval-check: ## Run eval gates without persisting results, events, traces, or proposals
	@chmod +x $(ADF)/hooks/eval-agent-flow.sh $(ADF)/hooks/eval-required.sh $(ADF)/hooks/eval-diagnose.sh
	@rc=0; ADF_EVAL_WRITE=0 $(ADF)/hooks/eval-agent-flow.sh --all || rc=1; \
	ADF_EVAL_WRITE=0 $(ADF)/hooks/eval-required.sh || rc=1; \
	ADF_EVAL_WRITE=0 $(ADF)/hooks/eval-diagnose.sh; \
	echo "▶ eval-check done — eval persistence suppressed"; exit $$rc

eval-agent-flow: export CASE := $(CASE)
eval-agent-flow: ## Run one agent-flow eval case (CASE=sum-bug): objective gate + trajectory + record to docs/evals/results.csv
	@chmod +x $(ADF)/hooks/eval-agent-flow.sh && $(ADF)/hooks/eval-agent-flow.sh "$${CASE:-sum-bug}"

eval-agent-flow-all: ## Run every fixture case (doesn't abort on a failing case) — refreshes all rows in results.csv
	@chmod +x $(ADF)/hooks/eval-agent-flow.sh && $(ADF)/hooks/eval-agent-flow.sh --all

eval-required: ## EDD gate: every changed skill/command/hook needs an eval, a self-test, or a dated waiver (BASE=<ref>)
	@chmod +x $(ADF)/hooks/eval-required.sh && BASE="$(BASE)" $(ADF)/hooks/eval-required.sh

eval-diagnose: ## Diagnose recurring eval failures → improvement-proposal stubs in docs/traces/proposals
	@chmod +x $(ADF)/hooks/eval-diagnose.sh && $(ADF)/hooks/eval-diagnose.sh

learn: ## Learning loop: recorded failures → improvement-proposal stubs (suggest-only, nothing applied)
	@chmod +x $(ADF)/hooks/eval-diagnose.sh $(ADF)/hooks/learn.sh
	@$(ADF)/hooks/eval-diagnose.sh
	@$(ADF)/hooks/learn.sh

learn-apply: ## Open a PR carrying the filled proposals (never commits to main; needs gh)
	@$(ADF)/hooks/learn-apply.sh

test-learn: ## Self-test the learning loop (aggregation, recurrence, filename safety, no-clobber)
	@chmod +x $(ADF)/hooks/test-learn.sh && $(ADF)/hooks/test-learn.sh

hooks: ## (Re)install the git pre-commit hook
	@chmod +x $(ADF)/hooks/*.sh $(ADF)/hooks/pre-commit \
	  && ln -sf ../../$(ADF)/hooks/pre-commit .git/hooks/pre-commit \
	  && echo "✓ pre-commit installed"

ci: ## Install the canonical GitHub-native pipeline at .github/workflows/ (repo root)
	@mkdir -p .github/workflows \
	  && cp $(ADF)/.github/workflows/*.yml .github/workflows/ \
	  && echo "✓ workflows installed from $(ADF)/.github/workflows/"

test-loop: ## Smoke-test the framework loop (graph build + gates + observability + rtk gain)
	@echo "▶ 1/4 rebuild graph"; command -v graphify >/dev/null 2>&1 && graphify build || echo "  (graphify absent — skipped)"
	@echo "▶ 2/4 quality gates"; $(MAKE) -s quality
	@echo "▶ 3/4 observability"; $(MAKE) -s test-observability
	@echo "▶ 4/4 token savings"; $(if $(RTK),rtk gain || echo "  (rtk gain unavailable — skipped)",echo "  (rtk absent — skipped)")
	@echo "✓ loop OK — now drive /spec → /plan → /build → /test → /review → /ship in your agent"

loop: ## List archetype modes. Enter one with: make loop-<archetype|phase> (e.g. loop-sweeper, loop-optimization)
	@echo "▶ archetype loops (Cherny) — enter with 'make loop-<name>':"
	@echo "  prototyper   (exploration)   explore fast, high churn"
	@echo "  builder      (implementation) prototype → production, gates hard"
	@echo "  sweeper      (optimization)   delete/simplify, RTK + Graphify auto"
	@echo "  grower       (growth)         iterate on real metrics"
	@echo "  maintainer   (maintenance)    security, reliability, scale"
	@echo "  meta                          route an unclear task (archetype-orchestrator)"

loop-%: ## (loop-<archetype|phase>) enter an archetype mode: print its loops/*.md context
	@a="$*"; case "$$a" in \
	  exploration) a=prototyper;; implementation) a=builder;; optimization) a=sweeper;; \
	  growth) a=grower;; maintenance) a=maintainer;; esac; \
	  f="loops/$$a.md"; \
	  [ -f "$$f" ] || { echo "✗ unknown loop '$*' — see 'make loop'"; exit 1; }; \
	  echo "▶ entering $$a loop — load this context into the agent:"; echo; cat "$$f"

token-budget: ## Long-workflow token health: rtk gain + graph-hit-rate in one view
	@echo "▶ token budget (long-workflow health)"; \
	if command -v rtk >/dev/null 2>&1; then echo "— rtk gain —"; rtk gain 2>/dev/null || echo "  (rtk gain unavailable)"; \
	else echo "  rtk absent — install RTK to measure output compression"; fi
	@echo "— graph hit rate —"; $(MAKE) -s graph-hit-rate

clean-links: ## Remove framework symlinks from .claude/ and .codex/
	@for l in .claude/agents .claude/commands .claude/skills .codex/agents; do \
	  [ -L "$$l" ] && rm -f "$$l" && echo "removed $$l" || true; done
	@echo "✓ per-item .codex/.cursor links left intact (remove manually if needed)"
