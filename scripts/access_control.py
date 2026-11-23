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
        state = {"user": {"username": "admin", "password": _hash(bootstrap_password), "must_change_password": True}, "cloud_accounts": [], "billing_scans": [], "inventory_scans": []}
        _write(state)
        return state
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("user"), dict) or not isinstance(data.get("cloud_accounts"), list):
            raise ValueError("invalid control state")
        data.setdefault("billing_scans", [])
        data.setdefault("inventory_scans", [])
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
        item={"id":secrets.token_hex(8),"name":name,"provider":"aws","account_id":account_id,"role_arn":role_arn,"region":region,"status":"onboarded","created_at":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}
        state["cloud_accounts"].append(item); _write(state)
        return {k:v for k,v in item.items() if k != "external_id"}

def get_account(account_id: str) -> dict[str, Any] | None:
    with _LOCK:
        for item in _read()["cloud_accounts"]:
            if item.get("account_id")==account_id: return dict(item)
    return None


def save_billing_scan(account_id: str, result: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        state = _read()
        item = {"id": secrets.token_hex(8), "account_id": account_id, **result}
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
        _write(state)
        return True


def save_inventory_scan(account_id: str, result: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        state = _read()
        item = {"id": secrets.token_hex(8), "account_id": account_id, **result}
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
