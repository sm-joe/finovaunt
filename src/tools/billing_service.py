"""Read-only, account-verified AWS Cost Explorer collection.

Service-level spend is contextual. It is never attributed to an individual
resource or treated as realized optimization savings.
"""
from __future__ import annotations

from datetime import date, timedelta, datetime, timezone
from decimal import Decimal, InvalidOperation

from src.tools.aws_errors import aws_call
from src.tools.aws_identity import resolve_aws_session


class BillingCollectionError(RuntimeError):
    """Unsafe, incomplete, or inconsistent billing evidence."""


def collect_billing(account: dict, *, external_id: str = "", today: date | None = None) -> dict:
    import boto3

    account_id = str(account["account_id"])
    region = str(account["region"])
    role_arn = str(account["role_arn"])
    if role_arn.split(":")[4] != account_id:
        raise BillingCollectionError("Onboarded account ID does not match its role ARN.")

    session_kwargs, identity_mode = resolve_aws_session(
        account, external_id=external_id, session_name="FinovauntBillingReadOnly"
    )

    ce = boto3.client("ce", region_name="us-east-1", **session_kwargs)
    today = today or datetime.now(timezone.utc).date()
    start = today.replace(day=1)
    end = today + timedelta(days=1)
    query = {
        "TimePeriod": {"Start": start.isoformat(), "End": end.isoformat()},
        "Granularity": "MONTHLY",
        "Metrics": ["UnblendedCost"],
        "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
        "Filter": {"Dimensions": {"Key": "LINKED_ACCOUNT", "Values": [account_id]}},
    }

    services: dict[str, Decimal] = {}
    currency: str | None = None
    token: str | None = None
    seen_tokens: set[str] = set()
    pages = 0
    while True:
        params = dict(query)
        if token:
            params["NextPageToken"] = token
        response = aws_call("cost_explorer", ce.get_cost_and_usage, **params)
        pages += 1
        if pages > 1000:
            raise BillingCollectionError("Cost Explorer pagination limit exceeded.")
        for period in response.get("ResultsByTime", []):
            for group in period.get("Groups", []):
                metric = group.get("Metrics", {}).get("UnblendedCost", {})
                unit = str(metric.get("Unit", "USD"))
                if currency is not None and unit != currency:
                    raise BillingCollectionError("Cost Explorer returned mixed currencies.")
                currency = unit
                try:
                    amount = Decimal(str(metric["Amount"]))
                except (KeyError, InvalidOperation, ValueError, TypeError) as exc:
                    raise BillingCollectionError("Cost Explorer returned an invalid amount.") from exc
                if not amount.is_finite():
                    raise BillingCollectionError("Cost Explorer returned a non-finite amount.")
                service = str(group.get("Keys", ["Unknown"])[0])
                services[service] = services.get(service, Decimal("0")) + amount
        token = response.get("NextPageToken")
        if not token:
            break
        if not isinstance(token, str) or token in seen_tokens:
            raise BillingCollectionError("Cost Explorer pagination token repeated or malformed.")
        seen_tokens.add(token)

    rows = [
        {
            "service": name,
            "amount": float(amount),
            "amount_exact": str(amount),
            "currency": currency or "USD",
        }
        for name, amount in sorted(services.items())
    ]
    total = sum(services.values(), Decimal("0"))
    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "period_start": start.isoformat(),
        "period_end_exclusive": end.isoformat(),
        "total_cost": round(float(total), 2),
        "total_cost_exact": str(total),
        "currency": currency or "USD",
        "services": rows,
        "status": "success",
        "cost_scope": "account_service_month_to_date",
        "resource_attribution": "not_available",
        "is_final": False,
        "pages_collected": pages,
        "aws_auth_mode": identity_mode,
    }
