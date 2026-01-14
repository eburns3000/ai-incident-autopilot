"""Tests for the normalizer service."""

import pytest
from app.services.normalizer import normalize_jira_webhook, detect_environment
from app.models import Environment


class TestNormalizeJiraWebhook:
    """Tests for normalize_jira_webhook function."""

    def test_normalizes_incident_payload(self, sample_jira_payload):
        """Test that a valid incident payload is normalized correctly."""
        result = normalize_jira_webhook(sample_jira_payload)

        assert result is not None
        assert result.jira_key == "INC-123"
        assert result.summary == "Production API outage - users cannot login"
        assert "500 errors" in result.description
        assert result.component == "auth-service"
        assert result.reporter == "John Doe"
        assert "prod" in result.labels
        assert "urgent" in result.labels

    def test_returns_none_for_non_incident(self, sample_non_incident_payload):
        """Test that non-incident issues return None."""
        result = normalize_jira_webhook(sample_non_incident_payload)
        assert result is None

    def test_handles_missing_component(self):
        """Test default component when none provided."""
        payload = {
            "issue": {
                "key": "INC-001",
                "fields": {
                    "issuetype": {"name": "Incident"},
                    "summary": "Test incident",
                    "description": "",
                    "labels": [],
                    "components": [],
                    "reporter": {"displayName": "Test User"},
                },
            },
        }
        result = normalize_jira_webhook(payload)

        assert result is not None
        assert result.component == "unknown"

    def test_handles_missing_description(self):
        """Test empty description handling."""
        payload = {
            "issue": {
                "key": "INC-002",
                "fields": {
                    "issuetype": {"name": "Incident"},
                    "summary": "Test incident",
                    "description": None,
                    "labels": [],
                    "components": [],
                    "reporter": {"displayName": "Test User"},
                },
            },
        }
        result = normalize_jira_webhook(payload)

        assert result is not None
        assert result.description == ""

    def test_handles_missing_reporter(self):
        """Test default reporter when none provided."""
        payload = {
            "issue": {
                "key": "INC-003",
                "fields": {
                    "issuetype": {"name": "Incident"},
                    "summary": "Test incident",
                    "labels": [],
                    "components": [],
                },
            },
        }
        result = normalize_jira_webhook(payload)

        assert result is not None
        assert result.reporter == "unknown"

    def test_handles_adf_description(self):
        """Test extraction of text from ADF description format."""
        payload = {
            "issue": {
                "key": "INC-004",
                "fields": {
                    "issuetype": {"name": "Incident"},
                    "summary": "Test incident",
                    "description": {
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "This is "},
                                    {"type": "text", "text": "ADF content"},
                                ],
                            },
                        ],
                    },
                    "labels": [],
                    "components": [],
                },
            },
        }
        result = normalize_jira_webhook(payload)

        assert result is not None
        assert "This is" in result.description
        assert "ADF content" in result.description


class TestDetectEnvironment:
    """Tests for environment detection."""

    def test_detects_prod_from_labels(self):
        """Test detection of prod environment from labels."""
        result = detect_environment(
            labels=["prod", "urgent"],
            summary="Test incident",
            description="",
            components=[],
        )
        assert result == Environment.PROD

    def test_detects_prod_from_summary(self):
        """Test detection of prod environment from summary."""
        result = detect_environment(
            labels=[],
            summary="Production API is down",
            description="",
            components=[],
        )
        assert result == Environment.PROD

    def test_detects_staging_from_labels(self):
        """Test detection of staging environment from labels."""
        result = detect_environment(
            labels=["staging"],
            summary="Test incident",
            description="",
            components=[],
        )
        assert result == Environment.STAGING

    def test_detects_dev_from_description(self):
        """Test detection of dev environment from description."""
        result = detect_environment(
            labels=[],
            summary="Test incident",
            description="Issue in development environment",
            components=[],
        )
        assert result == Environment.DEV

    def test_returns_unknown_when_no_match(self):
        """Test unknown environment when no patterns match."""
        result = detect_environment(
            labels=["foo", "bar"],
            summary="Generic issue",
            description="Something happened",
            components=["api"],
        )
        assert result == Environment.UNKNOWN

    def test_detects_uat_as_staging(self):
        """Test that UAT is classified as staging."""
        result = detect_environment(
            labels=["uat"],
            summary="Test incident",
            description="",
            components=[],
        )
        assert result == Environment.STAGING

    def test_detects_sandbox_as_dev(self):
        """Test that sandbox is classified as dev."""
        result = detect_environment(
            labels=[],
            summary="Sandbox issue",
            description="",
            components=[],
        )
        assert result == Environment.DEV
