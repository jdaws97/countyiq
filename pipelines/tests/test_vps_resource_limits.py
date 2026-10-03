"""Bounded local execution and VPS service resource limits."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


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
        "caddy": "256m",
    }
    for service, limit in expected.items():
        assert compose["services"][service]["mem_limit"] == limit
