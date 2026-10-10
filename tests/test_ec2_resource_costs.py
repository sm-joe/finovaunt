from datetime import date

import pytest

from src.tools.aws_costs import (
    collect_ec2_resource_costs,
    parse_ec2_resource_cost_responses,
)


def _group(
    resource_id: str,
    region: str,
    amount: str,
    currency: str = "USD",
) -> dict:
    return {
        "Keys": [resource_id, region],
        "Metrics": {
            "UnblendedCost": {
                "Amount": amount,
                "Unit": currency,
            }
        },
    }


def _page(*groups: dict, next_token: str | None = None) -> dict:
    response = {
        "ResultsByTime": [
            {
                "Groups": list(groups),
            }
        ]
    }
    if next_token:
        response["NextPageToken"] = next_token
    return response


def test_resource_costs_aggregate_daily_amounts_by_resource() -> None:
    result = parse_ec2_resource_cost_responses(
        [
            _page(_group("i-123", "us-east-1", "1.25")),
            _page(_group("i-123", "us-east-1", "2.75")),
        ],
        period_start="2026-09-26",
        period_end_exclusive="2026-10-10",
    )

    assert result["status"] == "available"
    assert result["resource_attribution"] == "resource_id"
    assert result["resources"] == [
        {
            "resource_id": "i-123",
            "region": "us-east-1",
            "amount": 4.0,
            "currency": "USD",
        }
    ]


def test_resource_costs_keep_currencies_separate() -> None:
    result = parse_ec2_resource_cost_responses(
        [
            _page(
                _group("i-usd", "us-east-1", "10.00", "USD"),
                _group("i-eur", "eu-central-1", "8.00", "EUR"),
            )
        ],
        period_start="2026-09-26",
        period_end_exclusive="2026-10-10",
    )

    assert result["status"] == "available"
    assert len(result["resources"]) == 2
    assert {
        (item["resource_id"], item["currency"], item["amount"])
        for item in result["resources"]
    } == {
        ("i-usd", "USD", 10.0),
        ("i-eur", "EUR", 8.0),
    }


def test_resource_costs_exclude_groups_without_resource_ids() -> None:
    result = parse_ec2_resource_cost_responses(
        [
            _page(
                _group("i-123", "us-east-1", "3.00"),
                _group("NoResourceId", "us-east-1", "7.00"),
            )
        ],
        period_start="2026-09-26",
        period_end_exclusive="2026-10-10",
    )

    assert result["status"] == "available"
    assert result["resource_attribution"] == "partial"
    assert result["unattributed_group_count"] == 1
    assert len(result["resources"]) == 1
    assert result["resources"][0]["resource_id"] == "i-123"


@pytest.mark.parametrize(
    "responses",
    [
        [],
        [_page(_group("NoResourceId", "us-east-1", "5.00"))],
        [_page()],
    ],
)
def test_resource_costs_unavailable_without_usable_resource_ids(
    responses: list[dict],
) -> None:
    result = parse_ec2_resource_cost_responses(
        responses,
        period_start="2026-09-26",
        period_end_exclusive="2026-10-10",
    )

    assert result["status"] == "unavailable"
    assert result["resource_attribution"] == "not_available"
    assert result["resources"] == []


def test_resource_costs_reject_non_finite_amounts() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        parse_ec2_resource_cost_responses(
            [_page(_group("i-123", "us-east-1", "NaN"))],
            period_start="2026-09-26",
            period_end_exclusive="2026-10-10",
        )


def test_collector_uses_expected_window_and_paginates() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.requests: list[dict] = []

        def get_cost_and_usage_with_resources(self, **kwargs: dict) -> dict:
            self.requests.append(kwargs)

            if len(self.requests) == 1:
                return _page(
                    _group("i-123", "us-east-1", "1.00"),
                    next_token="page-2",
                )

            return _page(_group("i-123", "us-east-1", "2.00"))

    class FakeSession:
        def __init__(self) -> None:
            self.client_instance = FakeClient()
            self.client_calls: list[tuple[str, str]] = []

        def client(self, service_name: str, *, region_name: str):
            self.client_calls.append((service_name, region_name))
            return self.client_instance

    session = FakeSession()
    result = collect_ec2_resource_costs(
        session=session,
        today=date(2026, 10, 10),
    )

    assert session.client_calls == [("ce", "us-east-1")]
    assert result["status"] == "available"
    assert result["period_start"] == "2026-09-26"
    assert result["period_end_exclusive"] == "2026-10-10"
    assert result["resources"][0]["amount"] == 3.0

    requests = session.client_instance.requests
    assert len(requests) == 2

    first, second = requests
    assert first["TimePeriod"] == {
        "Start": "2026-09-26",
        "End": "2026-10-10",
    }
    assert first["Granularity"] == "DAILY"
    assert first["Metrics"] == ["UnblendedCost"]
    assert first["Filter"]["Dimensions"] == {
        "Key": "SERVICE",
        "Values": ["Amazon Elastic Compute Cloud - Compute"],
    }
    assert first["GroupBy"] == [
        {"Type": "DIMENSION", "Key": "RESOURCE_ID"},
        {"Type": "DIMENSION", "Key": "REGION"},
    ]
    assert "NextPageToken" not in first
    assert second["NextPageToken"] == "page-2"


def test_collector_reports_api_failure_as_unavailable() -> None:
    class FakeClient:
        def get_cost_and_usage_with_resources(self, **kwargs: dict) -> dict:
            raise RuntimeError("resource-level billing is disabled")

    class FakeSession:
        def client(self, service_name: str, *, region_name: str):
            return FakeClient()

    result = collect_ec2_resource_costs(
        session=FakeSession(),
        today=date(2026, 10, 10),
    )

    assert result["status"] == "unavailable"
    assert result["resource_attribution"] == "not_available"
    assert result["resources"] == []
    assert "RuntimeError" in result["reason"]