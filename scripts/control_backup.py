"""Validated offline backup and restore for Finovaunt's local control plane.

Use only with API stopped. No AWS calls, no network and no implicit restore.
The archive holds sensitive inventory, password hashes and account metadata.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import tarfile
import tempfile


MAX_FILE_BYTES = 100 * 1024 * 1024
ALLOWED_ROOTS = {"data", "artifacts-live"}


def _check_path(name: str) -> None:
    p = PurePosixPath(name)
    if (not name or name.startswith("/") or "\\" in name
            or ".." in p.parts or p.parts[0] not in ALLOWED_ROOTS
            or len(p.parts) < 2):
        raise ValueError("Archive includes an unsafe or unexpected path.")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _payload_files(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for directory in ("data", "artifacts-live"):
        base = root / directory
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_symlink():
                raise ValueError("Refusing to back up a symlink.")
            if not path.is_file() or path.name.endswith(".tmp"):
                continue
            relative = path.relative_to(root).as_posix()
            _check_path(relative)
            if path.stat().st_size > MAX_FILE_BYTES:
                raise ValueError("Refusing to back up an oversized file.")
            files[relative] = path.read_bytes()
    if "data/control-plane.json" not in files:
        raise ValueError("No persisted Finovaunt control plane exists to back up.")
    json.loads(files["data/control-plane.json"].decode("utf-8"))
    return files


def create_backup(root: Path, destination: Path) -> dict:
    files = _payload_files(root.resolve())
    manifest = {
        "schema": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": {name: {"sha256": _digest(data), "bytes": len(data)}
                  for name, data in sorted(files.items())},
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".finovaunt-backup-", suffix=".tmp",
                                     dir=str(destination.parent))
    try:
        with os.fdopen(fd, "wb") as output:
            with tarfile.open(fileobj=output, mode="w:gz") as archive:
                for name, data in sorted(files.items()):
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.mode = 0o600
                    archive.addfile(info, io.BytesIO(data))
                raw = json.dumps(manifest, sort_keys=True).encode("utf-8")
                info = tarfile.TarInfo("manifest.json")
                info.size = len(raw)
                info.mode = 0o600
                archive.addfile(info, io.BytesIO(raw))
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return manifest


def verify_backup(archive_path: Path) -> tuple[dict, dict[str, bytes]]:
    files = {}
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) > 10000:
            raise ValueError("Archive has too many entries.")
        for member in members:
            if not member.isfile() or member.size > MAX_FILE_BYTES:
                raise ValueError("Archive contains non-file or oversized data.")
            if member.name != "manifest.json":
                _check_path(member.name)
            if member.name in files:
                raise ValueError("Archive includes duplicate paths.")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("Cannot read backup entry.")
            data = stream.read(MAX_FILE_BYTES + 1)
            if len(data) != member.size:
                raise ValueError("Archive entry is incomplete.")
            files[member.name] = data
    if "manifest.json" not in files:
        raise ValueError("Archive manifest is missing.")
    manifest = json.loads(files.pop("manifest.json").decode("utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise ValueError("Unsupported backup schema.")
    registered = manifest.get("files")
    if not isinstance(registered, dict) or set(registered) != set(files):
        raise ValueError("Backup manifest does not match archive contents.")
    if "data/control-plane.json" not in files:
        raise ValueError("Backup does not contain a control plane.")
    for name, data in files.items():
        expected = registered[name]
        if expected.get("bytes") != len(data) or expected.get("sha256") != _digest(data):
            raise ValueError("Backup integrity check failed.")
    state = json.loads(files["data/control-plane.json"].decode("utf-8"))
    if not isinstance(state, dict) or not isinstance(state.get("user"), dict) or not isinstance(state.get("cloud_accounts"), list):
        raise ValueError("Backup contains invalid control-plane state.")
    return manifest, files


def restore_backup(archive: Path, root: Path, *, force: bool = False) -> dict:
    manifest, files = verify_backup(archive)
    root = root.resolve()
    if not force:
        raise ValueError("Restore requires --force and a stopped Finovaunt API.")
    for name, contents in files.items():
        destination = root / name
        if destination.is_symlink() or destination.parent.is_symlink():
            raise ValueError("Restore destination contains a symbolic link.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".finovaunt-restore-", dir=str(destination.parent))
        try:
            with os.fdopen(fd, "wb") as target:
                target.write(contents)
                target.flush()
                os.fsync(target.fileno())
            os.chmod(temp, 0o600)
            os.replace(temp, destination)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline Finovaunt state backup and recovery")
    parser.add_argument("command", choices=("backup", "verify", "restore"))
    parser.add_argument("archive", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--force", action="store_true", help="Explicitly permit restore, only while API is stopped")
    args = parser.parse_args()
    if args.command == "backup":
        result = create_backup(args.root, args.archive)
    elif args.command == "verify":
        result, _ = verify_backup(args.archive)
    else:
        result = restore_backup(args.archive, args.root, force=args.force)
    print(json.dumps({"status": "success", "operation": args.command,
                      "files": len(result["files"]), "created_at": result["created_at"]}))


if __name__ == "__main__":
    main()
