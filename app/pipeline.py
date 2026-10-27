"""
Verification Pipeline Orchestrator.
Coordinates Stage A (Syntax) -> Stage B (DNS) -> Stage C (Heuristics) -> Stage D/E (SMTP & Catch-All) -> Stage F (Classification).
"""

import asyncio
import logging

from app.classify import (
    STATUS_HIDING_DOMAINS,
    VerificationResult,
    classifier,
)
from app.config import settings
from app.dns_checks import check_domain_dns
from app.smtp_probe import probe_email_smtp
from app.syntax import (
    mask_email_for_logging,
    normalize_email_syntax,
    parse_raw_email_input,
)

logger = logging.getLogger(__name__)

# Global concurrency limiter for full pipeline runs
_pipeline_semaphore = asyncio.Semaphore(settings.TOTAL_CONCURRENCY_LIMIT)


async def verify_single_email(email_token: str) -> VerificationResult:
    """
    Executes the modular verification pipeline for a single email token.
    """
    async with _pipeline_semaphore:
        # Stage A: Syntax Parsing & Normalization
        parsed = normalize_email_syntax(email_token)
        if not parsed.is_valid_syntax:
            logger.info("Syntax check failed for %s", mask_email_for_logging(parsed.normalized))
            return classifier.classify(
                email=parsed.normalized or email_token,
                reason_code="invalid_syntax",
                flags=[],
                details={"syntax_error": parsed.syntax_error},
            )

        email = parsed.normalized
        domain = parsed.domain
        local_part = parsed.local_part
        masked_email = mask_email_for_logging(email)

        # Stage C: Calculate Heuristic Flags early
        flags = classifier.check_heuristics(local_part, domain)

        # Stage B: DNS & Mail Server Verification
        dns_res = await check_domain_dns(domain)
        if dns_res.fallback_a_record:
            flags.append("fallback_mx_a_record")

        if not dns_res.has_valid_mail_server:
            logger.info("DNS validation failed for domain %s (email %s)", domain, masked_email)
            reason = dns_res.reason_code or "no_mail_server"
            return classifier.classify(
                email=email,
                reason_code=reason,
                custom_explanation=dns_res.error_message,
                flags=flags,
                details={
                    "is_null_mx": dns_res.is_null_mx,
                    "dns_error": dns_res.error_message,
                },
            )

        # Check for known providers that intentionally obscure mailbox status
        if domain in STATUS_HIDING_DOMAINS:
            logger.info(
                "Domain %s belongs to a known provider that hides mailbox status (%s)",
                domain,
                masked_email,
            )
            return classifier.classify(
                email=email,
                reason_code="provider_hides_status",
                flags=flags,
                details={"mx_hosts": [h[1] for h in dns_res.mx_hosts]},
            )

        # Stage D & E: SMTP Verification & Catch-All Detection
        smtp_res = await probe_email_smtp(email, domain, dns_res.mx_hosts)
        if smtp_res.is_catch_all and "catch_all" not in flags:
            flags.append("catch_all")

        logger.info(
            "Completed verification for %s: reason=%s",
            masked_email,
            smtp_res.reason_code,
        )

        return classifier.classify(
            email=email,
            reason_code=smtp_res.reason_code,
            flags=flags,
            details=smtp_res.details or {},
        )


async def run_verification_pipeline(
    raw_input: str | list[str],
) -> list[VerificationResult]:
    """
    Parses and executes verification across all supplied email addresses.
    Enforces maximum batch size limit (100 addresses) and concurrency.
    """
    tokens = parse_raw_email_input(raw_input)

    if not tokens:
        return []

    if len(tokens) > settings.MAX_EMAILS_PER_REQUEST:
        raise ValueError(
            f"Too many email addresses. Maximum allowed is {settings.MAX_EMAILS_PER_REQUEST}, received {len(tokens)}."
        )

    tasks = [verify_single_email(token) for token in tokens]
    results = await asyncio.gather(*tasks)
    return results
