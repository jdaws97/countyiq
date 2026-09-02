#!/usr/bin/env bash
# Verify a portable local-backfill bundle without restoring it.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

BUNDLE_DIR=""
DATABASE_CONTAINER=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --bundle)
            BUNDLE_DIR="${2:-}"
            shift 2
            ;;
        --database-container)
            DATABASE_CONTAINER="${2:-}"
            shift 2
            ;;
        *)
            echo "Unknown verification argument: $1" >&2
            exit 2
            ;;
    esac
done
if [ -z "$BUNDLE_DIR" ]; then
    echo "--bundle is required" >&2
    exit 2
fi
for command_name in sha256sum stat tar; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Required command is unavailable: $command_name" >&2
        exit 1
    fi
done
ALEMBIC_BIN="$REPO_ROOT/pipelines/.venv/bin/alembic"
if [ ! -x "$ALEMBIC_BIN" ]; then
    echo "Alembic executable is unavailable: $ALEMBIC_BIN" >&2
    exit 1
fi
mapfile -t REPOSITORY_SCHEMA_HEADS < <(
    cd "$REPO_ROOT/pipelines"
    "$ALEMBIC_BIN" heads | awk '{print $1}'
)
if [ "${#REPOSITORY_SCHEMA_HEADS[@]}" -ne 1 ]; then
    echo "Repository must have exactly one Alembic head" >&2
    exit 1
fi
REPOSITORY_SCHEMA_HEAD="${REPOSITORY_SCHEMA_HEADS[0]}"
if [ -n "$DATABASE_CONTAINER" ]; then
    if ! [[ "$DATABASE_CONTAINER" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]]; then
        echo "--database-container must be a Docker container name or ID" >&2
        exit 2
    fi
    if ! command -v docker >/dev/null 2>&1; then
        echo "Required command is unavailable: docker" >&2
        exit 1
    fi
    if [ "$(docker inspect -f '{{.State.Running}}' "$DATABASE_CONTAINER" 2>/dev/null || true)" != "true" ]; then
        echo "Database container is not running: $DATABASE_CONTAINER" >&2
        exit 1
    fi
else
    if ! command -v pg_restore >/dev/null 2>&1; then
        echo "Required command is unavailable: pg_restore" >&2
        exit 1
    fi
fi

BUNDLE_DIR="$(realpath -e -- "$BUNDLE_DIR")"
manifest_files=("$BUNDLE_DIR"/backfill-*.manifest)
if [ "${#manifest_files[@]}" -ne 1 ] || [ ! -f "${manifest_files[0]}" ]; then
    echo "Bundle must contain exactly one backfill manifest" >&2
    exit 1
fi
MANIFEST="${manifest_files[0]}"

manifest_value() {
    local key="$1"
    awk -F= -v expected="$key" '$1 == expected {print substr($0, index($0, "=") + 1)}' "$MANIFEST"
}

CODE_REF="$(manifest_value code_ref)"
SCHEMA_REVISION="$(manifest_value schema_revision)"
DUMP_NAME="$(manifest_value database_file)"
ARCHIVE_NAME="$(manifest_value archives_file)"
DUMP_SHA256="$(manifest_value database_sha256)"
ARCHIVE_SHA256="$(manifest_value archives_sha256)"
DUMP_BYTES="$(manifest_value database_bytes)"
ARCHIVE_BYTES="$(manifest_value archives_bytes)"

if ! [[ "$CODE_REF" =~ ^[0-9a-f]{40}$ ]] \
    || [ "$SCHEMA_REVISION" != "$REPOSITORY_SCHEMA_HEAD" ]; then
    echo "Manifest has an invalid code reference or schema revision" >&2
    exit 1
fi
if ! [[ "$DUMP_NAME" =~ ^[a-z_][a-z0-9_]*-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}\.dump$ ]] \
    || ! [[ "$ARCHIVE_NAME" =~ ^archives-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}\.tar\.gz$ ]]; then
    echo "Manifest contains an unsafe artifact filename" >&2
    exit 1
fi
if ! [[ "$DUMP_SHA256" =~ ^[0-9a-f]{64}$ ]] \
    || ! [[ "$ARCHIVE_SHA256" =~ ^[0-9a-f]{64}$ ]] \
    || ! [[ "$DUMP_BYTES" =~ ^[0-9]+$ ]] \
    || ! [[ "$ARCHIVE_BYTES" =~ ^[0-9]+$ ]]; then
    echo "Manifest integrity metadata is invalid" >&2
    exit 1
fi

DUMP_PATH="$BUNDLE_DIR/$DUMP_NAME"
ARCHIVE_PATH="$BUNDLE_DIR/$ARCHIVE_NAME"
if [ "$(sha256sum "$DUMP_PATH" | awk '{print $1}')" != "$DUMP_SHA256" ] \
    || [ "$(stat -c '%s' "$DUMP_PATH")" != "$DUMP_BYTES" ]; then
    echo "Database dump does not match the manifest" >&2
    exit 1
fi
if [ "$(sha256sum "$ARCHIVE_PATH" | awk '{print $1}')" != "$ARCHIVE_SHA256" ] \
    || [ "$(stat -c '%s' "$ARCHIVE_PATH")" != "$ARCHIVE_BYTES" ]; then
    echo "Archive bundle does not match the manifest" >&2
    exit 1
fi
if [ -n "$DATABASE_CONTAINER" ]; then
    CONTAINER_DUMP_PATH="/tmp/countyiq-verify-${DUMP_SHA256:0:12}.dump"
    cleanup() {
        docker exec "$DATABASE_CONTAINER" rm -f -- "$CONTAINER_DUMP_PATH" >/dev/null 2>&1 || true
    }
    trap cleanup EXIT
    docker cp "$DUMP_PATH" "$DATABASE_CONTAINER:$CONTAINER_DUMP_PATH" >/dev/null
    docker exec "$DATABASE_CONTAINER" pg_restore --list "$CONTAINER_DUMP_PATH" >/dev/null
    docker exec "$DATABASE_CONTAINER" rm -f -- "$CONTAINER_DUMP_PATH"
    CONTAINER_DUMP_PATH=""
    trap - EXIT
else
    pg_restore --list "$DUMP_PATH" >/dev/null
fi
tar -tzf "$ARCHIVE_PATH" | grep -Eq '^raw/|^llm/'

echo "Local backfill export verified: $BUNDLE_DIR"
echo "Code ref: $CODE_REF"
echo "Schema revision: $SCHEMA_REVISION"
