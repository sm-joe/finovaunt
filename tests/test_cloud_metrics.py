from src.tools.cloud_metrics import (
    _environment_from_tags,
    _summarize_cpu_datapoints,
)


def test_environment_tag_normalization():
    assert _environment_from_tags([
        {"Key": "Environment", "Value": "Production"}
    ]) == "prod"

    assert _environment_from_tags([
        {"Key": "env", "Value": "development"}
    ]) == "dev"

    assert _environment_from_tags([]) == "unknown"


def test_cpu_metrics_are_summarized():
    datapoints = [
        {"Average": 10.0, "Maximum": 22.0},
        {"Average": 20.0, "Maximum": 45.0},
        {"Average": 30.0, "Maximum": 38.0},
    ]

    assert _summarize_cpu_datapoints(datapoints) == (20.0, 45.0)


def test_missing_cpu_telemetry_is_not_treated_as_zero():
    assert _summarize_cpu_datapoints([]) is None
    assert _summarize_cpu_datapoints([
        {"Timestamp": "2026-10-10T00:00:00Z"}
    ]) is None