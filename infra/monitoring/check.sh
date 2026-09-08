#!/usr/bin/env bash
# Validate configuration and alert behavior with pinned upstream binaries.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
CHECK_DIR="${COUNTYIQ_MONITORING_CHECK_DIR:-${TMPDIR:-/tmp}/countyiq-monitoring-check}"
mkdir -p "$CHECK_DIR"

if [ -z "${ALLOY_BIN:-}" ]; then
    curl --fail --silent --show-error --location \
        https://github.com/grafana/alloy/releases/download/v1.19.2/alloy-linux-amd64.zip \
        -o "$CHECK_DIR/alloy.zip"
    printf '%s  %s\n' \
        3694ea4e1044b367e1c21ffe28117f209c5989fa5e604d000321809f871ab701 \
        "$CHECK_DIR/alloy.zip" | sha256sum --check --status
    unzip -oq "$CHECK_DIR/alloy.zip" -d "$CHECK_DIR/alloy"
    ALLOY_BIN="$CHECK_DIR/alloy/alloy-linux-amd64"
    chmod 755 "$ALLOY_BIN"
fi
if [ -z "${PROMTOOL:-}" ]; then
    curl --fail --silent --show-error --location \
        https://github.com/prometheus/prometheus/releases/download/v3.14.0/prometheus-3.14.0.linux-amd64.tar.gz \
        -o "$CHECK_DIR/prometheus.tar.gz"
    printf '%s  %s\n' \
        f665c6da19eb7ba399c915d30c7d9793c9b417bf8a749b504bc470678631478d \
        "$CHECK_DIR/prometheus.tar.gz" | sha256sum --check --status
    tar -xzf "$CHECK_DIR/prometheus.tar.gz" -C "$CHECK_DIR" \
        prometheus-3.14.0.linux-amd64/promtool
    PROMTOOL="$CHECK_DIR/prometheus-3.14.0.linux-amd64/promtool"
fi

export PROMTOOL
GRAFANA_METRICS_URL=https://validation.grafana.net/api/prom/push \
GRAFANA_LOGS_URL=https://validation.grafana.net/loki/api/v1/push \
    "$ALLOY_BIN" validate "$SCRIPT_DIR/config.alloy"
"$REPO_ROOT/pipelines/.venv/bin/python" -m unittest discover -s "$SCRIPT_DIR/tests"
"$REPO_ROOT/pipelines/.venv/bin/ruff" format --check "$SCRIPT_DIR"
bash -n "$SCRIPT_DIR"/install.sh "$SCRIPT_DIR"/deploy.sh "$SCRIPT_DIR"/check.sh
