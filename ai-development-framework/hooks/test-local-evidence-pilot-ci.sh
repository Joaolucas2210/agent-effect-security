#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$ROOT/.github/workflows/quality-gates.yml"
for workflow in "$TEMPLATE"; do
  checkout="$(grep -nE 'uses: actions/checkout@[0-9a-f]{40} # v4' "$workflow" | head -1 | cut -d: -f1)"  # pinned by commit SHA
  preflight="$(grep -n 'name: Verify pilot history prerequisites' "$workflow" | cut -d: -f1)"
  guard="$(grep -n 'name: Change safety guard' "$workflow" | cut -d: -f1)"
  pilot="$(grep -n 'name: Run local evidence pilot' "$workflow" | cut -d: -f1)"
  [ -n "$checkout" ] && [ -n "$preflight" ] && [ -n "$guard" ] && [ -n "$pilot" ]
  [ "$checkout" -lt "$preflight" ] && [ "$preflight" -lt "$guard" ] && [ "$guard" -lt "$pilot" ]
  pilot_run=$((pilot + 1))
  section="$(sed -n "${checkout},${pilot_run}p" "$workflow")"
  grep -q 'fetch-depth: 0' <<< "$section"
  grep -q 'persist-credentials: false' <<< "$section"
  grep -Fq "HEAD~1^{commit}" <<< "$section"
  grep -Fq "HEAD~2^{commit}" <<< "$section"
  grep -q 'pilot_history_prerequisite_unavailable' <<< "$section"
  grep -q 'exit 1' <<< "$section"
  grep -q 'make local-evidence-pilot' <<< "$section"
  ! grep -Eq 'git fetch|git remote|HEAD~[0-9]+[^\^]' <<< "$(sed -n "${preflight},$((preflight + 5))p" "$workflow")"
  guard_section="$(sed -n "${guard},$((pilot - 1))p" "$workflow")"
  grep -Fq 'base="origin/$BASE_REF"' <<< "$guard_section"
  grep -Fq '"${base}^{commit}"' <<< "$guard_section"
  grep -q 'change_safety_base_ref_unavailable' <<< "$guard_section"
  ! grep -Eq 'git fetch|git remote|https?://|/home|/tmp|runner/work' <<< "$guard_section"
done

echo "✓ local evidence pilot CI history prerequisites"
