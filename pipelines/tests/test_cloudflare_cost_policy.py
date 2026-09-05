"""The source-level cost guard must not silently ignore valid file variants."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("filename,contents", [
    ("extra.tf", '  resource "cloudflare_workers_script" "unexpected" {}\n'),
    ("extra.tf.json", '{"resource":{"cloudflare_workers_script":{"unexpected":{}}}}'),
])
def test_cost_policy_rejects_unreviewed_resource_formats(tmp_path, filename, contents):
    directory = ROOT / "infra/cloudflare"
    for source in [*directory.glob("*.tf"), directory / "production.auto.tfvars", directory / "check-cost-policy.sh"]:
        shutil.copyfile(source, tmp_path / source.name)
    baseline = subprocess.run(["bash", str(tmp_path / "check-cost-policy.sh")], capture_output=True, text=True)
    assert baseline.returncode == 0, baseline.stderr
    (tmp_path / filename).write_text(contents)
    result = subprocess.run(["bash", str(tmp_path / "check-cost-policy.sh")], capture_output=True, text=True)
    assert result.returncode != 0, "an unreviewed resource escaped the cost allowlist"
