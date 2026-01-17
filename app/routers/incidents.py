"""Incidents API router for web UI."""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Query

from app.config import get_settings
from app.db import get_database
from app.models import (
    IncidentCreate,
    StoredIncident,
    IncidentStatus,
    IncidentListItem,
    IncidentListResponse,
    DecisionRequest,
    PIRResponse,
    TriageResult,
    Severity,
    Environment,
    IncidentType,
    NormalizedIncident,
)
from app.services.llm_client import get_llm_client
from app.services.policy import get_policy_engine
from app.services.risk import calculate_risk_score
from app.services.runbook_matcher import match_runbooks, list_all_runbooks
from app.services.pir import generate_pir
from app.services.audit import get_audit_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["incidents"])

# Demo token for AI triage access
DEMO_TOKEN = "incident-autopilot-demo-2024"


def _init_incidents_table():
    """Initialize the web_incidents table if it doesn't exist."""
    db = get_database()
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS web_incidents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                component TEXT,
                environment TEXT,
                reporter TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                triage_json TEXT,
                decision_by TEXT,
                decision_at TEXT,
                decision_note TEXT,
                original_severity TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_web_incidents_status
            ON web_incidents(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_web_incidents_created
            ON web_incidents(created_at DESC)
        """)


# Initialize table on module load
_init_incidents_table()


def _row_to_incident(row: dict) -> StoredIncident:
    """Convert database row to StoredIncident model."""
    triage = None
    if row.get("triage_json"):
        try:
            triage_data = json.loads(row["triage_json"])
            triage = TriageResult(**triage_data)
        except Exception as e:
            logger.warning(f"Failed to parse triage JSON: {e}")

    original_severity = None
    if row.get("original_severity"):
        try:
            original_severity = Severity(row["original_severity"])
        except:
            pass

    decision_at = None
    if row.get("decision_at"):
        try:
            decision_at = datetime.fromisoformat(row["decision_at"])
        except:
            pass

    return StoredIncident(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        component=row.get("component", "unknown"),
        environment=Environment(row.get("environment", "unknown")),
        reporter=row.get("reporter", "unknown"),
        status=IncidentStatus(row.get("status", "pending")),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        triage=triage,
        decision_by=row.get("decision_by"),
        decision_at=decision_at,
        decision_note=row.get("decision_note"),
        original_severity=original_severity,
    )


def _incident_to_list_item(incident: StoredIncident) -> IncidentListItem:
    """Convert StoredIncident to list item summary."""
    return IncidentListItem(
        id=incident.id,
        title=incident.title,
        component=incident.component,
        environment=incident.environment,
        status=incident.status,
        severity=incident.triage.severity if incident.triage else None,
        risk_score=incident.triage.risk_score if incident.triage else None,
        created_at=incident.created_at,
        needs_human_review=incident.triage.needs_human_review if incident.triage else False,
    )


@router.post("/incidents", response_model=StoredIncident)
async def create_incident(
    incident: IncidentCreate,
    x_demo_token: Optional[str] = Header(None, alias="X-Demo-Token"),
):
    """
    Create a new incident and run AI triage.

    Without demo token: Uses mock AI (keyword-based).
    With valid demo token: Uses configured LLM provider.
    """
    db = get_database()
    settings = get_settings()

    # Generate unique ID
    incident_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow()

    # Log incident creation
    get_audit_service().log(
        event_type="incident_created",
        jira_key=incident_id,
        component=incident.component,
        action="create_incident",
        status="success",
        details={"title": incident.title, "source": "web_form"},
    )

    # Check demo token for AI provider selection
    use_real_ai = x_demo_token == DEMO_TOKEN and settings.llm_provider != "mock"

    # Create normalized incident for triage
    normalized = NormalizedIncident(
        jira_key=incident_id,
        summary=incident.title,
        description=incident.description,
        component=incident.component,
        environment=incident.environment,
        reporter=incident.reporter,
        labels=[],
        created_at=now,
        raw_payload={},
    )

    # Run LLM triage
    try:
        if use_real_ai:
            llm_client = get_llm_client()
        else:
            # Force mock provider for demo safety
            from app.services.llm_client import MockProvider
            class MockLLMClient:
                def __init__(self):
                    self.provider = MockProvider()
                async def triage(self, incident):
                    return await self.provider.triage(incident)
            llm_client = MockLLMClient()

        llm_result = await llm_client.triage(normalized)

        # Apply policy guardrails
        policy_result = get_policy_engine().apply_policies(normalized, llm_result)

        # Calculate risk score
        risk_score = calculate_risk_score(
            severity=policy_result.final_severity,
            confidence=llm_result.confidence,
            environment=incident.environment,
        )

        # Match runbooks
        primary_runbook, alternative_runbooks = match_runbooks(
            incident_type=llm_result.incident_type,
            title=incident.title,
            description=incident.description,
        )

        # Build triage result
        triage = TriageResult(
            incident_type=llm_result.incident_type,
            severity=policy_result.final_severity,
            confidence=llm_result.confidence,
            risk_score=risk_score,
            owner_team=llm_result.owner_team,
            short_summary=llm_result.short_summary,
            first_actions=llm_result.first_actions,
            primary_runbook=primary_runbook,
            alternative_runbooks=alternative_runbooks,
            needs_human_review=policy_result.needs_human_review,
            policy_override_reason=policy_result.override_reason,
        )

        status = IncidentStatus.TRIAGED

        # Log triage
        get_audit_service().log(
            event_type="incident_triaged",
            jira_key=incident_id,
            component=incident.component,
            severity=policy_result.final_severity.value,
            action="ai_triage",
            status="success",
            details={
                "incident_type": llm_result.incident_type.value,
                "confidence": llm_result.confidence,
                "risk_score": risk_score,
                "needs_human_review": policy_result.needs_human_review,
                "used_real_ai": use_real_ai,
            },
        )

    except Exception as e:
        logger.error(f"Triage failed for {incident_id}: {e}")
        triage = None
        status = IncidentStatus.PENDING

        get_audit_service().log(
            event_type="incident_triage_failed",
            jira_key=incident_id,
            component=incident.component,
            action="ai_triage",
            status="failure",
            details={"error": str(e)},
        )

    # Store incident
    triage_json = triage.model_dump_json() if triage else None

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO web_incidents
            (id, title, description, component, environment, reporter, status, created_at, updated_at, triage_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident_id,
                incident.title,
                incident.description,
                incident.component,
                incident.environment.value,
                incident.reporter,
                status.value,
                now.isoformat(),
                now.isoformat(),
                triage_json,
            ),
        )

    return StoredIncident(
        id=incident_id,
        title=incident.title,
        description=incident.description,
        component=incident.component,
        environment=incident.environment,
        reporter=incident.reporter,
        status=status,
        created_at=now,
        updated_at=now,
        triage=triage,
    )


@router.get("/incidents", response_model=IncidentListResponse)
async def list_incidents(
    status: Optional[IncidentStatus] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List incidents with optional filtering."""
    db = get_database()

    with db._get_connection() as conn:
        cursor = conn.cursor()

        # Build query
        query = "SELECT * FROM web_incidents"
        params = []

        if status:
            query += " WHERE status = ?"
            params.append(status.value)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = [dict(row) for row in cursor.fetchall()]

        # Get total count
        count_query = "SELECT COUNT(*) as total FROM web_incidents"
        if status:
            count_query += " WHERE status = ?"
            cursor.execute(count_query, [status.value])
        else:
            cursor.execute(count_query)
        total = cursor.fetchone()["total"]

    incidents = [_row_to_incident(row) for row in rows]
    items = [_incident_to_list_item(inc) for inc in incidents]

    return IncidentListResponse(incidents=items, total=total)


@router.get("/incidents/{incident_id}", response_model=StoredIncident)
async def get_incident(incident_id: str):
    """Get a single incident by ID."""
    db = get_database()

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM web_incidents WHERE id = ?", (incident_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")

    return _row_to_incident(dict(row))


