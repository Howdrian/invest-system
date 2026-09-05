#!/usr/bin/env bash
# Local deployment adapter. No API fallback, installation, publishing or trading.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --codex-model)
      [[ $# -ge 2 && -n "$2" ]] || { echo "--codex-model requires a value" >&2; exit 2; }
      export RESEARCH_CODEX_MODEL="$2"; shift 2 ;;
    --reasoning-effort)
      [[ $# -ge 2 && -n "$2" ]] || { echo "--reasoning-effort requires a value" >&2; exit 2; }
      export RESEARCH_CODEX_REASONING_EFFORT="$2"; shift 2 ;;
    --help)
      echo "Usage: $0 [--codex-model MODEL] [--reasoning-effort EFFORT] [daily runner options]"
      echo "Uses the configured models when omitted. No API fallback or cloud publishing."
      exit 0 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
# Use a project-owned CLI if installed; never upgrade the user's global executable here.
CLI_DIR="${RESEARCH_CODEX_BIN_DIR:-$ROOT/.local_archive/codex-runtime/node_modules/.bin}"
if [[ -x "$CLI_DIR/codex" ]]; then export PATH="$CLI_DIR:$PATH"; fi
command -v codex >/dev/null || { echo "Codex CLI is not installed" >&2; exit 2; }
export GENERATION_BACKEND=codex_cli
export GENERATION_FALLBACK_BACKEND=""
export RESEARCH_GENERATION_BACKEND=codex_cli
export AGENT_BACKEND=codex_app_server
export RESEARCH_AGENT_RUNTIME=llm
export RESEARCH_AGENT_MAX_CONCURRENCY="${RESEARCH_AGENT_MAX_CONCURRENCY:-1}"
export LOCAL_CLI_BACKEND_MAX_CONCURRENCY="${LOCAL_CLI_BACKEND_MAX_CONCURRENCY:-1}"
export GENERATION_BACKEND_TIMEOUT_SECONDS="${GENERATION_BACKEND_TIMEOUT_SECONDS:-300}"
PY="${PYTHON:-$ROOT/.venv311/bin/python}"
[[ -x "$PY" ]] || PY="python3"
exec "$PY" scripts/with_local_research_lock.py \
  "$ROOT/.local_archive/runtime/research.lock" -- \
  bash scripts/run_research_daily_local.sh "${ARGS[@]}"
