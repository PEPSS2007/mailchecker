"""
Stage D & E: SMTP Mailbox Verification, Catch-All Detection, and Host Capability Probing.
CRITICAL SAFETY RULE: Never issue DATA command, never send message content, never send real emails.
"""

import asyncio
import logging
import socket
import uuid
from dataclasses import dataclass

import aiosmtplib
from cachetools import TTLCache

from app.config import settings
from app.syntax import mask_email_for_logging

logger = logging.getLogger(__name__)

# TTL Cache for catch-all status per domain: domain -> bool
catch_all_cache: TTLCache = TTLCache(
    maxsize=settings.CATCH_ALL_CACHE_MAXSIZE,
    ttl=settings.CATCH_ALL_CACHE_TTL_SECONDS,
)
_catch_all_lock = asyncio.Lock()

# Cached SMTP capability (outbound port 25 availability)
_capability_cache: dict[str, tuple[bool, float]] = {}  # "smtp_available" -> (bool, timestamp)
_capability_lock = asyncio.Lock()

# Per-domain connection semaphores to prevent flooding destination mail exchangers
_domain_semaphores: dict[str, asyncio.Semaphore] = {}
_semaphores_meta_lock = asyncio.Lock()


@dataclass
class SMTPProbeResult:
    email: str
    domain: str
    code: int | None
    message: str | None
    reason_code: str
    is_catch_all: bool = False
    details: dict | None = None


async def get_domain_semaphore(domain: str) -> asyncio.Semaphore:
    """Returns or creates a per-domain concurrency limiter."""
    clean_domain = domain.strip().lower().rstrip(".")
    async with _semaphores_meta_lock:
        if clean_domain not in _domain_semaphores:
            _domain_semaphores[clean_domain] = asyncio.Semaphore(settings.DOMAIN_CONCURRENCY_LIMIT)
        return _domain_semaphores[clean_domain]


async def check_outbound_smtp_capability(force_refresh: bool = False) -> bool:
    """
    Tests whether outbound port 25 is permitted by the current host/network environment.
    Caches results for SMTP_CAPABILITY_CACHE_TTL_SECONDS to avoid repeated latency.
    """
    loop = asyncio.get_running_loop()
    now = loop.time()

    async with _capability_lock:
        if not force_refresh and "smtp_available" in _capability_cache:
            status, timestamp = _capability_cache["smtp_available"]
            if now - timestamp < settings.SMTP_CAPABILITY_CACHE_TTL_SECONDS:
                return status

    # Perform a quick TCP socket connect probe to a known mail exchange host
    available = False
    for probe_host in settings.SMTP_PROBE_HOSTS:
        try:
            # We only test if a TCP handshake to port 25 is allowed
            logger.debug("Testing outbound port 25 capability against %s...", probe_host)
            conn_task = asyncio.open_connection(probe_host, settings.SMTP_PORT)
            reader, writer = await asyncio.wait_for(conn_task, timeout=2.5)
            # Successfully connected
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            available = True
            logger.info("Outbound SMTP port 25 is AVAILABLE (connected to %s)", probe_host)
            break
        except (asyncio.TimeoutError, OSError, socket.error) as exc:
            logger.debug("Port 25 test to %s failed: %s", probe_host, exc)
            continue
        except Exception as exc:
            logger.debug("Unexpected error probing %s: %s", probe_host, exc)
            continue

    if not available:
        logger.warning(
            "Outbound SMTP port 25 is BLOCKED or UNREACHABLE on this host. Running in DNS-only degraded mode."
        )

    async with _capability_lock:
        _capability_cache["smtp_available"] = (available, now)

    return available


def _ensure_safety_constraints(command_name: str) -> None:
    """
    Architectural guarantee: absolutely forbids DATA command or email transmission.
    """
    if command_name.upper() == "DATA":
        raise RuntimeError("CRITICAL VIOLATION: DATA command is strictly forbidden by policy!")


async def _execute_single_rcpt_probe(
    mx_host: str,
    target_email: str,
    timeout: float,
) -> tuple[int, str]:
    """
    Performs a safe, restricted SMTP conversation:
    CONNECT -> EHLO -> MAIL FROM -> RCPT TO -> QUIT.
    Never issues DATA command or transmits email body.
    """
    client = aiosmtplib.SMTP(
        hostname=mx_host,
        port=settings.SMTP_PORT,
        timeout=timeout,
        start_tls=False,
    )

    try:
        await client.connect()

        # Perform EHLO, fallback to HELO
        try:
            _ensure_safety_constraints("EHLO")
            await client.ehlo(hostname=settings.SMTP_HELO_DOMAIN)
        except Exception:
            _ensure_safety_constraints("HELO")
            await client.helo(hostname=settings.SMTP_HELO_DOMAIN)

        # Issue MAIL FROM
        _ensure_safety_constraints("MAIL FROM")
        await client.mail(settings.SMTP_MAIL_FROM)

        # Issue RCPT TO
        _ensure_safety_constraints("RCPT TO")
        response = await client.rcpt(target_email)
        code = response.code
        message = response.message

        return code, message

    except aiosmtplib.errors.SMTPRecipientRefused as exc:
        return exc.code, exc.message
    except aiosmtplib.errors.SMTPResponseException as exc:
        return exc.code, exc.message
    finally:
        # Guarantee session closure and connection termination
        try:
            if client.is_connected:
                _ensure_safety_constraints("QUIT")
                await client.quit()
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass


