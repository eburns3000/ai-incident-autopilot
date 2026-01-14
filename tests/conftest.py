"""Pytest fixtures and configuration."""

import os
import pytest

# Set test environment variables before importing app modules
os.environ["AUTOPILOT_WEBHOOK_SECRET"] = "test-secret"
os.environ["DRY_RUN"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///./test_data/test_audit.db"
os.environ["AUDIT_JSONL_PATH"] = "./test_data/test_audit.jsonl"
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["LLM_PROVIDER"] = "openai"


@pytest.fixture
def sample_jira_payload():
    """Sample Jira webhook payload for an Incident."""
    return {
        "webhookEvent": "jira:issue_created",
        "issue": {
            "key": "INC-123",
            "fields": {
                "issuetype": {"name": "Incident"},
                "summary": "Production API outage - users cannot login",
                "description": "Multiple users reporting 500 errors on login endpoint. Error rate spiking.",
                "labels": ["prod", "urgent"],
                "components": [{"name": "auth-service"}],
                "reporter": {"displayName": "John Doe"},
                "created": "2024-01-15T10:30:00.000+0000",
            },
        },
    }


@pytest.fixture
def sample_non_incident_payload():
    """Sample Jira webhook payload for a non-Incident issue."""
    return {
        "webhookEvent": "jira:issue_created",
        "issue": {
            "key": "FEAT-456",
            "fields": {
                "issuetype": {"name": "Story"},
                "summary": "Add dark mode support",
                "description": "Users want dark mode.",
                "labels": [],
                "components": [],
                "reporter": {"displayName": "Jane Doe"},
            },
        },
    }


@pytest.fixture
def staging_incident_payload():
    """Sample Jira webhook payload for a staging Incident."""
    return {
        "webhookEvent": "jira:issue_created",
        "issue": {
            "key": "INC-789",
            "fields": {
                "issuetype": {"name": "Incident"},
                "summary": "Staging database connection failures",
                "description": "Database connection pool exhausted in staging environment.",
                "labels": ["staging"],
                "components": [{"name": "database"}],
                "reporter": {"displayName": "Dev User"},
                "created": "2024-01-15T11:00:00.000+0000",
            },
        },
    }


@pytest.fixture
def security_incident_payload():
    """Sample Jira webhook payload for a security Incident."""
    return {
        "webhookEvent": "jira:issue_created",
        "issue": {
            "key": "INC-SEC-001",
            "fields": {
                "issuetype": {"name": "Incident"},
                "summary": "Potential security breach detected",
                "description": "Unauthorized access attempt detected in production logs.",
                "labels": ["prod", "security"],
                "components": [{"name": "auth-service"}],
                "reporter": {"displayName": "Security Team"},
                "created": "2024-01-15T12:00:00.000+0000",
            },
        },
    }
