#!/usr/bin/env bash
# Reject unreviewed Cloudflare product classes before they can enter a plan.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# JSON configuration is valid OpenTofu input but is outside this text checker.
# Reject it rather than silently excluding it from the resource allowlist.
if compgen -G "$SCRIPT_DIR/*.tf.json" >/dev/null; then
    echo "JSON Terraform configuration requires a reviewed cost-policy parser" >&2
    exit 1
fi

if grep -Eq '^[[:space:]]*module[[:space:]]+"' "$SCRIPT_DIR"/*.tf; then
    echo "Cloudflare modules are prohibited because they can hide metered resources" >&2
    exit 1
fi

mapfile -t resource_types < <(
    sed -nE 's/^[[:space:]]*resource[[:space:]]+"([^"]+)".*/\1/p' "$SCRIPT_DIR"/*.tf | sort -u
)
for resource_type in "${resource_types[@]}"; do
    case "$resource_type" in
        cloudflare_dns_record|\
        cloudflare_r2_bucket|\
        cloudflare_r2_bucket_lifecycle|\
        cloudflare_r2_bucket_lock|\
        cloudflare_zero_trust_access_application|\
        cloudflare_zero_trust_access_identity_provider|\
        cloudflare_zero_trust_access_service_token|\
        cloudflare_zero_trust_organization|\
        cloudflare_zero_trust_tunnel_cloudflared|\
        cloudflare_zero_trust_tunnel_cloudflared_config|\
        random_bytes)
            ;;
        *)
            echo "Cloudflare cost policy rejects resource type: $resource_type" >&2
            exit 1
            ;;
    esac
done

standard_bucket_count="$(
    grep -hE '^[[:space:]]*storage_class[[:space:]]*=[[:space:]]*"Standard"' \
        "$SCRIPT_DIR"/*.tf | wc -l
)"
if [ "$standard_bucket_count" -ne 2 ]; then
    echo "Exactly two Standard-class R2 buckets are required" >&2
    exit 1
fi
if ! grep -Fxq 'database_backup_retention_days = 7' "$SCRIPT_DIR/production.auto.tfvars"; then
    echo "Production database backup retention must remain seven days" >&2
    exit 1
fi

echo "Cloudflare cost policy OK: only reviewed free-path resource classes are present."
