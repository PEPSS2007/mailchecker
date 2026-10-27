"""
Tests for Stage B: DNS records, RFC 7505 Null MX, A/AAAA fallback, SSRF prevention, and caching.
"""

from unittest.mock import MagicMock, patch

import dns.exception
import dns.resolver
import pytest

from app.dns_checks import (
    DNSCheckResult,
    _sync_resolve_dns,
    check_domain_dns,
    dns_cache,
    is_ip_prohibited,
)


def test_is_ip_prohibited():
    # Loopback
    assert is_ip_prohibited("127.0.0.1") is True
    assert is_ip_prohibited("::1") is True

    # Private RFC 1918
    assert is_ip_prohibited("10.0.0.1") is True
    assert is_ip_prohibited("192.168.1.100") is True
    assert is_ip_prohibited("172.16.5.2") is True

    # Cloud metadata link-local
    assert is_ip_prohibited("169.254.169.254") is True

    # Valid Public IPs
    assert is_ip_prohibited("8.8.8.8") is False
    assert is_ip_prohibited("142.250.190.46") is False
    assert is_ip_prohibited("1.1.1.1") is False

    # Invalid input
    assert is_ip_prohibited("not-an-ip") is True


def test_rfc7505_null_mx():
    """Verify that RFC 7505 Null MX (preference 0, exchange '.') explicitly fails."""
    mock_rdata = MagicMock()
    mock_rdata.preference = 0
    mock_rdata.exchange = "."

    with patch("dns.resolver.Resolver.resolve") as mock_resolve:
        mock_resolve.return_value = [mock_rdata]
        result = _sync_resolve_dns("nomail.example.com")

        assert result.has_valid_mail_server is False
        assert result.is_null_mx is True
        assert result.reason_code == "no_mail_server"
        assert "RFC 7505 Null MX" in result.error_message


def test_standard_mx_resolution():
    """Verify valid MX resolution and preference sorting."""
    mx1 = MagicMock()
    mx1.preference = 20
    mx1.exchange = "alt.mx.example.com."

    mx2 = MagicMock()
    mx2.preference = 10
    mx2.exchange = "main.mx.example.com."

    ip_record = MagicMock()
    ip_record.address = "93.184.216.34"  # Public IP

    def fake_resolve(qname, rdtype, **kwargs):
        if rdtype == "MX":
            return [mx1, mx2]
        if rdtype == "A":
            return [ip_record]
        raise dns.resolver.NoAnswer()

    with patch("dns.resolver.Resolver.resolve", side_effect=fake_resolve):
        result = _sync_resolve_dns("example.com")

        assert result.has_valid_mail_server is True
        assert len(result.mx_hosts) == 2
        # Priority 10 should be first
        assert result.mx_hosts[0] == (10, "main.mx.example.com")
        assert result.mx_hosts[1] == (20, "alt.mx.example.com")


def test_rfc5321_fallback_a_record():
    """Verify fallback to A record when no MX records exist."""
    ip_record = MagicMock()
    ip_record.address = "93.184.216.34"

    def fake_resolve(qname, rdtype, **kwargs):
        if rdtype == "MX":
            raise dns.resolver.NoAnswer()
        if rdtype == "A":
            return [ip_record]
        raise dns.resolver.NoAnswer()

    with patch("dns.resolver.Resolver.resolve", side_effect=fake_resolve):
        result = _sync_resolve_dns("nomx-fallback.com")

        assert result.has_valid_mail_server is True
        assert result.fallback_a_record is True
        assert result.mx_hosts == [(0, "nomx-fallback.com")]


def test_nxdomain_handling():
    """Verify NXDOMAIN error handling."""
    with patch("dns.resolver.Resolver.resolve", side_effect=dns.resolver.NXDOMAIN()):
        result = _sync_resolve_dns("nonexistent-domain-404.org")

        assert result.has_valid_mail_server is False
        assert result.reason_code == "no_mail_server"
        assert "NXDOMAIN" in result.error_message


def test_dns_timeout_handling():
    """Verify timeout handling returns server_unresponsive."""
    with patch("dns.resolver.Resolver.resolve", side_effect=dns.exception.Timeout()):
        result = _sync_resolve_dns("laggy-dns.org")

        assert result.has_valid_mail_server is False
        assert result.reason_code == "server_unresponsive"


@pytest.mark.asyncio
async def test_dns_cache_operation():
    """Verify TTL caching returns cached result on second invocation."""
    dns_cache.clear()
    cached_res = DNSCheckResult(
        domain="cached-test.com",
        has_valid_mail_server=True,
        mx_hosts=[(10, "mx.cached-test.com")],
    )

    with patch("app.dns_checks._sync_resolve_dns", return_value=cached_res) as mock_sync:
        res1 = await check_domain_dns("cached-test.com")
        res2 = await check_domain_dns("cached-test.com")

        assert res1.domain == "cached-test.com"
        assert res2.domain == "cached-test.com"
        # Should only call sync resolver once due to caching
        assert mock_sync.call_count == 1
