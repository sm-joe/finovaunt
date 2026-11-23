"""Prevent the login 502 regression caused by root-owned Docker bind mounts."""
from pathlib import Path

import yaml


def test_compose_repairs_persisted_data_permissions_before_nonroot_api():
    repo = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((repo / "docker-compose.yml").read_text(encoding="utf-8"))
    services = config["services"]
    setup = services["init-data"]
    api = services["api"]

    assert setup["user"] == "0:0"
    assert setup["restart"] == "no"
    assert "CHOWN" in setup["cap_add"]
    assert any("./data:/app/data" == volume for volume in setup["volumes"])
    command = "\n".join(setup["command"])
    assert "chown -R 10001:10001 /app/data" in command
    assert api["depends_on"]["init-data"]["condition"] == "service_completed_successfully"
    assert any("./data:/app/data" == volume for volume in api["volumes"])
    assert api["read_only"] is True
    assert "ALL" in api["cap_drop"]

    dockerfile = (repo / "Dockerfile").read_text(encoding="utf-8")
    assert "USER 10001:10001" in dockerfile
