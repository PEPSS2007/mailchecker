"""
Tests for Stage C & F: Heuristic flags, verdict assignment, and explanation clarity.
"""

from app.classify import classifier


def test_verdict_assignments():
    # Deliverable
    r1 = classifier.classify("user@example.com", "mailbox_accepted")
    assert r1.verdict == "deliverable"
    assert r1.reason == "mailbox_accepted"

    # Bounce
    r2 = classifier.classify("user@example.com", "mailbox_rejected")
    assert r2.verdict == "bounce"
    assert r2.reason == "mailbox_rejected"

    r3 = classifier.classify("user@example.com", "invalid_syntax")
    assert r3.verdict == "bounce"

    r4 = classifier.classify("user@example.com", "no_mail_server")
    assert r4.verdict == "bounce"

    # Unknown
    r5 = classifier.classify("user@example.com", "catch_all")
    assert r5.verdict == "unknown"

    r6 = classifier.classify("user@example.com", "temporary_failure")
    assert r6.verdict == "unknown"

    r7 = classifier.classify("user@example.com", "server_unresponsive")
    assert r7.verdict == "unknown"

    r8 = classifier.classify("user@example.com", "smtp_unavailable")
    assert r8.verdict == "unknown"

    r9 = classifier.classify("user@example.com", "provider_hides_status")
    assert r9.verdict == "unknown"


def test_heuristic_flags():
    # Disposable domain
    flags_disp = classifier.check_heuristics("random_user", "10minutemail.com")
    assert "disposable" in flags_disp

    # Role accounts
    flags_admin = classifier.check_heuristics("admin", "company.com")
    assert "role_account" in flags_admin

    flags_support = classifier.check_heuristics("support+billing", "company.com")
    assert "role_account" in flags_support

    flags_noreply = classifier.check_heuristics("no-reply", "service.com")
    assert "role_account" in flags_noreply

    # Free email provider
    flags_free = classifier.check_heuristics("john.doe", "gmail.com")
    assert "free_provider" in flags_free
    assert "role_account" not in flags_free
    assert "disposable" not in flags_free


def test_explanations_populated():
    r = classifier.classify("alice@example.com", "mailbox_accepted")
    assert len(r.explanation) > 10
    assert "recipient mailbox exists" in r.explanation
