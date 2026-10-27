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
from app.main import app  # noqa: E402


@app.middleware("http")
async def vercel_routing_middleware(request: Request, call_next):
    """
    Maps Vercel's rewritten ?path= parameter back to FastAPI's request.scope['path'].
    """
    path_param = request.query_params.get("path")
    if path_param:
        if path_param in ("docs", "openapi.json"):
            request.scope["path"] = f"/{path_param}"
        elif path_param.startswith("api/"):
            request.scope["path"] = f"/{path_param}"
        else:
            request.scope["path"] = f"/api/{path_param}"

    return await call_next(request)


# Vercel ASGI handler
handler = app
