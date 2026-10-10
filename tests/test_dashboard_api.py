from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen

import scripts.dashboard_api as dashboard_api


def test_health_endpoint_and_read_only_rejection() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_api.DashboardHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base}/api/health", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["read_only"] is True

        request = Request(f"{base}/api/overview", data=b"{}", method="POST")
        try:
            urlopen(request, timeout=2)
            raise AssertionError("POST should be rejected by the read-only API")
        except Exception as exc:
            assert getattr(exc, "code", None) == 405
            payload = json.loads(exc.read().decode("utf-8"))
            assert payload["error"] == "method_not_allowed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
