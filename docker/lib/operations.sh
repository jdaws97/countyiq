#!/usr/bin/env bash

# Shared, side-effect-free validation helpers for host-level operations.
# Callers retain ownership of `set -euo pipefail`, locks, and cleanup traps.

countyiq_require_command() {
    local command_name="$1"
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Required command is unavailable: $command_name" >&2
        return 1
    fi
}

countyiq_require_identifier() {
    local value="$1"
    local label="$2"
    if ! [[ "$value" =~ ^[a-z_][a-z0-9_]{0,62}$ ]]; then
        echo "$label must be a simple PostgreSQL identifier" >&2
        return 1
    fi
}

countyiq_load_environment() {
    local environment_file="$1"
    if [ ! -f "$environment_file" ]; then
        echo "CountyIQ environment file is missing: $environment_file" >&2
        return 1
    fi
    set -a
    # shellcheck disable=SC1090
    source "$environment_file"
    set +a
}

countyiq_validate_secret_file() {
    local secret_file="$1"
    local file_mode
    local file_owner
    if [ ! -f "$secret_file" ] || [ -L "$secret_file" ]; then
        echo "Secret environment must be a regular, non-symlink file: $secret_file" >&2
        return 1
    fi
    file_mode="$(stat -Lc '%a' "$secret_file")"
    file_owner="$(stat -Lc '%u' "$secret_file")"
    if [ "$file_owner" != "0" ]; then
        echo "The production environment file must be owned by root" >&2
        return 1
    fi
    if [ "$file_mode" != "600" ] && [ "$file_mode" != "400" ]; then
        echo "The production environment file must have mode 600 or 400" >&2
        return 1
    fi
}

