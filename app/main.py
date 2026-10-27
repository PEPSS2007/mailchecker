"""
FastAPI Main Application.
Defines /api/check, /api/health, rate limiting, static asset serving, and structured exception handling.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.pipeline import run_verification_pipeline
from app.smtp_probe import check_outbound_smtp_capability

# Configure structured logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mailchecker")

# Rate limiter initialized with client IP address
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Proactively check SMTP port 25 capability on startup
    logger.info("Starting Email Deliverability Checker service...")
    smtp_ok = await check_outbound_smtp_capability(force_refresh=True)
    mode = (
        "Full Verification (SMTP + DNS + Syntax)"
        if smtp_ok
        else "Degraded Mode (DNS + Syntax Only - Outbound SMTP Blocked)"
    )
    logger.info("Service initialized in mode: %s", mode)
    yield
    logger.info("Shutting down Email Deliverability Checker service...")


app = FastAPI(
    title="Email Deliverability Checker",
    description="Internship software development project: High-accuracy, privacy-first email deliverability verification without sending emails.",
    version="1.0.0",
    lifespan=lifespan,
)

# Attach SlowAPI rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CheckEmailsRequest(BaseModel):
    emails: list[str] | str = Field(
        ...,
        description="List of email addresses or a string separated by newlines, commas, or semicolons.",
    )


class CheckResultItem(BaseModel):
    email: str
    verdict: str
    reason: str
    explanation: str
    flags: list[str] = []
    details: dict = {}


class CheckResponse(BaseModel):
    total: int
    deliverable: int
    bounce: int
    unknown: int
    mode: str
    results: list[CheckResultItem]


class HealthResponse(BaseModel):
    status: str
    version: str
    smtp_available: bool
    mode: str
    description: str


@app.get("/api/health", response_model=HealthResponse)
@app.get("/health", response_model=HealthResponse)
async def get_health_status():
    """
    Returns service health and dynamic SMTP port 25 capability information.
    """
    smtp_available = await check_outbound_smtp_capability()
    mode = "full" if smtp_available else "dns_only"
    description = (
        "Full verification active: Outbound SMTP port 25 is accessible."
        if smtp_available
        else "Degraded mode active: Outbound port 25 is blocked by hosting environment. Performing syntax and DNS checks with honest unknown statuses."
    )

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        smtp_available=smtp_available,
        mode=mode,
        description=description,
    )


@app.post("/api/check", response_model=CheckResponse)
@app.post("/check", response_model=CheckResponse)
@limiter.limit(settings.DEFAULT_RATE_LIMIT)
async def check_emails(payload: CheckEmailsRequest, request: Request):
    """
    Verifies deliverability for submitted email addresses.
    Enforces maximum batch size (100 unique emails), deduplication, and rate limiting.
    """
    try:
        results = await run_verification_pipeline(payload.emails)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.error("Internal verification error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while verifying the email addresses.",
        )

    # Compute summary aggregates
    total = len(results)
    deliverable_count = sum(1 for r in results if r.verdict == "deliverable")
    bounce_count = sum(1 for r in results if r.verdict == "bounce")
    unknown_count = sum(1 for r in results if r.verdict == "unknown")

    smtp_available = await check_outbound_smtp_capability()
    active_mode = "full" if smtp_available else "dns_only"

    return CheckResponse(
        total=total,
        deliverable=deliverable_count,
        bounce=bounce_count,
        unknown=unknown_count,
        mode=active_mode,
        results=[CheckResultItem(**r.to_dict()) for r in results],
    )


# Mount static assets
if settings.STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def serve_index():
    """Serves the dashboard index.html frontend."""
    index_path = settings.STATIC_DIR / "index.html"
    if not index_path.exists():
        index_path = settings.BASE_DIR.parent / "public" / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    return JSONResponse({"message": "Email Deliverability Checker API is running."})

