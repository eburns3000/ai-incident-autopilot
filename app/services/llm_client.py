"""Provider-agnostic LLM client for incident triage."""

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from app.config import get_settings
from app.models import (
    NormalizedIncident,
    LLMTriageResult,
    IncidentType,
    Severity,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an IT incident triage assistant. Output ONLY valid JSON. No markdown, no code fences, no explanation.

You must classify incidents and return a JSON object with these exact keys:
- incident_type: one of "deployment", "database", "network", "application", "security", "infrastructure", "unknown"
- severity: one of "P1", "P2", "P3", "P4"
- confidence: a float between 0 and 1 indicating your confidence
- owner_team: the team that should own this incident
- short_summary: a 1-2 sentence summary of the incident
- first_actions: an array of 3-7 immediate action items
- runbook_suggestion: a suggested runbook or procedure name

CRITICAL CONSTRAINT: If the environment is NOT "prod", you must NEVER output P1 or P2 severity. Use P3 or P4 only for non-production environments."""


def build_user_prompt(incident: NormalizedIncident) -> str:
    """Build the user prompt for LLM triage."""
    return f"""Classify this incident and return JSON:

Summary: {incident.summary}
Description: {incident.description[:2000] if incident.description else 'No description'}
Component: {incident.component}
Environment: {incident.environment.value}
Labels: {', '.join(incident.labels) if incident.labels else 'None'}
Reporter: {incident.reporter}

Remember: If environment is not "prod", severity must be P3 or P4."""


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def triage(self, incident: NormalizedIncident) -> LLMTriageResult:
        """Perform incident triage."""
        pass


class MockProvider(LLMProvider):
    """Mock LLM provider for testing without API calls."""

    async def triage(self, incident: NormalizedIncident) -> LLMTriageResult:
        """Return mock triage results based on keyword analysis."""
        summary_lower = incident.summary.lower()
        desc_lower = incident.description.lower()
        combined = f"{summary_lower} {desc_lower}"

        # Determine incident type based on keywords
        if any(kw in combined for kw in ["deploy", "release", "rollout", "ci/cd"]):
            incident_type = IncidentType.DEPLOYMENT
            owner_team = "platform"
        elif any(kw in combined for kw in ["database", "db", "sql", "query", "postgres", "mysql"]):
            incident_type = IncidentType.DATABASE
            owner_team = "data-platform"
        elif any(kw in combined for kw in ["network", "dns", "load balancer", "connectivity", "timeout"]):
            incident_type = IncidentType.NETWORK
            owner_team = "infrastructure"
        elif any(kw in combined for kw in ["security", "breach", "unauthorized", "vulnerability"]):
            incident_type = IncidentType.SECURITY
            owner_team = "security"
        elif any(kw in combined for kw in ["infrastructure", "server", "vm", "cloud", "aws", "gcp"]):
            incident_type = IncidentType.INFRASTRUCTURE
            owner_team = "infrastructure"
        else:
            incident_type = IncidentType.APPLICATION
            owner_team = "engineering"

        # Determine severity based on keywords
        if any(kw in combined for kw in ["security", "breach", "critical", "p1"]):
            severity = Severity.P1
        elif any(kw in combined for kw in ["outage", "down", "500", "cannot", "failing"]):
            severity = Severity.P2
        elif any(kw in combined for kw in ["degraded", "slow", "intermittent"]):
            severity = Severity.P3
        else:
            severity = Severity.P4

        # Generate mock actions
        first_actions = [
            f"Check {incident.component} service logs",
            "Review monitoring dashboards for anomalies",
            "Check recent deployments or changes",
            f"Verify {incident.environment.value} environment health",
            "Escalate to on-call if severity warrants",
        ]

        return LLMTriageResult(
            incident_type=incident_type,
            severity=severity,
            confidence=0.85,
            owner_team=owner_team,
            short_summary=f"[MOCK] {incident.summary[:100]}",
            first_actions=first_actions,
            runbook_suggestion=f"runbook-{incident_type.value}-general",
        )


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""

    def __init__(self, api_key: str, model: str, timeout: int):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.base_url = "https://api.openai.com/v1"

    async def triage(self, incident: NormalizedIncident) -> LLMTriageResult:
        """Perform triage using OpenAI API."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": build_user_prompt(incident)},
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return _parse_llm_response(content)


class AnthropicProvider(LLMProvider):
    """Anthropic API provider."""

    def __init__(self, api_key: str, model: str, timeout: int):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.base_url = "https://api.anthropic.com/v1"

    async def triage(self, incident: NormalizedIncident) -> LLMTriageResult:
        """Perform triage using Anthropic API."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 1024,
                    "system": SYSTEM_PROMPT,
                    "messages": [
                        {"role": "user", "content": build_user_prompt(incident)},
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["content"][0]["text"]
            return _parse_llm_response(content)


def _parse_llm_response(content: str) -> LLMTriageResult:
    """Parse LLM response into LLMTriageResult."""
    # Clean up response - remove potential markdown
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1])

    data = json.loads(content)

    # Normalize incident type
    incident_type_str = data.get("incident_type", "unknown").lower()
    try:
        incident_type = IncidentType(incident_type_str)
    except ValueError:
        incident_type = IncidentType.UNKNOWN

    # Normalize severity
    severity_str = data.get("severity", "P4").upper()
    try:
        severity = Severity(severity_str)
    except ValueError:
        severity = Severity.P4

    # Parse confidence
    confidence = float(data.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))

    # Parse first actions
    first_actions = data.get("first_actions", [])
    if not isinstance(first_actions, list):
        first_actions = [str(first_actions)]
    first_actions = [str(a) for a in first_actions[:7]]  # Max 7 actions

    return LLMTriageResult(
        incident_type=incident_type,
        severity=severity,
        confidence=confidence,
        owner_team=str(data.get("owner_team", "platform")),
        short_summary=str(data.get("short_summary", "")),
        first_actions=first_actions,
        runbook_suggestion=str(data.get("runbook_suggestion", "")),
    )


class LLMClient:
    """Provider-agnostic LLM client."""

    def __init__(self):
        """Initialize LLM client based on configuration."""
        settings = get_settings()
        self.provider_name = settings.llm_provider.lower()
        self.timeout = settings.http_timeout

        if self.provider_name == "mock":
            logger.info("Using mock LLM provider for testing")
            self.provider: LLMProvider = MockProvider()
        elif self.provider_name == "anthropic":
            if not settings.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY is required")
            self.provider = AnthropicProvider(
                api_key=settings.anthropic_api_key,
                model=settings.anthropic_model,
                timeout=self.timeout,
            )
        else:  # Default to OpenAI
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required")
            self.provider = OpenAIProvider(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                timeout=self.timeout,
            )

    async def triage(self, incident: NormalizedIncident) -> LLMTriageResult:
        """Perform incident triage using configured provider."""
        logger.info(
            f"Triaging incident {incident.jira_key} with {self.provider_name}"
        )
        try:
            result = await self.provider.triage(incident)
            logger.info(
                f"Triage result for {incident.jira_key}: "
                f"type={result.incident_type.value}, "
                f"severity={result.severity.value}, "
                f"confidence={result.confidence:.2f}"
            )
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected LLM error: {e}")
            raise


# Singleton instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create LLM client singleton."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
