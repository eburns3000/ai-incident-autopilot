"""Jira webhook endpoint for incident processing."""

import logging
from fastapi import APIRouter, Request, HTTPException, Depends, status

from app.config import get_settings
from app.models import WebhookResponse, TriageOutput
from app.middleware import (
    verify_webhook_secret,
    get_rate_limiter,
)
from app.middleware.auth import get_client_ip
from app.services import (
    normalize_jira_webhook,
    get_audit_service,
    get_correlator_service,
    get_llm_client,
    get_policy_engine,
    get_jira_client,
    get_slack_client,
)
from app.routers.metrics import increment_metric

router = APIRouter(prefix="/webhook", tags=["webhook"])
logger = logging.getLogger(__name__)


@router.post("/jira", response_model=WebhookResponse)
async def handle_jira_webhook(
    request: Request,
    _auth: bool = Depends(verify_webhook_secret),
) -> WebhookResponse:
    """
    Handle Jira webhook for incident creation/update.

    Processes only Incident issue types.
    """
    settings = get_settings()
    audit = get_audit_service()

    # Rate limiting
    rate_limiter = get_rate_limiter()
    client_ip = get_client_ip(request)
    allowed, remaining, reset = rate_limiter.is_allowed(client_ip)

    if not allowed:
        increment_metric("webhooks_rejected")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(reset),
            },
        )

    increment_metric("webhooks_received")

    try:
        # Parse payload
        payload = await request.json()

        # Normalize the webhook payload
        incident = normalize_jira_webhook(payload)

        if incident is None:
            # Not an incident issue type
            return WebhookResponse(
                status="skipped",
                message="Not an Incident issue type",
                dry_run=settings.dry_run,
            )

        jira_key = incident.jira_key
        logger.info(f"Processing incident: {jira_key}")

        # Audit: webhook received
        audit.log_webhook_received(
            jira_key=jira_key,
            details={
                "event_type": payload.get("webhookEvent", "unknown"),
                "component": incident.component,
                "environment": incident.environment.value,
            },
        )

        # Audit: normalization
        audit.log_normalization(
            jira_key=jira_key,
            component=incident.component,
            environment=incident.environment.value,
        )

        # Check correlation
        correlator = get_correlator_service()
        is_correlated, correlated_key = correlator.check_correlation(incident)

        if is_correlated:
            increment_metric("incidents_correlated")

        audit.log_correlation(jira_key, correlated_key, incident.component)

        # Record incident for future correlation
        correlator.record_incident(incident)

        # LLM Triage
        increment_metric("llm_calls")
        try:
            llm_client = get_llm_client()
            llm_result = await llm_client.triage(incident)

            audit.log_llm_triage(
                jira_key=jira_key,
                incident_type=llm_result.incident_type.value,
                severity=llm_result.severity.value,
                confidence=llm_result.confidence,
            )
        except Exception as e:
            increment_metric("llm_errors")
            audit.log_llm_triage(
                jira_key=jira_key,
                incident_type="unknown",
                severity="unknown",
                confidence=0.0,
                status="failure",
                error=str(e),
            )
            logger.error(f"LLM triage failed for {jira_key}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"LLM triage failed: {str(e)}",
            )

        # Apply policy guardrails
        policy_engine = get_policy_engine()
        policy_result = policy_engine.apply_policies(incident, llm_result)

        if policy_result.severity_overridden:
            increment_metric("policy_overrides")
            audit.log_policy_override(
                jira_key=jira_key,
                original_severity=policy_result.original_severity.value,
                final_severity=policy_result.final_severity.value,
                reason=policy_result.override_reason or "Unknown",
            )

        if policy_result.needs_human_review:
            increment_metric("human_review_required")
            audit.log_human_review_required(
                jira_key=jira_key,
                confidence=policy_result.confidence,
            )

        # Build complete triage output
        triage_output = TriageOutput(
            incident=incident,
            llm_result=llm_result,
            policy_result=policy_result,
            correlated=is_correlated,
            correlated_with=correlated_key,
        )

        # Update Jira
        jira_client = get_jira_client()
        try:
            if settings.dry_run:
                audit.log_dry_run_action(
                    jira_key=jira_key,
                    action="update_jira",
                    target="issue",
                    details={
                        "priority": policy_result.final_severity.value,
                        "labels": policy_result.labels_to_add,
                    },
                )
            else:
                await jira_client.update_issue(triage_output)
                increment_metric("jira_updates")
                audit.log_jira_update(jira_key, action="updated_fields_and_comment")

        except Exception as e:
            increment_metric("jira_errors")
            audit.log_jira_update(
                jira_key, action="update", status="failure", error=str(e)
            )
            logger.error(f"Jira update failed for {jira_key}: {e}")
            # Continue to Slack notification even if Jira fails

        # Post Slack notification
        slack_client = get_slack_client()
        try:
            if settings.dry_run:
                audit.log_dry_run_action(
                    jira_key=jira_key,
                    action="post_slack",
                    target=settings.slack_channel,
                    details={
                        "severity": policy_result.final_severity.value,
                        "summary": llm_result.short_summary,
                    },
                )
            else:
                await slack_client.post_incident_notification(triage_output)
                increment_metric("slack_posts")
                audit.log_slack_post(jira_key, channel=settings.slack_channel)

        except Exception as e:
            increment_metric("slack_errors")
            audit.log_slack_post(
                jira_key,
                channel=settings.slack_channel,
                status="failure",
                error=str(e),
            )
            logger.error(f"Slack notification failed for {jira_key}: {e}")

        increment_metric("webhooks_processed")
        increment_metric("incidents_triaged")

        return WebhookResponse(
            status="processed",
            jira_key=jira_key,
            message=(
                f"Incident triaged as {policy_result.final_severity.value} "
                f"({llm_result.incident_type.value})"
            ),
            dry_run=settings.dry_run,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Webhook processing error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
