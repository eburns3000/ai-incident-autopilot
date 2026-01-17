"""Routers module for Incident Autopilot."""

from .webhook import router as webhook_router
from .health import router as health_router
from .metrics import router as metrics_router
from .incidents import router as incidents_router

__all__ = ["webhook_router", "health_router", "metrics_router", "incidents_router"]
