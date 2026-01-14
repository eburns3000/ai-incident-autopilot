"""Jira API client for updating issues."""

import logging
from base64 import b64encode
from typing import Optional

import httpx

from app.config import get_settings
from app.models import (
    TriageOutput,
    Severity,
    JiraPriority,
    SEVERITY_TO_PRIORITY,
)

logger = logging.getLogger(__name__)


class JiraClient:
    """Client for Jira REST API."""

    def __init__(self):
        """Initialize Jira client."""
        settings = get_settings()
        self.base_url = settings.jira_base_url.rstrip("/")
        self.email = settings.jira_email
        self.api_token = settings.jira_api_token
        self.timeout = settings.http_timeout
        self.dry_run = settings.dry_run

        # Build auth header
        credentials = f"{self.email}:{self.api_token}"
        self.auth_header = b64encode(credentials.encode()).decode()

    def _get_headers(self) -> dict:
        """Get request headers."""
        return {
            "Authorization": f"Basic {self.auth_header}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_issue_url(self, jira_key: str) -> str:
        """Get the browse URL for an issue."""
        return f"{self.base_url}/browse/{jira_key}"

    async def update_issue(self, triage: TriageOutput) -> bool:
        """
        Update Jira issue with triage results.

        Updates priority, adds labels, and adds a comment.
        """
        jira_key = triage.incident.jira_key

        if self.dry_run:
            logger.info(f"[DRY RUN] Would update Jira issue {jira_key}")
            return True

        try:
            # Update fields (priority and labels)
            await self._update_fields(triage)

            # Add comment
            await self._add_comment(triage)

            logger.info(f"Successfully updated Jira issue {jira_key}")
            return True

        except Exception as e:
            logger.error(f"Failed to update Jira issue {jira_key}: {e}")
            raise

    async def _update_fields(self, triage: TriageOutput):
        """Update issue fields (priority and labels)."""
        jira_key = triage.incident.jira_key
        policy = triage.policy_result
        llm = triage.llm_result

        # Map severity to Jira priority
        priority = SEVERITY_TO_PRIORITY.get(
            policy.final_severity, JiraPriority.MEDIUM
        )

        # Build update payload
        update_payload = {
            "fields": {
                "priority": {"name": priority.value},
            },
            "update": {
                "labels": [
                    {"add": label} for label in policy.labels_to_add
                ],
            },
        }

        # Add correlated label if applicable
        if triage.correlated:
            update_payload["update"]["labels"].append({"add": "correlated"})

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.put(
                f"{self.base_url}/rest/api/3/issue/{jira_key}",
                headers=self._get_headers(),
                json=update_payload,
            )
            response.raise_for_status()

    async def _add_comment(self, triage: TriageOutput):
        """Add a triage comment to the issue."""
        jira_key = triage.incident.jira_key
        llm = triage.llm_result
        policy = triage.policy_result

        # Build comment in Atlassian Document Format (ADF)
        comment_body = self._build_comment_adf(triage)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/rest/api/3/issue/{jira_key}/comment",
                headers=self._get_headers(),
                json={"body": comment_body},
            )
            response.raise_for_status()

    def _build_comment_adf(self, triage: TriageOutput) -> dict:
        """Build comment in Atlassian Document Format."""
        llm = triage.llm_result
        policy = triage.policy_result

        content = []

        # Header
        content.append({
            "type": "heading",
            "attrs": {"level": 3},
            "content": [{"type": "text", "text": "Autopilot Triage Summary"}],
        })

        # Status panel
        status_text = (
            f"Severity: {policy.final_severity.value} | "
            f"Type: {llm.incident_type.value} | "
            f"Confidence: {llm.confidence:.0%}"
        )
        if policy.severity_overridden:
            status_text += f" | Overridden from {policy.original_severity.value}"

        content.append({
            "type": "paragraph",
            "content": [
                {"type": "text", "text": status_text, "marks": [{"type": "strong"}]},
            ],
        })

        # Summary
        content.append({
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Summary: ", "marks": [{"type": "strong"}]},
                {"type": "text", "text": llm.short_summary},
            ],
        })

        # Correlation notice
        if triage.correlated:
            content.append({
                "type": "panel",
                "attrs": {"panelType": "warning"},
                "content": [{
                    "type": "paragraph",
                    "content": [{
                        "type": "text",
                        "text": f"This incident may be related to {triage.correlated_with}",
                    }],
                }],
            })

        # First actions
        if llm.first_actions:
            content.append({
                "type": "heading",
                "attrs": {"level": 4},
                "content": [{"type": "text", "text": "First Actions"}],
            })
            content.append({
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [{"type": "text", "text": action}],
                        }],
                    }
                    for action in llm.first_actions
                ],
            })

        # Runbook suggestion
        if llm.runbook_suggestion:
            content.append({
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Suggested Runbook: ", "marks": [{"type": "strong"}]},
                    {"type": "text", "text": llm.runbook_suggestion},
                ],
            })

        # Human review notice
        if policy.needs_human_review:
            content.append({
                "type": "panel",
                "attrs": {"panelType": "info"},
                "content": [{
                    "type": "paragraph",
                    "content": [{
                        "type": "text",
                        "text": (
                            f"Needs human review - confidence below threshold "
                            f"({llm.confidence:.0%}). Severity/priority not auto-assigned."
                        ),
                    }],
                }],
            })

        # Footer
        content.append({
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": "Generated by Incident Autopilot",
                    "marks": [{"type": "em"}],
                },
            ],
        })

        return {
            "version": 1,
            "type": "doc",
            "content": content,
        }

    async def add_human_review_comment(self, jira_key: str, confidence: float):
        """Add a comment requesting human review."""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would add human review comment to {jira_key}")
            return

        comment_body = {
            "version": 1,
            "type": "doc",
            "content": [{
                "type": "panel",
                "attrs": {"panelType": "warning"},
                "content": [{
                    "type": "paragraph",
                    "content": [{
                        "type": "text",
                        "text": (
                            f"Autopilot confidence is low ({confidence:.0%}). "
                            "Manual review required for severity assignment."
                        ),
                    }],
                }],
            }],
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/rest/api/3/issue/{jira_key}/comment",
                headers=self._get_headers(),
                json={"body": comment_body},
            )
            response.raise_for_status()


# Singleton instance
_jira_client: Optional[JiraClient] = None


def get_jira_client() -> JiraClient:
    """Get or create Jira client singleton."""
    global _jira_client
    if _jira_client is None:
        _jira_client = JiraClient()
    return _jira_client
