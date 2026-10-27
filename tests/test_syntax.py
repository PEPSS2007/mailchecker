"""
Tests for Stage A: Syntax validation, multi-delimiter parsing, deduplication, and safe log masking.
"""

from app.syntax import (
    mask_email_for_logging,
    normalize_email_syntax,
    parse_raw_email_input,
)


def test_parse_multi_delimiter_input():
    raw = """
    user1@example.com
    user2@example.com, user3@example.com; user4@example.com
    <user5@example.com>\t"user6@example.com"
    """
    tokens = parse_raw_email_input(raw)
    assert len(tokens) == 6
    assert tokens[0] == "user1@example.com"
    assert tokens[1] == "user2@example.com"
    assert tokens[2] == "user3@example.com"
    assert tokens[3] == "user4@example.com"
    assert tokens[4] == "user5@example.com"
    assert tokens[5] == "user6@example.com"


def test_parse_input_deduplication():
    raw = "alice@example.com, ALICE@EXAMPLE.COM, Bob@example.com, alice@example.com"
    tokens = parse_raw_email_input(raw)
    assert len(tokens) == 2
    assert tokens[0] == "alice@example.com"
    assert tokens[1] == "Bob@example.com"


def test_valid_syntax_normalization():
    parsed = normalize_email_syntax("  John.Doe+Newsletter@EXAMPLE.COM  ")
    assert parsed.is_valid_syntax is True
    assert parsed.domain == "example.com"
    assert parsed.normalized == "John.Doe+Newsletter@example.com"
    assert parsed.syntax_error is None


def test_invalid_syntax_missing_at():
    parsed = normalize_email_syntax("plainaddress.com")
    assert parsed.is_valid_syntax is False
    assert parsed.syntax_error is not None


def test_invalid_syntax_consecutive_dots():
    parsed = normalize_email_syntax("user..name@example.com")
    assert parsed.is_valid_syntax is False
    assert parsed.syntax_error is not None


def test_safe_log_masking():
    # Long local part
    masked1 = mask_email_for_logging("alexander@domain.com")
    assert masked1 == "a***r@domain.com"
    assert "alexander" not in masked1

    # Short local part
    masked2 = mask_email_for_logging("al@domain.com")
    assert masked2 == "a***@domain.com"

    # Edge cases
    assert mask_email_for_logging("") == "***"
    assert mask_email_for_logging("invalid") == "***"
