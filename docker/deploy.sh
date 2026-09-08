#!/usr/bin/env bash
# Fail-closed production release orchestration for the single-host Compose stack.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=docker/lib/operations.sh
source "$SCRIPT_DIR/lib/operations.sh"

CHECK_ONLY=false
INITIAL_DEPLOY=false
while [ "$#" -gt 0 ]; do
    case "$1" in
        --check)
            CHECK_ONLY=true
            shift
            ;;
        --initial)
            INITIAL_DEPLOY=true
            shift
            ;;
        *)
            echo "Unknown deploy argument: $1" >&2
            exit 2
            ;;
    esac
done

DEPLOY_REF="${COUNTYIQ_DEPLOY_REF:-}"
if ! [[ "$DEPLOY_REF" =~ ^[0-9a-f]{40}$ ]]; then
    echo "COUNTYIQ_DEPLOY_REF must be the reviewed 40-character Git commit SHA" >&2
    exit 1
fi
if [ "$(git -C "$REPO_ROOT" rev-parse HEAD)" != "$DEPLOY_REF" ]; then
    echo "The checked-out commit does not match COUNTYIQ_DEPLOY_REF" >&2
    exit 1
fi
if [ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all)" ]; then
    echo "Refusing to deploy a dirty working tree" >&2
    exit 1
fi

ENVIRONMENT_FILE="${COUNTYIQ_ENV_FILE:-/etc/countyiq/production.env}"
if [ "$CHECK_ONLY" = false ]; then
    if [ "$EUID" -ne 0 ]; then
        echo "Production deployment must run as root" >&2
        exit 1
    fi
    countyiq_validate_secret_file "$ENVIRONMENT_FILE"
    if [ -f "${COUNTYIQ_COST_GUARD_DIR:-/var/lib/countyiq/cost-guard}/tripped" ]; then
        echo "CountyIQ is hard-stopped by the cost guard; review and reset it before deploying" >&2
        exit 1
    fi
fi
countyiq_load_environment "$ENVIRONMENT_FILE"
countyiq_validate_production_environment
countyiq_require_command docker
countyiq_require_command git

export COUNTYIQ_DEPLOY_REF="$DEPLOY_REF"
export COUNTYIQ_IMAGE_TAG="$DEPLOY_REF"
COMPOSE=(docker compose --env-file "$ENVIRONMENT_FILE" -f "$SCRIPT_DIR/docker-compose.yml")
"${COMPOSE[@]}" config --quiet

if [ "$CHECK_ONLY" = true ]; then
    echo "Deployment configuration preflight is valid for $DEPLOY_REF"
    echo "Actual deployment also requires the root-only docker/check-host.sh host gate"
    echo "API image: countyiq-api:$COUNTYIQ_IMAGE_TAG"
    echo "Dagster image: countyiq-dagster:$COUNTYIQ_IMAGE_TAG"
    echo "Web image: countyiq-web:$COUNTYIQ_IMAGE_TAG"
    exit 0
fi

countyiq_validate_host

countyiq_require_command curl
countyiq_require_command flock
countyiq_require_command pg_restore
countyiq_require_command rclone

