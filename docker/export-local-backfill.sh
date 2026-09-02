#!/usr/bin/env bash
# Package a quiesced local intelligence database and its archives for VPS import.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

OUTPUT_DIR=""
ARCHIVE_ROOT=""
DATABASE_CONTAINER=""
QUIESCED=false
while [ "$#" -gt 0 ]; do
    case "$1" in
        --output-dir)
            OUTPUT_DIR="${2:-}"
            shift 2
            ;;
        --archive-root)
            ARCHIVE_ROOT="${2:-}"
            shift 2
            ;;
        --database-container)
            DATABASE_CONTAINER="${2:-}"
            shift 2
            ;;
        --confirm-quiesced)
            QUIESCED=true
            shift
            ;;
        *)
            echo "Unknown export argument: $1" >&2
            exit 2
            ;;
    esac
done

if [ -z "$OUTPUT_DIR" ] || [ -z "$ARCHIVE_ROOT" ]; then
    echo "--output-dir and --archive-root are required" >&2
    exit 2
fi
if [ "$QUIESCED" != true ]; then
    echo "Stop Dagster writers, then rerun with --confirm-quiesced" >&2
    exit 2
fi

for command_name in git psql sha256sum stat tar; do
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
    for command_name in pg_dump pg_restore; do
        if ! command -v "$command_name" >/dev/null 2>&1; then
            echo "Required command is unavailable: $command_name" >&2
            exit 1
        fi
    done
fi

if [ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all)" ]; then
    echo "Refusing to export a backfill from a dirty working tree" >&2
    exit 1
fi
CODE_REF="$(git -C "$REPO_ROOT" rev-parse HEAD)"
if ! [[ "$CODE_REF" =~ ^[0-9a-f]{40}$ ]]; then
    echo "The local backfill must be tied to an exact Git commit" >&2
    exit 1
fi

for pass_number in 0 1 2 3 4; do
    enabled_name="COUNTYIQ_PASS${pass_number}_ENABLED"
    enabled_value="${!enabled_name:-false}"
    if [[ "${enabled_value,,}" != "false" ]] \
        && [ "$enabled_value" != "0" ] \
        && [[ "${enabled_value,,}" != "no" ]] \
        && [[ "${enabled_value,,}" != "off" ]]; then
        echo "$enabled_name must be disabled before export" >&2
        exit 1
    fi
done

DATABASE_HOST="${DATABASE_HOST:-localhost}"
DATABASE_PORT="${DATABASE_PORT:-5433}"
DATABASE_NAME="${DATABASE_NAME:-countyiq}"
DATABASE_USER="${DATABASE_USER:-dagster_admin}"
DATABASE_PASSWORD="${DATABASE_PASSWORD:-localtest}"
for identifier in "$DATABASE_NAME" "$DATABASE_USER"; do
    if ! [[ "$identifier" =~ ^[a-z_][a-z0-9_]{0,62}$ ]]; then
        echo "Database name and user must be simple PostgreSQL identifiers" >&2
        exit 1
    fi
done
if ! [[ "$DATABASE_PORT" =~ ^[0-9]+$ ]]; then
    echo "DATABASE_PORT must be numeric" >&2
    exit 1
fi

ARCHIVE_ROOT="$(realpath -e -- "$ARCHIVE_ROOT")"
if [ ! -d "$ARCHIVE_ROOT/raw" ] || [ ! -d "$ARCHIVE_ROOT/llm" ]; then
    echo "Archive root must contain raw/ and llm/ directories" >&2
    exit 1
fi
mkdir -p -- "$OUTPUT_DIR"
OUTPUT_DIR="$(realpath -e -- "$OUTPUT_DIR")"

