"""
Stage B: DNS and Domain Verification with RFC 7505 Null MX, A/AAAA fallback, SSRF prevention, and TTL caching.
"""

import asyncio
import ipaddress
import logging
from dataclasses import dataclass, field

import dns.exception
import dns.resolver
from cachetools import TTLCache

from app.config import settings

logger = logging.getLogger(__name__)

# In-memory TTL cache for DNS results: domain -> DNSCheckResult
dns_cache: TTLCache = TTLCache(
    maxsize=settings.DNS_CACHE_MAXSIZE,
    ttl=settings.DNS_CACHE_TTL_SECONDS,
)
_dns_cache_lock = asyncio.Lock()


@dataclass
class DNSCheckResult:
    domain: str
    has_valid_mail_server: bool
    mx_hosts: list[tuple[int, str]] = field(default_factory=list)  # (priority, hostname)
    fallback_a_record: bool = False
    is_null_mx: bool = False
    reason_code: str | None = None
    error_message: str | None = None
    resolved_ips: list[str] = field(default_factory=list)


def is_ip_prohibited(ip_str: str) -> bool:
    """
    Validates if an IP address is private, loopback, link-local, multicast, or reserved.
    Prevents Server-Side Request Forgery (SSRF) and intranet scanning.
    """
    try:
        ip = ipaddress.ip_address(ip_str.strip())
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        return True


def _sync_resolve_dns(domain: str) -> DNSCheckResult:
    """
    Synchronous worker executed in thread pool for dnspython resolution.
    Follows RFC 5321 (MX lookup and A/AAAA fallback) and RFC 7505 (Null MX).
    """
    clean_domain = domain.strip().lower().rstrip(".")
    if not clean_domain:
        return DNSCheckResult(
            domain=domain,
            has_valid_mail_server=False,
            reason_code="no_mail_server",
            error_message="Empty domain name provided.",
        )

    resolver = dns.resolver.Resolver()
    resolver.timeout = settings.DNS_TIMEOUT_SECONDS
    resolver.lifetime = settings.DNS_TIMEOUT_SECONDS

    # 1. Check MX records
    try:
        mx_answers = resolver.resolve(clean_domain, "MX")
        mx_records: list[tuple[int, str]] = []

        for rdata in mx_answers:
            exchange = str(rdata.exchange).rstrip(".")
            preference = int(rdata.preference)
            mx_records.append((preference, exchange))

        # Check for RFC 7505 Null MX: exactly "0 ." or exchange is empty/dot
        for pref, host in mx_records:
            if pref == 0 and (host == "" or host == "."):
                return DNSCheckResult(
                    domain=clean_domain,
                    has_valid_mail_server=False,
                    is_null_mx=True,
                    reason_code="no_mail_server",
                    error_message="Domain explicitly publishes RFC 7505 Null MX and rejects all incoming email.",
                )

        # Sort MX records by priority (ascending preference number)
        mx_records.sort(key=lambda x: x[0])

        if mx_records:
            # Resolve and filter valid MX host IP addresses (SSRF protection)
            valid_mx_hosts: list[tuple[int, str]] = []
            all_resolved_ips: list[str] = []

            for pref, host in mx_records:
                if not host or host == ".":
                    continue
                try:
                    host_ips: list[str] = []
                    # Try A records
                    try:
                        a_answers = resolver.resolve(host, "A")
                        for a_data in a_answers:
                            host_ips.append(str(a_data.address))
                    except (
                        dns.resolver.NoAnswer,
                        dns.resolver.NXDOMAIN,
                        dns.exception.DNSException,
                    ):
                        pass

                    # Try AAAA records
                    try:
                        aaaa_answers = resolver.resolve(host, "AAAA")
                        for aaaa_data in aaaa_answers:
                            host_ips.append(str(aaaa_data.address))
                    except (
                        dns.resolver.NoAnswer,
                        dns.resolver.NXDOMAIN,
                        dns.exception.DNSException,
                    ):
                        pass

                    # Check for prohibited IP ranges
                    safe_ips = [ip for ip in host_ips if not is_ip_prohibited(ip)]
                    if safe_ips:
                        valid_mx_hosts.append((pref, host))
                        all_resolved_ips.extend(safe_ips)
                    elif host_ips:
                        # Had IPs but all were prohibited/private
                        logger.warning(
                            "Prohibited IP range detected for MX host %s: %s",
                            host,
                            host_ips,
                        )
                except Exception as e:
                    logger.debug("Error resolving IPs for MX host %s: %s", host, e)

            if valid_mx_hosts:
                return DNSCheckResult(
                    domain=clean_domain,
                    has_valid_mail_server=True,
                    mx_hosts=valid_mx_hosts,
                    resolved_ips=all_resolved_ips,
                )
            else:
                return DNSCheckResult(
                    domain=clean_domain,
                    has_valid_mail_server=False,
                    reason_code="no_mail_server",
                    error_message="MX records exist but could not be safely resolved to public IP addresses.",
                )

    except (dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        # No MX record found -> RFC 5321 mail routing fallback to A/AAAA
        pass
    except dns.resolver.NXDOMAIN:
        return DNSCheckResult(
            domain=clean_domain,
            has_valid_mail_server=False,
            reason_code="no_mail_server",
            error_message="Domain does not exist (NXDOMAIN).",
        )
    except dns.exception.Timeout:
        return DNSCheckResult(
            domain=clean_domain,
            has_valid_mail_server=False,
            reason_code="server_unresponsive",
            error_message="DNS resolution timed out for MX records.",
        )
    except dns.exception.DNSException as exc:
        return DNSCheckResult(
            domain=clean_domain,
            has_valid_mail_server=False,
            reason_code="no_mail_server",
            error_message=f"DNS error: {exc}",
        )

    # 2. RFC 5321 Fallback: check domain's A or AAAA records
    fallback_ips: list[str] = []
    try:
        try:
            a_answers = resolver.resolve(clean_domain, "A")
            for a_data in a_answers:
                fallback_ips.append(str(a_data.address))
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.exception.DNSException):
            pass

        try:
            aaaa_answers = resolver.resolve(clean_domain, "AAAA")
            for aaaa_data in aaaa_answers:
                fallback_ips.append(str(aaaa_data.address))
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.exception.DNSException):
            pass

        safe_fallback_ips = [ip for ip in fallback_ips if not is_ip_prohibited(ip)]
        if safe_fallback_ips:
            return DNSCheckResult(
                domain=clean_domain,
                has_valid_mail_server=True,
                mx_hosts=[(0, clean_domain)],
                fallback_a_record=True,
                resolved_ips=safe_fallback_ips,
            )
    except Exception as exc:
        logger.debug("Error during A/AAAA fallback resolution for %s: %s", clean_domain, exc)

    return DNSCheckResult(
        domain=clean_domain,
        has_valid_mail_server=False,
        reason_code="no_mail_server",
        error_message="Domain has no MX records and no fallback A/AAAA address records.",
    )


async def check_domain_dns(domain: str) -> DNSCheckResult:
    """
    Asynchronously checks DNS records for a domain with TTL in-memory caching.
    """
    clean_domain = domain.strip().lower().rstrip(".")
    async with _dns_cache_lock:
        if clean_domain in dns_cache:
            return dns_cache[clean_domain]

    # Run blocking DNS queries in threadpool
    result = await asyncio.to_thread(_sync_resolve_dns, clean_domain)

    async with _dns_cache_lock:
        dns_cache[clean_domain] = result

    return result
