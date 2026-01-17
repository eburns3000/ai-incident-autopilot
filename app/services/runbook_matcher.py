"""Runbook matching and fit scoring service."""

import json
import logging
from pathlib import Path
from typing import Optional

from app.models import IncidentType, RunbookFit

logger = logging.getLogger(__name__)

# Keywords associated with each runbook category
RUNBOOK_KEYWORDS = {
    "deployment": [
        "deploy", "release", "rollout", "ci/cd", "pipeline", "build",
        "container", "kubernetes", "k8s", "helm", "docker", "image",
        "version", "upgrade", "rollback", "canary", "blue-green"
    ],
    "database": [
        "database", "db", "sql", "query", "postgres", "mysql", "mongo",
        "redis", "cache", "connection pool", "replication", "deadlock",
        "slow query", "index", "migration", "backup", "restore"
    ],
    "network": [
        "network", "dns", "load balancer", "connectivity", "timeout",
        "latency", "ssl", "tls", "certificate", "firewall", "vpc",
        "routing", "proxy", "nginx", "haproxy", "cdn"
    ],
    "application": [
        "application", "app", "error", "exception", "crash", "memory",
        "cpu", "performance", "slow", "degraded", "bug", "500",
        "api", "endpoint", "service", "microservice"
    ],
    "security": [
        "security", "breach", "unauthorized", "vulnerability", "cve",
        "attack", "intrusion", "suspicious", "malware", "phishing",
        "credential", "leak", "exposure", "audit"
    ],
    "infrastructure": [
        "infrastructure", "server", "vm", "cloud", "aws", "gcp", "azure",
        "instance", "scaling", "autoscale", "disk", "storage", "compute",
        "region", "zone", "availability"
    ],
}

# Cache for loaded runbooks
_runbooks_cache: Optional[dict] = None


def load_runbooks() -> dict:
    """Load runbooks from JSON file."""
    global _runbooks_cache
    if _runbooks_cache is not None:
        return _runbooks_cache

    runbooks_path = Path(__file__).parent.parent.parent / "data" / "seed_runbooks.json"
    try:
        with open(runbooks_path) as f:
            _runbooks_cache = json.load(f)
            logger.info(f"Loaded {len(_runbooks_cache)} runbooks from {runbooks_path}")
            return _runbooks_cache
    except Exception as e:
        logger.error(f"Failed to load runbooks: {e}")
        return {}


def calculate_keyword_overlap(text: str, keywords: list[str]) -> float:
    """Calculate keyword overlap score between text and keyword list."""
    if not text or not keywords:
        return 0.0

    text_lower = text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in text_lower)

    # Normalize by keyword count, but boost for multiple matches
    base_score = matches / len(keywords)
    # Boost if multiple keywords match (max 2x boost)
    boost = min(2.0, 1.0 + (matches * 0.1))

    return min(1.0, base_score * boost)


def match_runbooks(
    incident_type: IncidentType,
    title: str,
    description: str,
) -> tuple[RunbookFit, list[RunbookFit]]:
    """
    Match incident to runbooks and return primary + alternatives.

    Returns:
        tuple: (primary_runbook, list of alternative_runbooks)
    """
    runbooks = load_runbooks()
    combined_text = f"{title} {description}"

    scored_runbooks: list[tuple[float, str, dict]] = []

    for key, runbook_data in runbooks.items():
        # Base score from incident type match
        type_score = 1.0 if key == incident_type.value else 0.0

        # Keyword overlap score
        keywords = RUNBOOK_KEYWORDS.get(key, [])
        keyword_score = calculate_keyword_overlap(combined_text, keywords)

        # Combined score: 60% type match, 40% keyword overlap
        combined_score = (type_score * 0.6) + (keyword_score * 0.4)

        scored_runbooks.append((combined_score, key, runbook_data))

    # Sort by score descending
    scored_runbooks.sort(key=lambda x: x[0], reverse=True)

    # Build RunbookFit objects
    def make_runbook_fit(score: float, key: str, data: dict) -> RunbookFit:
        return RunbookFit(
            runbook_key=key,
            runbook_name=data.get("name", key.title()),
            fit_score=round(score, 2),
            runbook_url=data.get("runbook_url", ""),
            steps=data.get("steps", []),
        )

    # Primary is highest score
    primary_score, primary_key, primary_data = scored_runbooks[0]
    primary = make_runbook_fit(primary_score, primary_key, primary_data)

    # Alternatives are next 3 with score > 0.1
    alternatives = []
    for score, key, data in scored_runbooks[1:4]:
        if score > 0.1:
            alternatives.append(make_runbook_fit(score, key, data))

    return primary, alternatives


def get_runbook(key: str) -> Optional[dict]:
    """Get a specific runbook by key."""
    runbooks = load_runbooks()
    return runbooks.get(key)


def list_all_runbooks() -> list[dict]:
    """List all available runbooks."""
    runbooks = load_runbooks()
    result = []
    for key, data in runbooks.items():
        result.append({
            "key": key,
            "name": data.get("name", key.title()),
            "description": data.get("description", ""),
            "runbook_url": data.get("runbook_url", ""),
            "steps": data.get("steps", []),
        })
    return result
