"""Risk score calculation service."""

from app.models import Severity, Environment


# Severity weights (higher = more severe)
SEVERITY_WEIGHTS = {
    Severity.P1: 1.0,
    Severity.P2: 0.75,
    Severity.P3: 0.5,
    Severity.P4: 0.25,
}

# Environment weights (higher = more critical)
ENVIRONMENT_WEIGHTS = {
    Environment.PROD: 1.0,
    Environment.STAGING: 0.5,
    Environment.DEV: 0.25,
    Environment.UNKNOWN: 0.5,
}


def calculate_risk_score(
    severity: Severity,
    confidence: float,
    environment: Environment,
) -> float:
    """
    Calculate deterministic risk score.

    Formula: risk = (severity_weight * 0.4) + (confidence_inverse * 0.3) + (env_weight * 0.3)

    - Severity: P1=1.0, P2=0.75, P3=0.5, P4=0.25
    - Confidence inverse: 1 - confidence (lower confidence = higher risk)
    - Environment: prod=1.0, staging=0.5, dev=0.25

    Returns a score between 0.0 (low risk) and 1.0 (high risk).
    """
    severity_weight = SEVERITY_WEIGHTS.get(severity, 0.5)
    confidence_inverse = 1.0 - confidence
    env_weight = ENVIRONMENT_WEIGHTS.get(environment, 0.5)

    risk = (severity_weight * 0.4) + (confidence_inverse * 0.3) + (env_weight * 0.3)

    # Clamp to [0, 1]
    return max(0.0, min(1.0, risk))


def get_risk_level(risk_score: float) -> str:
    """Get human-readable risk level from score."""
    if risk_score >= 0.8:
        return "critical"
    elif risk_score >= 0.6:
        return "high"
    elif risk_score >= 0.4:
        return "medium"
    else:
        return "low"
