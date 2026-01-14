"""Policy engine for deterministic guardrails."""

import re
import logging
from typing import Optional

from app.models import (
    NormalizedIncident,
    LLMTriageResult,
    PolicyResult,
    Severity,
    Environment,
)

logger = logging.getLogger(__name__)

# Outage keywords that indicate minimum P2 for prod
OUTAGE_KEYWORDS = [
    r"\boutage\b",
    r"\bdown\b",
    r"\bservice unavailable\b",
    r"\b500\b",
    r"\berror rate spike\b",
    r"\bcannot\b",
    r"\bfailing\b",
    r"\btimeouts?\b",
]

# Security keywords that force P1 for prod
SECURITY_KEYWORDS = [
    r"\bsecurity\b",
    r"\bbreach\b",
    r"\bunauthorized\b",
    r"\bleak\b",
    r"\bexfiltration\b",
    r"\bexploit\b",
    r"\bvulnerability\b",
    r"\bcve\b",
]

# Confidence threshold for auto-assignment
CONFIDENCE_THRESHOLD = 0.70

# Severity order for comparisons
SEVERITY_ORDER = {
    Severity.P1: 1,
    Severity.P2: 2,
    Severity.P3: 3,
    Severity.P4: 4,
}


def _contains_keywords(text: str, keywords: list[str]) -> bool:
    """Check if text contains any of the keywords."""
    text_lower = text.lower()
    for pattern in keywords:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    return False


def _severity_at_least(severity: Severity, min_severity: Severity) -> bool:
    """Check if severity is at least as severe as min_severity."""
    return SEVERITY_ORDER[severity] <= SEVERITY_ORDER[min_severity]


def _cap_severity(severity: Severity, max_severity: Severity) -> Severity:
    """Cap severity to not exceed max_severity (lower priority number = higher severity)."""
    if SEVERITY_ORDER[severity] < SEVERITY_ORDER[max_severity]:
        return max_severity
    return severity


def _raise_severity(severity: Severity, min_severity: Severity) -> Severity:
    """Raise severity to at least min_severity."""
    if SEVERITY_ORDER[severity] > SEVERITY_ORDER[min_severity]:
        return min_severity
    return severity


class PolicyEngine:
    """Engine for applying deterministic policy guardrails."""

    def __init__(self):
        """Initialize policy engine."""
        self.confidence_threshold = CONFIDENCE_THRESHOLD

    def apply_policies(
        self,
        incident: NormalizedIncident,
        llm_result: LLMTriageResult,
    ) -> PolicyResult:
        """
        Apply all policy guardrails to LLM result.

        Policy order (later policies can override earlier ones):
        1. Non-prod environment: max severity P3
        2. Prod + outage keywords: min severity P2
        3. Prod + security keywords: severity P1
        4. Low confidence: flag for human review
        """
        original_severity = llm_result.severity
        final_severity = llm_result.severity
        override_reason: Optional[str] = None
        needs_human_review = False

        # Combine text for keyword matching
        searchable_text = f"{incident.summary} {incident.description}"

        # Policy 1: Non-prod environments max at P3
        if incident.environment != Environment.PROD:
            if SEVERITY_ORDER[final_severity] < SEVERITY_ORDER[Severity.P3]:
                final_severity = _cap_severity(final_severity, Severity.P3)
                override_reason = (
                    f"Non-production environment ({incident.environment.value}) "
                    f"capped to P3"
                )
                logger.info(
                    f"[{incident.jira_key}] Policy: Non-prod cap applied, "
                    f"{original_severity.value} -> {final_severity.value}"
                )

        # Policy 2: Prod + outage keywords => min P2
        elif incident.environment == Environment.PROD:
            if _contains_keywords(searchable_text, OUTAGE_KEYWORDS):
                if SEVERITY_ORDER[final_severity] > SEVERITY_ORDER[Severity.P2]:
                    final_severity = _raise_severity(final_severity, Severity.P2)
                    override_reason = (
                        "Production outage keywords detected, raised to P2"
                    )
                    logger.info(
                        f"[{incident.jira_key}] Policy: Outage keywords found, "
                        f"{original_severity.value} -> {final_severity.value}"
                    )

            # Policy 3: Prod + security keywords => P1
            if _contains_keywords(searchable_text, SECURITY_KEYWORDS):
                final_severity = Severity.P1
                override_reason = (
                    "Production security keywords detected, set to P1"
                )
                logger.info(
                    f"[{incident.jira_key}] Policy: Security keywords found, "
                    f"setting to P1"
                )

        # Policy 4: Low confidence => human review
        if llm_result.confidence < self.confidence_threshold:
            needs_human_review = True
            logger.info(
                f"[{incident.jira_key}] Policy: Low confidence "
                f"({llm_result.confidence:.2f}), flagging for human review"
            )

        # Build labels
        labels_to_add = [
            "autopilot",
            f"type:{llm_result.incident_type.value}",
            f"sev:{final_severity.value}",
        ]
        if needs_human_review:
            labels_to_add.append("needs-review")

        severity_overridden = original_severity != final_severity

        return PolicyResult(
            original_severity=original_severity,
            final_severity=final_severity,
            severity_overridden=severity_overridden,
            override_reason=override_reason,
            needs_human_review=needs_human_review,
            confidence=llm_result.confidence,
            labels_to_add=labels_to_add,
        )


# Singleton instance
_policy_engine: Optional[PolicyEngine] = None


def get_policy_engine() -> PolicyEngine:
    """Get or create policy engine singleton."""
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = PolicyEngine()
    return _policy_engine
