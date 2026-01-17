"""Pydantic models for the Incident Autopilot."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Environment(str, Enum):
    """Environment classification."""
    PROD = "prod"
    STAGING = "staging"
    DEV = "dev"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    """Incident severity levels."""
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class IncidentType(str, Enum):
    """Types of incidents."""
    DEPLOYMENT = "deployment"
    DATABASE = "database"
    NETWORK = "network"
    APPLICATION = "application"
    SECURITY = "security"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


class JiraPriority(str, Enum):
    """Jira priority mapping."""
    HIGHEST = "Highest"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


# Mapping from severity to Jira priority
SEVERITY_TO_PRIORITY = {
    Severity.P1: JiraPriority.HIGHEST,
    Severity.P2: JiraPriority.HIGH,
    Severity.P3: JiraPriority.MEDIUM,
    Severity.P4: JiraPriority.LOW,
}


class NormalizedIncident(BaseModel):
    """Normalized incident data from Jira webhook."""
    jira_key: str
    summary: str
    description: str = ""
    labels: list[str] = Field(default_factory=list)
    component: str = "unknown"
    environment: Environment = Environment.UNKNOWN
    reporter: str = "unknown"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    raw_payload: dict = Field(default_factory=dict)


class LLMTriageResult(BaseModel):
    """Result from LLM triage."""
    incident_type: IncidentType
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    owner_team: str = "platform"
    short_summary: str
    first_actions: list[str] = Field(default_factory=list)
    runbook_suggestion: str = ""


class PolicyResult(BaseModel):
    """Result after applying policy guardrails."""
    original_severity: Severity
    final_severity: Severity
    severity_overridden: bool = False
    override_reason: Optional[str] = None
    needs_human_review: bool = False
    confidence: float
    labels_to_add: list[str] = Field(default_factory=list)


class TriageOutput(BaseModel):
    """Complete triage output combining LLM and policy."""
    incident: NormalizedIncident
    llm_result: LLMTriageResult
    policy_result: PolicyResult
    correlated: bool = False
    correlated_with: Optional[str] = None


class AuditEvent(BaseModel):
    """Audit log event."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str
    jira_key: Optional[str] = None
    component: Optional[str] = None
    severity: Optional[str] = None
    action: str
    status: str  # "success" or "failure"
    details: dict = Field(default_factory=dict)
    dry_run: bool = False


class MetricsCounter(BaseModel):
    """Application metrics."""
    webhooks_received: int = 0
    webhooks_processed: int = 0
    webhooks_rejected: int = 0
    incidents_triaged: int = 0
    incidents_correlated: int = 0
    llm_calls: int = 0
    llm_errors: int = 0
    jira_updates: int = 0
    jira_errors: int = 0
    slack_posts: int = 0
    slack_errors: int = 0
    policy_overrides: int = 0
    human_review_required: int = 0


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: str
    dry_run: bool


class WebhookResponse(BaseModel):
    """Response from webhook processing."""
    status: str
    jira_key: Optional[str] = None
    message: str
    dry_run: bool = False


# ============================================
# New models for Incident Autopilot Web UI
# ============================================

class IncidentStatus(str, Enum):
    """Status of an incident through the triage workflow."""
    PENDING = "pending"           # Just created, not triaged yet
    TRIAGED = "triaged"           # AI triage completed
    APPROVED = "approved"         # Human approved triage
    REJECTED = "rejected"         # Human rejected triage
    OVERRIDDEN = "overridden"     # Human overrode severity
    RESOLVED = "resolved"         # Incident resolved


class IncidentCreate(BaseModel):
    """Request to create a new incident via form submission."""
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=10, max_length=5000)
    component: str = Field(default="unknown", max_length=100)
    environment: Environment = Environment.PROD
    reporter: str = Field(default="web-user", max_length=100)


class RunbookFit(BaseModel):
    """Runbook match with fit score."""
    runbook_key: str
    runbook_name: str
    fit_score: float = Field(ge=0.0, le=1.0)
    runbook_url: str = ""
    steps: list[str] = Field(default_factory=list)


class TriageResult(BaseModel):
    """Full triage result with risk score and runbook alternatives."""
    incident_type: IncidentType
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)
    owner_team: str
    short_summary: str
    first_actions: list[str] = Field(default_factory=list)
    primary_runbook: RunbookFit
    alternative_runbooks: list[RunbookFit] = Field(default_factory=list)
    needs_human_review: bool = False
    policy_override_reason: Optional[str] = None


class StoredIncident(BaseModel):
    """Incident stored in database with full details."""
    id: str
    title: str
    description: str
    component: str
    environment: Environment
    reporter: str
    status: IncidentStatus = IncidentStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    triage: Optional[TriageResult] = None
    decision_by: Optional[str] = None
    decision_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    original_severity: Optional[Severity] = None


class DecisionRequest(BaseModel):
    """Request to make a decision on a triaged incident."""
    action: str = Field(..., pattern="^(approve|reject|override)$")
    new_severity: Optional[Severity] = None  # Required if action is 'override'
    note: Optional[str] = Field(default=None, max_length=500)
    decided_by: str = Field(default="anonymous", max_length=100)


class IncidentListItem(BaseModel):
    """Summary item for incident list view."""
    id: str
    title: str
    component: str
    environment: Environment
    status: IncidentStatus
    severity: Optional[Severity] = None
    risk_score: Optional[float] = None
    created_at: datetime
    needs_human_review: bool = False


class IncidentListResponse(BaseModel):
    """Response for listing incidents."""
    incidents: list[IncidentListItem]
    total: int


class PIRResponse(BaseModel):
    """Generated Post-Incident Review."""
    incident_id: str
    title: str
    markdown: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
