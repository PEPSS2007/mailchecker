"""
Vercel Serverless Function Entrypoint for FastAPI Application.
Handles Vercel path rewrites and exposes ASGI handler.
"""
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from fastapi import Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from app.main import app  # noqa: E402


@app.middleware("http")
async def vercel_routing_middleware(request: Request, call_next):
    # Vercel supplies the actual requested URL path in 'x-matched-path' or 'x-now-route-matches'
    matched_path = request.headers.get("x-matched-path")
    if matched_path:
        request.scope["path"] = matched_path
    elif request.scope.get("path") in ("/api/index.py", "/api/index"):
        request.scope["path"] = "/api/health"

    return await call_next(request)


@app.get("/api/debug")
@app.get("/debug")
async def vercel_debug_info(request: Request):
    return JSONResponse(
        {
            "path": request.url.path,
            "scope_path": request.scope.get("path"),
            "headers": {k: v for k, v in request.headers.items() if "auth" not in k.lower()},
        }
    )


# Vercel ASGI handler
handler = app
