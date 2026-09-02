"""Local and R2 archive resource behavior."""

from unittest import mock

import pytest

from countyiq.resources import storage
from countyiq.resources.storage import S3StorageResource


def test_local_archive_writes_payload_beneath_configured_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "get_dagster_logger", mock.Mock)
    resource = S3StorageResource(
        local_archive_dir=str(tmp_path),
        strict=True,
    )

    resource.archive("york/arcgis/parcels", {"pidn": "123"})

    archived = list(tmp_path.glob("york/arcgis/parcels/*/response.json"))
    assert len(archived) == 1
    assert archived[0].read_text(encoding="utf-8") == '{"pidn": "123"}'


def test_local_archive_file_streams_to_destination(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "get_dagster_logger", mock.Mock)
    source = tmp_path / "source.bin"
    source.write_bytes(b"source payload")
    archive_root = tmp_path / "archive"
    resource = S3StorageResource(
        local_archive_dir=str(archive_root),
        strict=True,
    )

    resource.archive_file("york/arcgis/address_points", str(source))

    archived = list(
        archive_root.glob("york/arcgis/address_points/*/source.bin")
    )
    assert len(archived) == 1
    assert archived[0].read_bytes() == b"source payload"


def test_local_archive_rejects_path_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "get_dagster_logger", mock.Mock)
    resource = S3StorageResource(
        local_archive_dir=str(tmp_path),
        strict=True,
    )

    with pytest.raises(RuntimeError, match="Archive of"):
        resource.archive("../escape", "payload")
