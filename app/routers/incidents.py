"""Incidents API router for web UI."""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel

from app.config import get_settings
from app.db import get_database
from app.models import (
    IncidentCreate,
    StoredIncident,
    IncidentStatus,
    IncidentListItem,
    IncidentListResponse,
    PIRResponse,
    TriageResult,
    Severity,
    Environment,
    IncidentType,
    NormalizedIncident,
)
from app.services.llm_client import get_llm_client, MockProvider
from app.services.policy import get_policy_engine
from app.services.risk import calculate_risk_score
from app.services.runbook_matcher import match_runbooks, list_all_runbooks
from app.services.pir import generate_pir
from app.services.audit import get_audit_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["incidents"])

# Demo token for AI triage access
DEMO_TOKEN = "incident-autopilot-demo-2024"


# Request models for new endpoints
class OverrideRequest(BaseModel):
    severity: Optional[str] = None
    category: Optional[str] = None
    reason: str


class ResolveRequest(BaseModel):
    resolution_note: str


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


def _get_incident_row(incident_id: str) -> dict:
    """Get raw incident row from database."""
    db = get_database()
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM web_incidents WHERE id = ?", (incident_id,))
        row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")
    return dict(row)


def _update_incident(incident_id: str, **kwargs):
    """Update incident fields in database."""
    db = get_database()
    kwargs["updated_at"] = datetime.utcnow().isoformat()

    set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [incident_id]

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE web_incidents SET {set_clause} WHERE id = ?",
            values
        )


