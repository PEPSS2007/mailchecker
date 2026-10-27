"""
Vercel Serverless Function Entrypoint for FastAPI Application.
Exposes FastAPI app directly for @vercel/python runtime.
"""
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.main import app  # noqa: E402, F401
