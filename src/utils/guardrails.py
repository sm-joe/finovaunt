"""Strict models, log redaction, and isolated HCL validation."""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Reject unknown fields."""
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

class ResourceMetric(StrictModel):
    """Normalized read-only cloud utilization data."""
    provider: Literal["aws", "gcp"]
    resource_id: str = Field(min_length=3, max_length=256)
    resource_type: Literal["compute", "database", "storage", "other"]
    name: str = Field(min_length=1, max_length=128)
    region: str
    environment: Literal["dev", "test", "staging", "prod", "unknown"] = "unknown"
    monthly_cost_usd: float = Field(ge=0, le=100_000_000)
    avg_cpu_percent: float = Field(ge=0, le=100)
    peak_cpu_percent: float = Field(ge=0, le=100)
    avg_memory_percent: float | None = Field(default=None, ge=0, le=100)
    production_critical: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)

class OptimizationProposal(StrictModel):
    """Validated proposal, not permission to mutate infrastructure."""
    resource_id: str
    provider: Literal["aws", "gcp"]
    action: Literal["rightsize", "review_only", "no_change"]
    rationale: str = Field(min_length=10, max_length=1200)
    estimated_monthly_savings_usd: float = Field(ge=0, le=100_000_000)
    savings_basis: Literal[
        "simulated_estimate",
        "verified_monthly_cost_estimate",
        "unavailable",
        "not_applicable",
    ] = "unavailable"
    risk: Literal["low", "medium", "high", "critical"]
    requires_human_approval: bool = True
    proposed_instance_type: str | None = None
    optimization_confidence: Literal["low", "medium", "high"] = "low"
    missing_evidence: list[str] = Field(default_factory=list, max_length=20)

class ProposalBundle(StrictModel):
    """Schema for a serialized optimization response."""
    run_id: str = Field(pattern=r"^[a-f0-9]{8,32}$")
    proposals: list[OptimizationProposal] = Field(min_length=1, max_length=100)
    generated_hcl: str = Field(min_length=1, max_length=100_000)

_PATTERNS = [
 (re.compile(r"(?i)\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
 (re.compile(r"(?i)\bASIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_SESSION_KEY]"),
 (re.compile(r"(?i)\b(aws_secret_access_key|secret_access_key)\s*[:=]\s*[^\s,;]+"), r"\1=[REDACTED]"),
 (re.compile(r"(?i)\b(authorization\s*:\s*bearer)\s+[A-Za-z0-9._~+/=-]+"), r"\1 [REDACTED]"),
 (re.compile(r"(?i)\bAIza[0-9A-Za-z_-]{30,}\b"), "[REDACTED_GOOGLE_KEY]"),
 (re.compile(r"(?i)\b(client_secret|access_token|refresh_token)\s*[:=]\s*[^\s,;]+"), r"\1=[REDACTED]"),
 (re.compile(r"(?<!\d)\d{12}(?!\d)"), "[REDACTED_ACCOUNT_ID]"),
]
def scrub_sensitive_text(value: object) -> str:
    """Redact common cloud secrets and account identifiers."""
    result = str(value)
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result

def strip_markdown_fences(value: str) -> str:
    """Strip one outer HCL fence and reject nested fences."""
    text = value.strip()
    match = re.fullmatch(r"```(?:hcl|terraform|tf)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    if match:
        text = match.group(1).strip()
    if "```" in text or "\x00" in text:
        raise ValueError("Disallowed Markdown fence or NUL")
    return text + "\n"

def validate_hcl_locally(generated_text: str, *, require_tflint: bool = False, timeout_seconds: int = 20) -> str:
    """Run terraform fmt and optional TFLint in a temporary directory, without a shell."""
    if not generated_text.strip() or len(generated_text) > 100_000:
        raise ValueError("HCL must be non-empty and at most 100 KB")
    hcl = strip_markdown_fences(generated_text)
    if re.search(r"(?m)^\s*(?:#!|<\?|<script\b)", hcl, re.IGNORECASE):
        raise ValueError("Script markers rejected")
    terraform = shutil.which("terraform")
    if not terraform:
        raise RuntimeError("terraform executable not found on PATH")
    tflint = shutil.which("tflint")
    if (require_tflint or os.getenv("FINOPS_REQUIRE_TFLINT", "false").lower() == "true") and not tflint:
        raise RuntimeError("tflint is required but missing")
    with tempfile.TemporaryDirectory(prefix="finops-hcl-") as temp:
        work = Path(temp)
        target = work / "main.tf"
        target.write_text(hcl, encoding="utf-8")
        fmt = subprocess.run([terraform, "fmt", "-no-color", str(target)], check=False, cwd=work, capture_output=True, text=True, timeout=timeout_seconds, shell=False)
        if fmt.returncode:
            raise ValueError("terraform fmt failed: " + scrub_sensitive_text(fmt.stderr or fmt.stdout))
        formatted = target.read_text(encoding="utf-8")
        if tflint:
            lint = subprocess.run([tflint, "--chdir", str(work), "--format", "compact"], check=False, cwd=work, capture_output=True, text=True, timeout=timeout_seconds, shell=False)
            if lint.returncode:
                raise ValueError("tflint failed: " + scrub_sensitive_text(lint.stderr or lint.stdout))
        return formatted
