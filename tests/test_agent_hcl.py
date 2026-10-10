from src.agent import optimize
from src.tools.cloud_metrics import collect_mock_metrics


def test_generated_hcl_declares_terraform_version_and_uses_output():
    result = optimize({"metrics": [m.model_dump(mode="json") for m in collect_mock_metrics()]})
    hcl = result["generated_hcl"]

    assert 'required_version = ">= 1.5.0"' in hcl
    assert 'output "finops_review"' in hcl
    assert "locals {" not in hcl
