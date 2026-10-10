from datetime import date

from src.tools.aws_costs import (
    parse_cost_responses,
    previous_complete_month,
)


def test_previous_complete_month_in_october():
    assert previous_complete_month(date(2026, 10, 10)) == (
        "2026-09-01",
        "2026-10-01",
    )


def test_previous_complete_month_crosses_year_boundary():
    assert previous_complete_month(date(2026, 1, 10)) == (
        "2025-12-01",
        "2026-01-01",
    )


def test_cost_response_groups_by_service_and_region():
    response = {
        "ResultsByTime": [
            {
                "Total": {
                    "UnblendedCost": {
                        "Amount": "125.50",
                        "Unit": "USD",
                    }
                },
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud", "EU-Central-1"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "100.00",
                                "Unit": "USD",
                            }
                        },
                    },
                    {
                        "Keys": ["Amazon Relational Database Service", "EU-Central-1"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "25.50",
                                "Unit": "USD",
                            }
                        },
                    },
                ],
            }
        ]
    }

    result = parse_cost_responses(
        [response],
        period_start="2026-09-01",
        period_end_exclusive="2026-10-01",
    )

    assert result["status"] == "available"
    assert result["total_cost"] == 125.5
    assert result["currency"] == "USD"
    assert result["period_start"] == "2026-09-01"
    assert result["period_end_exclusive"] == "2026-10-01"
    assert len(result["groups"]) == 2
    assert result["resource_attribution"] == "not_available"


def test_cost_response_with_no_results_is_unavailable():
    result = parse_cost_responses(
        [],
        period_start="2026-09-01",
        period_end_exclusive="2026-10-01",
    )

    assert result["status"] == "unavailable"
    assert result["resource_attribution"] == "not_available"