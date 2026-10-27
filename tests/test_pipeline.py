"""
Tests for Verification Pipeline: Concurrency, batch limits, and end-to-end integration.
"""

from unittest.mock import patch

import pytest

from app.dns_checks import DNSCheckResult
from app.pipeline import run_verification_pipeline
from app.smtp_probe import SMTPProbeResult


@pytest.mark.asyncio
async def test_pipeline_max_100_limit():
    """Verify that batches larger than 100 addresses are rejected with ValueError."""
    large_list = [f"user{i}@example.com" for i in range(101)]

    with pytest.raises(ValueError, match="Maximum allowed is 100"):
        await run_verification_pipeline(large_list)


@pytest.mark.asyncio
async def test_pipeline_empty_input():
    results = await run_verification_pipeline("")
    assert results == []

    results_empty_list = await run_verification_pipeline([])
    assert results_empty_list == []


@pytest.mark.asyncio
async def test_pipeline_end_to_end_mocked():
    """Test full pipeline flow with syntax, DNS, and SMTP mocks."""
    raw_input = """
    valid@stripe.com,
    invalid-syntax-email,
    bounced@stripe.com
    """

    mock_dns = DNSCheckResult(
        domain="stripe.com",
        has_valid_mail_server=True,
        mx_hosts=[(10, "mx.stripe.com")],
    )

    async def fake_probe(email, domain, mx_hosts):
        if "valid" in email:
            return SMTPProbeResult(
                email=email,
                domain=domain,
                code=250,
                message="OK",
                reason_code="mailbox_accepted",
            )
        return SMTPProbeResult(
            email=email,
            domain=domain,
            code=550,
            message="No such mailbox",
            reason_code="mailbox_rejected",
        )

    with (
        patch("app.pipeline.check_domain_dns", return_value=mock_dns),
        patch("app.pipeline.probe_email_smtp", side_effect=fake_probe),
    ):
        results = await run_verification_pipeline(raw_input)

        assert len(results) == 3

        # valid@stripe.com
        assert results[0].email == "valid@stripe.com"
        assert results[0].verdict == "deliverable"
        assert results[0].reason == "mailbox_accepted"

        # invalid-syntax-email
        assert results[1].email == "invalid-syntax-email"
        assert results[1].verdict == "bounce"
        assert results[1].reason == "invalid_syntax"

        # bounced@stripe.com
        assert results[2].email == "bounced@stripe.com"
        assert results[2].verdict == "bounce"
        assert results[2].reason == "mailbox_rejected"
