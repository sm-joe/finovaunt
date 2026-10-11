"""Read-only sync of the latest successful Finovaunt GitHub Actions scan artifact."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

ALLOWED_FILES = {
    "manifest.json",
    "audit.json",
    "billing.json",
    "cost_evidence.json",
    "cost_history.json",
    "proposal.json",
}
USER_AGENT = "Finovaunt-ReadOnly-Dashboard-Sync/1.0"


class SyncError(RuntimeError):
    pass


class _SafeRedirectHandler(HTTPRedirectHandler):
    """Do not forward GitHub credentials to the signed artifact-download host."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return Request(newurl, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})


def _request(url: str, token: str, *, accept: str = "application/vnd.github+json") -> bytes:
    request = Request(
        url,
        headers={
            "Accept": accept,
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        opener = build_opener(_SafeRedirectHandler())
        with opener.open(request, timeout=30) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SyncError(f"GitHub artifact request failed: {exc}") from exc


def _json_request(url: str, token: str) -> dict[str, Any]:
    try:
        value = json.loads(_request(url, token).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SyncError("GitHub API returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise SyncError("GitHub API returned an unexpected response.")
    return value


def _validated_files(archive: bytes) -> dict[str, bytes]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as exc:
        raise SyncError("Downloaded scan artifact is not a valid ZIP archive.") from exc

    with zf:
        files: dict[str, bytes] = {}
        for info in zf.infolist():
            if info.is_dir():
                continue
            # Reject paths and ignore anything not part of the known scan schema.
            if Path(info.filename).name != info.filename:
                raise SyncError("Scan artifact contains an unexpected nested path.")
            if info.filename in ALLOWED_FILES:
                files[info.filename] = zf.read(info.filename)

    if "manifest.json" not in files or "cost_evidence.json" not in files:
        raise SyncError("Scan artifact is missing manifest.json or cost_evidence.json.")
    try:
        manifest = json.loads(files["manifest.json"].decode("utf-8"))
        evidence = json.loads(files["cost_evidence.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SyncError("Scan artifact contains invalid JSON.") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        raise SyncError("Scan manifest has an unsupported structure.")
    if not isinstance(evidence, dict) or not evidence.get("run_id"):
        raise SyncError("Scan evidence has no run ID.")

    # Validate SHA-256 hashes for all known files listed in the manifest.
    for filename, expected in manifest["files"].items():
        if filename not in ALLOWED_FILES or filename not in files:
            continue
        actual = hashlib.sha256(files[filename]).hexdigest()
        if not isinstance(expected, str) or actual.lower() != expected.lower():
            raise SyncError(f"Scan artifact hash validation failed: {filename}")

    if manifest.get("run_id") and manifest["run_id"] != evidence["run_id"]:
        raise SyncError("Manifest run ID does not match cost evidence.")
    return files


def sync_latest_scan(output_dir: Path, *, token: str, repository: str, workflow: str) -> dict[str, Any]:
    """Download only the latest successful workflow artifact; never writes to GitHub."""
    if not token.strip():
        raise SyncError("Set FINOVAUNT_GITHUB_TOKEN or GH_TOKEN to enable automatic sync.")
    parts = repository.split("/")
    if len(parts) != 2 or not all(parts):
        raise SyncError("FINOVAUNT_GITHUB_REPOSITORY must be owner/repository.")
    owner, repo = parts
    base = f"https://api.github.com/repos/{owner}/{repo}"
    workflow_url = f"{base}/actions/workflows/{workflow}/runs?status=success&per_page=10"
    runs = _json_request(workflow_url, token).get("workflow_runs", [])
    if not isinstance(runs, list):
        raise SyncError("GitHub returned an unexpected workflow-run list.")

    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("id"), int):
            continue
        run_id = run["id"]
        marker = output_dir / ".finovaunt-sync.json"
        if marker.exists():
            try:
                old = json.loads(marker.read_text(encoding="utf-8"))
                evidence_path = output_dir / "cost_evidence.json"
                evidence_is_present = False
                if evidence_path.is_file():
                    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                    evidence_is_present = (
                        isinstance(evidence, dict)
                        and bool(evidence.get("run_id"))
                        and evidence.get("run_id") == old.get("scan_run_id")
                    )
                if old.get("github_run_id") == run_id and evidence_is_present:
                    return {
                        "status": "unchanged",
                        "github_run_id": run_id,
                        "github_run_url": old.get("github_run_url"),
                        "scan_run_id": old.get("scan_run_id"),
                        "synced_at": old.get("synced_at"),
                    }
            except (OSError, json.JSONDecodeError, AttributeError):
                # A stale/corrupt marker or missing evidence must trigger a fresh download.
                pass

        artifact_payload = _json_request(f"{base}/actions/runs/{run_id}/artifacts?per_page=100", token)
        artifacts = artifact_payload.get("artifacts", [])
        artifact = next((a for a in artifacts if isinstance(a, dict) and a.get("name") == "finovaunt-scan" and not a.get("expired")), None)
        if not artifact or not isinstance(artifact.get("id"), int):
            continue

        archive = _request(f"{base}/actions/artifacts/{artifact['id']}/zip", token, accept="application/vnd.github+json")
        files = _validated_files(archive)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Replace data files atomically, with cost_evidence.json written last as the snapshot marker.
        ordered = sorted((name for name in files if name != "cost_evidence.json"))
        ordered.append("cost_evidence.json")
        for filename in ordered:
            fd, temp_name = tempfile.mkstemp(prefix=".finovaunt-", suffix=".tmp", dir=output_dir)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(files[filename])
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, output_dir / filename)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)

        evidence = json.loads(files["cost_evidence.json"].decode("utf-8"))
        marker_data = {
            "github_run_id": run_id,
            "github_run_url": run.get("html_url"),
            "scan_run_id": evidence.get("run_id"),
            "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        marker.write_text(json.dumps(marker_data, indent=2) + "\n", encoding="utf-8")
        return {"status": "synced", **marker_data}

    raise SyncError("No successful scan run with an unexpired finovaunt-scan artifact was found.")
