from src.utils.guardrails import ResourceMetric, scrub_sensitive_text, strip_markdown_fences

def test_invalid_cpu_rejected():
    try:
        ResourceMetric(provider="aws", resource_id="aws:ec2:abc", resource_type="compute", name="x", region="eu-central-1", monthly_cost_usd=1, avg_cpu_percent=101, peak_cpu_percent=20)
    except ValueError:
        return
    raise AssertionError("invalid CPU should fail")

def test_scrub_secrets():
    value = scrub_sensitive_text("AKIAABCDEFGHIJKLMNOP 123456789012")
    assert "AKIAABCDEFGHIJKLMNOP" not in value and "123456789012" not in value

def test_strip_fence():
    assert "locals {}" in strip_markdown_fences("```hcl\nlocals {}\n```")
