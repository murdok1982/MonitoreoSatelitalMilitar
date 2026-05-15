"""
Unit tests for AEGIS-IMINT FastAPI REST API.
Tests cover:
  - API key validation (verify_api_key)
  - RateLimitMiddleware (N requests then 429)
  - Core endpoints (status, analyze, history, zones, reports)

Run: python3 -m pytest tests/test_api.py -v
  or: python3 -m unittest tests.test_api -v
"""
import os
import sys
import asyncio
import time
import unittest
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Helpers to create a minimal ASGI test client without requiring the full
# project's database / Ollama / GDELT stack.
# ---------------------------------------------------------------------------
from fastapi.testclient import TestClient
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader

VALID_KEY = "test-aegis-key-9999"

# Patch env before importing api.main so stubs pick it up
os.environ["AEGIS_API_KEY"] = VALID_KEY
os.environ.setdefault("AEGIS_DB_PATH", ":memory:")

from api.middleware import RateLimitMiddleware


# ---------------------------------------------------------------------------
# Minimal app fixture for middleware and auth tests
# ---------------------------------------------------------------------------

def _make_minimal_app(max_requests: int = 5, window_seconds: int = 60) -> FastAPI:
    """Create a tiny FastAPI app with RateLimitMiddleware for isolation."""
    _app = FastAPI()
    _app.add_middleware(RateLimitMiddleware, max_requests=max_requests,
                        window_seconds=window_seconds)

    _api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

    def _verify(key: str = Security(_api_key_header)) -> str:
        if key != VALID_KEY:
            raise HTTPException(status_code=403, detail="API Key invalida")
        return key

    @_app.get("/ping")
    def ping(key: str = Depends(_verify)):
        return {"pong": True}

    @_app.get("/open")
    def open_route():
        return {"ok": True}

    return _app


# ---------------------------------------------------------------------------
# Tests: RateLimitMiddleware
# ---------------------------------------------------------------------------

class TestRateLimitMiddleware(unittest.TestCase):
    """Verify that the sliding-window rate limiter enforces the request cap."""

    def setUp(self):
        self.app = _make_minimal_app(max_requests=3, window_seconds=60)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def _headers(self):
        return {"X-API-Key": VALID_KEY}

    def test_allows_requests_up_to_limit(self):
        for i in range(3):
            resp = self.client.get("/ping", headers=self._headers())
            self.assertEqual(resp.status_code, 200,
                             f"Request {i+1} should succeed (got {resp.status_code})")

    def test_blocks_request_over_limit(self):
        for _ in range(3):
            self.client.get("/ping", headers=self._headers())
        resp = self.client.get("/ping", headers=self._headers())
        self.assertEqual(resp.status_code, 429,
                         "4th request should be rate-limited (429)")

    def test_429_response_is_json(self):
        for _ in range(3):
            self.client.get("/ping", headers=self._headers())
        resp = self.client.get("/ping", headers=self._headers())
        self.assertEqual(resp.headers.get("content-type", ""), "application/json")
        body = resp.json()
        self.assertIn("detail", body)

    def test_rate_limit_headers_present_on_success(self):
        resp = self.client.get("/open")
        self.assertIn("X-RateLimit-Limit", resp.headers)
        self.assertIn("X-RateLimit-Remaining", resp.headers)
        self.assertIn("X-RateLimit-Window", resp.headers)

    def test_rate_limit_remaining_decreases(self):
        resp1 = self.client.get("/open")
        rem1 = int(resp1.headers["X-RateLimit-Remaining"])
        resp2 = self.client.get("/open")
        rem2 = int(resp2.headers["X-RateLimit-Remaining"])
        self.assertGreater(rem1, rem2, "Remaining count should decrease with each request")

    def test_retry_after_header_on_429(self):
        for _ in range(3):
            self.client.get("/open")
        resp = self.client.get("/open")
        self.assertEqual(resp.status_code, 429)
        self.assertIn("Retry-After", resp.headers)

    def test_different_ips_have_independent_buckets(self):
        """Requests from different IPs use separate rate-limit buckets."""
        # Exhaust quota for first IP
        for _ in range(3):
            self.client.get("/open", headers={"X-Forwarded-For": "10.0.0.1"})
        blocked = self.client.get("/open", headers={"X-Forwarded-For": "10.0.0.1"})
        self.assertEqual(blocked.status_code, 429)

        # Second IP should still be allowed
        allowed = self.client.get("/open", headers={"X-Forwarded-For": "10.0.0.2"})
        self.assertEqual(allowed.status_code, 200)

    def test_window_reset_allows_new_requests(self):
        """After the window expires old entries are evicted and requests pass."""
        app = _make_minimal_app(max_requests=2, window_seconds=1)
        client = TestClient(app, raise_server_exceptions=False)

        for _ in range(2):
            client.get("/open")

        # Over limit
        self.assertEqual(client.get("/open").status_code, 429)

        # Wait for window to expire
        time.sleep(1.1)
        self.assertEqual(client.get("/open").status_code, 200)


