"""
Stage C & F: Heuristics and Result Classification.
Assigns standardized verdicts (deliverable, bounce, unknown), reason codes, human-friendly explanations, and warning flags.
"""

from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings

# Common role-based account prefixes
ROLE_ACCOUNT_PREFIXES: set[str] = {
    "admin",
    "administrator",
    "postmaster",
    "hostmaster",
    "abuse",
    "security",
    "webmaster",
    "root",
    "info",
    "support",
    "help",
    "contact",
    "sales",
    "billing",
    "invoice",
    "accounts",
    "press",
    "media",
    "marketing",
    "legal",
    "compliance",
    "jobs",
    "careers",
    "hr",
    "recruit",
    "office",
    "team",
    "staff",
    "service",
    "noreply",
    "no-reply",
    "mailer-daemon",
    "daemon",
    "system",
    "notification",
    "notifications",
}

# Major free/consumer email domains
FREE_EMAIL_DOMAINS: set[str] = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.uk",
    "yahoo.fr",
    "yahoo.de",
    "yahoo.es",
    "yahoo.it",
    "ymail.com",
    "hotmail.com",
    "hotmail.co.uk",
    "hotmail.fr",
    "outlook.com",
    "live.com",
    "msn.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "aol.com",
    "aim.com",
    "proton.me",
    "protonmail.com",
    "zoho.com",
    "gmx.com",
    "gmx.net",
    "gmx.de",
    "mail.com",
    "yandex.com",
    "yandex.ru",
}

# Known providers that hide mailbox status, reject automated RCPT checks, or defer validation
STATUS_HIDING_DOMAINS: set[str] = {
    "yahoo.com",
    "yahoo.co.uk",
    "yahoo.fr",
    "yahoo.de",
    "ymail.com",
    "aol.com",
    "aim.com",
}

# Standardized explanations dictionary
EXPLANATIONS: dict[str, str] = {
    "invalid_syntax": "The email address has invalid syntax or does not conform to RFC standards.",
    "no_mail_server": "The domain does not have active MX records or valid mail servers.",
    "mailbox_accepted": "The destination mail server confirmed that the recipient mailbox exists and is ready to receive email.",
    "mailbox_rejected": "The destination mail server permanently rejected the recipient mailbox (user does not exist or mailbox was disabled).",
    "catch_all": "The destination mail server accepts all incoming addresses (catch-all), making individual mailbox deliverability inconclusive.",
    "temporary_failure": "The mail server returned a temporary error (such as rate limiting, greylisting, or mailbox full). Please re-check later.",
    "server_unresponsive": "The mail server did not respond or the connection timed out.",
    "provider_hides_status": "The mail provider accepts all incoming addresses at the border or defers mailbox checks, obscuring true mailbox deliverability.",
    "smtp_unavailable": "Outbound SMTP (port 25) is blocked on this hosting platform; domain and syntax are valid, but mailbox status cannot be verified directly.",
    "prohibited_ip_range": "The mail server resolved to an internal, private, or prohibited IP address range.",
}


@dataclass
class VerificationResult:
    email: str
    verdict: str  # "deliverable" | "bounce" | "unknown"
    reason: str
    explanation: str
    flags: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "verdict": self.verdict,
            "reason": self.reason,
            "explanation": self.explanation,
            "flags": self.flags,
            "details": self.details,
        }


class HeuristicClassifier:
    def __init__(self, disposable_domains_file: Path | None = None) -> None:
        self.disposable_domains: set[str] = set()
        file_path = disposable_domains_file or settings.DISPOSABLE_DOMAINS_FILE
        self._load_disposable_domains(file_path)

    def _load_disposable_domains(self, file_path: Path) -> None:
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip().lower()
                        if line and not line.startswith("#"):
                            self.disposable_domains.add(line)
            except Exception:
                pass

    def check_heuristics(self, local_part: str, domain: str) -> list[str]:
        """
        Calculates informative flags for the given email without changing verdict automatically.
        """
        flags: list[str] = []
        clean_local = local_part.strip().lower()
        clean_domain = domain.strip().lower().rstrip(".")

        # Check disposable domain
        if clean_domain in self.disposable_domains:
            flags.append("disposable")

        # Check role account
        # Normalize local part (e.g. support+123 -> support)
        base_local = clean_local.split("+")[0].split(".")[0]
        if clean_local in ROLE_ACCOUNT_PREFIXES or base_local in ROLE_ACCOUNT_PREFIXES:
            flags.append("role_account")

        # Check free email provider
        if clean_domain in FREE_EMAIL_DOMAINS:
            flags.append("free_provider")

        return flags

    def classify(
        self,
        email: str,
        reason_code: str,
        custom_explanation: str | None = None,
        flags: list[str] | None = None,
        details: dict | None = None,
    ) -> VerificationResult:
        """
        Applies canonical verdict rules based on reason code.
        """
        # Exact allowed verdicts: "deliverable", "bounce", "unknown"
        if reason_code in ("mailbox_accepted",):
            verdict = "deliverable"
        elif reason_code in ("invalid_syntax", "no_mail_server", "mailbox_rejected"):
            verdict = "bounce"
        else:
            verdict = "unknown"

        explanation = custom_explanation or EXPLANATIONS.get(
            reason_code,
            "Unable to verify deliverability status conclusively.",
        )

        return VerificationResult(
            email=email,
            verdict=verdict,
            reason=reason_code,
            explanation=explanation,
            flags=flags or [],
            details=details or {},
        )


classifier = HeuristicClassifier()