@router.post("/incidents/{incident_id}/decision", response_model=StoredIncident)
async def make_decision(incident_id: str, decision: DecisionRequest):
    """
    Make a decision on a triaged incident.

    Actions:
    - approve: Accept the AI triage as-is
    - reject: Reject the triage (requires re-triage or manual handling)
    - override: Change the severity to a different value
    """
    db = get_database()
    now = datetime.utcnow()

    # Get existing incident
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM web_incidents WHERE id = ?", (incident_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident = _row_to_incident(dict(row))

    if incident.status == IncidentStatus.PENDING:
        raise HTTPException(status_code=400, detail="Incident has not been triaged yet")

    # Process decision
    if decision.action == "approve":
        new_status = IncidentStatus.APPROVED
    elif decision.action == "reject":
        new_status = IncidentStatus.REJECTED
    elif decision.action == "override":
        if not decision.new_severity:
            raise HTTPException(status_code=400, detail="new_severity required for override")
        new_status = IncidentStatus.OVERRIDDEN
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    # Update triage if overriding
    original_severity = None
    triage_json = row["triage_json"]
    if decision.action == "override" and incident.triage:
        original_severity = incident.triage.severity
        # Update severity in triage
        updated_triage = incident.triage.model_copy()
        updated_triage.severity = decision.new_severity
        # Recalculate risk score
        updated_triage.risk_score = calculate_risk_score(
            severity=decision.new_severity,
            confidence=updated_triage.confidence,
            environment=incident.environment,
        )
        triage_json = updated_triage.model_dump_json()

    # Update database
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE web_incidents
            SET status = ?, updated_at = ?, decision_by = ?, decision_at = ?,
                decision_note = ?, original_severity = ?, triage_json = ?
            WHERE id = ?
            """,
            (
                new_status.value,
                now.isoformat(),
                decision.decided_by,
                now.isoformat(),
                decision.note,
                original_severity.value if original_severity else None,
                triage_json,
                incident_id,
            ),
        )

    # Log decision
    get_audit_service().log(
        event_type="incident_decision",
        jira_key=incident_id,
        component=incident.component,
        severity=decision.new_severity.value if decision.new_severity else incident.triage.severity.value if incident.triage else None,
        action=f"decision_{decision.action}",
        status="success",
        details={
            "decided_by": decision.decided_by,
            "note": decision.note,
            "original_severity": original_severity.value if original_severity else None,
            "new_severity": decision.new_severity.value if decision.new_severity else None,
        },
    )

    # Fetch and return updated incident
    return await get_incident(incident_id)


@router.get("/incidents/{incident_id}/audit")
async def get_audit_trail(incident_id: str):
    """Get audit trail for an incident."""
    db = get_database()

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM audit_events
            WHERE jira_key = ?
            ORDER BY timestamp ASC
            """,
            (incident_id,),
        )
        rows = [dict(row) for row in cursor.fetchall()]

    # Parse details JSON
    for row in rows:
        if row.get("details"):
            try:
                row["details"] = json.loads(row["details"])
            except:
                pass

    return {"incident_id": incident_id, "events": rows}


@router.get("/incidents/{incident_id}/pir", response_model=PIRResponse)
async def get_pir(incident_id: str):
    """Generate Post-Incident Review for an incident."""
    # Get incident
    incident = await get_incident(incident_id)

    # Get audit trail
    audit_data = await get_audit_trail(incident_id)

    # Generate PIR
    markdown = generate_pir(incident, audit_data["events"])

    # Log PIR generation
    get_audit_service().log(
        event_type="pir_generated",
        jira_key=incident_id,
        component=incident.component,
        action="generate_pir",
        status="success",
        details={},
    )

    return PIRResponse(
        incident_id=incident_id,
        title=incident.title,
        markdown=markdown,
    )


@router.get("/runbooks")
async def get_runbooks():
    """List all available runbooks."""
    return {"runbooks": list_all_runbooks()}
