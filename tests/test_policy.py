"""Tests for the policy engine guardrails."""

import pytest
from app.services.policy import PolicyEngine, CONFIDENCE_THRESHOLD
from app.models import (
    NormalizedIncident,
    LLMTriageResult,
    Environment,
    Severity,
    IncidentType,
)


@pytest.fixture
def policy_engine():
    """Create a policy engine instance."""
    return PolicyEngine()


@pytest.fixture
def prod_incident():
    """Create a production incident."""
    return NormalizedIncident(
        jira_key="INC-001",
        summary="API is down",
        description="Users cannot access the API",
        component="api-gateway",
        environment=Environment.PROD,
        labels=["prod"],
        reporter="Test User",
    )


@pytest.fixture
def staging_incident():
    """Create a staging incident."""
    return NormalizedIncident(
        jira_key="INC-002",
        summary="Staging server slow",
        description="Staging environment is slow",
        component="api-gateway",
        environment=Environment.STAGING,
        labels=["staging"],
        reporter="Test User",
    )


@pytest.fixture
def dev_incident():
    """Create a dev incident."""
    return NormalizedIncident(
        jira_key="INC-003",
        summary="Dev database issue",
        description="Development database is not responding",
        component="database",
        environment=Environment.DEV,
        labels=["dev"],
        reporter="Test User",
    )


def create_llm_result(severity: Severity, confidence: float = 0.85) -> LLMTriageResult:
    """Helper to create LLM triage results."""
    return LLMTriageResult(
        incident_type=IncidentType.APPLICATION,
        severity=severity,
        confidence=confidence,
        owner_team="platform",
        short_summary="Test summary",
        first_actions=["Check logs"],
        runbook_suggestion="runbook-app-debug",
    )


class TestNonProdEnvironmentCap:
    """Tests for non-production environment severity cap (max P3)."""

    def test_staging_p1_capped_to_p3(self, policy_engine, staging_incident):
        """Test that P1 in staging is capped to P3."""
        llm_result = create_llm_result(Severity.P1)
        result = policy_engine.apply_policies(staging_incident, llm_result)

        assert result.final_severity == Severity.P3
        assert result.severity_overridden is True
        assert "Non-production" in result.override_reason

    def test_staging_p2_capped_to_p3(self, policy_engine, staging_incident):
        """Test that P2 in staging is capped to P3."""
        llm_result = create_llm_result(Severity.P2)
        result = policy_engine.apply_policies(staging_incident, llm_result)

        assert result.final_severity == Severity.P3
        assert result.severity_overridden is True

    def test_staging_p3_unchanged(self, policy_engine, staging_incident):
        """Test that P3 in staging remains P3."""
        llm_result = create_llm_result(Severity.P3)
        result = policy_engine.apply_policies(staging_incident, llm_result)

        assert result.final_severity == Severity.P3
        assert result.severity_overridden is False

    def test_staging_p4_unchanged(self, policy_engine, staging_incident):
        """Test that P4 in staging remains P4."""
        llm_result = create_llm_result(Severity.P4)
        result = policy_engine.apply_policies(staging_incident, llm_result)

        assert result.final_severity == Severity.P4
        assert result.severity_overridden is False

    def test_dev_p1_capped_to_p3(self, policy_engine, dev_incident):
        """Test that P1 in dev is capped to P3."""
        llm_result = create_llm_result(Severity.P1)
        result = policy_engine.apply_policies(dev_incident, llm_result)

        assert result.final_severity == Severity.P3
        assert result.severity_overridden is True


class TestProdOutageKeywords:
    """Tests for production outage keywords (minimum P2)."""

    def test_outage_keyword_raises_p4_to_p2(self, policy_engine, prod_incident):
        """Test that 'outage' keyword raises P4 to P2 in prod."""
        prod_incident.summary = "Complete service outage"
        llm_result = create_llm_result(Severity.P4)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert result.final_severity == Severity.P2
        assert result.severity_overridden is True
        assert "outage" in result.override_reason.lower()

    def test_down_keyword_raises_p3_to_p2(self, policy_engine, prod_incident):
        """Test that 'down' keyword raises P3 to P2 in prod."""
        prod_incident.description = "The service is down"
        llm_result = create_llm_result(Severity.P3)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert result.final_severity == Severity.P2
        assert result.severity_overridden is True

    def test_500_keyword_raises_to_p2(self, policy_engine, prod_incident):
        """Test that '500' error code raises to P2 in prod."""
        prod_incident.description = "Seeing many 500 errors"
        llm_result = create_llm_result(Severity.P4)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert result.final_severity == Severity.P2
        assert result.severity_overridden is True

    def test_error_rate_spike_raises_to_p2(self, policy_engine, prod_incident):
        """Test that 'error rate spike' raises to P2 in prod."""
        prod_incident.summary = "Error rate spike in production"
        llm_result = create_llm_result(Severity.P3)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert result.final_severity == Severity.P2
        assert result.severity_overridden is True

    def test_timeouts_keyword_raises_to_p2(self, policy_engine, prod_incident):
        """Test that 'timeouts' raises to P2 in prod."""
        prod_incident.summary = "API timeouts affecting users"
        llm_result = create_llm_result(Severity.P3)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert result.final_severity == Severity.P2
        assert result.severity_overridden is True

    def test_already_p1_not_changed(self, policy_engine, prod_incident):
        """Test that P1 remains P1 even with outage keywords."""
        prod_incident.summary = "Major outage"
        llm_result = create_llm_result(Severity.P1)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert result.final_severity == Severity.P1
        # May be overridden to P1 by security check, but final is still P1


