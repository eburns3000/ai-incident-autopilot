"""Incident correlation service."""

import logging
from difflib import SequenceMatcher
from typing import Optional, Tuple

from app.config import get_settings
from app.db import get_database
from app.models import NormalizedIncident

logger = logging.getLogger(__name__)


class CorrelatorService:
    """Service for correlating incidents."""

    def __init__(self):
        """Initialize correlator."""
        settings = get_settings()
        self.db = get_database()
        self.window_minutes = settings.correlation_window_minutes
        self.similarity_threshold = 0.6  # 60% summary similarity

    def check_correlation(
        self, incident: NormalizedIncident
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if incident correlates with recent incidents.

        Returns:
            Tuple of (is_correlated, correlated_jira_key or None)
        """
        if incident.component == "unknown":
            # Cannot correlate without component
            return False, None

        # Find recent incidents with same component
        related = self.db.find_correlated_incidents(
            component=incident.component,
            summary=incident.summary,
            window_minutes=self.window_minutes,
            exclude_key=incident.jira_key,
        )

        if not related:
            return False, None

        # Check for similar summaries
        for related_incident in related:
            similarity = self._calculate_similarity(
                incident.summary, related_incident["summary"]
            )
            if similarity >= self.similarity_threshold:
                logger.info(
                    f"Found correlation: {incident.jira_key} -> "
                    f"{related_incident['jira_key']} "
                    f"(similarity: {similarity:.2f})"
                )
                return True, related_incident["jira_key"]

        return False, None

    def record_incident(self, incident: NormalizedIncident):
        """Record incident in database for future correlation."""
        self.db.insert_incident(incident)

    def _calculate_similarity(self, a: str, b: str) -> float:
        """Calculate similarity ratio between two strings."""
        # Normalize strings
        a = a.lower().strip()
        b = b.lower().strip()

        # Use SequenceMatcher for similarity
        return SequenceMatcher(None, a, b).ratio()


# Singleton instance
_correlator: Optional[CorrelatorService] = None


def get_correlator_service() -> CorrelatorService:
    """Get or create correlator service singleton."""
    global _correlator
    if _correlator is None:
        _correlator = CorrelatorService()
    return _correlator
