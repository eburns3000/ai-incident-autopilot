"""Authentication middleware for webhook validation."""

import hmac
import logging
from fastapi import HTTPException, Request, status

from app.config import get_settings

logger = logging.getLogger(__name__)


async def verify_webhook_secret(request: Request) -> bool:
    """
    Verify the webhook secret from request header.

    Raises HTTPException if verification fails.
    """
    settings = get_settings()
    expected_secret = settings.autopilot_webhook_secret

    # Get secret from header
    provided_secret = request.headers.get("X-AUTOPILOT-SECRET")

    if not provided_secret:
        logger.warning("Missing X-AUTOPILOT-SECRET header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-AUTOPILOT-SECRET header",
        )

    # Use constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(provided_secret, expected_secret):
        logger.warning("Invalid webhook secret provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )

    return True


def get_client_ip(request: Request) -> str:
    """
    Extract client IP from request.

    Handles X-Forwarded-For header for proxied requests.
    """
    # Check for forwarded header first (common with reverse proxies)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP (original client)
        return forwarded.split(",")[0].strip()

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    return "unknown"
