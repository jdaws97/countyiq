"""Monorepo contracts that keep runtime modules and deployment authority separate."""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    return imports


def test_api_and_pipeline_packages_do_not_import_each_other() -> None:
    api_files = [REPO_ROOT / "api/main.py"]
    api_files += list((REPO_ROOT / "api/lib").rglob("*.py"))
    api_files += list((REPO_ROOT / "api/routes").rglob("*.py"))
    for path in api_files:
        forbidden = _top_level_imports(path) & {"countyiq", "dagster", "pipelines"}
        assert not forbidden, f"{path.relative_to(REPO_ROOT)} imports {forbidden}"

    for path in (REPO_ROOT / "pipelines/countyiq").rglob("*.py"):
        forbidden = _top_level_imports(path) & {"api"}
        assert not forbidden, f"{path.relative_to(REPO_ROOT)} imports {forbidden}"


def test_compose_enforces_credentials_networks_and_versioned_images() -> None:
    compose = yaml.safe_load(
        (REPO_ROOT / "docker/docker-compose.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    assert not services["postgres"].get("ports")
    api = services["api"]
    migration = services["migrate"]

    assert compose["name"] == "countyiq"
    assert api["image"] == "countyiq-api:${COUNTYIQ_IMAGE_TAG:-local}"
    assert migration["image"] == "countyiq-migrate:${COUNTYIQ_IMAGE_TAG:-local}"
    assert api["environment"]["DATABASE_USER"] == (
        "${DATABASE_API_USER:?DATABASE_API_USER must be set}"
    )

    api_forbidden = {
        "DATABASE_URL",
        "DATABASE_PIPELINE_PASSWORD",
        "OPENROUTER_API_KEY",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "SLACK_WEBHOOK_CRITICAL",
    }
    assert not (api_forbidden & set(api["environment"]))
    assert set(api["networks"]) == {"proxy", "database", "api-egress"}
    assert set(migration["networks"]) == {"database"}

    database_url_services = {
        name
        for name, service in services.items()
        if "DATABASE_URL" in (service.get("environment") or {})
    }
    assert database_url_services == {"migrate"}
    assert compose["volumes"]["postgres-data"]["name"] == ("countyiq-postgres-data")
    for service in services.values():
        assert service["logging"]["driver"] == "json-file"
        assert service["logging"]["options"] == {
            "max-size": "10m",
            "max-file": "5",
        }


def test_deploy_requires_quiesced_verified_backup_before_migration() -> None:
    deploy = (REPO_ROOT / "docker/deploy.sh").read_text(encoding="utf-8")
    stop_position = deploy.index("stop -t 60 api")
    backup_position = deploy.index('"$SCRIPT_DIR/backup.sh" --reason pre-deploy')
    migration_position = deploy.rindex('"${COMPOSE[@]}" run --rm migrate')

    assert stop_position < backup_position < migration_position
    assert "pg_stat_activity" in deploy
    assert "MIGRATION_STARTED=true" in deploy
    assert "persist_image_tag" in deploy
    assert "install-operation-units.sh" in deploy
    assert (
        deploy.index("backup_operation_units")
        < deploy.index('"$SCRIPT_DIR/install-operation-units.sh"')
        < deploy.index("RELEASE_RECORDED=true")
    )
    assert "restore_operation_units" in deploy
    assert "legacy Postgres volume" in deploy
    assert "COUNTYIQ_BACKUP_ID" in deploy
    assert "docker compose down" not in deploy
    assert "down -v" not in deploy
    assert "volume rm" not in deploy

    backup = (REPO_ROOT / "docker/backup.sh").read_text(encoding="utf-8")
    manifest_upload = backup.index(
        'rclone copyto --immutable "$MANIFEST_FILE" '
        '"${REMOTE_MANIFEST_PATH}/${manifest_name}"'
    )
    assert backup.index("rclone check") < manifest_upload
    assert "rclone delete" not in backup
    assert "A manifest is uploaded last" in backup
    assert "COUNTYIQ_BACKUP_ID=" in backup


def test_production_environment_validation_fails_closed() -> None:
    admin_password = "a" * 40
    environment = {
        **os.environ,
        "DATABASE_NAME": "countyiq",
        "DATABASE_USER": "dagster_admin",
        "DATABASE_PASSWORD": admin_password,
        "DATABASE_URL": (
            f"postgresql://dagster_admin:{admin_password}@postgres:5432/countyiq"
        ),
        "DATABASE_PIPELINE_USER": "countyiq_pipeline",
        "DATABASE_PIPELINE_PASSWORD": "b" * 40,
        "DATABASE_API_USER": "countyiq_api",
        "DATABASE_API_PASSWORD": "c" * 40,
        "DOMAIN": "countyiq.test",
        "COUNTYIQ_TRUSTED_HOSTS": "app.countyiq.test",
        "CLOUDFLARE_TUNNEL_TOKEN": "t" * 128,
        "COUNTYIQ_AUTH_PROVIDER": "cloudflare_access",
        "COUNTYIQ_ACCESS_ISSUER": "https://team.cloudflareaccess.com",
        "COUNTYIQ_ACCESS_AUD": "reviewed-app-audience",
        "COUNTYIQ_APP_URL": "https://app.countyiq.test",
        "COUNTYIQ_WORKSPACE_ORIGINS": "https://app.countyiq.test",
        "COUNTYIQ_EXPOSE_API_DOCS": "false",
        "COUNTYIQ_ARCHIVE_STRICT": "true",
        "COUNTYIQ_ENABLE_RESTRICTED_DISTRESS": "false",
        "COUNTYIQ_BACKUP_BUCKET_LOCK_CONFIRMED": "true",
        "R2_ACCESS_KEY_ID": "test-raw-access",
        "R2_SECRET_ACCESS_KEY": "test-raw-secret",
        "S3_RAW_BUCKET": "countyiq-raw",
        "COUNTYIQ_BACKUP_R2_ACCESS_KEY_ID": "test-backup-access",
        "COUNTYIQ_BACKUP_R2_SECRET_ACCESS_KEY": "test-backup-secret",
        "R2_ENDPOINT_URL": (
            "https://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.r2.cloudflarestorage.com"
        ),
        "COUNTYIQ_BACKUP_R2_BUCKET": "countyiq-backups",
    }
    command = (
        "source docker/lib/operations.sh; countyiq_validate_production_environment"
    )
    valid = subprocess.run(
        ["bash", "-c", command],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert valid.returncode == 0, valid.stderr

    environment["COUNTYIQ_PASS2_ENABLED"] = "true"
    paid_pass = subprocess.run(
        ["bash", "-c", command],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert paid_pass.returncode != 0
    assert "COUNTYIQ_PASS2_ENABLED must remain false" in paid_pass.stderr


def test_restore_drill_targets_only_disposable_sibling_databases() -> None:
    restore = (REPO_ROOT / "docker/restore-drill.sh").read_text(encoding="utf-8")
    assert 'PRIMARY_DRILL_DATABASE="${PRIMARY_DATABASE}_restore_drill"' in restore
    assert "countyiq_validate_restore_targets" in restore
    create_position = restore.index("docker exec countyiq-postgres createdb")
    assert (
        restore.index('CREATED_DRILL_DATABASE="$PRIMARY_DRILL_DATABASE"')
        > create_position
    )
    assert '"$CREATED_DRILL_DATABASE"' in restore
    assert "pg_restore --clean" not in restore