RELEASE_DIR="${COUNTYIQ_RELEASE_DIR:-/var/lib/countyiq/releases}"
RESTORE_RECEIPT_DIR="${COUNTYIQ_RESTORE_RECEIPT_DIR:-/var/lib/countyiq/restore-drills}"
BACKFILL_STATE_DIR="${COUNTYIQ_BACKFILL_STATE_DIR:-/var/lib/countyiq/intelligence}"
ARCHIVE_HOST_DIR="${COUNTYIQ_ARCHIVE_HOST_DIR:-/var/lib/countyiq/archives}"
CODEX_AUTH_DIR="${COUNTYIQ_CODEX_AUTH_DIR:-/var/lib/countyiq/codex-auth}"
CURRENT_RELEASE="$RELEASE_DIR/current.env"
CURRENT_RESTORE_RECEIPT="$RESTORE_RECEIPT_DIR/current.env"
RESTORE_MAX_AGE_DAYS="${COUNTYIQ_RESTORE_DRILL_MAX_AGE_DAYS:-120}"
if [[ ! "$BACKFILL_STATE_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
    echo "COUNTYIQ_BACKFILL_STATE_DIR must be an absolute path using safe characters" >&2
    exit 1
fi
install -d -o root -g root -m 700 "$RELEASE_DIR" "$RESTORE_RECEIPT_DIR"
install -d -o 10001 -g 10001 -m 700 "$BACKFILL_STATE_DIR"
if [[ ! "$CODEX_AUTH_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
    echo "COUNTYIQ_CODEX_AUTH_DIR must be an absolute path using safe characters" >&2
    exit 1
fi
install -d -o 10001 -g 10001 -m 700 "$CODEX_AUTH_DIR"
if [[ ! "$ARCHIVE_HOST_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
    echo "COUNTYIQ_ARCHIVE_HOST_DIR must be an absolute path using safe characters" >&2
    exit 1
fi
install -d -o 10001 -g 10001 -m 700 "$ARCHIVE_HOST_DIR"

if [ "$INITIAL_DEPLOY" = true ]; then
    if [ -f "$CURRENT_RELEASE" ]; then
        echo "--initial is valid only before the first recorded release" >&2
        exit 1
    fi
else
    if [ ! -f "$CURRENT_RELEASE" ]; then
        echo "No recorded release exists; use --initial for the first deployment" >&2
        exit 1
    fi
    if ! [[ "$RESTORE_MAX_AGE_DAYS" =~ ^[0-9]+$ ]] || [ "$RESTORE_MAX_AGE_DAYS" -lt 1 ]; then
        echo "COUNTYIQ_RESTORE_DRILL_MAX_AGE_DAYS must be a positive integer" >&2
        exit 1
    fi
    if [ ! -f "$CURRENT_RESTORE_RECEIPT" ]; then
        echo "A successful off-host restore-drill receipt is required before deploy" >&2
        exit 1
    fi
    if [ "${COUNTYIQ_PUBLIC_READY_URL:-}" != "https://app.${DOMAIN}/api/ready" ]; then
        echo "Ordinary deploy requires COUNTYIQ_PUBLIC_READY_URL=https://app.${DOMAIN}/api/ready" >&2
        exit 1
    fi
    if [ -z "${COUNTYIQ_PUBLIC_READY_CURL_CONFIG:-}" ]; then
        echo "Configure authenticated public readiness for Cloudflare Access before deployment" >&2
        exit 1
    fi
    countyiq_validate_secret_file "$COUNTYIQ_PUBLIC_READY_CURL_CONFIG"
    restore_age_seconds=$(( $(date +%s) - $(stat -c '%Y' "$CURRENT_RESTORE_RECEIPT") ))
    if [ "$restore_age_seconds" -lt 0 ]; then
        echo "The latest restore-drill receipt has a future timestamp" >&2
        exit 1
    fi
    if [ "$restore_age_seconds" -gt $(( RESTORE_MAX_AGE_DAYS * 86400 )) ]; then
        echo "The latest restore drill is older than $RESTORE_MAX_AGE_DAYS days" >&2
        exit 1
    fi
fi

exec 8>/var/lock/countyiq-deploy.lock
if ! flock -n 8; then
    echo "Another CountyIQ deployment is already running" >&2
    exit 1
fi

# Compose cannot materialize an environment-backed secret in a read-only
# container. Stage one protected file for cloudflared's explicit runtime GID.
COUNTYIQ_TUNNEL_TOKEN_FILE="${COUNTYIQ_TUNNEL_TOKEN_FILE:-/etc/countyiq/cloudflared.token}"
export COUNTYIQ_TUNNEL_TOKEN_FILE
countyiq_prepare_tunnel_secret "$COUNTYIQ_TUNNEL_TOKEN_FILE"

if [ "$INITIAL_DEPLOY" = true ] \
    && ! docker volume inspect countyiq-postgres-data >/dev/null 2>&1; then
    legacy_database_volumes="$(
        docker volume ls \
            --filter label=com.docker.compose.volume=postgres-data \
            --format '{{.Name}}' \
            | grep -Fxv countyiq-postgres-data || true
    )"
    if [ -n "$legacy_database_volumes" ]; then
        echo "Refusing to initialize beside an existing legacy Postgres volume:" >&2
        printf '%s\n' "$legacy_database_volumes" >&2
        echo "Review and migrate that volume explicitly before the first release" >&2
        exit 1
    fi
fi

PREVIOUS_REF="none"
if [ -f "$CURRENT_RELEASE" ]; then
    PREVIOUS_REF="$(awk -F= '$1 == "deploy_ref" {print $2}' "$CURRENT_RELEASE")"
    if ! [[ "$PREVIOUS_REF" =~ ^[0-9a-f]{40}$ ]]; then
        echo "The current release receipt contains an invalid deploy_ref" >&2
        exit 1
    fi
    if ! git -C "$REPO_ROOT" merge-base --is-ancestor "$PREVIOUS_REF" "$DEPLOY_REF"; then
        echo "Ordinary deployment must move forward from the recorded release" >&2
        echo "Use the reviewed code-only rollback procedure; never run older migrations blindly" >&2
        exit 1
    fi
fi
SCHEMA_BEFORE="unknown"
SCHEMA_AFTER="unknown"
BACKUP_ID=""
SERVICES_STOPPED=false
MIGRATION_STARTED=false
MIGRATION_COMPLETED=false
RELEASE_RECORDED=false
OPERATION_UNIT_BACKUP_DIRECTORY=""

backup_operation_units() {
    local unit_name
    local source_path

    OPERATION_UNIT_BACKUP_DIRECTORY="$(mktemp -d "$RELEASE_DIR/.operation-units.XXXXXX")"
    for unit_name in \
        countyiq-backup.service \
        countyiq-backup.timer \
        countyiq-cost-guard.service \
        countyiq-cost-guard.timer; do
        source_path="/etc/systemd/system/$unit_name"
        if [ -f "$source_path" ]; then
            cp -p -- "$source_path" "$OPERATION_UNIT_BACKUP_DIRECTORY/$unit_name"
            touch "$OPERATION_UNIT_BACKUP_DIRECTORY/$unit_name.present"
        fi
    done
}

restore_operation_units() {
    local unit_name
    local destination_path

    for unit_name in \
        countyiq-backup.service \
        countyiq-backup.timer \
        countyiq-cost-guard.service \
        countyiq-cost-guard.timer; do
        destination_path="/etc/systemd/system/$unit_name"
        if [ -f "$OPERATION_UNIT_BACKUP_DIRECTORY/$unit_name.present" ]; then
            install -o root -g root -m 644 \
                "$OPERATION_UNIT_BACKUP_DIRECTORY/$unit_name" \
                "$destination_path"
        else
            rm -f -- "$destination_path"
        fi
    done
    systemctl daemon-reload || true
    rm -rf -- "$OPERATION_UNIT_BACKUP_DIRECTORY"
    OPERATION_UNIT_BACKUP_DIRECTORY=""
}

read_schema_revision() {
    countyiq_read_schema_revision "${COMPOSE[@]}"
}

persist_image_tag() {
    local environment_directory
    local environment_temp
    local environment_mode_value
    environment_directory="$(dirname -- "$ENVIRONMENT_FILE")"
    environment_temp="$(mktemp "$environment_directory/.countyiq-env.XXXXXX")"
    environment_mode_value="$(stat -Lc '%a' "$ENVIRONMENT_FILE")"
    awk -v tag="$DEPLOY_REF" '
        BEGIN { written = 0 }
        /^COUNTYIQ_IMAGE_TAG=/ {
            if (!written) {
                print "COUNTYIQ_IMAGE_TAG=" tag
                written = 1
            }
            next
        }
        { print }
        END {
            if (!written) {
                print "COUNTYIQ_IMAGE_TAG=" tag
            }
        }
    ' "$ENVIRONMENT_FILE" > "$environment_temp"
    chown --reference="$ENVIRONMENT_FILE" "$environment_temp"
    chmod "$environment_mode_value" "$environment_temp"
    mv "$environment_temp" "$ENVIRONMENT_FILE"
}

on_exit() {
    local status=$?
    if [ "$status" -eq 0 ] || [ "$RELEASE_RECORDED" = true ]; then
        return
    fi
    echo "Deployment failed; no release receipt was promoted." >&2
    if [ -n "$OPERATION_UNIT_BACKUP_DIRECTORY" ]; then
        restore_operation_units
    fi
    if [ "$SERVICES_STOPPED" = true ]; then
        local current_schema="unknown"
        current_schema="$(read_schema_revision || true)"
        if [ "$MIGRATION_STARTED" = false ] && [ "$current_schema" = "$SCHEMA_BEFORE" ] \
            && countyiq_require_cost_guard_clear; then
            echo "Schema is unchanged; restarting the stopped prior containers." >&2
            "${COMPOSE[@]}" start api dagster-webserver dagster-daemon >/dev/null 2>&1 || true
        else
            echo "A migration started or the schema may have changed; application services remain stopped for reviewed recovery." >&2
            "${COMPOSE[@]}" stop api dagster-webserver dagster-daemon >/dev/null 2>&1 || true
        fi
    fi
}
trap on_exit EXIT

echo "[1/8] Building commit-addressed application images..."
"${COMPOSE[@]}" build --pull api dagster-webserver caddy
"${COMPOSE[@]}" pull cloudflared
"${COMPOSE[@]}" run --rm --no-deps api \
    /app/.venv/bin/python -c "from api.main import app; assert app"
"${COMPOSE[@]}" run --rm --no-deps dagster-webserver \
    python -c "from countyiq.definitions import defs; assert defs"
"${COMPOSE[@]}" run --rm --no-deps caddy \
    caddy validate --config /etc/caddy/Caddyfile

# Keep scheduled backups out of the migration/release interval. The nested
# pre-deploy backup reuses this inherited lock instead of reacquiring it.
countyiq_lock_backup_operations

echo "[2/8] Starting only PostgreSQL and recording the current schema..."
countyiq_require_cost_guard_clear
"${COMPOSE[@]}" up -d --wait --wait-timeout 120 postgres
SCHEMA_BEFORE="$(read_schema_revision)"

echo "[3/8] Quiescing API and Dagster before the rollback backup..."
# A failed stop can still have stopped some containers; recovery must handle it.
SERVICES_STOPPED=true
"${COMPOSE[@]}" stop -t 60 api dagster-webserver dagster-daemon
active_sessions="$(
    "${COMPOSE[@]}" exec -T postgres psql \
        -U "$DATABASE_USER" -d "$DATABASE_NAME" -At -v ON_ERROR_STOP=1 \
        -c "SELECT COUNT(*) FROM pg_stat_activity WHERE usename IN ('$DATABASE_API_USER', '$DATABASE_PIPELINE_USER') AND pid <> pg_backend_pid();"
)"
if [ "$active_sessions" != "0" ]; then
    echo "Refusing migration while $active_sessions API/pipeline database session(s) remain" >&2
    exit 1
fi

echo "[4/8] Creating and remotely verifying the pre-deploy backup..."
backup_output="$(
    COUNTYIQ_ENV_FILE="$ENVIRONMENT_FILE" \
        COUNTYIQ_BACKUP_CODE_REF="$PREVIOUS_REF" \
        "$SCRIPT_DIR/backup.sh" --reason pre-deploy --label "${DEPLOY_REF:0:12}"
)"
printf '%s\n' "$backup_output"
BACKUP_ID="$(printf '%s\n' "$backup_output" | awk -F= '$1 == "COUNTYIQ_BACKUP_ID" {print $2}')"
if [ -z "$BACKUP_ID" ]; then
    echo "Backup completed without a machine-readable backup ID" >&2
    exit 1
fi

echo "[5/8] Applying the reviewed migration chain while services are stopped..."
MIGRATION_STARTED=true
"${COMPOSE[@]}" run --rm migrate
MIGRATION_COMPLETED=true
"${COMPOSE[@]}" exec -T postgres /docker-entrypoint-initdb.d/02-runtime-role.sh
"${COMPOSE[@]}" exec -T postgres /docker-entrypoint-initdb.d/03-api-role.sh
SCHEMA_AFTER="$(read_schema_revision)"

echo "[6/8] Replacing services with commit-addressed images..."
countyiq_require_cost_guard_clear
"${COMPOSE[@]}" up -d --remove-orphans --wait --wait-timeout 240 \
    api dagster-webserver dagster-daemon caddy cloudflared
countyiq_require_cost_guard_clear
"${COMPOSE[@]}" exec -T api \
    curl --fail --silent --show-error http://localhost:8000/api/ready >/dev/null
if [ -n "${COUNTYIQ_PUBLIC_READY_URL:-}" ]; then
    countyiq_check_public_readiness "$COUNTYIQ_PUBLIC_READY_URL"
fi

echo "[7/8] Installing operation units for this exact release checkout..."
backup_operation_units
"$SCRIPT_DIR/install-operation-units.sh" \
    --repository-root "$REPO_ROOT" \
    --env-file "$ENVIRONMENT_FILE"

echo "[8/8] Writing the immutable release receipt..."
receipt_timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
receipt_file="$RELEASE_DIR/${receipt_timestamp}-${DEPLOY_REF}.env"
if [ -e "$receipt_file" ]; then
    echo "Refusing to overwrite an existing release receipt" >&2
    exit 1
fi
receipt_temp="$(mktemp "$RELEASE_DIR/.release.XXXXXX")"
api_image_id="$(docker image inspect --format '{{.Id}}' "countyiq-api:$COUNTYIQ_IMAGE_TAG")"
dagster_image_id="$(docker image inspect --format '{{.Id}}' "countyiq-dagster:$COUNTYIQ_IMAGE_TAG")"
web_image_id="$(docker image inspect --format '{{.Id}}' "countyiq-web:$COUNTYIQ_IMAGE_TAG")"
cloudflared_image_id="$(docker image inspect --format '{{.Id}}' 'cloudflare/cloudflared:2026.8.3@sha256:51c9cefcb4569df44e1ad403ab1d3d8065aa8e84339bcfc6aee75502e1140339')"
{
    printf 'deploy_ref=%s\n' "$DEPLOY_REF"
    printf 'previous_ref=%s\n' "$PREVIOUS_REF"
    printf 'deployed_at=%s\n' "$(date -u -Iseconds)"
    printf 'backup_id=%s\n' "$BACKUP_ID"
    printf 'schema_before=%s\n' "$SCHEMA_BEFORE"
    printf 'schema_after=%s\n' "$SCHEMA_AFTER"
    printf 'api_image=%s\n' "$api_image_id"
    printf 'dagster_image=%s\n' "$dagster_image_id"
    printf 'web_image=%s\n' "$web_image_id"
    printf 'cloudflared_image=%s\n' "$cloudflared_image_id"
} > "$receipt_temp"
chmod 400 "$receipt_temp"
mv "$receipt_temp" "$receipt_file"
persist_image_tag
current_temp="$(mktemp "$RELEASE_DIR/.current.XXXXXX")"
cp "$receipt_file" "$current_temp"
chmod 400 "$current_temp"
mv "$current_temp" "$CURRENT_RELEASE"
RELEASE_RECORDED=true
rm -rf -- "$OPERATION_UNIT_BACKUP_DIRECTORY"
OPERATION_UNIT_BACKUP_DIRECTORY=""

echo "[8/8] Deployment complete."
echo "Release receipt: $receipt_file"
echo "Rollback backup: $BACKUP_ID"
