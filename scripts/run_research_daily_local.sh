#!/usr/bin/env bash
# Local-only research daily closure: data → evidence → agents → artifact → reader → validation.
set -euo pipefail

RUN_DATE=""
RUNTIME="${RESEARCH_AGENT_RUNTIME:-llm}"
SYMBOLS="${STOCK_LIST:-}"
DOCS_DIR="docs"
REPORTS_DIR="reports"
MARKET="${MARKET_REVIEW_REGION:-}"
RUN_ORIGINAL_ANALYSIS="${RUN_ORIGINAL_ANALYSIS:-0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date) RUN_DATE="$2"; shift 2 ;;
    --runtime) RUNTIME="$2"; shift 2 ;;
    --symbols) SYMBOLS="$2"; shift 2 ;;
    --docs-dir) DOCS_DIR="$2"; shift 2 ;;
    --runtime-reports-dir) REPORTS_DIR="$2"; shift 2 ;;
    --market) MARKET="$2"; shift 2 ;;
    --with-original-analysis) RUN_ORIGINAL_ANALYSIS="1"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$RUN_DATE" ]]; then
  RUN_DATE="${ANALYSIS_RUN_DATE:-$(date +%F)}"
fi

if [[ -x ".venv311/bin/python" ]]; then
  PY="${PYTHON:-.venv311/bin/python}"
elif [[ -x ".venv/bin/python" ]]; then
  PY="${PYTHON:-.venv/bin/python}"
else
  PY="${PYTHON:-python3}"
fi

# The application loads .env itself, but bash does not. Read only the two
# non-secret runner settings so a normal local invocation uses the same
# universe/market as the upstream application.
if [[ -z "$SYMBOLS" || -z "$MARKET" ]]; then
  ENV_RUNNER_SETTINGS="$($PY - <<'PY'
from dotenv import dotenv_values
values = dotenv_values('.env')
print(str(values.get('STOCK_LIST') or ''))
print(str(values.get('MARKET_REVIEW_REGION') or ''))
PY
)"
  ENV_STOCK_LIST="$(printf '%s\n' "$ENV_RUNNER_SETTINGS" | sed -n '1p')"
  ENV_MARKET="$(printf '%s\n' "$ENV_RUNNER_SETTINGS" | sed -n '2p')"
  SYMBOLS="${SYMBOLS:-$ENV_STOCK_LIST}"
  MARKET="${MARKET:-$ENV_MARKET}"
fi
SYMBOLS="${SYMBOLS:-}"
MARKET="${MARKET:-cn}"

echo "== invest-system local research daily =="
echo "date=$RUN_DATE runtime=$RUNTIME symbols=$SYMBOLS python=$PY"
echo "No push, no cloud workflow, no trading action."
export RESEARCH_AGENT_LLM_TIMEOUT_SECONDS="${RESEARCH_AGENT_LLM_TIMEOUT_SECONDS:-90}"
export ANALYSIS_RUN_DATE="$RUN_DATE"

"$PY" scripts/write_local_acceptance.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR" --kind baseline
"$PY" scripts/collect_intelligence_evidence.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR"

if [[ "$RUN_ORIGINAL_ANALYSIS" == "1" ]]; then
  echo "== original-system AI analysis =="
  # The original-analysis refresh is an input snapshot step, not a historical
  # evaluation run. Disable the application's automatic backtest here so a
  # daily report does not re-fetch unrelated historical symbols and stall the
  # evidence pipeline.
  BACKTEST_ENABLED=false "$PY" main.py --stocks "$SYMBOLS" --no-notify --force-run --no-market-review
  # Daily research currently covers A/H/US. Keep the upstream market review,
  # but do not spend time refreshing JP/KR contexts that cannot enter this
  # run's universe or department packs.
  MARKET_REVIEW_REGION=cn,hk,us "$PY" main.py --market-review --no-notify --force-run
fi

"$PY" scripts/build_daily_universe.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR" --symbols "$SYMBOLS" --market "$MARKET"
"$PY" scripts/export_original_analysis_snapshot.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR" --symbols "$SYMBOLS"
"$PY" -m src.macro.official_sources --refresh --fred-only
"$PY" scripts/collect_subject_evidence.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR" --symbols "$SYMBOLS" --market "$MARKET"
"$PY" scripts/fetch_official_event_sources.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR" --symbols "$SYMBOLS"
"$PY" scripts/write_source_health_ledgers.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR"
"$PY" scripts/run_daily_department_agents.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR" --runtime-reports-dir "$REPORTS_DIR" --runtime "$RUNTIME"
# Rebuild research health once after Agent/CIO enrichment. Publication health
# is validated later and never feeds back into investment evidence.
"$PY" scripts/write_source_health_ledgers.py \
  --date "$RUN_DATE" \
  --docs-dir "$DOCS_DIR" \
  --preserve-runtime-enrichment
"$PY" src/render_report_html.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR"
"$PY" scripts/audit_semantic_quality.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR" --fail-on-error
"$PY" scripts/build_pages_compat_bundle.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR" --runtime-reports-dir "$REPORTS_DIR"
"$PY" src/render_homepage.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR"

VALIDATION_PATH="$DOCS_DIR/run_status/$RUN_DATE/pages_validation.json"
"$PY" scripts/validate_pages_bundle.py \
  --date "$RUN_DATE" \
  --docs-dir "$DOCS_DIR" \
  --output "$VALIDATION_PATH" \
  --fail-on-error
# Finalize publication health from the completed validator, rebuild the same
# artifact/Reader contract, then validate once more. Research Agents never see
# this publication-only status.
"$PY" scripts/write_source_health_ledgers.py \
  --date "$RUN_DATE" \
  --docs-dir "$DOCS_DIR" \
  --preserve-runtime-enrichment \
  --include-pages-validation
"$PY" src/render_report_html.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR"
"$PY" scripts/audit_semantic_quality.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR" --fail-on-error
"$PY" scripts/build_pages_compat_bundle.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR" --runtime-reports-dir "$REPORTS_DIR"
"$PY" src/render_homepage.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR"
"$PY" scripts/validate_pages_bundle.py \
  --date "$RUN_DATE" \
  --docs-dir "$DOCS_DIR" \
  --output "$VALIDATION_PATH" \
  --fail-on-error
"$PY" scripts/audit_department_data_flow.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR"
"$PY" scripts/audit_data_temporality.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR" --fail-on-error

if [[ "${RUN_FULL_GATE:-0}" == "1" ]]; then
  "$PY" -m compileall -q main.py server.py api bot data_provider scripts src
  ./scripts/ci_gate.sh
fi

if [[ "${RUN_WEB_GATE:-0}" == "1" ]]; then
  (cd apps/dsa-web && npm test && npm run lint && npm run build)
fi

"$PY" scripts/write_local_acceptance.py --date "$RUN_DATE" --docs-dir "$DOCS_DIR" --kind final --command-status "local runner completed; RUN_FULL_GATE=${RUN_FULL_GATE:-0}; RUN_WEB_GATE=${RUN_WEB_GATE:-0}"

echo "OK: $DOCS_DIR/reports/$RUN_DATE.html"
echo "OK: $DOCS_DIR/reports/$RUN_DATE.artifact.json"
echo "OK: $DOCS_DIR/reports/$RUN_DATE.diagnostics.html"
echo "OK: $DOCS_DIR/local_acceptance/$RUN_DATE/final_acceptance.md"
