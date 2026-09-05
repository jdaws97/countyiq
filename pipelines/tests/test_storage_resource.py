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


def test_strict_r2_archive_fails_when_cost_guard_is_tripped(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "get_dagster_logger", mock.Mock)
    guard = tmp_path / "tripped"
    guard.write_text("reason=r2_hard_limit\n", encoding="utf-8")
    resource = S3StorageResource(
        bucket="countyiq-raw",
        endpoint_url="https://example.r2.cloudflarestorage.com",
        access_key_id="access",
        secret_access_key="secret",
        strict=True,
        cost_guard_file=str(guard),
    )

    with mock.patch.object(S3StorageResource, "_client") as client:
        with pytest.raises(RuntimeError, match="cost guard is tripped"):
            resource.archive("york/arcgis/parcels", {"pidn": "123"})

    client.assert_not_called()


def test_non_strict_r2_archive_skips_write_when_cost_guard_is_tripped(
    tmp_path, monkeypatch
):
    logger = mock.Mock()
    monkeypatch.setattr(storage, "get_dagster_logger", lambda: logger)
    guard = tmp_path / "tripped"
    guard.write_text("reason=manual\n", encoding="utf-8")
    resource = S3StorageResource(
        strict=False,
        cost_guard_file=str(guard),
    )

    with mock.patch.object(S3StorageResource, "_client") as client:
        resource.archive("york/arcgis/parcels", {"pidn": "123"})

    client.assert_not_called()
    logger.warning.assert_called_once_with(
        "Cloudflare R2 write blocked because the CountyIQ cost guard is tripped"
    )


@pytest.mark.parametrize("streamed", [False, True])
def test_same_day_reruns_never_overwrite_locked_objects(tmp_path, monkeypatch, streamed):
    monkeypatch.setattr(storage, "get_dagster_logger", mock.Mock)
    keys = set()

    def put_object(**kwargs):
        key = kwargs["Key"]
        assert key not in keys, "R2 bucket locks reject overwrites"
        keys.add(key)

    client = mock.Mock()
    client.put_object.side_effect = put_object
    client.upload_file.side_effect = lambda path, bucket, key: put_object(Key=key)
    source = tmp_path / "input.json"
    source.write_text('{"pidn":"123"}')
    resource = S3StorageResource(strict=True)
    with mock.patch.object(S3StorageResource, "_client", return_value=client):
        for _ in range(2):
            if streamed:
                resource.archive_file("york/arcgis/parcels", str(source), "response.json")
            else:
                resource.archive("york/arcgis/parcels", {"pidn": "123"})
    assert len(keys) == 2
    assert all(key.startswith("york/arcgis/parcels/") and key.endswith("/response.json") for key in keys)
