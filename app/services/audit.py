"""Audit logging service - SQLite + JSONL."""

import json
import os
import logging
from datetime import datetime
from typing import Optional

from app.config import get_settings
from app.db import get_database
from app.models import AuditEvent

logger = logging.getLogger(__name__)


class AuditService:
    """Service for audit logging to SQLite and JSONL."""

    def __init__(self, jsonl_path: Optional[str] = None):
        """Initialize audit service."""
        settings = get_settings()
        self.jsonl_path = jsonl_path or settings.audit_jsonl_path
        self.dry_run = settings.dry_run
        self.db = get_database()

        # Ensure directory exists for JSONL
        os.makedirs(os.path.dirname(self.jsonl_path) or ".", exist_ok=True)

    def log(
        self,
        event_type: str,
        action: str,
        status: str,
        jira_key: Optional[str] = None,
        component: Optional[str] = None,
        severity: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> AuditEvent:
        """Log an audit event to both SQLite and JSONL."""
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            event_type=event_type,
            jira_key=jira_key,
            component=component,
            severity=severity,
            action=action,
            status=status,
            details=details or {},
            dry_run=self.dry_run,
        )

        # Log to SQLite
        try:
            self.db.insert_audit_event(event)
        except Exception as e:
            logger.error(f"Failed to write audit event to SQLite: {e}")

        # Log to JSONL
        try:
            self._write_jsonl(event)
        except Exception as e:
            logger.error(f"Failed to write audit event to JSONL: {e}")

        # Also log to standard logger
        log_msg = f"[{event.event_type}] {event.action}: {event.status}"
        if event.jira_key:
            log_msg = f"[{event.jira_key}] {log_msg}"
        if status == "success":
            logger.info(log_msg)
        else:
            logger.warning(log_msg)

        return event

    def _write_jsonl(self, event: AuditEvent):
        """Append event to JSONL file."""
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.model_dump(), default=str) + "\n")

    def log_webhook_received(self, jira_key: str, details: dict) -> AuditEvent:
        """Log webhook receipt."""
        return self.log(
            event_type="webhook",
            action="received",
            status="success",
            jira_key=jira_key,
            details=details,
        )

    def log_normalization(
        self, jira_key: str, component: str, environment: str
    ) -> AuditEvent:
        """Log successful normalization."""
        return self.log(
            event_type="normalization",
            action="normalized",
            status="success",
            jira_key=jira_key,
            component=component,
            details={"environment": environment},
        )

    def log_correlation(
        self, jira_key: str, correlated_with: Optional[str], component: str
    ) -> AuditEvent:
        """Log correlation check result."""
        return self.log(
            event_type="correlation",
            action="checked",
            status="success" if correlated_with else "no_match",
            jira_key=jira_key,
            component=component,
            details={"correlated_with": correlated_with},
        )

    def log_llm_triage(
        self,
        jira_key: str,
        incident_type: str,
        severity: str,
        confidence: float,
        status: str = "success",
        error: Optional[str] = None,
    ) -> AuditEvent:
        """Log LLM triage result."""
        details = {
            "incident_type": incident_type,
            "severity": severity,
            "confidence": confidence,
        }
        if error:
            details["error"] = error
        return self.log(
            event_type="llm_triage",
            action="triaged",
            status=status,
            jira_key=jira_key,
            severity=severity,
            details=details,
        )

    def log_policy_override(
        self,
        jira_key: str,
        original_severity: str,
        final_severity: str,
        reason: str,
    ) -> AuditEvent:
        """Log policy override."""
        return self.log(
            event_type="policy",
            action="override",
            status="applied",
            jira_key=jira_key,
            severity=final_severity,
            details={
                "original_severity": original_severity,
                "final_severity": final_severity,
                "reason": reason,
            },
        )

    def log_human_review_required(
        self, jira_key: str, confidence: float
    ) -> AuditEvent:
        """Log when human review is required."""
        return self.log(
            event_type="policy",
            action="human_review_required",
            status="flagged",
            jira_key=jira_key,
            details={"confidence": confidence},
        )

    def log_jira_update(
        self,
        jira_key: str,
        action: str,
        status: str = "success",
        error: Optional[str] = None,
    ) -> AuditEvent:
        """Log Jira update."""
        details = {}
        if error:
            details["error"] = error
        return self.log(
            event_type="jira",
            action=action,
            status=status,
            jira_key=jira_key,
            details=details,
        )

    def log_slack_post(
        self,
        jira_key: str,
        channel: str,
        status: str = "success",
        error: Optional[str] = None,
    ) -> AuditEvent:
        """Log Slack notification."""
        details = {"channel": channel}
        if error:
            details["error"] = error
        return self.log(
            event_type="slack",
            action="posted",
            status=status,
            jira_key=jira_key,
            details=details,
        )

    def log_dry_run_action(
        self, jira_key: str, action: str, target: str, details: dict
    ) -> AuditEvent:
        """Log an action that would have been taken in dry run mode."""
        return self.log(
            event_type="dry_run",
            action=f"would_have_{action}",
            status="skipped",
            jira_key=jira_key,
            details={"target": target, **details},
        )


# Singleton instance
_audit_service: Optional[AuditService] = None


def get_audit_service() -> AuditService:
    """Get or create audit service singleton."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service
