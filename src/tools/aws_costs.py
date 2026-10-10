"""Read-only AWS Cost Explorer billing summaries."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


def previous_complete_month(today: date | None = None) -> tuple[str, str]:
    """Return the start and exclusive end of the previous calendar month."""
    today = today or date.today()
    first_day_this_month = date(today.year, today.month, 1)

    if today.month == 1:
        first_day_previous_month = date(today.year - 1, 12, 1)
    else:
        first_day_previous_month = date(today.year, today.month - 1, 1)

    return (
        first_day_previous_month.isoformat(),
        first_day_this_month.isoformat(),
    )


def _decimal_amount(value: Any) -> Decimal:
    """Parse a monetary amount without introducing binary float errors."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Cost Explorer returned an invalid cost amount.") from exc

    if not amount.is_finite():
        raise ValueError("Cost Explorer returned a non-finite cost amount.")

    return amount


def _unavailable_summary(
    *,
    period_start: str,
    period_end_exclusive: str,
    reason: str,
) -> dict[str, Any]:
    """Build a consistent unavailable-billing response."""
    return {
        "status": "unavailable",
        "period_start": period_start,
        "period_end_exclusive": period_end_exclusive,
        "reason": reason,
        "resource_attribution": "not_available",
    }


def parse_cost_responses(
    responses: list[dict[str, Any]],
    *,
    period_start: str,
    period_end_exclusive: str,
) -> dict[str, Any]:
    """Normalize Cost Explorer pages into a service/region summary.

    Prefer Cost Explorer's account-level total when available. Some valid
    responses contain an empty Total object while still returning service
    and region groups. In that case, calculate the total from those groups.

    Costs are account-level groupings. They are not attributed to individual
    resources by this function.
    """
    if not responses:
        return _unavailable_summary(
            period_start=period_start,
            period_end_exclusive=period_end_exclusive,
            reason="Cost Explorer returned no result pages.",
        )

    first_total: dict[str, Any] | None = None
    grouped_amounts: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)

    for response in responses:
        for result in response.get("ResultsByTime", []):
            # Preserve the first usable account-level total. Cost Explorer
            # may return an empty Total object even when Groups contain costs.
            total = result.get("Total")
            if first_total is None and isinstance(total, dict):
                metric = total.get("UnblendedCost")
                if isinstance(metric, dict) and "Amount" in metric:
                    first_total = metric

            for group in result.get("Groups", []):
                keys = group.get("Keys", [])
                if len(keys) < 2:
                    continue

                metric = group.get("Metrics", {}).get("UnblendedCost", {})
                if not isinstance(metric, dict) or "Amount" not in metric:
                    continue

                amount = _decimal_amount(metric["Amount"])
                currency = str(metric.get("Unit", "unknown"))

                service, region = str(keys[0]), str(keys[1])
                grouped_amounts[(service, region, currency)] += amount

    groups = [
        {
            "service": service,
            "region": region,
            "amount": float(amount),
            "currency": currency,
        }
        for (service, region, currency), amount in grouped_amounts.items()
    ]
    groups.sort(key=lambda item: item["amount"], reverse=True)

    if first_total is not None:
        # Use the authoritative account-level total when present.
        total_currency = str(first_total.get("Unit", "unknown"))
        total_amount = _decimal_amount(first_total["Amount"])
    else:
        # The total may be absent even though the service/region breakdown
        # is valid. Sum those groups instead of incorrectly reporting
        # billing as unavailable.
        if not grouped_amounts:
            return _unavailable_summary(
                period_start=period_start,
                period_end_exclusive=period_end_exclusive,
                reason=(
                    "Cost Explorer returned neither an account-level total "
                    "nor usable service/region cost groups."
                ),
            )

        currencies = {currency for _, _, currency in grouped_amounts}

        if len(currencies) != 1:
            return _unavailable_summary(
                period_start=period_start,
                period_end_exclusive=period_end_exclusive,
                reason=(
                    "Cost Explorer did not return an account-level total, "
                    "and grouped costs use multiple currencies. "
                    "The amounts cannot safely be combined."
                ),
            )

        total_currency = next(iter(currencies))
        total_amount = sum(grouped_amounts.values(), Decimal("0"))

    return {
        "status": "available",
        "period_start": period_start,
        "period_end_exclusive": period_end_exclusive,
        "metric": "UnblendedCost",
        "currency": total_currency,
        "total_cost": float(total_amount),
        "group_by": ["SERVICE", "REGION"],
        "groups": groups,
        "resource_attribution": "not_available",
        "note": (
            "Account-level costs grouped by service and region. "
            "Cost Explorer data can be delayed. These amounts must not be "
            "treated as individual resource costs or realized savings."
        ),
    }


def collect_aws_cost_summary(
    *,
    session: Any = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Retrieve the previous complete month's AWS account-level costs.

    Uses the caller's existing boto3 credential chain. The Cost Explorer
    endpoint is queried in us-east-1. No cloud resources are modified.
    """
    if session is None:
        import boto3

        session = boto3.Session()

    period_start, period_end_exclusive = previous_complete_month(today)

    client = session.client("ce", region_name="us-east-1")
    responses: list[dict[str, Any]] = []
    next_page_token: str | None = None

    while True:
        request: dict[str, Any] = {
            "TimePeriod": {
                "Start": period_start,
                "End": period_end_exclusive,
            },
            "Granularity": "MONTHLY",
            "Metrics": ["UnblendedCost"],
            "GroupBy": [
                {"Type": "DIMENSION", "Key": "SERVICE"},
                {"Type": "DIMENSION", "Key": "REGION"},
            ],
        }

        if next_page_token:
            request["NextPageToken"] = next_page_token

        response = client.get_cost_and_usage(**request)
        responses.append(response)

        next_page_token = response.get("NextPageToken")
        if not next_page_token:
            break

    return parse_cost_responses(
        responses,
        period_start=period_start,
        period_end_exclusive=period_end_exclusive,
    )