# ---------------------------------------------------------------------------
# Tests: API key validation logic
# ---------------------------------------------------------------------------

class TestApiKeyValidation(unittest.TestCase):
    """Verify that verify_api_key accepts the correct key and rejects others."""

    def setUp(self):
        self.app = _make_minimal_app(max_requests=1000)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_valid_key_grants_access(self):
        resp = self.client.get("/ping", headers={"X-API-Key": VALID_KEY})
        self.assertEqual(resp.status_code, 200)

    def test_wrong_key_returns_403(self):
        resp = self.client.get("/ping", headers={"X-API-Key": "wrong-key"})
        self.assertEqual(resp.status_code, 403)

    def test_missing_key_returns_401_403_or_422(self):
        resp = self.client.get("/ping")
        self.assertIn(resp.status_code, (401, 403, 422),
                      "Missing key should return 401, 403, or 422")

    def test_empty_key_returns_auth_error(self):
        resp = self.client.get("/ping", headers={"X-API-Key": ""})
        self.assertIn(resp.status_code, (401, 403, 422))

    def test_wrong_key_body_contains_detail(self):
        resp = self.client.get("/ping", headers={"X-API-Key": "bad"})
        body = resp.json()
        self.assertIn("detail", body)

    def test_key_is_case_sensitive(self):
        resp = self.client.get("/ping",
                               headers={"X-API-Key": VALID_KEY.upper()})
        self.assertNotEqual(resp.status_code, 200,
                            "Key comparison must be case-sensitive")


# ---------------------------------------------------------------------------
# Tests: RateLimitMiddleware unit-level (bucket logic)
# ---------------------------------------------------------------------------

class TestRateLimitBucketLogic(unittest.TestCase):
    """White-box tests on the middleware's internal sliding-window bucket."""

    def _make_middleware(self, max_req=5, window=60):
        dummy_app = FastAPI()
        mw = RateLimitMiddleware(dummy_app, max_requests=max_req,
                                 window_seconds=window)
        return mw

    def test_bucket_evicts_old_entries(self):
        mw = self._make_middleware(max_req=3, window=1)
        ip = "192.168.1.1"
        now = time.time()
        # Manually insert stale entries
        mw._buckets[ip].extend([now - 5, now - 3, now - 2])
        # Simulate eviction (mimics the logic in dispatch)
        bucket = mw._buckets[ip]
        while bucket and bucket[0] < now - mw.window:
            bucket.popleft()
        self.assertEqual(len(bucket), 0, "All entries outside window should be evicted")

    def test_bucket_does_not_evict_recent_entries(self):
        mw = self._make_middleware(max_req=5, window=60)
        ip = "10.1.1.1"
        now = time.time()
        mw._buckets[ip].extend([now - 10, now - 5, now - 1])
        bucket = mw._buckets[ip]
        while bucket and bucket[0] < now - mw.window:
            bucket.popleft()
        self.assertEqual(len(bucket), 3)

    def test_bucket_is_per_ip(self):
        mw = self._make_middleware()
        mw._buckets["1.1.1.1"].append(time.time())
        mw._buckets["2.2.2.2"].append(time.time())
        self.assertEqual(len(mw._buckets["1.1.1.1"]), 1)
        self.assertEqual(len(mw._buckets["2.2.2.2"]), 1)
        self.assertNotIn("3.3.3.3", mw._buckets)


# ---------------------------------------------------------------------------
# Tests: /api/status endpoint via full app
# ---------------------------------------------------------------------------

class TestApiStatusEndpoint(unittest.TestCase):
    """Test the /api/status endpoint on the real app (with stubs active)."""

    @classmethod
    def setUpClass(cls):
        # Import the real app — stubs are loaded because project deps missing
        from api.main import app
        cls.client = TestClient(app, raise_server_exceptions=False)
        cls.headers = {"X-API-Key": VALID_KEY}

    def test_status_200_with_valid_key(self):
        resp = self.client.get("/api/status", headers=self.headers)
        self.assertEqual(resp.status_code, 200)

    def test_status_auth_required_without_key(self):
        resp = self.client.get("/api/status")
        self.assertIn(resp.status_code, (401, 403, 422))

    def test_status_has_required_fields(self):
        resp = self.client.get("/api/status", headers=self.headers)
        body = resp.json()
        for field in ("status", "version", "ollama_available", "db_path", "timestamp"):
            self.assertIn(field, body, f"Missing field: {field}")

    def test_status_version_is_string(self):
        resp = self.client.get("/api/status", headers=self.headers)
        self.assertIsInstance(resp.json()["version"], str)

    def test_status_operational(self):
        resp = self.client.get("/api/status", headers=self.headers)
        self.assertEqual(resp.json()["status"], "operational")


# ---------------------------------------------------------------------------
# Tests: /api/reports endpoint
# ---------------------------------------------------------------------------

