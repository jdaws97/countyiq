import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Union
from uuid import uuid4

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
    local_archive_dir: str = ""
    cost_guard_file: str = ""

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

    def _local_destination(self, source_path: str, filename: str) -> Path:
        root = Path(self.local_archive_dir).expanduser().resolve()
        relative = Path(source_path) / datetime.now(timezone.utc).strftime("%Y-%m-%d") / filename
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Local archive path must remain beneath its configured root")
        destination = (root / relative).resolve()
        if not destination.is_relative_to(root):
            raise ValueError("Local archive path escaped its configured root")
        return destination

    def _write_local_bytes(self, destination: Path, body: bytes) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            dir=destination.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(body)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, destination)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    def _copy_local_file(self, destination: Path, local_path: str) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            dir=destination.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with open(local_path, "rb") as source, os.fdopen(descriptor, "wb") as output:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, destination)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    def _r2_write_allowed(self, log) -> bool:
        if not self.cost_guard_file or not Path(self.cost_guard_file).exists():
            return True
        message = (
            "Cloudflare R2 write blocked because the CountyIQ cost guard is tripped"
        )
        if self.strict:
            raise RuntimeError(message)
        log.warning(message)
        return False

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
        # Each attempt gets an immutable object key: R2 locks reject even an
        # identical overwrite when an asset is rerun on the same day.
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{source_path}/{date_str}/{uuid4().hex}/{filename}"

        if isinstance(data, (dict, list)):
            body = json.dumps(data, default=str).encode("utf-8")
        elif isinstance(data, str):
            body = data.encode("utf-8")
        else:
            body = data

        try:
            if self.local_archive_dir:
                destination = self._local_destination(source_path, filename)
                self._write_local_bytes(destination, body)
                log.info(f"Archived locally to {destination} ({len(body)} bytes)")
                return
            if not self._r2_write_allowed(log):
                return
            self._client().put_object(Bucket=self.bucket, Key=key, Body=body)
            log.info(
                f"Archived to {self.endpoint_url or 's3 (default AWS endpoint!)'}"
                f"/{self.bucket}/{key} ({len(body)} bytes)"
            )
        except (BotoCoreError, ClientError, OSError, ValueError) as e:
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
        key = f"{source_path}/{date_str}/{uuid4().hex}/{resolved_name}"

        try:
            if self.local_archive_dir:
                destination = self._local_destination(source_path, resolved_name)
                self._copy_local_file(destination, local_path)
                size = destination.stat().st_size
                log.info(f"Archived locally to {destination} ({size} bytes)")
                return
            if not self._r2_write_allowed(log):
                return
            self._client().upload_file(local_path, self.bucket, key)
            size = os.path.getsize(local_path)
            log.info(
                f"Archived to {self.endpoint_url or 's3 (default AWS endpoint!)'}"
                f"/{self.bucket}/{key} ({size} bytes)"
            )
        except (BotoCoreError, ClientError, OSError, ValueError) as e:
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
        local_archive_dir=os.environ.get("COUNTYIQ_LOCAL_RAW_ARCHIVE_DIR", ""),
        cost_guard_file=os.environ.get("COUNTYIQ_COST_GUARD_FILE", ""),
    )
