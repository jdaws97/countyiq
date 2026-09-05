# Production secrets

`production.sops.env` and `cloudflare-iac.sops.env` are the only environment
artifacts in this directory that may be committed. SOPS encrypts them to the
public half of `jdawskey`; the private key never belongs in Git, Cloudflare,
the VPS, or an OpenTofu state file.

Create the Cloudflare/OpenTofu file from hidden prompts after creating the
scoped IaC token and state-bucket R2 token:

```bash
infra/secrets/bootstrap-cloudflare-iac.sh
```

After OpenTofu creates the Tunnel and application buckets, create independent
object-read/write R2 tokens scoped to `countyiq-raw` and `countyiq-backups`.
Then generate the production environment from hidden prompts:

```bash
infra/secrets/bootstrap-production.sh
```

The production helper prompts for the raw and backup R2 key pairs and retrieves
the Tunnel token automatically through the encrypted OpenTofu credentials.
Run it in a local WSL terminal; secret inputs are not echoed.

The production helper generates independent 64-character PostgreSQL admin,
pipeline-writer, and API-reader passwords locally. Both helpers stream
plaintext directly into SOPS and never create a plaintext environment file.
They refuse to replace an existing encrypted file unless `--replace` is
specified for an intentional credential rotation.

Edit it without producing a repository plaintext file:

```bash
SOPS_AGE_SSH_PRIVATE_KEY_FILE=/home/jdaws/.ssh/jdawskey \
  sops --input-type dotenv --output-type dotenv \
  infra/secrets/production.sops.env
```

Publish it atomically to the VPS with `docker/publish-production-env.sh`.
That script validates the critical fail-closed settings and streams plaintext
over strict host-key-checked SSH into `/etc/countyiq/production.env` mode 0600.

`cloudflare-iac.sops.env` contains only `CLOUDFLARE_API_TOKEN` and the
state-bucket `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`. Run OpenTofu only
through `infra/cloudflare/tofu-sops.sh`; it injects those values into one child
process and rejects `destroy`.
