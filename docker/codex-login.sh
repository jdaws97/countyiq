#!/usr/bin/env bash
# Run on the VPS after deploying the pinned Dagster image.
set -euo pipefail

interactive=(-i)
if [[ -t 0 && -t 1 ]]; then
    interactive+=(-t)
fi

exec docker exec "${interactive[@]}" --user 10001:10001 \
    countyiq-dagster-webserver \
    /opt/pipelines/.venv/bin/python /opt/pipelines/scripts/codex_login.py "$@"
