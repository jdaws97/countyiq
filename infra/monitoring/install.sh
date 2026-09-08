#!/usr/bin/env bash
# Install the monitoring project independently of application images.
set -euo pipefail
umask 077

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR=/opt/countyiq-monitoring
CACHE_DIR=/var/cache/countyiq/monitoring
ALLOY_VERSION=1.19.2
ALLOY_SHA256=3694ea4e1044b367e1c21ffe28117f209c5989fa5e604d000321809f871ab701
UV_VERSION=0.10.7
UV_SHA256=9ac6cee4e379a5abfca06e78a777b26b7ba1f81cb7935b97054d80d85ac00774

if [ "$EUID" -ne 0 ]; then
    echo "Run the monitoring installer as root." >&2
    exit 1
fi
if [ "$(uname -m)" != x86_64 ]; then
    echo "This installer is reviewed for Linux x86_64 only." >&2
    exit 1
fi
for executable in curl sha256sum tar systemctl docker; do
    if ! command -v "$executable" >/dev/null; then
        echo "Missing monitoring prerequisite: $executable" >&2
        exit 1
    fi
done

install -d -o root -g root -m 755 "$INSTALL_DIR" "$INSTALL_DIR/bin" "$CACHE_DIR"
install -d -o root -g root -m 755 /var/lib/countyiq/monitoring/metrics
if [ ! -f /var/lib/countyiq/monitoring/container-logs.json ]; then
    printf '[]\n' > /var/lib/countyiq/monitoring/container-logs.json
    chmod 644 /var/lib/countyiq/monitoring/container-logs.json
fi

download_verified() {
    local url="$1" destination="$2" checksum="$3"
    if [ ! -f "$destination" ] || ! printf '%s  %s\n' "$checksum" "$destination" | sha256sum --check --status; then
        curl --fail --silent --show-error --location --proto '=https' \
            --tlsv1.2 "$url" -o "$destination.pending"
        printf '%s  %s\n' "$checksum" "$destination.pending" | sha256sum --check --status
        mv "$destination.pending" "$destination"
    fi
}

download_verified \
    "https://github.com/grafana/alloy/releases/download/v$ALLOY_VERSION/alloy-linux-amd64.zip" \
    "$CACHE_DIR/alloy-$ALLOY_VERSION.zip" "$ALLOY_SHA256"
download_verified \
    "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-unknown-linux-gnu.tar.gz" \
    "$CACHE_DIR/uv-$UV_VERSION.tar.gz" "$UV_SHA256"

temporary="$(mktemp -d "$CACHE_DIR/install.XXXXXX")"
trap 'rm -rf -- "$temporary"' EXIT
tar -xzf "$CACHE_DIR/uv-$UV_VERSION.tar.gz" -C "$temporary"
install -m 755 "$temporary/uv-x86_64-unknown-linux-gnu/uv" "$INSTALL_DIR/bin/uv"

if [ "$SOURCE_DIR" != "$INSTALL_DIR" ]; then
    for filename in pyproject.toml uv.lock collect.py probes.py retention.py config.alloy; do
        install -m 644 "$SOURCE_DIR/$filename" "$INSTALL_DIR/$filename"
    done
fi

# A project virtual environment, not the host distribution's Python.
UV_PYTHON_INSTALL_DIR="$INSTALL_DIR/python" \
    "$INSTALL_DIR/bin/uv" sync --project "$INSTALL_DIR" --python 3.11 --frozen --no-dev

"$INSTALL_DIR/.venv/bin/python" -m zipfile -e \
    "$CACHE_DIR/alloy-$ALLOY_VERSION.zip" "$temporary"
install -m 755 "$temporary/alloy-linux-amd64" "$INSTALL_DIR/bin/alloy"

GRAFANA_METRICS_URL=https://validation.grafana.net/api/prom/push \
GRAFANA_LOGS_URL=https://validation.grafana.net/loki/api/v1/push \
    "$INSTALL_DIR/bin/alloy" validate "$INSTALL_DIR/config.alloy"

for unit in "$SOURCE_DIR"/systemd/*; do
    install -m 644 "$unit" "/etc/systemd/system/$(basename "$unit")"
done
systemctl daemon-reload
systemctl enable --now countyiq-monitor-fast.timer countyiq-monitor-slow.timer countyiq-monitor-storage.timer
systemctl enable --now countyiq-docker-retention.timer
systemctl start countyiq-monitor@fast.service countyiq-monitor@slow.service countyiq-monitor@storage.service

if [ -f /etc/countyiq/monitoring.env ]; then
    if [ "$(stat -c '%U:%G:%a' /etc/countyiq/monitoring.env)" != root:root:600 ]; then
        echo "Monitoring credentials must be root:root mode 0600." >&2
        exit 1
    fi
    systemctl enable countyiq-alloy.service
    systemctl restart countyiq-alloy.service
    systemctl is-active --quiet countyiq-alloy.service
    echo "Monitoring probes and Grafana collector installed. Verify ingestion in Grafana."
else
    echo "Monitoring probes installed. Grafana export awaits protected account credentials."
fi
