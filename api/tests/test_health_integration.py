"""
Integration test: hits the live /health/ai endpoint via HTTP.
Requires the stack to be running (docker compose up -d).
Run with: docker compose exec api pytest tests/test_health_integration.py -v
Or against live stack: pytest tests/test_health_integration.py -v --base-url=http://localhost:8080/kms/api
"""
import pytest
import httpx


@pytest.mark.integration
def test_health_ai_returns_valid_response():
    """Verify /health/ai returns a valid response from a live stack."""
    try:
        r = httpx.get("http://localhost:8080/kms/api/health/ai", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "ai" in data
        assert data["ai"] in ("online", "offline")
    except httpx.ConnectError:
        pytest.skip("Stack not running — skipping integration test")


@pytest.mark.integration
def test_health_ai_test_env_returns_valid_response():
    """Verify /health/ai returns a valid response from the test stack."""
    try:
        r = httpx.get("http://localhost:8081/kms/api/health/ai", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "ai" in data
        assert data["ai"] in ("online", "offline")
    except httpx.ConnectError:
        pytest.skip("Test stack not running — skipping integration test")
