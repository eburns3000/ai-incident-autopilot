# Incident Autopilot (Public Demo, No Login)

AI-assisted incident triage + runbook routing with risk scoring, decision gates, audit trail, and PIR generation.

## What it does
- Submit an incident (no login)
- AI triage routes to a runbook category (deployment/database/network/application/security/infrastructure/unknown)
- Shows: severity, confidence, risk score, runbook fit, and top alternative categories
- Decision gate: flags when human review is required
- Persists incidents + triage + audit events (SQLite)
- Generates an editable Post-Incident Review (PIR) from the audit trail

## Live Demo
- App: **(paste your deployed URL here)**
- API Docs (Swagger): **(paste your deployed URL)/docs**

## How to run locally
```bash
cd incident-autopilot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000

