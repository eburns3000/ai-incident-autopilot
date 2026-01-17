# Incident Autopilot

**AI-assisted incident triage and runbook routing for IT operations**  
_Public demo • No login • API-first_

Incident Autopilot is a lightweight incident-management application that demonstrates how AI can support (not replace) human decision-making during production incidents. The system emphasizes **risk awareness, human approval gates, auditability, and post-incident learning** rather than autonomous remediation.

---

## Live Demo (Local)

> This project currently runs locally. A public deployment link will be added next.

- **Application UI:** http://localhost:8080  
- **API / Swagger (OpenAPI):** http://localhost:8000/docs  

---

## What this project demonstrates

This project mirrors how **real internal incident tools** are designed and evaluated:

- AI-assisted classification with confidence scoring
- Deterministic risk scoring (not black-box AI)
- Explicit decision gates requiring human review
- Full audit trail of actions and decisions
- Automatic Post-Incident Review (PIR) generation

---

## Core features

- **Incident submission (no login required)**
- **AI-assisted triage**
  - Incident category (deployment, database, network, application, security, infrastructure, unknown)
  - Severity and confidence score
  - Deterministic risk score with risk level
  - Runbook match with fit score
  - Alternative category suggestions
- **Decision gate**
  - Flags when human review is required
  - Supports manual override with justification
- **Audit trail**
  - Every action is logged (triage, override, resolution, PIR generation)
- **Post-Incident Review (PIR)**
  - Automatically generated in editable Markdown
- **Demo-safe AI usage**
  - Dry-run / mock mode by default
  - Optional demo token gate for real AI calls

---

## How the system works

1. An incident is created via the UI or API  
2. AI triage analyzes the incident and returns:
   - Category, severity, confidence
   - Risk score
   - Runbook recommendation
   - Decision-gate outcome
3. A human may approve, override, or escalate  
4. All actions are written to an audit trail  
5. When resolved, the system generates a **Post-Incident Review (PIR)**  
6. PIR is editable and exportable

This reflects real workflows used by SRE and platform teams.

---

## How to run locally

```bash
git clone <your-repo-url>
cd incident-autopilot

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start the backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
