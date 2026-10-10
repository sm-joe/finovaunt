"""Regression tests for read-only AWS Cost Explorer billing."""

from datetime import date
from decimal import Decimal

import pytest

from src.tools.aws_costs import (
    collect_aws_cost_summary,
    parse_cost_responses,
    previous_complete_month,
)


def _cost_group(
    service: str,
    region: str,
    amount: str,
    currency: str = "USD",
) -> dict:
    return {
        "Keys": [service, region],
        "Metrics": {
            "UnblendedCost": {
                "Amount": amount,
                "Unit": currency,
            }
        },
    }


def _result(
    *,
    total: dict | None = None,
    groups: list[dict] | None = None,
) -> dict:
    return {
        "ResultsByTime": [
            {
                "TimePeriod": {
                    "Start": "2026-09-01",
                    "End": "2026-10-01",
                },
                "Total": total if total is not None else {},
                "Groups": groups or [],
            }
        ]
    }


@pytest.mark.parametrize(
    ("today", "expected_start", "expected_end"),
    [
        (
            date(2026, 10, 10),
            "2026-09-01",
            "2026-10-01",
        ),
        (
            date(2026, 1, 1),
            "2025-12-01",
            "2026-01-01",
        ),
        (
            date(2024, 3, 1),
            "2024-02-01",
            "2024-03-01",
        ),
        (
            date(2024, 2, 29),
            "2024-01-01",
            "2024-02-01",
        ),
    ],
)
def test_previous_complete_month(
    today: date,
    expected_start: str,
    expected_end: str,
) -> None:
    assert previous_complete_month(today) == (
        expected_start,
        expected_end,
    )


def test_parser_prefers_account_level_total() -> None:
    response = _result(
        total={
            "UnblendedCost": {
                "Amount": "100.50",
                "Unit": "USD",
            }
        },
        groups=[
            _cost_group(
                "Amazon EC2",
                "us-east-1",
                "75.25",
            ),
            _cost_group(
                "Amazon S3",
                "us-east-1",
                "25.25",
            ),
        ],
    )

    summary = parse_cost_responses(
        [response],
        period_start="2026-09-01",
        period_end_exclusive="2026-10-01",
    )

    assert summary["status"] == "available"
    assert summary["total_cost"] == 100.50
    assert summary["currency"] == "USD"
    assert summary["metric"] == "UnblendedCost"
    assert summary["group_by"] == ["SERVICE", "REGION"]
    assert summary["resource_attribution"] == "not_available"
    assert len(summary["groups"]) == 2

    # Account-level cost must not be represented as a resource cost.
    assert "resource_id" not in summary
    assert "realized_savings" not in summary


def test_parser_sorts_groups_by_cost_descending() -> None:
    response = _result(
        total={
            "UnblendedCost": {
                "Amount": "16",
                "Unit": "USD",
            }
        },
        groups=[
            _cost_group("Amazon S3", "us-east-1", "1"),
            _cost_group("Amazon EC2", "us-east-1", "10"),
            _cost_group("AWS Lambda", "us-east-1", "5"),
        ],
    )

    summary = parse_cost_responses(
        [response],
        period_start="2026-09-01",
        period_end_exclusive="2026-10-01",
    )

    assert [
        group["service"] for group in summary["groups"]
    ] == [
        "Amazon EC2",
        "AWS Lambda",
        "Amazon S3",
    ]


def test_parser_sums_groups_when_account_total_is_empty() -> None:
    response = _result(
        total={},
        groups=[
            _cost_group("Amazon EC2", "us-east-1", "10.25"),
            _cost_group("Amazon S3", "us-east-1", "2.25"),
        ],
    )

    summary = parse_cost_responses(
        [response],
        period_start="2026-09-01",
        period_end_exclusive="2026-10-01",
    )

    assert summary["status"] == "available"
    assert summary["total_cost"] == 12.5
    assert summary["currency"] == "USD"
    assert len(summary["groups"]) == 2


def test_parser_combines_repeated_groups_across_pages() -> None:
    responses = [
        _result(
            total={
                "UnblendedCost": {
                    "Amount": "15",
                    "Unit": "USD",
                }
            },
            groups=[
                _cost_group("Amazon EC2", "us-east-1", "5"),
            ],
        ),
        _result(
            total={},
            groups=[
                _cost_group("Amazon EC2", "us-east-1", "10"),
            ],
        ),
    ]

    summary = parse_cost_responses(
        responses,
        period_start="2026-09-01",
        period_end_exclusive="2026-10-01",
    )

    assert summary["status"] == "available"
    assert summary["total_cost"] == 15
    assert len(summary["groups"]) == 1
    assert summary["groups"][0]["amount"] == 15


