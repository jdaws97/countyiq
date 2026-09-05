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

countyiq_configure_r2_raw_remote() {
    : "${R2_ACCESS_KEY_ID:?R2_ACCESS_KEY_ID must be set for raw archives}"
    : "${R2_SECRET_ACCESS_KEY:?R2_SECRET_ACCESS_KEY must be set for raw archives}"
    : "${R2_ENDPOINT_URL:?R2_ENDPOINT_URL must be set for raw archives}"
    : "${S3_RAW_BUCKET:?S3_RAW_BUCKET must be set}"

    if ! [[ "$R2_ENDPOINT_URL" =~ ^https://[0-9a-f]{32}(\.(eu|us|fedramp))?\.r2\.cloudflarestorage\.com/?$ ]]; then
        echo "R2_ENDPOINT_URL must be the reviewed Cloudflare R2 HTTPS account endpoint" >&2
        return 1
    fi
    if ! [[ "$S3_RAW_BUCKET" =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]]; then
        echo "S3_RAW_BUCKET is not a valid bucket name" >&2
        return 1
    fi

    export RCLONE_CONFIG_COUNTYIQRAW_TYPE=s3
    export RCLONE_CONFIG_COUNTYIQRAW_PROVIDER=Cloudflare
    export RCLONE_CONFIG_COUNTYIQRAW_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
    export RCLONE_CONFIG_COUNTYIQRAW_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
    export RCLONE_CONFIG_COUNTYIQRAW_ENDPOINT="$R2_ENDPOINT_URL"
    export RCLONE_CONFIG_COUNTYIQRAW_ACL=private
    export RCLONE_CONFIG_COUNTYIQRAW_NO_CHECK_BUCKET=true
    COUNTYIQ_RAW_REMOTE="countyiqraw:${S3_RAW_BUCKET}"
    export COUNTYIQ_RAW_REMOTE
}

# DOMAIN serves marketing only. All product UI/API traffic uses app.DOMAIN.
countyiq_validate_account_environment() {
    local provider="${COUNTYIQ_AUTH_PROVIDER:-disabled}"
    local sync="${COUNTYIQ_WATCH_SYNC_ENABLED:-false}"
    case "${sync,,}" in
        true|1|yes|on) sync=true ;;
        false|0|no|off) sync=false ;;
        *) echo "COUNTYIQ_WATCH_SYNC_ENABLED must be a boolean" >&2; return 1 ;;
    esac
    case "$provider" in
        disabled)
            if [ "$sync" = true ]; then
                echo "Saved account work requires a configured authentication provider" >&2
                return 1
            fi
            return 0
            ;;
        cloudflare_access) ;;
        *) echo "Unsupported COUNTYIQ_AUTH_PROVIDER" >&2; return 1 ;;
    esac
    if ! [[ "${COUNTYIQ_ACCESS_ISSUER:-}" =~ ^https://[a-z0-9-]+\.cloudflareaccess\.com$ ]]; then
        echo "COUNTYIQ_ACCESS_ISSUER must identify the reviewed Cloudflare Access team" >&2
        return 1
    fi
    if [ -z "${COUNTYIQ_ACCESS_AUD:-}" ] || [[ "$COUNTYIQ_ACCESS_AUD" == *[[:space:]]* ]]         || [[ "$COUNTYIQ_ACCESS_AUD" == *CHANGE_ME* ]] || [[ "$COUNTYIQ_ACCESS_AUD" == *'<'* ]]; then
        echo "COUNTYIQ_ACCESS_AUD must be the non-placeholder application audience" >&2
        return 1
    fi
    if [ "${COUNTYIQ_APP_URL:-}" != "https://app.${DOMAIN}" ]         || [ "${COUNTYIQ_WORKSPACE_ORIGINS:-}" != "https://app.${DOMAIN}" ]; then
        echo "Account app URL and workspace origin must match https://app.DOMAIN" >&2
        return 1
    fi
}

countyiq_prepare_tunnel_secret() {
    local destination="$1"
    local directory
    local temporary
    if [[ "$destination" != /* ]] || [ -L "$destination" ]; then
        echo "Tunnel secret must use an absolute non-symlink file path" >&2
        return 1
    fi
    : "${CLOUDFLARE_TUNNEL_TOKEN:?CLOUDFLARE_TUNNEL_TOKEN must be set}"
    directory="$(dirname -- "$destination")"
    install -d -o root -g root -m 700 "$directory"
    temporary="$(mktemp "$directory/.cloudflared-token.XXXXXX")"
    printf '%s' "$CLOUDFLARE_TUNNEL_TOKEN" > "$temporary"
    chown root:65532 "$temporary"
    chmod 440 "$temporary"
    mv -f -- "$temporary" "$destination"
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
    : "${CLOUDFLARE_TUNNEL_TOKEN:?CLOUDFLARE_TUNNEL_TOKEN must be set}"
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
        *",app.${DOMAIN},"*) ;;
        *)
            echo "COUNTYIQ_TRUSTED_HOSTS must contain app.DOMAIN exactly" >&2
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
    if [ "${#CLOUDFLARE_TUNNEL_TOKEN}" -lt 100 ]; then
        echo "CLOUDFLARE_TUNNEL_TOKEN does not look like a remotely managed tunnel token" >&2
        return 1
    fi

    countyiq_validate_account_environment || return 1
    if [ "${COUNTYIQ_AUTH_PROVIDER:-disabled}" != "cloudflare_access" ]; then
        echo "Production app access requires cloudflare_access during the private alpha" >&2
        return 1
    fi
    countyiq_validate_r2_backup_environment
}

# A redirect to Access or a 200 HTML error page is not application readiness.
# Optional credentials belong in a root-owned curl config, never argv/logs.
countyiq_check_public_readiness() {
    local url="$1"
    local response status body
    local -a options=()
    if [ -n "${COUNTYIQ_PUBLIC_READY_CURL_CONFIG:-}" ]; then
        countyiq_validate_secret_file "$COUNTYIQ_PUBLIC_READY_CURL_CONFIG" || return 1
        options+=(--config "$COUNTYIQ_PUBLIC_READY_CURL_CONFIG")
    fi
    response="$(curl "${options[@]}" --fail --silent --show-error --max-time 20 \
        --write-out $'\n%{http_code}' "$url")" || return 1
    status="${response##*$'\n'}"
    body="${response%$'\n'*}"
    body="${body//[[:space:]]/}"
    if [ "$status" != "200" ] || [ "$body" != '{"status":"ok"}' ]; then
        echo "Public readiness did not return HTTP 200 with the expected API health response; check Access authentication and the origin" >&2
        return 1
    fi
}

# Every live/temporary database must be distinct, including cross-pair names.
countyiq_validate_restore_targets() {
    local name
    local -A seen=()
    for name in "$@"; do
        countyiq_require_identifier "$name" "restore database" || return 1
        if [ -n "${seen[$name]:-}" ]; then
            echo "Live and restore-drill database names must all be distinct" >&2
            return 1
        fi
        seen[$name]=1
    done
}

countyiq_require_cost_guard_clear() {
    if [ -f "${COUNTYIQ_COST_GUARD_DIR:-/var/lib/countyiq/cost-guard}/tripped" ]; then
        echo "CountyIQ cost stop is latched; refusing to start services" >&2
        return 1
    fi
}

# The caller passes its Compose argv and enables pipefail. A failed Alembic
# invocation must never be converted into a successful 'base' revision.
countyiq_read_schema_revision() {
    local revision
    revision="$("$@" run --rm migrate \
        alembic -c /opt/pipelines/alembic.ini current 2>/dev/null \
        | tail -n 1)" || return 1
    printf '%s\n' "${revision:-base}"
}

# A deployment retains this lock through migration and receipt promotion. Its
# pre-deploy backup inherits fd 9 and must reuse it, not reopen/self-deadlock.
countyiq_lock_backup_operations() {
    local lock_path="${1:-/var/lock/countyiq-backup.lock}"
    local held_path expected_path
    expected_path="$(readlink -f "$lock_path")" || return 1
    held_path="$(readlink "/proc/$$/fd/9" 2>/dev/null || true)"
    if [ "$held_path" != "$expected_path" ]; then
        exec 9>"$lock_path"
    fi
    if ! flock -n 9; then
        echo "Another CountyIQ backup or deployment is using the database snapshot boundary" >&2
        return 1
    fi
}

# Read-only checks of the actual host, separate from portable Compose validation.
countyiq_validate_host() {
    local effective setting guard_dir
    guard_dir="${COUNTYIQ_COST_GUARD_DIR:-/var/lib/countyiq/cost-guard}"
    countyiq_require_command sshd || return 1
    countyiq_require_command setpriv || return 1
    effective="$(sshd -T)" || return 1
    for setting in 'passwordauthentication no' 'kbdinteractiveauthentication no' 'permitrootlogin no' 'pubkeyauthentication yes'; do
        if ! grep -Fxq "$setting" <<< "$effective"; then
            echo "Host SSH policy is not effective: expected $setting. Apply the reviewed Ansible bootstrap before deployment." >&2
            return 1
        fi
    done
    if [ ! -d "$guard_dir" ] || [ -L "$guard_dir" ] \
        || [ "$(stat -c '%u:%a' "$guard_dir")" != '0:755' ]; then
        echo "Cost-guard directory must be root-owned mode 755: $guard_dir" >&2
        return 1
    fi
    if ! setpriv --reuid=10001 --regid=10001 --clear-groups \
        sh -c 'test -x "$1" && ! test -w "$1"' host-guard "$guard_dir"; then
        echo "Application UID 10001 must traverse, but not write, the cost-guard directory" >&2
        return 1
    fi
}
