"""Slack client for posting notifications."""

import logging
from typing import Optional

import httpx

from app.config import get_settings
from app.models import TriageOutput, Severity

logger = logging.getLogger(__name__)

# Severity to emoji/color mapping
SEVERITY_COLORS = {
    Severity.P1: "#FF0000",  # Red
    Severity.P2: "#FFA500",  # Orange
    Severity.P3: "#FFFF00",  # Yellow
    Severity.P4: "#00FF00",  # Green
}

SEVERITY_EMOJI = {
    Severity.P1: ":rotating_light:",
    Severity.P2: ":warning:",
    Severity.P3: ":large_yellow_circle:",
    Severity.P4: ":large_green_circle:",
}


class SlackClient:
    """Client for Slack API."""

    def __init__(self):
        """Initialize Slack client."""
        settings = get_settings()
        self.bot_token = settings.slack_bot_token
        self.channel = settings.slack_channel
        self.timeout = settings.http_timeout
        self.dry_run = settings.dry_run
        self.jira_base_url = settings.jira_base_url.rstrip("/")

    def _get_headers(self) -> dict:
        """Get request headers."""
        return {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json",
        }

    async def post_incident_notification(
        self,
        triage: TriageOutput,
        channel: Optional[str] = None,
    ) -> bool:
        """Post incident notification to Slack."""
        target_channel = channel or self.channel
        jira_key = triage.incident.jira_key

        if self.dry_run:
            logger.info(
                f"[DRY RUN] Would post Slack notification for {jira_key} "
                f"to {target_channel}"
            )
            return True

        try:
            message = self._build_message(triage)

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers=self._get_headers(),
                    json={
                        "channel": target_channel,
                        "text": self._build_fallback_text(triage),
                        "blocks": message["blocks"],
                        "attachments": message.get("attachments", []),
                    },
                )
                response.raise_for_status()
                data = response.json()

                if not data.get("ok"):
                    error = data.get("error", "Unknown error")
                    logger.error(f"Slack API error: {error}")
                    raise Exception(f"Slack API error: {error}")

                logger.info(
                    f"Posted Slack notification for {jira_key} to {target_channel}"
                )
                return True

        except Exception as e:
            logger.error(f"Failed to post Slack notification: {e}")
            raise

    def _build_fallback_text(self, triage: TriageOutput) -> str:
        """Build fallback text for notifications."""
        incident = triage.incident
        policy = triage.policy_result
        return (
            f"{SEVERITY_EMOJI.get(policy.final_severity, '')} "
            f"[{policy.final_severity.value}] {incident.jira_key}: {incident.summary}"
        )

    def _build_message(self, triage: TriageOutput) -> dict:
        """Build Slack Block Kit message."""
        incident = triage.incident
        llm = triage.llm_result
        policy = triage.policy_result

        severity = policy.final_severity
        color = SEVERITY_COLORS.get(severity, "#808080")
        emoji = SEVERITY_EMOJI.get(severity, ":question:")
        jira_url = f"{self.jira_base_url}/browse/{incident.jira_key}"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Incident: {incident.jira_key}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*<{jira_url}|{incident.summary}>*",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{severity.value}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Type:*\n{llm.incident_type.value}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Component:*\n{incident.component}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Environment:*\n{incident.environment.value}",
                    },
                ],
            },
        ]

        # Add summary section
        if llm.short_summary:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Summary:* {llm.short_summary}",
                },
            })

        # Add correlation notice
        if triage.correlated:
            blocks.append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": f":link: Possibly related to {triage.correlated_with}",
                }],
            })

        # Add human review notice
        if policy.needs_human_review:
            blocks.append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": (
                        f":eyes: *Needs human review* - "
                        f"Low confidence ({llm.confidence:.0%})"
                    ),
                }],
            })

        # Add owner team
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": f"Owner Team: {llm.owner_team} | Reporter: {incident.reporter}",
            }],
        })

        # Add action buttons
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View in Jira"},
                    "url": jira_url,
                    "action_id": "view_jira",
                },
            ],
        })

        return {
            "blocks": blocks,
            "attachments": [
                {
                    "color": color,
                    "blocks": [],
                }
            ],
        }


# Singleton instance
_slack_client: Optional[SlackClient] = None


def get_slack_client() -> SlackClient:
    """Get or create Slack client singleton."""
    global _slack_client
    if _slack_client is None:
        _slack_client = SlackClient()
    return _slack_client
