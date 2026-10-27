"""
Stage A: Email parsing, normalization, and syntax validation.
"""

import re
from typing import NamedTuple

from email_validator import EmailNotValidError, validate_email


class ParsedEmail(NamedTuple):
    raw: str
    normalized: str
    local_part: str
    domain: str
    is_valid_syntax: bool
    syntax_error: str | None = None


def parse_raw_email_input(raw_input: str | list[str]) -> list[str]:
    """
    Splits multi-line, comma, semicolon, or whitespace separated email strings.
    Removes surrounding angle brackets or quotes.
    Returns deduplicated list in order of appearance.
    """
    if isinstance(raw_input, list):
        items = raw_input
    elif isinstance(raw_input, str):
        # Split on commas, semicolons, newlines, and carriage returns
        # Also handle spaces
        split_items = re.split(r"[\r\n,;\t\s]+", raw_input)
        items = split_items
    else:
        items = []

    cleaned_tokens: list[str] = []
    seen: set[str] = set()

    for item in items:
        if not item:
            continue
        token = item.strip().strip("<>\"'()")
        if not token:
            continue
        # Deduplication case-insensitively on domain, but preserve raw token first
        lower_token = token.lower()
        if lower_token not in seen:
            seen.add(lower_token)
            cleaned_tokens.append(token)

    return cleaned_tokens


def normalize_email_syntax(email_token: str) -> ParsedEmail:
    """
    Validates email syntax using email-validator without deliverability DNS checks.
    Normalizes domain to lowercase while preserving valid local-part rules.
    """
    cleaned = email_token.strip().strip("<>\"'()")
    if not cleaned or "@" not in cleaned:
        return ParsedEmail(
            raw=email_token,
            normalized=cleaned,
            local_part="",
            domain="",
            is_valid_syntax=False,
            syntax_error="Email address must contain an '@' symbol and domain.",
        )

    try:
        # check_deliverability=False ensures Stage A does not perform network DNS lookups
        validation = validate_email(cleaned, check_deliverability=False)
        normalized_email = validation.normalized
        local_part = validation.local_part
        domain = validation.domain.lower()

        return ParsedEmail(
            raw=email_token,
            normalized=normalized_email,
            local_part=local_part,
            domain=domain,
            is_valid_syntax=True,
            syntax_error=None,
        )
    except EmailNotValidError as exc:
        # Extract domain part if possible for reporting
        parts = cleaned.rsplit("@", 1)
        local_part = parts[0] if len(parts) > 0 else ""
        domain = parts[1].lower() if len(parts) > 1 else ""

        return ParsedEmail(
            raw=email_token,
            normalized=cleaned,
            local_part=local_part,
            domain=domain,
            is_valid_syntax=False,
            syntax_error=str(exc),
        )


def mask_email_for_logging(email: str) -> str:
    """
    Masks the local part of an email address for privacy-safe logging.
    Example: 'johndoe@example.com' -> 'j***e@example.com'
    """
    if not email or "@" not in email:
        return "***"
    local_part, domain = email.rsplit("@", 1)
    if len(local_part) <= 2:
        masked_local = f"{local_part[:1]}***"
    else:
        masked_local = f"{local_part[0]}***{local_part[-1]}"
    return f"{masked_local}@{domain}"
