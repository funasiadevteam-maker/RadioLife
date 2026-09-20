#!/usr/bin/env bash
# FUUSIC brand-drift guard — fails if the legacy consumer brand "RadioLife"
# (any branded capitalisation) creeps back into the UI. The lowercase
# technical variant key `radiolife` and the legacy `design_radiolife/`
# screens are intentionally allowed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PATTERN='RadioLife|RADIOLIFE|Radio Life|RADIO LIFE'
# UI surfaces only — backend has legitimate migration/infra references
# (e.g. games_v2 brand migration, mailgun infra) that must not trip the guard.
TARGETS=(frontend/src mobile/app mobile/src)

# Only scan files that exist; exclude the legacy variant + tests + node_modules.
HITS=$(grep -rInE "$PATTERN" "${TARGETS[@]}" 2>/dev/null \
  | grep -vE '/design_radiolife/|/node_modules/|/tests/|/__tests__/' \
  || true)

if [[ -n "$HITS" ]]; then
  echo "❌ FUUSIC brand-drift guard: legacy 'RadioLife' brand text found."
  echo "   Use the central brand config (config/brand) instead of hardcoding."
  echo "   (Allowed: lowercase 'radiolife' variant key, design_radiolife/ screens.)"
  echo "-------------------------------------------------------------------"
  echo "$HITS"
  exit 1
fi

echo "✅ FUUSIC brand-drift guard: no legacy brand text in the UI."
