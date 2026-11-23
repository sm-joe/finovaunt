"""Persistent local authentication and cloud-account registry for Finovaunt."""
from __future__ import annotations
import base64, hashlib, hmac, json, os, secrets, threading, time
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
_SESSIONS: dict[str, tuple[str, float]] = {}
_SESSION_TTL_SECONDS = 12 * 60 * 60
_ITERATIONS = 310_000

def _path() -> Path:
    configured = os.getenv("FINOVAUNT_CONTROL_FILE", "data/control-plane.json")
    path = Path(configured)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    return path

def _hash(password: str, salt: bytes | None = None) -> dict[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return {"salt": base64.b64encode(salt).decode(), "hash": base64.b64encode(digest).decode()}

def _read() -> dict[str, Any]:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        bootstrap_password = os.getenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "")
        if len(bootstrap_password) < 12:
            raise RuntimeError(
                "Set FINOVAUNT_BOOTSTRAP_PASSWORD (at least 12 characters) "
                "before starting a new Finovaunt installation."
            )
        state = {"user": {"username": "admin", "password": _hash(bootstrap_password), "must_change_password": True}, "cloud_accounts": [], "billing_scans": [], "inventory_scans": [], "recommendation_decisions": [], "ebs_reviews": [], "optimization_ledger": [], "account_config_audit": [], "finops_assessments": [], "nonprod_schedules": []}
        _write(state)
        return state
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("user"), dict) or not isinstance(data.get("cloud_accounts"), list):
            raise ValueError("invalid control state")
        data.setdefault("billing_scans", [])
        data.setdefault("inventory_scans", [])
        data.setdefault("recommendation_decisions", [])
        data.setdefault("ebs_reviews", [])
        data.setdefault("optimization_ledger", [])
        data.setdefault("account_config_audit", [])
        data.setdefault("finops_assessments", [])
        data.setdefault("nonprod_schedules", [])
        return data
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Finovaunt control-plane state is unreadable; refusing to reset credentials or account records.") from exc

def _write(state: dict[str, Any]) -> None:
    path = _path(); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    try: os.chmod(temp, 0o600)
    except OSError: pass
    temp.replace(path)

def login(username: str, password: str) -> dict[str, Any] | None:
    with _LOCK:
        user = _read()["user"]
        if not hmac.compare_digest(username, str(user.get("username", ""))): return None
        stored = user.get("password", {})
        try:
            salt = base64.b64decode(stored["salt"]); expected = base64.b64decode(stored["hash"])
        except Exception: return None
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
        if not hmac.compare_digest(actual, expected): return None
        token = secrets.token_urlsafe(32); _SESSIONS[token] = (username, time.monotonic() + _SESSION_TTL_SECONDS)
        return {"token": token, "username": username, "must_change_password": bool(user.get("must_change_password", False))}

def session(token: str | None) -> dict[str, Any] | None:
    if not token: return None
    with _LOCK:
        record = _SESSIONS.get(token)
        if not record: return None
        username, expires_at = record
        if time.monotonic() >= expires_at:
            _SESSIONS.pop(token, None)
            return None
        state = _read(); user = state["user"]
        if username != user.get("username"): return None
        return {"username": username, "must_change_password": bool(user.get("must_change_password", False))}

def logout(token: str | None) -> None:
    if token:
        with _LOCK: _SESSIONS.pop(token, None)

def change_password(token: str | None, current: str, new: str) -> bool:
    with _LOCK:
        record = _SESSIONS.get(token or "")
        if not record or time.monotonic() >= record[1] or len(new) < 12 or new == "admin": return False
        state = _read(); user = state["user"]
        try:
            salt = base64.b64decode(user["password"]["salt"]); expected = base64.b64decode(user["password"]["hash"])
            current_matches = hmac.compare_digest(
                hashlib.pbkdf2_hmac("sha256", current.encode(), salt, _ITERATIONS), expected
            )
        except Exception:
            current_matches = False
        if not current_matches:
            return False
        user["password"] = _hash(new); user["must_change_password"] = False; _write(state)
        _SESSIONS.clear()  # Revoke all sessions after a credential rotation.
        return True

