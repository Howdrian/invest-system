#!/bin/sh
set -eu

# The image serves both scheduler-only and API modes.  API containers must
# prove their HTTP endpoint is alive; scheduler-only containers are healthy
# only while PID 1 is still running.
cmdline="$(tr '\000' ' ' </proc/1/cmdline 2>/dev/null || true)"
case "$cmdline" in
  *--serve*|*server.py*|*uvicorn*)
    port="${API_PORT:-${WEBUI_PORT:-8000}}"
    curl -fsS "http://127.0.0.1:${port}/api/health" >/dev/null \
      || curl -fsS "http://127.0.0.1:${port}/health" >/dev/null
    ;;
  *)
    kill -0 1
    ;;
esac
