"""
Application Configuration and Settings.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable override support."""

    # API & Execution Limits
    MAX_EMAILS_PER_REQUEST: int = 100
    DEFAULT_RATE_LIMIT: str = "30/minute"
    TOTAL_CONCURRENCY_LIMIT: int = 20
    DOMAIN_CONCURRENCY_LIMIT: int = 2

    # DNS Settings
    DNS_TIMEOUT_SECONDS: float = 3.0
    DNS_CACHE_TTL_SECONDS: int = 300
    DNS_CACHE_MAXSIZE: int = 2048

    # SMTP Settings
    SMTP_CONNECT_TIMEOUT_SECONDS: float = 5.0
    SMTP_COMMAND_TIMEOUT_SECONDS: float = 8.0
    SMTP_MAX_RETRIES: int = 1
    SMTP_PORT: int = 25
    SMTP_HELO_DOMAIN: str = "mailchecker.internal"
    SMTP_MAIL_FROM: str = "verify@mailchecker.internal"
    SMTP_CAPABILITY_CACHE_TTL_SECONDS: int = 60
    CATCH_ALL_CACHE_TTL_SECONDS: int = 600
    CATCH_ALL_CACHE_MAXSIZE: int = 1024

    # Well-known probe hosts for SMTP capability detection
    SMTP_PROBE_HOSTS: list[str] = [
        "aspmx.l.google.com",
        "mx1.mail.icloud.com",
        "mail.protection.outlook.com",
    ]

    # Server Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent
    DATA_DIR: Path = BASE_DIR / "data"
    STATIC_DIR: Path = BASE_DIR / "static"
    DISPOSABLE_DOMAINS_FILE: Path = DATA_DIR / "disposable_domains.txt"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
