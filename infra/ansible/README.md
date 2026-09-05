# CountyIQ VPS bootstrap

This playbook turns the fresh OVH Ubuntu 24.04 VPS into the production Docker
host. It deliberately exposes only key-authenticated SSH. Public application
traffic reaches Caddy through an outbound Cloudflare Tunnel, so ports 80 and
443 remain closed on the VPS.

Run from WSL:

```bash
cd infra/ansible
uvx --from ansible-core ansible-playbook playbooks/bootstrap.yml
```

The checked-in inventory contains only the public server address and the path
to the selected local SSH key. Neither value is a secret. Run the playbook a
second time after changes to verify idempotence.

The playbook does not clone or deploy the application. Release checkout,
secret rendering, database import, and application start are separate steps so
a base-system update cannot implicitly change production data.
