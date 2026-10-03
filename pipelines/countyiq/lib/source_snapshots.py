"""Portable, bounded source snapshots shared by local acquisition and VPS ingestion.

Only the named public feeds below are supported. A snapshot is raw evidence,
never a database dump; normal assets retain authorization, parsing and SCD2.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests
from pydantic import BaseModel, ConfigDict, Field

from countyiq.lib.arcgis_client import query_all_features
from countyiq.lib.county_config import get_county_config

SNAPSHOT_VERSION = 1
MAX_PAYLOAD_BYTES = 100 * 1024 * 1024
MAX_BUNDLE_BYTES = 300 * 1024 * 1024
MAX_AGE = timedelta(hours=24)


@dataclass(frozen=True)
class SourceSpec:
    key: str
    asset: str
    source_key: str
    url: str
    method: str = "arcgis_rest"
    where: str = "1=1"
    spatial_filter: dict = field(default_factory=dict)


def source_specs() -> dict[str, SourceSpec]:
    county = get_county_config()
    specs = [
        SourceSpec(
            "penndot_roads",
            "penndot_roads_arcgis",
            "penndot_open_data",
            county.penndot_roads_url,
            where=f"CTY_CODE='{county.penndot_roads_cty_code}'",
        ),
        SourceSpec(
            "traffic_counts",
            "traffic_counts_arcgis",
            "penndot_open_data",
            county.traffic_counts_url,
            where=f"CTY_CODE='{county.traffic_counts_cty_code}'",
        ),
        SourceSpec(
            "storage_tanks",
            "pa_dep_environmental_diligence",
            "pa_dep_open_data",
            county.pa_dep_storage_tanks_url,
            where=f"FACILITY_COUNTY = '{county.name.removesuffix(' County')}'",
        ),
        SourceSpec(
            "cleanup_sites",
            "pa_dep_environmental_diligence",
            "pa_dep_open_data",
            county.pa_dep_cleanup_sites_url,
            spatial_filter={
                "geometry": ",".join(str(value) for value in county.pa_dep_query_bbox),
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
            },
        ),
        SourceSpec(
            "tax_claims",
            "tax_claims",
            "tax_claims",
            county.tax_claims_pdf_url,
            method="official_pdf",
        ),
    ]
    project_layers = (
        county.penndot_projects_layers if county.penndot_projects_url else ()
    )
    for layer in project_layers:
        specs.append(
            SourceSpec(
                f"penndot_projects_{layer}",
                "penndot_projects_arcgis",
                "penndot_open_data",
                f"{county.penndot_projects_url}/{layer}",
                where=f"COUNTY_NAME='{county.penndot_projects_county_filter}'",
            )
        )
    return {
        spec.key: spec
        for spec in specs
        if spec.url
        and (spec.source_key != "pa_dep_open_data" or county.pa_dep_query_bbox)
    }


def fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def contract_fingerprint() -> str:
    return fingerprint({key: asdict(spec) for key, spec in source_specs().items()})


def utc_now() -> datetime:
    return datetime.now(UTC)


def require_recent(timestamp: datetime, *, now: datetime | None = None) -> None:
    now = now or utc_now()
    if timestamp.tzinfo is None or not now - MAX_AGE <= timestamp <= now + timedelta(
        minutes=5
    ):
        raise ValueError(
            "Snapshot timestamp must be timezone-aware and within the last 24 hours"
        )


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SnapshotEntry(StrictModel):
    request: dict
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_count: int = Field(gt=0, le=MAX_PAYLOAD_BYTES)
    record_count: int | None = Field(default=None, ge=0)


class AcquisitionPermit(StrictModel):
    issued_at: datetime
    contract: str = Field(pattern=r"^[0-9a-f]{64}$")
    keys: list[str]
    policy_receipts: dict[str, str]

    def validate_for_acquisition(self) -> None:
        require_recent(self.issued_at)
        specs = source_specs()
        if (
            self.contract != contract_fingerprint()
            or not self.keys
            or len(self.keys) != len(set(self.keys))
            or not set(self.keys) <= specs.keys()
        ):
            raise ValueError("Acquisition permit does not match the configured sources")
        required_policies = {specs[key].source_key for key in self.keys}
        if set(self.policy_receipts) != required_policies or any(
            not re.fullmatch(r"[0-9a-f]{64}", value)
            for value in self.policy_receipts.values()
        ):
            raise ValueError("Acquisition permit is missing source policy receipts")


class SnapshotManifest(StrictModel):
    version: int
    bundle_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    contract: str = Field(pattern=r"^[0-9a-f]{64}$")
    started_at: datetime
    completed_at: datetime
    permit: AcquisitionPermit
    entries: dict[str, SnapshotEntry]


def read_bounded(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError(
            f"Snapshot file is absent, a link, or exceeds its size limit: {path.name}"
        )
    with path.open("rb") as source:
        payload = source.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("Snapshot file grew beyond its size limit")
    return payload


def validate_arcgis(payload: dict) -> list[dict]:
    features = payload.get("features")
    count = payload.get("count")
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict) or "error" in metadata:
        raise ValueError("ArcGIS snapshot has invalid layer metadata")
    if (
        type(count) is not int
        or not isinstance(features, list)
        or count != len(features)
    ):
        raise ValueError(
            "ArcGIS snapshot count disagrees with its complete feature list"
        )
    oid_field = metadata.get("objectIdField") or next(
        (
            item["name"]
            for item in metadata.get("fields", [])
            if item.get("type") == "esriFieldTypeOID"
        ),
        None,
    )
    if not oid_field:
        raise ValueError("ArcGIS metadata must identify its object ID field")
    identifiers = []
    for feature in features:
        if not isinstance(feature, dict) or not isinstance(
            feature.get("attributes"), dict
        ):
            raise TypeError("ArcGIS feature is missing its attributes")
        identifier = feature["attributes"].get(oid_field)
        if type(identifier) is not int:
            raise ValueError("ArcGIS feature is missing a numeric object ID")
        identifiers.append(identifier)
    if len(set(identifiers)) != count:
        raise ValueError("ArcGIS snapshot contains duplicate object IDs")
    return features


def fetch_metadata(url: str) -> dict:
    response = requests.get(url, params={"f": "json"}, timeout=60)
    response.raise_for_status()
    metadata = response.json()
    if (
        not isinstance(metadata, dict)
        or "error" in metadata
        or not metadata.get("fields")
    ):
        raise ValueError("ArcGIS returned invalid layer metadata")
    return metadata


def fetch_arcgis(spec: SourceSpec) -> dict:
    metadata = fetch_metadata(spec.url)
    params = {
        "where": spec.where,
        "f": "json",
        "returnCountOnly": "true",
        **spec.spatial_filter,
    }

    def fetch_count() -> int:
        response = requests.get(f"{spec.url}/query", params=params, timeout=60)
        response.raise_for_status()
        result = response.json()
        if (
            not isinstance(result, dict)
            or "error" in result
            or type(result.get("count")) is not int
        ):
            raise ValueError("ArcGIS returned an invalid source count")
        return result["count"]

    before = fetch_count()
    features = query_all_features(
        spec.url,
        where=spec.where,
        out_fields="*",
        out_sr=4326,
        batch_size=1000,
        extra_params=spec.spatial_filter,
    )
    after = fetch_count()
    if before != after:
        raise ValueError("ArcGIS count changed during acquisition; retry the snapshot")
    payload = {"metadata": metadata, "count": after, "features": features}
    validate_arcgis(payload)
    return payload


class SourceBundle:
    def __init__(self, root: Path, bundle_id: str, manifest_sha256: str):
        if not re.fullmatch(r"[0-9a-f]{32}", bundle_id):
            raise ValueError("Invalid snapshot bundle ID")
        if not re.fullmatch(r"[0-9a-f]{64}", manifest_sha256):
            raise ValueError("A trusted manifest SHA-256 is required")
        self.directory = root / bundle_id
        if self.directory.is_symlink() or not self.directory.resolve().is_relative_to(
            root.resolve()
        ):
            raise ValueError("Snapshot directory escaped the configured inbox")
        raw = read_bounded(self.directory / "manifest.json", 128 * 1024)
        if hashlib.sha256(raw).hexdigest() != manifest_sha256:
            raise ValueError("Snapshot manifest hash mismatch")
        self.manifest = SnapshotManifest.model_validate_json(raw)
        manifest = self.manifest
        if (
            manifest.version != SNAPSHOT_VERSION
            or manifest.bundle_id != bundle_id
            or manifest.contract != contract_fingerprint()
        ):
            raise ValueError(
                "Snapshot identity, version or county source contract mismatch"
            )
        require_recent(manifest.started_at)
        require_recent(manifest.completed_at)
        manifest.permit.validate_for_acquisition()
        if manifest.permit.issued_at > manifest.started_at:
            raise ValueError("Acquisition started before the source policy check")
        if manifest.completed_at < manifest.started_at:
            raise ValueError("Snapshot completed before acquisition started")
        specs = source_specs()
        keys = set(manifest.entries)
        if keys != set(manifest.permit.keys):
            raise ValueError("Snapshot sources do not match the acquisition permit")
        if not keys or not keys <= specs.keys():
            raise ValueError("Snapshot includes unknown or missing sources")
        self.assets = {specs[key].asset for key in keys}
        expected = {key for key, spec in specs.items() if spec.asset in self.assets}
        if keys != expected:
            raise ValueError(
                "Snapshot must include every layer required by each selected asset"
            )
        if (
            sum(entry.byte_count for entry in manifest.entries.values())
            > MAX_BUNDLE_BYTES
        ):
            raise ValueError("Snapshot exceeds the total byte limit")
        expected_files = {"manifest.json", *(f"{key}.payload" for key in keys)}
        if {path.name for path in self.directory.iterdir()} != expected_files:
            raise ValueError("Snapshot directory contains unexpected files")
        # Validate all payloads before any selected asset can write to staging.
        for key in keys:
            if manifest.entries[key].request != asdict(specs[key]):
                raise ValueError(
                    "Snapshot URL or county query does not match the configured source"
                )
            self.read(key)

    def read(self, key: str) -> bytes | dict:
        entry = self.manifest.entries[key]
        body = read_bounded(self.directory / f"{key}.payload", MAX_PAYLOAD_BYTES)
        if (
            len(body) != entry.byte_count
            or hashlib.sha256(body).hexdigest() != entry.sha256
        ):
            raise ValueError(f"Snapshot payload hash or size mismatch: {key}")
        if source_specs()[key].method == "official_pdf":
            if not body.startswith(b"%PDF-") or b"%%EOF" not in body[-4096:]:
                raise ValueError("Snapshot PDF is incomplete or invalid")
            return body
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise TypeError("Snapshot payload must be an object")
        features = validate_arcgis(payload)
        if len(features) != entry.record_count:
            raise ValueError("Snapshot manifest record count mismatch")
        return payload