export PGPASSWORD="$DATABASE_PASSWORD"
PSQL=(psql -X -v ON_ERROR_STOP=1 -h "$DATABASE_HOST" -p "$DATABASE_PORT" -U "$DATABASE_USER" -d "$DATABASE_NAME")
SCHEMA_REVISION="$("${PSQL[@]}" -Atc "SELECT version_num FROM alembic_version")"
if [ "$SCHEMA_REVISION" != "$REPOSITORY_SCHEMA_HEAD" ]; then
    echo "Backfill export requires repository Alembic head $REPOSITORY_SCHEMA_HEAD; found ${SCHEMA_REVISION:-base}" >&2
    exit 1
fi

INTEGRITY_COUNTS="$("${PSQL[@]}" -At -F '|' -c \
    "SELECT unresolved_contradiction_count, unlinked_projection_count, projection_mismatch_count FROM meta.intelligence_integrity_status")"
REJECTIONS_24H="$("${PSQL[@]}" -Atc \
    "SELECT rejections_last_24h FROM meta.intelligence_validation_rejection_status")"
TEST_FIXTURE_COUNTS="$("${PSQL[@]}" -At -F '|' -c \
    "SELECT
        (SELECT COUNT(*) FROM meta.intelligence_inference_history
         WHERE requested_model LIKE 'test/%' AND prompt_version = 'test-prompt'),
        (SELECT COUNT(*) FROM meta.intelligence_validation_rejections
         WHERE subject_key LIKE 'rejection-test:%' AND requested_model LIKE 'test/%')")"
if [ "$INTEGRITY_COUNTS" != "0|0|0" ] \
    || [ "$REJECTIONS_24H" != "0" ] \
    || [ "$TEST_FIXTURE_COUNTS" != "0|0" ]; then
    echo "Backfill integrity is not clean: $INTEGRITY_COUNTS, rejections_24h=$REJECTIONS_24H" >&2
    echo "Integration-test fixture counts (history|rejections): $TEST_FIXTURE_COUNTS" >&2
    exit 1
fi

EXPORT_TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EXPORT_ID="${EXPORT_TIMESTAMP}-${CODE_REF:0:12}"
BUNDLE_DIR="$OUTPUT_DIR/$EXPORT_ID"
if [ -e "$BUNDLE_DIR" ]; then
    echo "Refusing to overwrite existing export: $BUNDLE_DIR" >&2
    exit 1
fi
WORK_DIR="$(mktemp -d "$OUTPUT_DIR/.backfill-export.XXXXXX")"
CONTAINER_DUMP_PATH=""
cleanup() {
    local status=$?
    if [ -n "${CONTAINER_DUMP_PATH:-}" ] && [ -n "${DATABASE_CONTAINER:-}" ]; then
        docker exec "$DATABASE_CONTAINER" rm -f -- "$CONTAINER_DUMP_PATH" >/dev/null 2>&1 || true
    fi
    if [ -n "${WORK_DIR:-}" ] && [ -d "$WORK_DIR" ]; then
        rm -rf -- "$WORK_DIR"
    fi
    return "$status"
}
trap cleanup EXIT

DUMP_NAME="${DATABASE_NAME}-${EXPORT_ID}.dump"
ARCHIVE_NAME="archives-${EXPORT_ID}.tar.gz"
MANIFEST_NAME="backfill-${EXPORT_ID}.manifest"
if [ -n "$DATABASE_CONTAINER" ]; then
    DATABASE_CONTAINER_HOST="${DATABASE_CONTAINER_HOST:-localhost}"
    DATABASE_CONTAINER_PORT="${DATABASE_CONTAINER_PORT:-5432}"
    if ! [[ "$DATABASE_CONTAINER_PORT" =~ ^[0-9]+$ ]]; then
        echo "DATABASE_CONTAINER_PORT must be numeric" >&2
        exit 1
    fi
    CONTAINER_DUMP_PATH="/tmp/countyiq-backfill-${EXPORT_ID}.dump"
    docker exec \
        -e PGPASSWORD="$DATABASE_PASSWORD" \
        "$DATABASE_CONTAINER" \
        pg_dump \
        -h "$DATABASE_CONTAINER_HOST" \
        -p "$DATABASE_CONTAINER_PORT" \
        -U "$DATABASE_USER" \
        -d "$DATABASE_NAME" \
        --format=custom \
        --file="$CONTAINER_DUMP_PATH"
    docker exec "$DATABASE_CONTAINER" pg_restore --list "$CONTAINER_DUMP_PATH" >/dev/null
    docker cp "$DATABASE_CONTAINER:$CONTAINER_DUMP_PATH" "$WORK_DIR/$DUMP_NAME" >/dev/null
    docker exec "$DATABASE_CONTAINER" rm -f -- "$CONTAINER_DUMP_PATH"
    CONTAINER_DUMP_PATH=""
