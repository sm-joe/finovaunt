"""Offline backup/restore is verifiable and does not destroy state on corruption."""
import io
import json
from pathlib import Path
import tarfile

import pytest

from scripts.control_backup import create_backup, restore_backup, verify_backup


def _fixture(root: Path) -> None:
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "artifacts-live").mkdir(parents=True, exist_ok=True)
    (root / "data/control-plane.json").write_text(
        json.dumps({"user": {"username": "admin", "password": {"hash": "never-log"}},
                    "cloud_accounts": [{"account_id": "123456789012"}],
                    "billing_scans": [{"total_cost": 99.5}]}),
        encoding="utf-8")
    (root / "artifacts-live/cost_history.json").write_text('{"observations": 12}')


def test_backup_verify_and_restore_preserves_billing_and_state(tmp_path):
    root = tmp_path / "live"
    _fixture(root)
    archive = tmp_path / "backup.tar.gz"
    manifest = create_backup(root, archive)
    assert archive.exists()
    assert manifest["files"]["data/control-plane.json"]["sha256"]
    assert verify_backup(archive)[0]["schema"] == 1
    (root / "data/control-plane.json").write_text('{"bad":"state"}')
    with pytest.raises(ValueError, match="requires --force"):
        restore_backup(archive, root)
    assert (root / "data/control-plane.json").read_text() == '{"bad":"state"}'
    restore_backup(archive, root, force=True)
    restored = json.loads((root / "data/control-plane.json").read_text())
    assert restored["billing_scans"][0]["total_cost"] == 99.5
    assert restored["cloud_accounts"][0]["account_id"] == "123456789012"
    assert (root / "artifacts-live/cost_history.json").read_text() == '{"observations": 12}'


def test_backup_refuses_symlink_and_missing_control_plane(tmp_path):
    root = tmp_path / "live"
    root.mkdir()
    with pytest.raises(ValueError, match="control plane"):
        create_backup(root, tmp_path / "missing.tar.gz")
    _fixture(root)
    (root / "data/linked").symlink_to(root / "data/control-plane.json")
    with pytest.raises(ValueError, match="symlink"):
        create_backup(root, tmp_path / "link.tar.gz")


def test_checksum_tampering_and_unsafe_archive_paths_are_rejected(tmp_path):
    root = tmp_path / "live"
    _fixture(root)
    archive = tmp_path / "backup.tar.gz"
    create_backup(root, archive)
    manifest, files = verify_backup(archive)
    tampered = tmp_path / "tampered.tar.gz"
    with tarfile.open(tampered, "w:gz") as out:
        files["data/control-plane.json"] = b'{"user": {}, "cloud_accounts":[]}'
        for name, data in {**files, "manifest.json": json.dumps(manifest).encode()}.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            out.addfile(info, io.BytesIO(data))
    with pytest.raises(ValueError, match="integrity"):
        verify_backup(tampered)

    bad = tmp_path / "traversal.tar.gz"
    with tarfile.open(bad, "w:gz") as out:
        data = b"malicious"
        info = tarfile.TarInfo("../outside.txt")
        info.size = len(data)
        out.addfile(info, io.BytesIO(data))
    with pytest.raises(ValueError, match="unsafe"):
        verify_backup(bad)
