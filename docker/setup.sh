#!/usr/bin/env bash
# Compatibility entrypoint retained to prevent use of the retired mutable setup.

set -euo pipefail

echo "docker/setup.sh is retired." >&2
echo "Bootstrap the VPS with infra/ansible, publish SOPS secrets with" >&2
echo "docker/publish-production-env.sh, then run docker/deploy.sh." >&2
exit 2