async def _run_triage(incident_id: str, title: str, description: str,
                      component: str, environment: Environment) -> TriageResult:
    """Run AI triage on an incident."""
    # Create normalized incident for triage
    normalized = NormalizedIncident(
        jira_key=incident_id,
        summary=title,
        description=description,
        component=component,
        environment=environment,
        reporter="web-user",
        labels=[],
        created_at=datetime.utcnow(),
        raw_payload={},
    )

    # Use mock provider for demo safety
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
        environment=environment,
    )

    # Match runbooks
    primary_runbook, alternative_runbooks = match_runbooks(
        incident_type=llm_result.incident_type,
        title=title,
        description=description,
    )

    # Build triage result
    return TriageResult(
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


# ============================================
# CRUD Endpoints
# ============================================

@router.post("/incidents", response_model=StoredIncident)
async def create_incident(incident: IncidentCreate):
    """Create a new incident (without triage - call /triage separately)."""
    db = get_database()

    incident_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow()

    # Log creation
    get_audit_service().log(
        event_type="incident_created",
        jira_key=incident_id,
        component=incident.component,
        action="create_incident",
        status="success",
        details={"title": incident.title, "source": "web_form"},
    )

    # Store incident (no triage yet)
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO web_incidents
            (id, title, description, component, environment, reporter, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident_id,
                incident.title,
                incident.description,
                incident.component,
                incident.environment.value,
                incident.reporter,
                IncidentStatus.PENDING.value,
                now.isoformat(),
                now.isoformat(),
            ),
        )

    return StoredIncident(
        id=incident_id,
        title=incident.title,
        description=incident.description,
        component=incident.component,
        environment=incident.environment,
        reporter=incident.reporter,
        status=IncidentStatus.PENDING,
        created_at=now,
        updated_at=now,
        triage=None,
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

        query = "SELECT * FROM web_incidents"
        params = []

        if status:
            query += " WHERE status = ?"
            params.append(status.value)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = [dict(row) for row in cursor.fetchall()]

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
    row = _get_incident_row(incident_id)
    return _row_to_incident(row)


# ============================================
# Action Endpoints (matching new frontend)
# ============================================

@router.post("/incidents/{incident_id}/triage", response_model=StoredIncident)
async def triage_incident(incident_id: str):
    """Run AI triage on an incident."""
    row = _get_incident_row(incident_id)
    incident = _row_to_incident(row)

    try:
        triage = await _run_triage(
            incident_id=incident_id,
            title=incident.title,
            description=incident.description,
            component=incident.component,
            environment=incident.environment,
        )

        _update_incident(
            incident_id,
            status=IncidentStatus.TRIAGED.value,
            triage_json=triage.model_dump_json(),
        )

        get_audit_service().log(
            event_type="incident_triaged",
            jira_key=incident_id,
            component=incident.component,
            severity=triage.severity.value,
            action="ai_triage",
            status="success",
            details={
                "incident_type": triage.incident_type.value,
                "confidence": triage.confidence,
                "risk_score": triage.risk_score,
                "needs_human_review": triage.needs_human_review,
            },
        )

    except Exception as e:
        logger.error(f"Triage failed for {incident_id}: {e}")
        get_audit_service().log(
            event_type="incident_triage_failed",
            jira_key=incident_id,
            component=incident.component,
            action="ai_triage",
            status="failure",
            details={"error": str(e)},
        )
        raise HTTPException(status_code=500, detail=f"Triage failed: {e}")

    return await get_incident(incident_id)


@router.post("/incidents/{incident_id}/approve", response_model=StoredIncident)
async def approve_incident(incident_id: str):
    """Approve the AI triage for an incident."""
    row = _get_incident_row(incident_id)
    incident = _row_to_incident(row)

    if not incident.triage:
        raise HTTPException(status_code=400, detail="Incident has not been triaged yet")

    now = datetime.utcnow()
    _update_incident(
        incident_id,
        status=IncidentStatus.APPROVED.value,
        decision_by="web-user",
        decision_at=now.isoformat(),
        decision_note="Approved via web UI",
    )

    get_audit_service().log(
        event_type="incident_approved",
        jira_key=incident_id,
        component=incident.component,
        severity=incident.triage.severity.value,
        action="approve",
        status="success",
        details={},
    )

    return await get_incident(incident_id)


@router.post("/incidents/{incident_id}/override", response_model=StoredIncident)
async def override_incident(incident_id: str, req: OverrideRequest):
    """Override severity and/or category for an incident."""
    row = _get_incident_row(incident_id)
    incident = _row_to_incident(row)

    if not incident.triage:
        raise HTTPException(status_code=400, detail="Incident has not been triaged yet")

    # Update triage with overrides
    triage_data = json.loads(row["triage_json"])
    original_severity = triage_data.get("severity")
    original_category = triage_data.get("incident_type")

    if req.severity:
        try:
            new_sev = Severity(req.severity.upper())
            triage_data["severity"] = new_sev.value
            # Recalculate risk score
            triage_data["risk_score"] = calculate_risk_score(
                severity=new_sev,
                confidence=triage_data.get("confidence", 0.5),
                environment=incident.environment,
            )
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {req.severity}")

    if req.category:
        try:
            new_cat = IncidentType(req.category.lower())
            triage_data["incident_type"] = new_cat.value
            # Re-match runbooks
            primary, alts = match_runbooks(new_cat, incident.title, incident.description)
            triage_data["primary_runbook"] = primary.model_dump()
            triage_data["alternative_runbooks"] = [a.model_dump() for a in alts]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid category: {req.category}")

    now = datetime.utcnow()
    _update_incident(
        incident_id,
        status=IncidentStatus.OVERRIDDEN.value,
        triage_json=json.dumps(triage_data),
        decision_by="web-user",
        decision_at=now.isoformat(),
        decision_note=req.reason,
        original_severity=original_severity,
    )

    get_audit_service().log(
        event_type="incident_overridden",
        jira_key=incident_id,
        component=incident.component,
        severity=triage_data.get("severity"),
        action="override",
        status="success",
        details={
            "reason": req.reason,
            "original_severity": original_severity,
            "new_severity": req.severity,
            "original_category": original_category,
            "new_category": req.category,
        },
    )

    return await get_incident(incident_id)


@router.post("/incidents/{incident_id}/resolve", response_model=StoredIncident)
async def resolve_incident(incident_id: str, req: ResolveRequest):
    """Mark an incident as resolved."""
    row = _get_incident_row(incident_id)
    incident = _row_to_incident(row)

    now = datetime.utcnow()
    _update_incident(
        incident_id,
        status=IncidentStatus.RESOLVED.value,
        decision_by="web-user",
        decision_at=now.isoformat(),
        decision_note=req.resolution_note,
    )

    get_audit_service().log(
        event_type="incident_resolved",
        jira_key=incident_id,
        component=incident.component,
        severity=incident.triage.severity.value if incident.triage else None,
        action="resolve",
        status="success",
        details={"resolution_note": req.resolution_note},
    )

    return await get_incident(incident_id)


@router.post("/incidents/{incident_id}/pir", response_model=PIRResponse)
async def generate_pir_endpoint(incident_id: str):
    """Generate Post-Incident Review for an incident."""
    incident = await get_incident(incident_id)
    audit_data = await get_audit_trail(incident_id)

    markdown = generate_pir(incident, audit_data["events"])

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

    for row in rows:
        if row.get("details"):
            try:
                row["details"] = json.loads(row["details"])
            except:
                pass

    return {"incident_id": incident_id, "events": rows}


@router.get("/runbooks")
async def get_runbooks():
    """List all available runbooks."""
    return {"runbooks": list_all_runbooks()}
