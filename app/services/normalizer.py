"""Jira webhook payload normalizer."""

import re
import logging
from datetime import datetime
from typing import Optional

from app.models import NormalizedIncident, Environment

logger = logging.getLogger(__name__)

# Environment detection patterns
ENVIRONMENT_PATTERNS = {
    Environment.PROD: [
        r"\bprod\b",
        r"\bproduction\b",
        r"\bprd\b",
        r"\blive\b",
    ],
    Environment.STAGING: [
        r"\bstaging\b",
        r"\bstage\b",
        r"\bstg\b",
        r"\buat\b",
        r"\bpre-?prod\b",
    ],
    Environment.DEV: [
        r"\bdev\b",
        r"\bdevelopment\b",
        r"\btest\b",
        r"\bqa\b",
        r"\blocal\b",
        r"\bsandbox\b",
    ],
}


def detect_environment(
    labels: list[str],
    summary: str,
    description: str,
    components: list[str],
) -> Environment:
    """Detect environment from incident metadata."""
    # Combine all text to search
    searchable = " ".join(
        [summary, description] + labels + components
    ).lower()

    # Check each environment pattern
    for env, patterns in ENVIRONMENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, searchable, re.IGNORECASE):
                return env

    return Environment.UNKNOWN


def extract_component(fields: dict) -> str:
    """Extract primary component from Jira fields."""
    components = fields.get("components", [])
    if components and isinstance(components, list):
        # Get first component name
        first = components[0]
        if isinstance(first, dict):
            return first.get("name", "unknown")
        elif isinstance(first, str):
            return first
    return "unknown"


def extract_labels(fields: dict) -> list[str]:
    """Extract labels from Jira fields."""
    labels = fields.get("labels", [])
    if isinstance(labels, list):
        return [str(label) for label in labels]
    return []


def extract_reporter(fields: dict) -> str:
    """Extract reporter from Jira fields."""
    reporter = fields.get("reporter")
    if isinstance(reporter, dict):
        return reporter.get("displayName") or reporter.get("name", "unknown")
    elif isinstance(reporter, str):
        return reporter
    return "unknown"


def normalize_jira_webhook(payload: dict) -> Optional[NormalizedIncident]:
    """
    Normalize a Jira webhook payload into our internal schema.

    Returns None if the payload is not for an Incident issue type.
    """
    try:
        issue = payload.get("issue", {})
        fields = issue.get("fields", {})

        # Check issue type
        issue_type = fields.get("issuetype", {})
        if isinstance(issue_type, dict):
            type_name = issue_type.get("name", "").lower()
        else:
            type_name = str(issue_type).lower()

        if type_name != "incident":
            logger.debug(f"Skipping non-incident issue type: {type_name}")
            return None

        # Extract basic fields
        jira_key = issue.get("key", "")
        if not jira_key:
            logger.warning("No issue key in webhook payload")
            return None

        summary = fields.get("summary", "") or ""
        description = fields.get("description", "") or ""

        # Handle Atlassian Document Format (ADF) description
        if isinstance(description, dict):
            # Extract text from ADF content
            description = _extract_text_from_adf(description)

        labels = extract_labels(fields)
        component = extract_component(fields)
        reporter = extract_reporter(fields)

        # Get component list for environment detection
        components = fields.get("components", [])
        component_names = []
        for c in components:
            if isinstance(c, dict):
                component_names.append(c.get("name", ""))
            elif isinstance(c, str):
                component_names.append(c)

        # Detect environment
        environment = detect_environment(
            labels, summary, description, component_names
        )

        # Parse created timestamp
        created_str = fields.get("created")
        created_at = datetime.utcnow()
        if created_str:
            try:
                # Handle Jira timestamp format
                created_at = datetime.fromisoformat(
                    created_str.replace("Z", "+00:00").split("+")[0]
                )
            except (ValueError, AttributeError):
                pass

        return NormalizedIncident(
            jira_key=jira_key,
            summary=summary,
            description=description,
            labels=labels,
            component=component,
            environment=environment,
            reporter=reporter,
            created_at=created_at,
            raw_payload=payload,
        )

    except Exception as e:
        logger.error(f"Error normalizing webhook payload: {e}")
        raise


def _extract_text_from_adf(adf: dict) -> str:
    """Extract plain text from Atlassian Document Format."""
    texts = []

    def extract_recursive(node):
        if isinstance(node, dict):
            if node.get("type") == "text":
                texts.append(node.get("text", ""))
            for child in node.get("content", []):
                extract_recursive(child)
        elif isinstance(node, list):
            for item in node:
                extract_recursive(item)

    extract_recursive(adf)
    return " ".join(texts)
