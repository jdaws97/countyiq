"""Every `county.<attr>` access in pipeline code must be a real CountyConfig field.

CountyConfig is a frozen dataclass, so a typo'd or missing attribute raises
AttributeError at runtime — usually deep inside a weekly asset run, after the
expensive fetch has already happened (this exact bug shipped in parcels_arcgis).
This test catches the whole class statically by AST-scanning the codebase.
"""

import ast
import dataclasses
from pathlib import Path

from countyiq.lib.county_config import CountyConfig

PIPELINE_ROOT = Path(__file__).resolve().parents[1] / "countyiq"
SCAN_DIRS = [PIPELINE_ROOT / "assets", PIPELINE_ROOT / "lib", PIPELINE_ROOT / "jobs"]

# Variable names conventionally bound to get_county_config() results.
CONFIG_VAR_NAMES = {"county", "county_config"}


def _config_attr_accesses(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(), filename=str(path))
    hits = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in CONFIG_VAR_NAMES
        ):
            hits.append((node.lineno, node.attr))
        # Direct chained access: get_county_config().attr
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "get_county_config"
        ):
            hits.append((node.lineno, node.attr))
    return hits


def test_all_county_config_attribute_accesses_exist():
    valid_fields = {f.name for f in dataclasses.fields(CountyConfig)}
    violations = []
    for scan_dir in SCAN_DIRS:
        for path in sorted(scan_dir.rglob("*.py")):
            for lineno, attr in _config_attr_accesses(path):
                if attr not in valid_fields:
                    violations.append(
                        f"{path.relative_to(PIPELINE_ROOT.parent)}:{lineno} -> county.{attr}"
                    )
    assert not violations, (
        "Attribute(s) accessed on CountyConfig that do not exist as dataclass fields:\n"
        + "\n".join(violations)
    )


def test_scan_found_accesses():
    # Guard against the scanner silently matching nothing (e.g. after a rename).
    total = sum(
        len(_config_attr_accesses(p)) for d in SCAN_DIRS for p in d.rglob("*.py")
    )
    assert total > 50, f"expected many county.<attr> accesses, found {total}"
