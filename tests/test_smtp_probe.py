"""
Tests for Stage D & E: SMTP verification, Catch-all detection, and strict architectural safety guarantees.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.smtp_probe import (
    _ensure_safety_constraints,
    _execute_single_rcpt_probe,
    probe_catch_all,
    probe_email_smtp,
)


def test_safety_constraint_strictly_forbids_data():
    """Critical safety guarantee: DATA command is strictly forbidden and raises RuntimeError."""
    with pytest.raises(RuntimeError, match="DATA command is strictly forbidden"):
        _ensure_safety_constraints("DATA")

    with pytest.raises(RuntimeError, match="DATA command is strictly forbidden"):
        _ensure_safety_constraints("data")

    # Allowed commands should not raise
    _ensure_safety_constraints("EHLO")
    _ensure_safety_constraints("MAIL FROM")
    _ensure_safety_constraints("RCPT TO")
    _ensure_safety_constraints("QUIT")


@pytest.mark.asyncio
async def test_smtp_mailbox_accepted():
    """Verify 250 response translates to mailbox_accepted when catch-all is false."""
    with (
        patch("app.smtp_probe.check_outbound_smtp_capability", return_value=True),
        patch("app.smtp_probe._execute_single_rcpt_probe", return_value=(250, "OK")),
        patch("app.smtp_probe.probe_catch_all", return_value=False),
    ):
        result = await probe_email_smtp(
            email="valid.user@example.com",
            domain="example.com",
            mx_hosts=[(10, "mx.example.com")],
        )

        assert result.reason_code == "mailbox_accepted"
        assert result.code == 250
        assert result.is_catch_all is False


@pytest.mark.asyncio
async def test_smtp_mailbox_rejected():
    """Verify 550 response translates to mailbox_rejected."""
    with (
        patch("app.smtp_probe.check_outbound_smtp_capability", return_value=True),
        patch("app.smtp_probe._execute_single_rcpt_probe", return_value=(550, "User unknown")),
    ):
        result = await probe_email_smtp(
            email="invalid.user@example.com",
            domain="example.com",
            mx_hosts=[(10, "mx.example.com")],
        )

        assert result.reason_code == "mailbox_rejected"
        assert result.code == 550


@pytest.mark.asyncio
async def test_smtp_catch_all_detection():
    """Verify that if domain accepts synthetic addresses, reason becomes catch_all."""
    with (
        patch("app.smtp_probe.check_outbound_smtp_capability", return_value=True),
        patch("app.smtp_probe._execute_single_rcpt_probe", return_value=(250, "OK")),
        patch("app.smtp_probe.probe_catch_all", return_value=True),
    ):
        result = await probe_email_smtp(
            email="any.user@catchall-domain.com",
            domain="catchall-domain.com",
            mx_hosts=[(10, "mx.catchall-domain.com")],
        )

        assert result.reason_code == "catch_all"
        assert result.is_catch_all is True


@pytest.mark.asyncio
async def test_probe_catch_all_function():
    """Verify probe_catch_all returns True when synthetic address receives 250."""
    with patch("app.smtp_probe._execute_single_rcpt_probe", return_value=(250, "Recipient ok")):
        is_catch_all = await probe_catch_all("mx.domain.com", "domain-synthetic-check.com")
        assert is_catch_all is True

    with patch("app.smtp_probe._execute_single_rcpt_probe", return_value=(550, "No such user")):
        is_catch_all = await probe_catch_all("mx.domain.com", "domain-synthetic-check-2.com")
        assert is_catch_all is False


@pytest.mark.asyncio
async def test_smtp_temporary_failure_retry():
    """Verify 450 greylisting retries at most once."""
    mock_probe = AsyncMock(side_effect=[(450, "Greylisted, please try again"), (450, "Greylisted")])

    with (
        patch("app.smtp_probe.check_outbound_smtp_capability", return_value=True),
        patch("app.smtp_probe._execute_single_rcpt_probe", mock_probe),
        patch("asyncio.sleep", return_value=None),
    ):
        result = await probe_email_smtp(
            email="greylisted@example.com",
            domain="example.com",
            mx_hosts=[(10, "mx.example.com")],
        )

        assert result.reason_code == "temporary_failure"
        assert mock_probe.call_count == 2  # 1 initial + 1 retry


@pytest.mark.asyncio
async def test_smtp_unavailable_degraded_mode():
    """Verify that when host blocks port 25, probe returns smtp_unavailable."""
    with patch("app.smtp_probe.check_outbound_smtp_capability", return_value=False):
        result = await probe_email_smtp(
            email="user@blocked-host.com",
            domain="blocked-host.com",
            mx_hosts=[(10, "mx.blocked-host.com")],
        )

        assert result.reason_code == "smtp_unavailable"
        assert result.details.get("active_mode") == "dns_only"


@pytest.mark.asyncio
async def test_proves_no_data_command_or_message_is_sent():
    """
    CRITICAL TEST: Asserts that neither data() nor send_message() is EVER invoked on the SMTP client.
    """
    mock_client = AsyncMock()
    mock_client.is_connected = True
    mock_client.rcpt.return_value = MagicMock(code=250, message="OK")

    with patch("aiosmtplib.SMTP", return_value=mock_client):
        code, msg = await _execute_single_rcpt_probe(
            mx_host="mx.test.com",
            target_email="test@test.com",
            timeout=5.0,
        )

        # Confirm expected handshake sequence
        mock_client.connect.assert_awaited_once()
        mock_client.ehlo.assert_awaited_once()
        mock_client.mail.assert_awaited_once()
        mock_client.rcpt.assert_awaited_once_with("test@test.com")
        mock_client.quit.assert_awaited_once()

        # Crucial check: DATA and message sending must NEVER be called!
        assert not mock_client.data.called, "CRITICAL ERROR: data() method was called!"
        assert not mock_client.send_message.called, "CRITICAL ERROR: send_message() was called!"
