"""
Vercel Serverless Function Entrypoint for FastAPI Application.
Handles Vercel path rewrites and exposes ASGI handler.
"""
import sys
from pathlib import Path
from urllib.parse import parse_qs

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.main import app as fastapi_app  # noqa: E402


class VercelPathFixMiddleware:
    """
    Pure ASGI middleware that modifies scope['path'] before FastAPI routing dispatches.
    Restores the target path forwarded by Vercel query rewrites (?path=...).
    """

    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            qs = scope.get("query_string", b"").decode("utf-8")
            params = parse_qs(qs)
            if "path" in params and params["path"]:
                target = params["path"][0]
                if target in ("docs", "openapi.json"):
                    scope["path"] = f"/{target}"
                elif target.startswith("api/"):
                    scope["path"] = f"/{target}"
                else:
                    scope["path"] = f"/api/{target}"

        await self.asgi_app(scope, receive, send)


# Exported ASGI entrypoint for Vercel runtime
app = VercelPathFixMiddleware(fastapi_app)
handler = app
