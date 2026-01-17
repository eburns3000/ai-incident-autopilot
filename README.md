Incident Autopilot

Incident Autopilot is an AI assisted incident triage and governance demo designed to show how AI can support better decision making under pressure without removing human accountability.

The project models how modern internal incident tools should work. AI proposes. Humans decide. Everything is auditable.

What this project demonstrates

AI assisted incident triage with severity risk and confidence scoring
Human in the loop governance with approve override and resolve actions
Clear P1 through P4 severity signaling
Explicit incident status lifecycle
Full audit trail of every decision
Post incident review generation
Production style internal tooling user interface

This is not a chatbot or automation demo. It is a decision support system.

Core features
Incident Management

Create and view incidents in a dashboard style interface.
Each incident includes severity P1 through P4 current status and timestamped history.

AI Triage

AI performs initial triage on an incident and outputs suggested severity risk assessment and confidence level.
AI output is advisory only and cannot take final action.

Human in the Loop Controls

Users can approve AI recommendations override AI decisions or manually resolve incidents.
All actions require explicit user intent.

Audit Trail

Every action is logged including AI triage events human approvals overrides and resolutions.
The audit log is immutable and visible in the interface.

Post Incident Review

After an incident is resolved a post incident review can be generated.
The review summarizes incident context AI recommendations human decisions and final outcome.
This supports learning and continuous improvement.

Production Style User Interface

Clean internal tool layout with clear visual hierarchy for severity status and actions.
Purposefully minimal and optimized for clarity rather than aesthetics.
Designed to resemble real world SRE and incident response tooling.

Why this project exists

Many AI demos focus on automation.
Real organizations require trust governance and accountability.

This project explores how AI can reduce cognitive load during incidents improve consistency of initial triage preserve human ownership of decisions and maintain a clear audit trail for compliance and review.

Running locally

git clone https://github.com/eburns3000/ai-incident-autopilot.git

cd ai-incident-autopilot
Follow setup steps in the repository.

The application runs locally at http://localhost:8080

This project is intended to be run locally. A public deployment is not required for evaluation.

Intended audience

Hiring managers
Technical project managers
SRE and operations leaders
AI governance and risk teams

The project is designed to be reviewed through code screenshots and documentation rather than a public live demo.

Status

Complete. This version represents a finished end to end artifact.

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
