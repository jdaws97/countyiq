"""Single-host controls that prevent Dagster work from starving the product."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dagster_queues_only_one_run():
    config = yaml.safe_load((REPO_ROOT / "pipelines/dagster.yaml").read_text())
    assert config["run_queue"]["max_concurrent_runs"] == 1


def test_dagster_storage_paths_are_explicit_per_environment():
    config = yaml.safe_load((REPO_ROOT / "pipelines/dagster.yaml").read_text())
    assert config["local_artifact_storage"]["config"]["base_dir"] == {
        "env": "DAGSTER_LOCAL_ARTIFACT_STORAGE_DIR"
    }
    assert config["compute_logs"]["config"]["base_dir"] == {
        "env": "DAGSTER_COMPUTE_LOGS_DIR"
    }

    compose = yaml.safe_load((REPO_ROOT / "docker/docker-compose.yml").read_text())
    environment = compose["x-dagster-common"]["environment"]
    assert environment["DAGSTER_LOCAL_ARTIFACT_STORAGE_DIR"] == (
        "/opt/dagster/storage/artifacts"
    )
    assert environment["DAGSTER_COMPUTE_LOGS_DIR"] == (
        "/opt/dagster/storage/compute_logs"
    )


def test_dagster_temp_directory_uses_persistent_storage_volume():
    compose = yaml.safe_load((REPO_ROOT / "docker/docker-compose.yml").read_text())
    dagster_common = compose["x-dagster-common"]
    temp_directory = dagster_common["environment"]["TMPDIR"]

    assert temp_directory == "/opt/dagster/storage"
    assert f"dagster-storage:{temp_directory}" in dagster_common["volumes"]
    assert compose["volumes"]["dagster-storage"]["name"] == "countyiq-dagster-storage"


def test_every_registered_job_uses_one_step_executor():
    from countyiq.definitions import defs

    repository = defs.get_repository_def()
    for unresolved_job in defs.jobs:
        job = repository.get_job(unresolved_job.name)
        assert job.executor_def.name == "bounded_multiprocess_executor"
        resolved = job.executor_def.config_schema.resolve_config({})
        assert resolved.success
        assert resolved.value["config"]["max_concurrent"] == 1


def test_runtime_services_have_memory_containment():
    compose = yaml.safe_load((REPO_ROOT / "docker/docker-compose.yml").read_text())
    expected = {
        "postgres": "2g",
        "api": "768m",
        "dagster-webserver": "768m",
        "dagster-daemon": "3g",
        "caddy": "256m",
    }
    for service, limit in expected.items():
        assert compose["services"][service]["mem_limit"] == limit
