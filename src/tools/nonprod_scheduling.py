"""Non-production EC2 scheduling policy evaluation; NO AWS write operations.

This module is a read-only planning boundary. No credentials, EC2 stop/start,
job scheduler or executor are imported. A future separately authorized executor
must require explicit opt-in, tagged target allowlists and audited approval.
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SAFE_TAGS = {"Environment": {"dev", "development", "test", "qa", "staging"}}


def validate_shutdown_policy(policy: dict) -> dict:
    if not isinstance(policy, dict):
        raise ValueError("Policy must be an object.")
    if policy.get("enabled") is not False:
        raise ValueError("The assessment-only policy must remain disabled for execution.")
    if policy.get("service") != "ec2":
        raise ValueError("Only EC2 non-production planning is supported.")
    tag_key = policy.get("tag_key")
    tag_value = str(policy.get("tag_value", "")).lower().strip()
    if tag_key not in SAFE_TAGS or tag_value not in SAFE_TAGS[tag_key]:
        raise ValueError("Only explicitly tagged non-production EC2 resources may be considered.")
    try:
        zone = ZoneInfo(str(policy["timezone"]))
    except (KeyError, ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValueError("A valid IANA time zone is required.") from exc
    try:
        start = time.fromisoformat(str(policy["shutdown_local"]))
        end = time.fromisoformat(str(policy["startup_local"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Valid local shutdown/startup times are required.") from exc
    if start.tzinfo or end.tzinfo or start == end:
        raise ValueError("Shutdown/startup must be distinct local wall-clock times.")
    if policy.get("weekends") is not True:
        raise ValueError("Weekend opt-in must be explicit.")
    return {"enabled": False, "service": "ec2",
            "tag_key": tag_key, "tag_value": tag_value,
            "timezone": zone.key, "shutdown_local": start.isoformat(timespec="minutes"),
            "startup_local": end.isoformat(timespec="minutes"), "weekends": True,
            "execution_mode": "planning_only", "aws_write_permissions": False}


def evaluate_shutdown_window(policy: dict, *, now: datetime) -> dict:
    validated = validate_shutdown_policy(policy)
    if now.tzinfo is None:
        raise ValueError("An aware datetime is required.")
    local = now.astimezone(ZoneInfo(validated["timezone"]))
    closing = time.fromisoformat(validated["shutdown_local"])
    opening = time.fromisoformat(validated["startup_local"])
    clock = local.timetz().replace(tzinfo=None)
    # Overnight quiet time (e.g. stop at 19:00, start at 08:00).
    quiet_hours = clock >= closing or clock < opening if closing > opening else closing <= clock < opening
    should_be_stopped = bool(local.weekday() >= 5 or quiet_hours)
    return {"desired_state": "stopped" if should_be_stopped else "running",
            "evaluated_at": now.isoformat(),
            "execution_performed": False, "action": "manual_review_only",
            "tag_filter": {validated["tag_key"]: validated["tag_value"]},
            "timezone": validated["timezone"]}
