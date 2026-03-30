"""AWS Lambda entry point for the FastAPI application."""

from mangum import Mangum

try:
    from api.main import app
except ModuleNotFoundError:  # pragma: no cover - Lambda local import fallback
    from main import app

handler = Mangum(app)
