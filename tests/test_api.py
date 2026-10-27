"""
Tests for API endpoints: /api/check, /api/health, rate limiting, and static serving.
"""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.classify import VerificationResult
from app.main import app


@pytest.mark.asyncio
async def test_api_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.main.check_outbound_smtp_capability", return_value=True):
            response = await client.get("/api/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["smtp_available"] is True
            assert data["mode"] == "full"


@pytest.mark.asyncio
async def test_api_health_endpoint_degraded():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.main.check_outbound_smtp_capability", return_value=False):
            response = await client.get("/api/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["smtp_available"] is False
            assert data["mode"] == "dns_only"


@pytest.mark.asyncio
async def test_api_check_valid_request():
    mock_results = [
        VerificationResult(
            email="test@example.com",
            verdict="deliverable",
            reason="mailbox_accepted",
            explanation="Mailbox confirmed.",
            flags=["free_provider"],
        )
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.main.run_verification_pipeline", return_value=mock_results):
            response = await client.post(
                "/api/check",
                json={"emails": ["test@example.com"]},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["deliverable"] == 1
            assert data["bounce"] == 0
            assert len(data["results"]) == 1
            item = data["results"][0]
            assert item["email"] == "test@example.com"
            assert item["verdict"] == "deliverable"
            assert item["reason"] == "mailbox_accepted"


@pytest.mark.asyncio
async def test_api_check_exceeds_max_limit():
    large_list = [f"user{i}@example.com" for i in range(101)]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/check",
            json={"emails": large_list},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Maximum allowed is 100" in data["detail"]


@pytest.mark.asyncio
async def test_api_serve_index():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "Email Deliverability Checker" in response.text