async def probe_email_smtp(
    email: str,
    domain: str,
    mx_hosts: list[tuple[int, str]],
) -> SMTPProbeResult:
    """
    Performs Stage D (SMTP verification) and Stage E (Catch-all detection).
    Enforces per-domain concurrency, safe timeouts, and retries.
    """
    masked = mask_email_for_logging(email)
    logger.info("Starting SMTP verification for %s", masked)

    if not mx_hosts:
        return SMTPProbeResult(
            email=email,
            domain=domain,
            code=None,
            message="No MX hosts available",
            reason_code="no_mail_server",
        )

    # Use the highest-priority MX host (lowest preference value)
    best_mx = mx_hosts[0][1]

    # Check if outbound SMTP is available on this environment
    smtp_enabled = await check_outbound_smtp_capability()
    if not smtp_enabled:
        return SMTPProbeResult(
            email=email,
            domain=domain,
            code=None,
            message="Outbound port 25 is blocked on this host",
            reason_code="smtp_unavailable",
            details={"active_mode": "dns_only"},
        )

    # Enforce per-domain concurrency
    semaphore = await get_domain_semaphore(domain)
    async with semaphore:
        attempt = 0
        max_attempts = 1 + settings.SMTP_MAX_RETRIES
        last_code: int | None = None
        last_message: str | None = None

        while attempt < max_attempts:
            attempt += 1
            try:
                code, msg = await _execute_single_rcpt_probe(
                    mx_host=best_mx,
                    target_email=email,
                    timeout=settings.SMTP_COMMAND_TIMEOUT_SECONDS,
                )
                last_code = code
                last_message = msg

                # 250 / 251: Recipient accepted
                if code in (250, 251):
                    # Check for catch-all domain
                    is_catch_all = await probe_catch_all(best_mx, domain)
                    if is_catch_all:
                        return SMTPProbeResult(
                            email=email,
                            domain=domain,
                            code=code,
                            message=msg,
                            reason_code="catch_all",
                            is_catch_all=True,
                            details={"mx_host": best_mx, "smtp_response": msg},
                        )
                    return SMTPProbeResult(
                        email=email,
                        domain=domain,
                        code=code,
                        message=msg,
                        reason_code="mailbox_accepted",
                        is_catch_all=False,
                        details={"mx_host": best_mx, "smtp_response": msg},
                    )

                # Permanent failure: 550, 551, 552, 553, 554
                if 500 <= code <= 559:
                    return SMTPProbeResult(
                        email=email,
                        domain=domain,
                        code=code,
                        message=msg,
                        reason_code="mailbox_rejected",
                        details={"mx_host": best_mx, "smtp_response": msg},
                    )

                # Temporary failure: 421, 450, 451, 452
                if 400 <= code <= 499:
                    if attempt < max_attempts:
                        await asyncio.sleep(1.0)
                        continue
                    return SMTPProbeResult(
                        email=email,
                        domain=domain,
                        code=code,
                        message=msg,
                        reason_code="temporary_failure",
                        details={"mx_host": best_mx, "smtp_response": msg},
                    )

            except (aiosmtplib.errors.SMTPConnectTimeoutError, asyncio.TimeoutError):
                if attempt < max_attempts:
                    await asyncio.sleep(1.0)
                    continue
                return SMTPProbeResult(
                    email=email,
                    domain=domain,
                    code=None,
                    message="Connection to MX host timed out",
                    reason_code="server_unresponsive",
                    details={"mx_host": best_mx},
                )
            except (aiosmtplib.errors.SMTPConnectError, ConnectionError, OSError) as exc:
                if attempt < max_attempts:
                    await asyncio.sleep(1.0)
                    continue
                return SMTPProbeResult(
                    email=email,
                    domain=domain,
                    code=None,
                    message=f"Connection failure: {exc}",
                    reason_code="server_unresponsive",
                    details={"mx_host": best_mx},
                )
            except Exception as exc:
                logger.error("Unexpected SMTP error for %s: %s", masked, exc)
                return SMTPProbeResult(
                    email=email,
                    domain=domain,
                    code=None,
                    message=f"SMTP verification error: {exc}",
                    reason_code="server_unresponsive",
                    details={"mx_host": best_mx},
                )

        return SMTPProbeResult(
            email=email,
            domain=domain,
            code=last_code,
            message=last_message or "Max retries reached with temporary error",
            reason_code="temporary_failure",
            details={"mx_host": best_mx},
        )


async def probe_catch_all(mx_host: str, domain: str) -> bool:
    """
    Stage E: Detects whether a domain accepts mail for any synthetic recipient.
    Uses cached result if available to save DNS and socket operations.
    """
    clean_domain = domain.strip().lower().rstrip(".")
    async with _catch_all_lock:
        if clean_domain in catch_all_cache:
            return catch_all_cache[clean_domain]

    # Generate an unambiguously nonexistent synthetic local part
    synthetic_local = f"antigravity-probe-{uuid.uuid4().hex[:12]}"
    synthetic_recipient = f"{synthetic_local}@{clean_domain}"

    try:
        code, msg = await _execute_single_rcpt_probe(
            mx_host=mx_host,
            target_email=synthetic_recipient,
            timeout=settings.SMTP_COMMAND_TIMEOUT_SECONDS,
        )
        # If server accepts the bogus synthetic address, it is a catch-all
        is_catch_all = code in (250, 251)
    except Exception as exc:
        logger.debug("Catch-all probe exception on %s: %s", clean_domain, exc)
        is_catch_all = False

    async with _catch_all_lock:
        catch_all_cache[clean_domain] = is_catch_all

    return is_catch_all