else
    pg_dump \
        -h "$DATABASE_HOST" \
        -p "$DATABASE_PORT" \
        -U "$DATABASE_USER" \
        -d "$DATABASE_NAME" \
        --format=custom \
        --file="$WORK_DIR/$DUMP_NAME"
    pg_restore --list "$WORK_DIR/$DUMP_NAME" >/dev/null
fi
tar -C "$ARCHIVE_ROOT" -czf "$WORK_DIR/$ARCHIVE_NAME" raw llm

DUMP_SHA256="$(sha256sum "$WORK_DIR/$DUMP_NAME" | awk '{print $1}')"
ARCHIVE_SHA256="$(sha256sum "$WORK_DIR/$ARCHIVE_NAME" | awk '{print $1}')"
DUMP_BYTES="$(stat -c '%s' "$WORK_DIR/$DUMP_NAME")"
ARCHIVE_BYTES="$(stat -c '%s' "$WORK_DIR/$ARCHIVE_NAME")"
DATA_COUNTS="$("${PSQL[@]}" -At -F '=' -c "
    SELECT 'current_parcels', COUNT(*) FROM staging.parcels WHERE valid_to IS NULL
    UNION ALL SELECT 'proceedings', COUNT(*) FROM staging.public_proceedings WHERE valid_to IS NULL
    UNION ALL SELECT 'development_signals', COUNT(*) FROM public.development_signals
    UNION ALL SELECT 'accepted_inferences', COUNT(*) FROM meta.intelligence_inference_history WHERE disposition = 'accepted'
    UNION ALL SELECT 'parcel_briefs', COUNT(*) FROM public.parcel_briefs
    UNION ALL SELECT 'owner_briefs', COUNT(*) FROM public.owner_briefs
    ORDER BY 1")"

{
    printf 'export_id=%s\n' "$EXPORT_ID"
    printf 'created_at=%s\n' "$(date -u -Iseconds)"
    printf 'code_ref=%s\n' "$CODE_REF"
    printf 'schema_revision=%s\n' "$SCHEMA_REVISION"
    printf 'database_name=%s\n' "$DATABASE_NAME"
    printf 'database_file=%s\n' "$DUMP_NAME"
    printf 'database_bytes=%s\n' "$DUMP_BYTES"
    printf 'database_sha256=%s\n' "$DUMP_SHA256"
    printf 'archives_file=%s\n' "$ARCHIVE_NAME"
    printf 'archives_bytes=%s\n' "$ARCHIVE_BYTES"
    printf 'archives_sha256=%s\n' "$ARCHIVE_SHA256"
    printf '%s\n' "$DATA_COUNTS"
} > "$WORK_DIR/$MANIFEST_NAME"

chmod 400 "$WORK_DIR/$MANIFEST_NAME" "$WORK_DIR/$DUMP_NAME" "$WORK_DIR/$ARCHIVE_NAME"
mv -- "$WORK_DIR" "$BUNDLE_DIR"
WORK_DIR=""
echo "Local backfill export complete: $BUNDLE_DIR"
echo "COUNTYIQ_LOCAL_BACKFILL_EXPORT=$BUNDLE_DIR"
