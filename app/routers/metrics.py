"""Metrics endpoint for observability."""

from fastapi import APIRouter

from app.models import MetricsCounter
from app.middleware import get_rate_limiter

router = APIRouter(tags=["metrics"])

# Global metrics counter
_metrics = MetricsCounter()


def get_metrics() -> MetricsCounter:
    """Get the global metrics counter."""
    return _metrics


def increment_metric(name: str, amount: int = 1):
    """Increment a metric counter."""
    global _metrics
    if hasattr(_metrics, name):
        current = getattr(_metrics, name)
        setattr(_metrics, name, current + amount)


@router.get("/metrics")
async def get_metrics_endpoint() -> dict:
    """Get application metrics."""
    rate_limiter = get_rate_limiter()

    return {
        "counters": _metrics.model_dump(),
        "rate_limiter": rate_limiter.get_stats(),
    }
