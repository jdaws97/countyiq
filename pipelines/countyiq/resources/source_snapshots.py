"""Optional Dagster input transport for manually acquired public source bundles."""

import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from dagster import AssetExecutionContext, ConfigurableResource, MetadataValue
from pydantic import PrivateAttr

from countyiq.lib.county_config import get_county_config
from countyiq.lib.http_retry import get_with_retry
from countyiq.lib.source_snapshots import (
    SourceBundle,
    fetch_arcgis,
    fetch_metadata,
    source_specs,
    utc_now,
)
from countyiq.resources.storage import S3StorageResource


class SourceSnapshotsResource(ConfigurableResource):
    bundle_id: str = ""
    manifest_sha256: str = ""
    _bundle: SourceBundle | None = PrivateAttr(default=None)
    _started_at: datetime | None = PrivateAttr(default=None)
    _attempt_id: str = PrivateAttr(default_factory=lambda: uuid4().hex)

    def snapshot_identity(self) -> str:
        return self.manifest_sha256 if self.bundle_id else self._attempt_id

    def acquisition_time(self) -> datetime:
        if self.bundle_id:
            return self._load_bundle().manifest.started_at
        if self._started_at is None:
            raise RuntimeError("Source acquisition has not started")
        return self._started_at

    def _load_bundle(self) -> SourceBundle:
        if self._bundle is None:
            root = Path(
                os.environ.get("COUNTYIQ_SOURCE_INBOX", "/opt/countyiq/source-inbox")
            )
            self._bundle = SourceBundle(root, self.bundle_id, self.manifest_sha256)
        return self._bundle

    def _read(self, key: str, context: AssetExecutionContext) -> bytes | dict:
        bundle = self._load_bundle()
        spec = source_specs()[key]
        if spec.asset != context.asset_key.to_user_string():
            raise ValueError("Snapshot source does not belong to the selected asset")
        latest = context.instance.get_latest_materialization_event(context.asset_key)
        if latest and latest.timestamp >= bundle.manifest.started_at.timestamp():
            raise ValueError(
                "This asset already materialized after snapshot acquisition began; acquire a new snapshot"
            )
        context.add_output_metadata(
            {
                "source_bundle_id": MetadataValue.text(self.bundle_id),
                "source_manifest_sha256": MetadataValue.text(self.manifest_sha256),
                "source_acquired_at": MetadataValue.text(
                    bundle.manifest.started_at.isoformat()
                ),
            }
        )
        return bundle.read(key)

    def arcgis(self, key: str, context: AssetExecutionContext) -> list[dict]:
        if self.bundle_id:
            return self._read(key, context)["features"]
        if self.manifest_sha256:
            raise ValueError("A manifest hash requires a snapshot bundle ID")
        self._started_at = self._started_at or utc_now()
        return fetch_arcgis(source_specs()[key])["features"]

    def metadata(self, key: str) -> dict:
        if self.bundle_id:
            return self._load_bundle().read(key)["metadata"]
        return fetch_metadata(source_specs()[key].url)

    def archive_receipt(
        self, s3: S3StorageResource, context: AssetExecutionContext
    ) -> None:
        """Keep acquisition provenance alongside the normal raw source archives."""
        if not self.bundle_id:
            return
        bundle = self._load_bundle()
        asset = context.asset_key.to_user_string()
        metadata = {}
        for key in bundle.manifest.entries:
            spec = source_specs()[key]
            if spec.asset == asset and spec.method == "arcgis_rest":
                metadata[key] = bundle.read(key)["metadata"]
        receipt = {
            "manifest": bundle.manifest.model_dump(mode="json"),
            "manifest_sha256": self.manifest_sha256,
            "asset": asset,
            "layer_metadata": metadata,
        }
        s3.archive(
            f"{get_county_config().s3_prefix}/source_snapshots/{self.bundle_id}",
            receipt,
            filename=f"{asset}.json",
        )

    def pdf(self, key: str, context: AssetExecutionContext) -> bytes:
        if self.bundle_id:
            return self._read(key, context)
        if self.manifest_sha256:
            raise ValueError("A manifest hash requires a snapshot bundle ID")
        self._started_at = self._started_at or utc_now()
        return get_with_retry(source_specs()[key].url, timeout=120).content