class TestSecurityKeywords:
    """Tests for security keywords (force P1 in prod)."""

    def test_security_keyword_forces_p1(self, policy_engine, prod_incident):
        """Test that 'security' keyword forces P1 in prod."""
        prod_incident.summary = "Security alert in production"
        llm_result = create_llm_result(Severity.P4)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert result.final_severity == Severity.P1
        assert result.severity_overridden is True
        assert "security" in result.override_reason.lower()

    def test_breach_keyword_forces_p1(self, policy_engine, prod_incident):
        """Test that 'breach' keyword forces P1 in prod."""
        prod_incident.description = "Possible data breach detected"
        llm_result = create_llm_result(Severity.P3)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert result.final_severity == Severity.P1
        assert result.severity_overridden is True

    def test_unauthorized_keyword_forces_p1(self, policy_engine, prod_incident):
        """Test that 'unauthorized' keyword forces P1 in prod."""
        prod_incident.description = "Unauthorized access attempt detected"
        llm_result = create_llm_result(Severity.P2)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert result.final_severity == Severity.P1
        assert result.severity_overridden is True

    def test_leak_keyword_forces_p1(self, policy_engine, prod_incident):
        """Test that 'leak' keyword forces P1 in prod."""
        prod_incident.summary = "Potential data leak discovered"
        llm_result = create_llm_result(Severity.P3)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert result.final_severity == Severity.P1
        assert result.severity_overridden is True

    def test_security_in_staging_capped_at_p3(self, policy_engine, staging_incident):
        """Test that security keywords in staging are still capped at P3."""
        staging_incident.summary = "Security test in staging"
        llm_result = create_llm_result(Severity.P1)
        result = policy_engine.apply_policies(staging_incident, llm_result)

        # Non-prod cap takes precedence
        assert result.final_severity == Severity.P3
        assert result.severity_overridden is True


class TestConfidenceGate:
    """Tests for low confidence human review flag."""

    def test_low_confidence_flags_human_review(self, policy_engine, prod_incident):
        """Test that low confidence flags for human review."""
        llm_result = create_llm_result(Severity.P3, confidence=0.50)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert result.needs_human_review is True
        assert "needs-review" in result.labels_to_add

    def test_at_threshold_not_flagged(self, policy_engine, prod_incident):
        """Test that confidence at threshold is not flagged."""
        llm_result = create_llm_result(Severity.P3, confidence=CONFIDENCE_THRESHOLD)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert result.needs_human_review is False

    def test_above_threshold_not_flagged(self, policy_engine, prod_incident):
        """Test that high confidence is not flagged."""
        llm_result = create_llm_result(Severity.P3, confidence=0.95)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert result.needs_human_review is False

    def test_just_below_threshold_flagged(self, policy_engine, prod_incident):
        """Test that confidence just below threshold is flagged."""
        llm_result = create_llm_result(Severity.P3, confidence=0.69)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert result.needs_human_review is True


class TestLabelsGeneration:
    """Tests for automatic label generation."""

    def test_autopilot_label_always_added(self, policy_engine, prod_incident):
        """Test that autopilot label is always added."""
        llm_result = create_llm_result(Severity.P3)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert "autopilot" in result.labels_to_add

    def test_type_label_added(self, policy_engine, prod_incident):
        """Test that type label is added."""
        llm_result = create_llm_result(Severity.P3)
        llm_result.incident_type = IncidentType.DATABASE
        result = policy_engine.apply_policies(prod_incident, llm_result)

        assert "type:database" in result.labels_to_add

    def test_sev_label_uses_final_severity(self, policy_engine, staging_incident):
        """Test that sev label uses final (not original) severity."""
        llm_result = create_llm_result(Severity.P1)  # Will be capped to P3
        result = policy_engine.apply_policies(staging_incident, llm_result)

        assert "sev:P3" in result.labels_to_add
        assert "sev:P1" not in result.labels_to_add


class TestPolicyPrecedence:
    """Tests for policy precedence and combinations."""

    def test_security_overrides_outage_in_prod(self, policy_engine, prod_incident):
        """Test that security P1 overrides outage P2."""
        prod_incident.summary = "Security breach causing outage"
        llm_result = create_llm_result(Severity.P4)
        result = policy_engine.apply_policies(prod_incident, llm_result)

        # Security should win
        assert result.final_severity == Severity.P1

    def test_non_prod_cap_overrides_security(self, policy_engine, staging_incident):
        """Test that non-prod cap applies even with security keywords."""
        staging_incident.summary = "Security test breach simulation"
        llm_result = create_llm_result(Severity.P1)
        result = policy_engine.apply_policies(staging_incident, llm_result)

        # Non-prod cap should win
        assert result.final_severity == Severity.P3
