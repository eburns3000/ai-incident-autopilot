"""In-memory rate limiter for webhook endpoints."""

import time
import logging
from collections import defaultdict
from typing import Optional, Tuple
from threading import Lock

from app.config import get_settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple in-memory rate limiter by IP address."""

    def __init__(
        self,
        max_requests: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ):
        """Initialize rate limiter."""
        settings = get_settings()
        self.max_requests = max_requests or settings.rate_limit_requests
        self.window_seconds = window_seconds or settings.rate_limit_window_seconds

        # Store: {ip: [(timestamp, count), ...]}
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, ip: str) -> Tuple[bool, int, int]:
        """
        Check if request from IP is allowed.

        Returns:
            Tuple of (allowed, remaining, reset_seconds)
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            # Clean old entries and count recent requests
            self._requests[ip] = [
                ts for ts in self._requests[ip] if ts > cutoff
            ]

            current_count = len(self._requests[ip])
            remaining = max(0, self.max_requests - current_count - 1)

            # Calculate reset time
            if self._requests[ip]:
                oldest = min(self._requests[ip])
                reset_seconds = int(oldest + self.window_seconds - now)
            else:
                reset_seconds = self.window_seconds

            if current_count >= self.max_requests:
                logger.warning(
                    f"Rate limit exceeded for IP {ip}: "
                    f"{current_count}/{self.max_requests}"
                )
                return False, 0, reset_seconds

            # Record this request
            self._requests[ip].append(now)
            return True, remaining, reset_seconds

    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds

            active_ips = 0
            total_requests = 0

            for ip, timestamps in self._requests.items():
                valid = [ts for ts in timestamps if ts > cutoff]
                if valid:
                    active_ips += 1
                    total_requests += len(valid)

            return {
                "active_ips": active_ips,
                "total_requests_in_window": total_requests,
                "max_requests": self.max_requests,
                "window_seconds": self.window_seconds,
            }

    def clear(self):
        """Clear all rate limit data."""
        with self._lock:
            self._requests.clear()


# Singleton instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create rate limiter singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