countyiq_validate_r2_backup_environment() {
    : "${COUNTYIQ_BACKUP_R2_ACCESS_KEY_ID:?COUNTYIQ_BACKUP_R2_ACCESS_KEY_ID must be set}"
    : "${COUNTYIQ_BACKUP_R2_SECRET_ACCESS_KEY:?COUNTYIQ_BACKUP_R2_SECRET_ACCESS_KEY must be set}"
    : "${R2_ENDPOINT_URL:?R2_ENDPOINT_URL must be set for off-host backups}"
    : "${COUNTYIQ_BACKUP_R2_BUCKET:?COUNTYIQ_BACKUP_R2_BUCKET must be set}"

    if { [ -n "${R2_ACCESS_KEY_ID:-}" ] \
            && [ "$COUNTYIQ_BACKUP_R2_ACCESS_KEY_ID" = "$R2_ACCESS_KEY_ID" ]; } \
        || { [ -n "${R2_SECRET_ACCESS_KEY:-}" ] \
            && [ "$COUNTYIQ_BACKUP_R2_SECRET_ACCESS_KEY" = "$R2_SECRET_ACCESS_KEY" ]; }; then
        echo "Pipeline raw-archive and host backup R2 credentials must be distinct" >&2
        return 1
    fi

    if ! [[ "$R2_ENDPOINT_URL" =~ ^https://[0-9a-f]{32}(\.(eu|us|fedramp))?\.r2\.cloudflarestorage\.com/?$ ]]; then
        echo "R2_ENDPOINT_URL must be the reviewed Cloudflare R2 HTTPS account endpoint" >&2
        return 1
    fi
    if ! [[ "$COUNTYIQ_BACKUP_R2_BUCKET" =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]]; then
        echo "COUNTYIQ_BACKUP_R2_BUCKET is not a valid bucket name" >&2
        return 1
    fi

    # Use an environment-defined rclone remote so a fresh host has no hidden
    # dependency on an interactive `rclone config` profile.
    export RCLONE_CONFIG_COUNTYIQR2_TYPE=s3
    export RCLONE_CONFIG_COUNTYIQR2_PROVIDER=Cloudflare
    export RCLONE_CONFIG_COUNTYIQR2_ACCESS_KEY_ID="$COUNTYIQ_BACKUP_R2_ACCESS_KEY_ID"
    export RCLONE_CONFIG_COUNTYIQR2_SECRET_ACCESS_KEY="$COUNTYIQ_BACKUP_R2_SECRET_ACCESS_KEY"
    export RCLONE_CONFIG_COUNTYIQR2_ENDPOINT="$R2_ENDPOINT_URL"
    export RCLONE_CONFIG_COUNTYIQR2_ACL=private
    export RCLONE_CONFIG_COUNTYIQR2_NO_CHECK_BUCKET=true
    COUNTYIQ_BACKUP_REMOTE="countyiqr2:${COUNTYIQ_BACKUP_R2_BUCKET}"
    export COUNTYIQ_BACKUP_REMOTE
}

countyiq_validate_production_environment() {
    local credential
    local pass_number

    : "${DATABASE_NAME:?DATABASE_NAME must be set}"
    : "${DATABASE_USER:?DATABASE_USER must be set}"
    : "${DATABASE_PASSWORD:?DATABASE_PASSWORD must be set}"
    : "${DATABASE_URL:?DATABASE_URL must be set}"
    : "${DATABASE_PIPELINE_USER:?DATABASE_PIPELINE_USER must be set}"
    : "${DATABASE_PIPELINE_PASSWORD:?DATABASE_PIPELINE_PASSWORD must be set}"
    : "${DATABASE_API_USER:?DATABASE_API_USER must be set}"
    : "${DATABASE_API_PASSWORD:?DATABASE_API_PASSWORD must be set}"
    : "${DOMAIN:?DOMAIN must be set}"
    : "${COUNTYIQ_TRUSTED_HOSTS:?COUNTYIQ_TRUSTED_HOSTS must be set}"
    : "${R2_ACCESS_KEY_ID:?R2_ACCESS_KEY_ID must be set for raw archives}"
    : "${R2_SECRET_ACCESS_KEY:?R2_SECRET_ACCESS_KEY must be set for raw archives}"
    : "${S3_RAW_BUCKET:?S3_RAW_BUCKET must be set}"

    countyiq_require_identifier "$DATABASE_NAME" "DATABASE_NAME"
    countyiq_require_identifier "$DATABASE_USER" "DATABASE_USER"
    countyiq_require_identifier "$DATABASE_PIPELINE_USER" "DATABASE_PIPELINE_USER"
    countyiq_require_identifier "$DATABASE_API_USER" "DATABASE_API_USER"
    if ! [[ "$S3_RAW_BUCKET" =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]]; then
        echo "S3_RAW_BUCKET is not a valid bucket name" >&2
        return 1
    fi
    if [ "$DATABASE_USER" = "$DATABASE_PIPELINE_USER" ] \
        || [ "$DATABASE_USER" = "$DATABASE_API_USER" ] \
        || [ "$DATABASE_PIPELINE_USER" = "$DATABASE_API_USER" ]; then
        echo "Administrator, pipeline, and API database users must be distinct" >&2
        return 1
    fi

    for credential in \
        "$DATABASE_PASSWORD" \
        "$DATABASE_PIPELINE_PASSWORD" \
        "$DATABASE_API_PASSWORD"; do
        if [ "${#credential}" -lt 32 ] || [[ "$credential" == *CHANGE_ME* ]]; then
            echo "Database credentials must be non-placeholder values of at least 32 characters" >&2
            return 1
        fi
    done
    local expected_database_url="postgresql://${DATABASE_USER}:${DATABASE_PASSWORD}@postgres:5432/${DATABASE_NAME}"
    if [ "$DATABASE_URL" != "$expected_database_url" ]; then
        echo "DATABASE_URL must exactly use the reviewed administrator login and Compose database" >&2
        return 1
    fi

    for pass_number in 0 1 2 3 4; do
        local enabled_name="COUNTYIQ_PASS${pass_number}_ENABLED"
        local enabled_value="${!enabled_name:-false}"
        if [[ "${enabled_value,,}" != "false" ]] \
            && [[ "$enabled_value" != "0" ]] \
            && [[ "${enabled_value,,}" != "no" ]] \
            && [[ "${enabled_value,,}" != "off" ]]; then
            echo "$enabled_name must remain false during an ordinary deployment" >&2
            return 1
        fi
    done
    if [[ "${COUNTYIQ_ARCHIVE_STRICT:-false}" != "true" ]]; then
        echo "COUNTYIQ_ARCHIVE_STRICT=true is required in production" >&2
        return 1
    fi
    if [ "$DOMAIN" = "localhost" ] \
        || ! [[ "$DOMAIN" =~ ^[a-z0-9][a-z0-9.-]*[a-z0-9]$ ]] \
        || [[ "$DOMAIN" != *.* ]] \
        || [[ "$DOMAIN" == *..* ]]; then
        echo "DOMAIN must be the reviewed public lowercase hostname" >&2
        return 1
    fi
    case ",${COUNTYIQ_TRUSTED_HOSTS}," in
        *",${DOMAIN},"*) ;;
        *)
            echo "COUNTYIQ_TRUSTED_HOSTS must contain DOMAIN exactly" >&2
            return 1
            ;;
    esac
    if [[ "${COUNTYIQ_EXPOSE_API_DOCS:-false}" != "false" ]]; then
        echo "Public API documentation must remain disabled in production" >&2
        return 1
    fi
    if [[ "${COUNTYIQ_ENABLE_RESTRICTED_DISTRESS:-false}" != "false" ]]; then
        echo "Restricted distress routes require a separate reviewed rollout" >&2
        return 1
    fi
    if [[ "${COUNTYIQ_BACKUP_BUCKET_LOCK_CONFIRMED:-false}" != "true" ]]; then
        echo "Confirm the private R2 backup bucket lock before production deployment" >&2
        return 1
    fi

    countyiq_validate_r2_backup_environment
}
