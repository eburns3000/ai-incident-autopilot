# Incident Autopilot – AI-Assisted IT Ops Triage System

## Overview
Incident Autopilot is a production-style IT operations automation system that ingests Jira incident webhooks, normalizes and correlates events, and performs AI-assisted triage to classify severity, ownership, and next actions.

The system is designed with safety, auditability, and extensibility in mind and runs fully containerized via Docker.

## Problem Statement
IT Ops teams often receive high volumes of incident tickets with inconsistent quality and urgency. Manual triage slows response times and increases the risk of misclassification, delayed escalation, and alert fatigue.

## Solution
This system automates first-pass incident triage by:
- Validating and ingesting Jira webhook events
- Normalizing ticket data into a standard incident schema
- Correlating related incidents to reduce noise
- Classifying incident type and severity using an AI abstraction layer
- Applying policy guardrails and confidence thresholds
- Safely integrating with downstream tools using DRY_RUN mode

## System Architecture
Event-driven pipeline:
1. Jira webhook ingestion with secret validation and rate limiting
2. Normalization of ticket payload into structured incident data
3. Correlation check against recent incidents
4. AI-assisted triage via pluggable LLM interface
5. Policy enforcement (severity, environment, confidence thresholds)
6. Safe execution layer (DRY_RUN) for Jira and Slack updates
7. Audit logging and metrics collection

## AI Design
The AI component is implemented as a replaceable provider interface.
For demonstration purposes, a mock LLM is used to produce deterministic, explainable triage results without external API dependencies.

This allows:
- Safe testing without vendor lock-in
- Predictable demo behavior
- Easy future swap to OpenAI or Anthropic

## Safety and Guardrails
- DRY_RUN mode prevents unintended production changes
- Confidence thresholds trigger human review
- Environment-aware severity enforcement
- Full audit logs for every decision

## Tech Stack
- Python (FastAPI)
- Docker & Docker Compose
- Mock LLM abstraction
- Structured logging & metrics
- REST webhooks (Jira-compatible)

## Demo
A sample Jira webhook payload is included and can be replayed locally to demonstrate the full incident lifecycle:
- Webhook ingestion
- AI triage
- Policy enforcement
- Logged downstream actions

## Status
Fully functional MVP running locally with Docker.
Ready for real API integrations when desired.
