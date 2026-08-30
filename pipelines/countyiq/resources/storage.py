import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dagster import ConfigurableResource, get_dagster_logger


ArchivePayload = Union[bytes, str, dict, list]


class S3StorageResource(ConfigurableResource):
    """S3-compatible client for archiving raw pipeline responses.

    Production target is Cloudflare R2 (r2://countyiq-raw/<source>/<date>/...),
    configured via R2_ENDPOINT_URL + R2_ACCESS_KEY_ID + R2_SECRET_ACCESS_KEY.
    Without ``endpoint_url`` boto3 would silently target AWS S3 instead —
    that misconfiguration ran undetected for months, so ``archive`` logs the
    endpoint it's using.

    In local dev (no creds), logs a warning and skips the upload unless
    ``strict`` is set, in which case failures raise so the asset run fails
    visibly instead of silently dropping raw data.
    """

    bucket: str = "countyiq-raw"
    region: str = "auto"
    endpoint_url: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    strict: bool = False

    def _client(self):
        kwargs: dict = {"region_name": self.region}
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        if self.access_key_id and self.secret_access_key:
            kwargs["aws_access_key_id"] = self.access_key_id
            kwargs["aws_secret_access_key"] = self.secret_access_key
        return boto3.client("s3", **kwargs)

    def _handle_failure(self, log, message: str, exc: Exception) -> None:
        if self.strict:
            raise RuntimeError(f"{message}: {exc}") from exc
        log.warning(f"{message} ({exc}). Data not persisted.")

    def archive(
        self,
        source_path: str,
        data: ArchivePayload,
        filename: str = "response.json",
    ) -> None:
        """Archive raw data to object storage.

        Args:
            source_path: e.g. "arcgis/parcels"
            data: dict, list, str, or bytes to archive
            filename: file name within the date folder
        """
        log = get_dagster_logger()
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{source_path}/{date_str}/{filename}"

        if isinstance(data, (dict, list)):
            body = json.dumps(data, default=str).encode("utf-8")
        elif isinstance(data, str):
            body = data.encode("utf-8")
        else:
            body = data

        try:
            self._client().put_object(Bucket=self.bucket, Key=key, Body=body)
            log.info(
                f"Archived to {self.endpoint_url or 's3 (default AWS endpoint!)'}"
                f"/{self.bucket}/{key} ({len(body)} bytes)"
            )
        except (BotoCoreError, ClientError) as e:
            self._handle_failure(log, f"Archive of {key} failed", e)

    def archive_file(
        self,
        source_path: str,
        local_path: str,
        filename: str | None = None,
    ) -> None:
        """Archive a local file to object storage without loading it fully into memory."""
        log = get_dagster_logger()
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        resolved_name = filename or Path(local_path).name
        key = f"{source_path}/{date_str}/{resolved_name}"

        try:
            self._client().upload_file(local_path, self.bucket, key)
            size = os.path.getsize(local_path)
            log.info(
                f"Archived to {self.endpoint_url or 's3 (default AWS endpoint!)'}"
                f"/{self.bucket}/{key} ({size} bytes)"
            )
        except (BotoCoreError, ClientError) as e:
            self._handle_failure(log, f"Archive of {key} failed", e)


def make_s3_resource() -> S3StorageResource:
    strict_env = os.environ.get("COUNTYIQ_ARCHIVE_STRICT", "").strip().lower()
    return S3StorageResource(
        bucket=os.environ.get("S3_RAW_BUCKET", "countyiq-raw"),
        region=os.environ.get("AWS_DEFAULT_REGION", "auto"),
        endpoint_url=os.environ.get("R2_ENDPOINT_URL", ""),
        access_key_id=os.environ.get("R2_ACCESS_KEY_ID", ""),
        secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY", ""),
        strict=strict_env in {"1", "true", "yes", "on"},
    )
