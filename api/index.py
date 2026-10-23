"""Vercel Serverless Function entrypoint for LearnLoop FastAPI application."""
from pathlib import Path
import sys

# Ensure repository root is on sys.path so 'app' package is importable
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app  # noqa: E402