class TestApiReportsEndpoint(unittest.TestCase):
    """Test report listing and download safety checks."""

    @classmethod
    def setUpClass(cls):
        from api.main import app
        cls.client = TestClient(app, raise_server_exceptions=False)
        cls.headers = {"X-API-Key": VALID_KEY}

    def test_list_reports_returns_list(self):
        resp = self.client.get("/api/reports", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_download_nonexistent_report_404(self):
        resp = self.client.get("/api/reports/nonexistent.pdf",
                               headers=self.headers)
        self.assertEqual(resp.status_code, 404)

    def test_download_non_pdf_rejected(self):
        resp = self.client.get("/api/reports/some_file.txt",
                               headers=self.headers)
        self.assertIn(resp.status_code, (400, 404))

    def test_path_traversal_rejected(self):
        resp = self.client.get("/api/reports/../secret.pdf",
                               headers=self.headers)
        # FastAPI normalises the URL so path ends up as /api/reports/secret.pdf
        # Either 400 or 404 is acceptable — must NOT be 200
        self.assertNotEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Tests: /api/history endpoint
# ---------------------------------------------------------------------------

class TestApiHistoryEndpoint(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from api.main import app
        cls.client = TestClient(app, raise_server_exceptions=False)
        cls.headers = {"X-API-Key": VALID_KEY}

    def test_history_returns_list(self):
        resp = self.client.get("/api/history", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_history_requires_auth(self):
        resp = self.client.get("/api/history")
        self.assertIn(resp.status_code, (401, 403, 422))

    def test_history_limit_param_accepted(self):
        resp = self.client.get("/api/history?limit=10", headers=self.headers)
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Tests: /api/zones endpoint
# ---------------------------------------------------------------------------

class TestApiZonesEndpoint(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from api.main import app
        cls.client = TestClient(app, raise_server_exceptions=False)
        cls.headers = {"X-API-Key": VALID_KEY}

    def test_list_zones_returns_list(self):
        resp = self.client.get("/api/zones", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_create_zone_returns_created(self):
        payload = {
            "nombre": "Zona Test",
            "lon_min": -4.0,
            "lat_min": 40.0,
            "lon_max": -3.5,
            "lat_max": 40.5,
        }
        resp = self.client.post("/api/zones", json=payload, headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get("status"), "created")
        self.assertEqual(body.get("nombre"), "Zona Test")

    def test_create_zone_requires_auth(self):
        payload = {
            "nombre": "No Auth Zone",
            "lon_min": 0.0, "lat_min": 0.0,
            "lon_max": 1.0, "lat_max": 1.0,
        }
        resp = self.client.post("/api/zones", json=payload)
        self.assertIn(resp.status_code, (401, 403, 422))


# ---------------------------------------------------------------------------
# Tests: /api/analyze endpoint (demo mode)
# ---------------------------------------------------------------------------

class TestApiAnalyzeEndpoint(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from api.main import app
        cls.client = TestClient(app, raise_server_exceptions=False)
        cls.headers = {"X-API-Key": VALID_KEY}
        cls.payload = {
            "lon_min": -3.7,
            "lat_min": 40.4,
            "lon_max": -3.6,
            "lat_max": 40.5,
            "zone_name": "Test Zone",
            "generate_report": False,
            "alert_threshold": 999,  # prevent real alerts
        }

    def test_analyze_returns_200(self):
        resp = self.client.post("/api/analyze", json=self.payload,
                                headers=self.headers)
        self.assertEqual(resp.status_code, 200)

    def test_analyze_response_has_required_fields(self):
        resp = self.client.post("/api/analyze", json=self.payload,
                                headers=self.headers)
        body = resp.json()
        for field in ("scan_id", "timestamp", "vehicle_count",
                      "threat_level", "threat_action", "bbox", "alert_sent"):
            self.assertIn(field, body, f"Missing field: {field}")

    def test_analyze_bbox_echoed(self):
        resp = self.client.post("/api/analyze", json=self.payload,
                                headers=self.headers)
        body = resp.json()
        self.assertEqual(body["bbox"],
                         [-3.7, 40.4, -3.6, 40.5])

    def test_analyze_threat_level_valid(self):
        resp = self.client.post("/api/analyze", json=self.payload,
                                headers=self.headers)
        self.assertIn(resp.json()["threat_level"],
                      ("VERDE", "AMARILLO", "NARANJA", "ROJO"))

    def test_analyze_requires_auth(self):
        resp = self.client.post("/api/analyze", json=self.payload)
        self.assertIn(resp.status_code, (401, 403, 422))

    def test_analyze_missing_bbox_returns_422(self):
        resp = self.client.post("/api/analyze", json={"zone_name": "Bad"},
                                headers=self.headers)
        self.assertEqual(resp.status_code, 422)


if __name__ == '__main__':
    unittest.main(verbosity=2)