def list_accounts() -> list[dict[str, Any]]:
    with _LOCK: return [{k:v for k,v in item.items() if k != "external_id"} for item in _read()["cloud_accounts"]]

def add_account(name: str, provider: str, account_id: str, role_arn: str, region: str, external_id: str = "") -> dict[str, Any]:
    name=name.strip(); provider=provider.strip().lower(); account_id=account_id.strip(); role_arn=role_arn.strip(); region=region.strip()
    if not name or provider != "aws" or not account_id or not role_arn.startswith("arn:") or not region:
        raise ValueError("Provide a name, AWS account ID, IAM role ARN, and region. AWS role-based onboarding is currently supported.")
    if not account_id.isdigit() or len(account_id) != 12: raise ValueError("AWS account ID must contain exactly 12 digits.")
    expected_prefix = f"arn:aws:iam::{account_id}:role/"
    if not role_arn.startswith(expected_prefix) or len(role_arn) <= len(expected_prefix):
        raise ValueError("Role ARN must identify an IAM role in the onboarded AWS account.")
    with _LOCK:
        state=_read()
        if any(a.get("account_id")==account_id for a in state["cloud_accounts"]): raise ValueError("This AWS account is already onboarded.")
        item={"id":secrets.token_hex(8),"name":name,"provider":"aws","account_id":account_id,"role_arn":role_arn,"region":region,"status":"onboarded","created_at":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "config_revision": 1}
        state["cloud_accounts"].append(item); _write(state)
        return {k:v for k,v in item.items() if k != "external_id"}

def update_account_configuration(*, account_id: str, name: str, role_arn: str, region: str,
                                 reviewed_by: str, note: str) -> dict[str, Any]:
    """Change collector configuration without deleting any historical evidence.

    Increment the revision on role or region changes so snapshots under old
    authorization/scope cannot be presented as a current-account collection.
    """
    import re
    from datetime import datetime, timezone
    name, role_arn, region, note = (value.strip() for value in (name, role_arn, region, note))
    if not name or len(name) > 120:
        raise ValueError("Account display name must be between 1 and 120 characters.")
    if not re.fullmatch(r"arn:aws:iam::" + re.escape(account_id) + r":role/[A-Za-z0-9+=,.@_/-]+", role_arn):
        raise ValueError("Role ARN must identify a role in the onboarded AWS account.")
    if not re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-[0-9]", region):
        raise ValueError("Provide a valid AWS region code.")
    if not 10 <= len(note) <= 2000:
        raise ValueError("Record a reason of 10 to 2000 characters for the configuration change.")
    with _LOCK:
        state = _read()
        account = next((item for item in state["cloud_accounts"] if item.get("account_id") == account_id), None)
        if account is None:
            raise ValueError("Account is not onboarded.")
        previous = {key: account.get(key) for key in ("name", "region", "role_arn")}
        revised = account.get("region") != region or account.get("role_arn") != role_arn
        account.update(name=name, role_arn=role_arn, region=region)
        if revised:
            account["config_revision"] = int(account.get("config_revision", 1)) + 1
        state.setdefault("account_config_audit", []).append({
            "id": secrets.token_hex(12), "account_id": account_id,
            "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": reviewed_by,
            "reason": note, "previous": previous,
            "current": {key: account[key] for key in previous},
            "config_revision": int(account.get("config_revision", 1)),
            "collection_scope_changed": revised, "aws_resources_modified": False,
        })
        state["account_config_audit"] = state["account_config_audit"][-2000:]
        _write(state)
        return {k: v for k, v in account.items() if k != "external_id"}


