import json
import os
from datetime import datetime, timezone
from pathlib import Path

import boto3
from dagster import ConfigurableResource, get_dagster_logger


class S3StorageResource(ConfigurableResource):
    """S3 client for archiving raw pipeline responses.

    Archives to s3://countyiq-raw/<source>/<date>/<filename>.
    In local dev (no AWS creds), logs a warning and skips the upload.
    """

    bucket: str = "countyiq-raw"
    region: str = "us-east-1"

    def archive(self, source_path: str, data, filename: str = "response.json"):
        """Archive raw data to S3.

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
            client = boto3.client("s3", region_name=self.region)
            client.put_object(Bucket=self.bucket, Key=key, Body=body)
            log.info(f"Archived to s3://{self.bucket}/{key} ({len(body)} bytes)")
        except Exception as e:
            log.warning(f"S3 archive skipped ({e}). Data not persisted to S3.")

    def archive_file(self, source_path: str, local_path: str, filename: str | None = None):
        """Archive a local file to S3 without loading it fully into memory."""
        log = get_dagster_logger()
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        resolved_name = filename or Path(local_path).name
        key = f"{source_path}/{date_str}/{resolved_name}"

        try:
            client = boto3.client("s3", region_name=self.region)
            client.upload_file(local_path, self.bucket, key)
            size = os.path.getsize(local_path)
            log.info(f"Archived to s3://{self.bucket}/{key} ({size} bytes)")
        except Exception as e:
            log.warning(f"S3 archive skipped ({e}). File not persisted to S3.")


def make_s3_resource() -> S3StorageResource:
    return S3StorageResource(
        bucket=os.environ.get("S3_RAW_BUCKET", "countyiq-raw"),
        region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )
