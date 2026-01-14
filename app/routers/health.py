"""Health check endpoint."""

from fastapi import APIRouter

from app import __version__
from app.config import get_settings
from app.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=__version__,
        dry_run=settings.dry_run,
    )