def account_configuration_audit(account_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        return [dict(item) for item in _read().get("account_config_audit", [])
                if item.get("account_id") == account_id]

def get_account(account_id: str) -> dict[str, Any] | None:
    with _LOCK:
        for item in _read()["cloud_accounts"]:
            if item.get("account_id")==account_id: return dict(item)
    return None


def save_billing_scan(account_id: str, result: dict[str, Any], *, expected_revision: int | None = None) -> dict[str, Any]:
    with _LOCK:
        state = _read()
        active = next((a for a in state["cloud_accounts"] if a.get("account_id") == account_id), None)
        if active is None:
            raise ValueError("AWS account was removed before scan evidence was saved.")
        if expected_revision is not None and int(active.get("config_revision", 1)) != expected_revision:
            raise ValueError("Collector configuration changed during the scan. Refresh and collect again.")
        item = {"id": secrets.token_hex(8), "account_id": account_id, "config_revision": int(next((a.get("config_revision", 1) for a in state["cloud_accounts"] if a.get("account_id") == account_id), 1)), **result}
        state.setdefault("billing_scans", []).append(item)
        state["billing_scans"] = state["billing_scans"][-100:]
        _write(state)
        return item

def billing_history(account_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        state = _read()
        return [item for item in state.get("billing_scans", []) if item.get("account_id") == account_id]


def delete_account(account_id: str) -> bool:
    """Remove one cloud account and its billing history, without AWS mutations."""
    with _LOCK:
        state = _read()
        before = len(state["cloud_accounts"])
        state["cloud_accounts"] = [
            item for item in state["cloud_accounts"]
            if item.get("account_id") != account_id
        ]
        if len(state["cloud_accounts"]) == before:
            return False
        state["billing_scans"] = [
            item for item in state.get("billing_scans", [])
            if item.get("account_id") != account_id
        ]
        state["inventory_scans"] = [
            item for item in state.get("inventory_scans", [])
            if item.get("account_id") != account_id
        ]
        state["ebs_reviews"] = [
            item for item in state.get("ebs_reviews", [])
            if item.get("account_id") != account_id
        ]
        for field in ("finops_assessments", "nonprod_schedules"):
            state[field] = [x for x in state.get(field, []) if x.get("account_id") != account_id]
        state["account_config_audit"] = [
            item for item in state.get("account_config_audit", [])
            if item.get("account_id") != account_id
        ]
        state["optimization_ledger"] = [
            item for item in state.get("optimization_ledger", [])
            if item.get("account_id") != account_id
        ]
        _write(state)
        return True


def save_finops_assessment(account_id: str, result: dict[str, Any], *,
                           expected_revision: int) -> dict[str, Any]:
    """Bounded local evidence history, guarded against changes mid-scan."""
    with _LOCK:
        state = _read()
        current = next((a for a in state["cloud_accounts"] if a.get("account_id") == account_id), None)
        if current is None or int(current.get("config_revision", 1)) != expected_revision:
            raise ValueError("Account collector configuration changed during assessment.")
        item = {"id": secrets.token_hex(12), **result, "account_id": account_id,
                "config_revision": expected_revision}
        state.setdefault("finops_assessments", []).append(item)
        state["finops_assessments"] = state["finops_assessments"][-40:]
        _write(state)
        return item


def latest_finops_assessment(account_id: str) -> dict[str, Any] | None:
    with _LOCK:
        state = _read()
        account = next((a for a in state["cloud_accounts"] if a.get("account_id") == account_id), None)
        if account is None:
            return None
        current = int(account.get("config_revision", 1))
        matching = [a for a in state.get("finops_assessments", [])
                    if a.get("account_id") == account_id
                    and int(a.get("config_revision", 1)) == current]
        return dict(matching[-1]) if matching else None


def save_inventory_scan(account_id: str, result: dict[str, Any], *, expected_revision: int | None = None) -> dict[str, Any]:
    with _LOCK:
        state = _read()
        active = next((a for a in state["cloud_accounts"] if a.get("account_id") == account_id), None)
        if active is None:
            raise ValueError("AWS account was removed before scan evidence was saved.")
        if expected_revision is not None and int(active.get("config_revision", 1)) != expected_revision:
            raise ValueError("Collector configuration changed during the scan. Refresh and collect again.")
        item = {"id": secrets.token_hex(8), "account_id": account_id, "config_revision": int(next((x.get("config_revision", 1) for x in state["cloud_accounts"] if x.get("account_id") == account_id), 1)), **result}
        # Atomic with scan persistence: a scan cannot be saved without its
        # corresponding history update, and failures do not invent outcomes.
        from src.utils.optimization_ledger import update_ledger
        ledger = state.get("optimization_ledger", [])
        # Backfill solely from previously persisted real inventory snapshots
        # when upgrading an older Finovaunt installation. Do not manufacture
        # candidates from volume names or reported savings.
        if not ledger and state.get("inventory_scans"):
            for earlier in state["inventory_scans"]:
                if earlier.get("account_id"):
                    ledger = update_ledger(ledger, earlier["account_id"], earlier)
        state["optimization_ledger"] = update_ledger(ledger, account_id, item)
        state.setdefault("inventory_scans", []).append(item)
        state["inventory_scans"] = state["inventory_scans"][-30:]
        _write(state)
        return item


def latest_inventory_scan(account_id: str) -> dict[str, Any] | None:
    with _LOCK:
        matches = [
            item for item in _read().get("inventory_scans", [])
            if item.get("account_id") == account_id
        ]
        return matches[-1] if matches else None


def record_recommendation_decision(
    *,
    run_id: str,
    resource_id: str,
    action: str,
    note: str,
    reviewed_by: str,
) -> dict[str, Any]:
    """Append a human decision. This never executes a Terraform change."""
    if action not in {"approved", "rejected"}:
        raise ValueError("Decision must be approved or rejected.")
    if not run_id.strip() or not resource_id.strip() or len(resource_id) > 256:
        raise ValueError("A valid run and resource are required.")
    if len(note.strip()) < 10 or len(note) > 2000:
        raise ValueError("A review note must contain 10 to 2000 characters.")
    with _LOCK:
        state = _read()
        from datetime import datetime, timezone
        item = {
            "id": secrets.token_hex(12),
            "run_id": run_id,
            "resource_id": resource_id,
            "decision": action,
            "note": note.strip(),
            "reviewed_by": reviewed_by,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "infrastructure_applied": False,
        }
        state.setdefault("recommendation_decisions", []).append(item)
        state["recommendation_decisions"] = state["recommendation_decisions"][-1000:]
        _write(state)
        return item


def recommendation_decisions(run_id: str | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        items = _read().get("recommendation_decisions", [])
        return [
            dict(item) for item in items
            if run_id is None or item.get("run_id") == run_id
        ]


def record_ebs_review(*, account_id: str, inventory_scan_id: str, resource_id: str,
                      decision: str, note: str, reviewed_by: str) -> dict[str, Any]:
    """Audited local decision only. AWS deletion and kubectl mutation are forbidden."""
    if decision not in {"approved_for_manual_review", "rejected"}:
        raise ValueError("Decision must be approved_for_manual_review or rejected.")
    if not (10 <= len(note.strip()) <= 2000):
        raise ValueError("Provide an evidence-based review note of 10 to 2000 characters.")
    with _LOCK:
        state = _read()
        if not any(a.get("account_id") == account_id for a in state["cloud_accounts"]):
            raise ValueError("AWS account is not onboarded.")
        scans = [x for x in state.get("inventory_scans", []) if x.get("account_id") == account_id]
        if not scans or scans[-1].get("id") != inventory_scan_id:
            raise ValueError("Inventory evidence is stale. Collect current inventory and review again.")
        asset = next((x for x in scans[-1].get("assets", [])
                      if x.get("id") == resource_id and x.get("type") == "ebs"
                      and x.get("state") == "available"), None)
        if asset is None:
            raise ValueError("Unattached EBS candidate is absent from the current scan.")
        from datetime import datetime, timezone
        item = {
            "id": secrets.token_hex(12), "account_id": account_id,
            "inventory_scan_id": inventory_scan_id, "resource_id": resource_id,
            "decision": decision, "note": note.strip(), "reviewed_by": reviewed_by,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "infrastructure_applied": False,
            "savings_verified": False,
        }
        state.setdefault("ebs_reviews", []).append(item)
        state["ebs_reviews"] = state["ebs_reviews"][-1000:]
        _write(state)
        return dict(item)


def ebs_reviews(account_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        return [dict(x) for x in _read().get("ebs_reviews", [])
                if x.get("account_id") == account_id]


def optimization_history(account_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        state = _read()
        ledger = state.get("optimization_ledger", [])
        if not ledger and state.get("inventory_scans"):
            # Read-only compatibility for retained scans predating this feature.
            from src.utils.optimization_ledger import update_ledger
            for scan in state["inventory_scans"]:
                if scan.get("account_id"):
                    ledger = update_ledger(ledger, scan["account_id"], scan)
        return [dict(item) for item in ledger if item.get("account_id") == account_id]