def test_parser_rejects_group_fallback_with_mixed_currencies() -> None:
    response = _result(
        total={},
        groups=[
            _cost_group(
                "Amazon EC2",
                "us-east-1",
                "10",
                "USD",
            ),
            _cost_group(
                "Amazon S3",
                "eu-west-1",
                "5",
                "EUR",
            ),
        ],
    )

    summary = parse_cost_responses(
        [response],
        period_start="2026-09-01",
        period_end_exclusive="2026-10-01",
    )

    assert summary["status"] == "unavailable"
    assert "multiple currencies" in summary["reason"]
    assert summary["resource_attribution"] == "not_available"


def test_parser_returns_unavailable_for_no_pages() -> None:
    summary = parse_cost_responses(
        [],
        period_start="2026-09-01",
        period_end_exclusive="2026-10-01",
    )

    assert summary["status"] == "unavailable"
    assert summary["resource_attribution"] == "not_available"


def test_parser_returns_unavailable_without_usable_cost_data() -> None:
    summary = parse_cost_responses(
        [_result(total={}, groups=[])],
        period_start="2026-09-01",
        period_end_exclusive="2026-10-01",
    )

    assert summary["status"] == "unavailable"
    assert "neither an account-level total" in summary["reason"]


@pytest.mark.parametrize(
    "invalid_amount",
    [
        "not-a-number",
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_parser_rejects_invalid_group_amounts(
    invalid_amount: str,
) -> None:
    response = _result(
        total={},
        groups=[
            _cost_group(
                "Amazon EC2",
                "us-east-1",
                invalid_amount,
            ),
        ],
    )

    with pytest.raises(ValueError, match="cost amount"):
        parse_cost_responses(
            [response],
            period_start="2026-09-01",
            period_end_exclusive="2026-10-01",
        )


def test_parser_rejects_invalid_account_total() -> None:
    response = _result(
        total={
            "UnblendedCost": {
                "Amount": "invalid",
                "Unit": "USD",
            }
        },
        groups=[
            _cost_group("Amazon EC2", "us-east-1", "10"),
        ],
    )

    with pytest.raises(ValueError, match="cost amount"):
        parse_cost_responses(
            [response],
            period_start="2026-09-01",
            period_end_exclusive="2026-10-01",
        )


def test_parser_uses_decimal_arithmetic_for_group_sums() -> None:
    response = _result(
        total={},
        groups=[
            _cost_group("Service A", "us-east-1", "0.1"),
            _cost_group("Service B", "us-east-1", "0.2"),
        ],
    )

    summary = parse_cost_responses(
        [response],
        period_start="2026-09-01",
        period_end_exclusive="2026-10-01",
    )

    expected = float(Decimal("0.1") + Decimal("0.2"))

    assert summary["status"] == "available"
    assert summary["total_cost"] == expected


def test_collect_aws_cost_summary_follows_pagination() -> None:
    first_page = {
        "ResultsByTime": [
            {
                "Total": {
                    "UnblendedCost": {
                        "Amount": "15",
                        "Unit": "USD",
                    }
                },
                "Groups": [
                    _cost_group(
                        "Amazon EC2",
                        "us-east-1",
                        "5",
                    )
                ],
            }
        ],
        "NextPageToken": "page-two",
    }

    second_page = {
        "ResultsByTime": [
            {
                "Total": {},
                "Groups": [
                    _cost_group(
                        "Amazon S3",
                        "us-east-1",
                        "10",
                    )
                ],
            }
        ]
    }

    class FakeClient:
        def __init__(self) -> None:
            self.requests: list[dict] = []
            self.responses = [first_page, second_page]

        def get_cost_and_usage(self, **kwargs) -> dict:
            self.requests.append(kwargs)
            return self.responses[len(self.requests) - 1]

    class FakeSession:
        def __init__(self) -> None:
            self.client_instance = FakeClient()
            self.client_arguments: list[tuple] = []
            self.client_kwargs: list[dict] = []

        def client(self, *args, **kwargs) -> FakeClient:
            self.client_arguments.append(args)
            self.client_kwargs.append(kwargs)
            return self.client_instance

    session = FakeSession()

    summary = collect_aws_cost_summary(
        session=session,
        today=date(2026, 10, 10),
    )

    assert summary["status"] == "available"
    assert summary["period_start"] == "2026-09-01"
    assert summary["period_end_exclusive"] == "2026-10-01"
    assert summary["total_cost"] == 15

    assert session.client_arguments == [("ce",)]
    assert session.client_kwargs == [{"region_name": "us-east-1"}]

    requests = session.client_instance.requests
    assert len(requests) == 2

    assert requests[0]["TimePeriod"] == {
        "Start": "2026-09-01",
        "End": "2026-10-01",
    }
    assert requests[0]["Granularity"] == "MONTHLY"
    assert requests[0]["Metrics"] == ["UnblendedCost"]

    assert "NextPageToken" not in requests[0]
    assert requests[1]["NextPageToken"] == "page-two"