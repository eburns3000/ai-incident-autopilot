// API base URL
const API_BASE = '/api';

// Current incident ID for detail view
let currentIncidentId = null;
let currentPIRMarkdown = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadIncidents();
    setupDecisionFormListeners();
});

// View management
function showView(viewName) {
    // Hide all views
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));

    // Show requested view
    document.getElementById(`${viewName}-view`).classList.add('active');
    const navLink = document.querySelector(`.nav-link[data-view="${viewName}"]`);
    if (navLink) navLink.classList.add('active');

    // Load data if needed
    if (viewName === 'home') {
        loadIncidents();
    }
}

// Load incidents list
async function loadIncidents() {
    const listEl = document.getElementById('incidents-list');
    listEl.innerHTML = '<p class="loading">Loading incidents...</p>';

    try {
        const response = await fetch(`${API_BASE}/incidents?limit=50`);
        if (!response.ok) throw new Error('Failed to load incidents');

        const data = await response.json();

        if (data.incidents.length === 0) {
            listEl.innerHTML = `
                <div class="empty-state">
                    <p>No incidents yet.</p>
                    <p>Click "New Incident" to submit one.</p>
                </div>
            `;
            return;
        }

        listEl.innerHTML = data.incidents.map(incident => `
            <div class="incident-item" onclick="showIncidentDetail('${incident.id}')">
                <div class="incident-severity ${getSeverityClass(incident.severity)}">
                    ${incident.severity || '?'}
                </div>
                <div class="incident-info">
                    <div class="incident-title">${escapeHtml(incident.title)}</div>
                    <div class="incident-meta">
                        <span>${incident.component}</span>
                        <span>${incident.environment}</span>
                        <span>${formatDate(incident.created_at)}</span>
                        ${incident.risk_score !== null ? `<span>Risk: ${(incident.risk_score * 100).toFixed(0)}%</span>` : ''}
                    </div>
                </div>
                <span class="incident-status status-${incident.status}">${incident.status}</span>
                ${incident.needs_human_review ? '<span class="review-badge">Needs Review</span>' : ''}
            </div>
        `).join('');

    } catch (error) {
        listEl.innerHTML = `<div class="empty-state"><p>Error: ${error.message}</p></div>`;
    }
}

// Submit new incident
async function submitIncident(event) {
    event.preventDefault();

    const form = event.target;
    const submitBtn = document.getElementById('submit-btn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Processing...';

    const data = {
        title: form.title.value,
        description: form.description.value,
        component: form.component.value || 'unknown',
        environment: form.environment.value,
        reporter: form.reporter.value || 'web-user'
    };

    try {
        const response = await fetch(`${API_BASE}/incidents`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                // Include demo token for AI triage
                'X-Demo-Token': 'incident-autopilot-demo-2024'
            },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to create incident');
        }

        const incident = await response.json();

        // Reset form
        form.reset();

        // Show the new incident
        showIncidentDetail(incident.id);

    } catch (error) {
        alert(`Error: ${error.message}`);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Submit & Run AI Triage';
    }
}

// Show incident detail
async function showIncidentDetail(incidentId) {
    currentIncidentId = incidentId;
    showView('detail');

    const detailEl = document.getElementById('incident-detail');
    detailEl.innerHTML = '<p class="loading">Loading incident...</p>';

    try {
        // Load incident and audit trail in parallel
        const [incidentRes, auditRes] = await Promise.all([
            fetch(`${API_BASE}/incidents/${incidentId}`),
            fetch(`${API_BASE}/incidents/${incidentId}/audit`)
        ]);

        if (!incidentRes.ok) throw new Error('Incident not found');

        const incident = await incidentRes.json();
        const auditData = await auditRes.json();

        document.getElementById('detail-title').textContent = incident.title;

        detailEl.innerHTML = renderIncidentDetail(incident, auditData.events);

    } catch (error) {
        detailEl.innerHTML = `<div class="empty-state"><p>Error: ${error.message}</p></div>`;
    }
}

// Render incident detail HTML
function renderIncidentDetail(incident, auditEvents) {
    const triage = incident.triage;

    let triageHtml = '<p>Triage not completed.</p>';
    if (triage) {
        triageHtml = `
            <div class="detail-grid">
                <div class="detail-item">
                    <label>Severity</label>
                    <div class="value">
                        <span class="incident-severity ${getSeverityClass(triage.severity)}" style="width: 32px; height: 32px; font-size: 12px; display: inline-flex;">
                            ${triage.severity}
                        </span>
                    </div>
                </div>
                <div class="detail-item">
                    <label>Incident Type</label>
                    <div class="value">${triage.incident_type}</div>
                </div>
                <div class="detail-item">
                    <label>Confidence</label>
                    <div class="value">${(triage.confidence * 100).toFixed(0)}%</div>
                </div>
                <div class="detail-item">
                    <label>Risk Score</label>
                    <div class="risk-score">
                        <span>${(triage.risk_score * 100).toFixed(0)}%</span>
                        <div class="risk-bar">
                            <div class="risk-fill ${getRiskClass(triage.risk_score)}" style="width: ${triage.risk_score * 100}%"></div>
                        </div>
                    </div>
                </div>
                <div class="detail-item">
                    <label>Owner Team</label>
                    <div class="value">${triage.owner_team}</div>
                </div>
                <div class="detail-item">
                    <label>Needs Human Review</label>
                    <div class="value">${triage.needs_human_review ? '<span class="review-badge">Yes</span>' : 'No'}</div>
                </div>
            </div>
            <div style="margin-top: 16px;">
                <label style="font-size: 12px; color: var(--color-text-light); text-transform: uppercase;">Summary</label>
                <p style="margin-top: 4px;">${escapeHtml(triage.short_summary)}</p>
            </div>
            ${triage.policy_override_reason ? `
                <div style="margin-top: 12px; padding: 8px 12px; background: #fef3c7; border-radius: 4px; font-size: 13px;">
                    <strong>Policy Override:</strong> ${escapeHtml(triage.policy_override_reason)}
                </div>
            ` : ''}
        `;
    }

    let actionsHtml = '<p>No actions defined.</p>';
    if (triage && triage.first_actions && triage.first_actions.length > 0) {
        actionsHtml = `
            <ul class="actions-list">
                ${triage.first_actions.map(a => `<li>${escapeHtml(a)}</li>`).join('')}
            </ul>
        `;
    }

    let runbookHtml = '<p>No runbook assigned.</p>';
    if (triage && triage.primary_runbook) {
        const rb = triage.primary_runbook;
        runbookHtml = `
            <div class="runbook-card primary">
                <div class="runbook-header">
                    <span class="runbook-name">${escapeHtml(rb.runbook_name)}</span>
                    <span class="runbook-score">Fit: ${(rb.fit_score * 100).toFixed(0)}%</span>
                </div>
                ${rb.runbook_url ? `<p style="font-size: 13px; margin-bottom: 8px;"><a href="${rb.runbook_url}" target="_blank">${rb.runbook_url}</a></p>` : ''}
                ${rb.steps && rb.steps.length > 0 ? `
                    <ol class="runbook-steps">
                        ${rb.steps.map(s => `<li>${escapeHtml(s)}</li>`).join('')}
                    </ol>
                ` : ''}
            </div>
            ${triage.alternative_runbooks && triage.alternative_runbooks.length > 0 ? `
                <h4 style="font-size: 14px; margin: 16px 0 8px; color: var(--color-text-light);">Alternative Runbooks</h4>
                ${triage.alternative_runbooks.map(alt => `
                    <div class="runbook-card">
                        <div class="runbook-header">
                            <span class="runbook-name">${escapeHtml(alt.runbook_name)}</span>
                            <span class="runbook-score">Fit: ${(alt.fit_score * 100).toFixed(0)}%</span>
                        </div>
                    </div>
                `).join('')}
            ` : ''}
        `;
    }

    let auditHtml = '<p>No events recorded.</p>';
    if (auditEvents && auditEvents.length > 0) {
        auditHtml = `
            <div class="audit-timeline">
                ${auditEvents.map(e => `
                    <div class="audit-event ${e.status}">
                        <div class="audit-time">${formatDate(e.timestamp)}</div>
                        <div class="audit-action">${escapeHtml(e.action)}</div>
                        <div class="audit-details">${e.event_type} - ${e.status}</div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    const canMakeDecision = incident.status === 'triaged' ||
                            (incident.status === 'pending' && incident.triage);

    let decisionHtml = '';
    if (incident.decision_by) {
        decisionHtml = `
            <p><strong>Decision:</strong> ${incident.status.toUpperCase()}</p>
            <p><strong>By:</strong> ${escapeHtml(incident.decision_by)}</p>
            ${incident.decision_at ? `<p><strong>At:</strong> ${formatDate(incident.decision_at)}</p>` : ''}
            ${incident.decision_note ? `<p><strong>Note:</strong> ${escapeHtml(incident.decision_note)}</p>` : ''}
            ${incident.original_severity ? `<p><strong>Original Severity:</strong> ${incident.original_severity}</p>` : ''}
        `;
    } else if (canMakeDecision) {
        decisionHtml = `
            <p>This incident requires a decision.</p>
            <div class="decision-gate">
                <button onclick="openDecisionModal('${incident.id}')" class="btn btn-primary">Make Decision</button>
            </div>
        `;
    } else {
        decisionHtml = '<p>Waiting for triage to complete.</p>';
    }

    return `
        <div class="detail-card">
            <h3>Incident Information</h3>
            <div class="detail-grid">
                <div class="detail-item">
                    <label>ID</label>
                    <div class="value">${incident.id}</div>
                </div>
                <div class="detail-item">
                    <label>Status</label>
                    <div class="value"><span class="incident-status status-${incident.status}">${incident.status}</span></div>
                </div>
                <div class="detail-item">
                    <label>Component</label>
                    <div class="value">${incident.component}</div>
                </div>
                <div class="detail-item">
                    <label>Environment</label>
                    <div class="value">${incident.environment}</div>
                </div>
                <div class="detail-item">
                    <label>Reporter</label>
                    <div class="value">${incident.reporter}</div>
                </div>
                <div class="detail-item">
                    <label>Created</label>
                    <div class="value">${formatDate(incident.created_at)}</div>
                </div>
            </div>
            <div style="margin-top: 16px;">
                <label style="font-size: 12px; color: var(--color-text-light); text-transform: uppercase;">Description</label>
                <p style="margin-top: 4px; white-space: pre-wrap;">${escapeHtml(incident.description)}</p>
            </div>
        </div>

        <div class="detail-card">
            <h3>AI Triage Results</h3>
            ${triageHtml}
        </div>

        <div class="detail-card">
            <h3>Recommended Actions</h3>
            ${actionsHtml}
        </div>

        <div class="detail-card">
            <h3>Runbook Assignment</h3>
            ${runbookHtml}
        </div>

        <div class="detail-card">
            <h3>Decision Gate</h3>
            ${decisionHtml}
        </div>

        <div class="detail-card">
            <h3>Audit Trail</h3>
            ${auditHtml}
        </div>

        <div class="detail-card">
            <h3>Post-Incident Review</h3>
            <p>Generate a comprehensive PIR document from this incident's data and audit trail.</p>
            <button onclick="showPIR('${incident.id}')" class="btn btn-primary" style="margin-top: 12px;">
                Generate PIR
            </button>
        </div>
    `;
}

// Decision modal
function openDecisionModal(incidentId) {
    document.getElementById('decision-incident-id').value = incidentId;
    document.getElementById('decision-form').reset();
    document.getElementById('severity-override-group').style.display = 'none';
    document.getElementById('decision-modal').classList.add('active');
}

function closeModal() {
    document.getElementById('decision-modal').classList.remove('active');
}

function setupDecisionFormListeners() {
    const radios = document.querySelectorAll('input[name="action"]');
    radios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            const overrideGroup = document.getElementById('severity-override-group');
            overrideGroup.style.display = e.target.value === 'override' ? 'block' : 'none';
        });
    });
}

async function submitDecision(event) {
    event.preventDefault();

    const form = event.target;
    const incidentId = document.getElementById('decision-incident-id').value;

    const data = {
        action: form.action.value,
        note: form.note.value || null,
        decided_by: form.decided_by.value || 'anonymous'
    };

    if (data.action === 'override') {
        data.new_severity = form.new_severity.value;
    }

    try {
        const response = await fetch(`${API_BASE}/incidents/${incidentId}/decision`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to submit decision');
        }

        closeModal();
        showIncidentDetail(incidentId);

    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

// PIR
async function showPIR(incidentId) {
    currentIncidentId = incidentId;
    showView('pir');

    const pirEl = document.getElementById('pir-content');
    pirEl.innerHTML = '<p class="loading">Generating PIR...</p>';

    try {
        const response = await fetch(`${API_BASE}/incidents/${incidentId}/pir`);
        if (!response.ok) throw new Error('Failed to generate PIR');

        const data = await response.json();
        currentPIRMarkdown = data.markdown;

        pirEl.textContent = data.markdown;

    } catch (error) {
        pirEl.innerHTML = `<p>Error: ${error.message}</p>`;
    }
}

function downloadPIR() {
    if (!currentPIRMarkdown) return;

    const blob = new Blob([currentPIRMarkdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `PIR-${currentIncidentId}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Utility functions
function getSeverityClass(severity) {
    if (!severity) return 'severity-pending';
    return `severity-${severity.toLowerCase()}`;
}

function getRiskClass(score) {
    if (score >= 0.8) return 'risk-critical';
    if (score >= 0.6) return 'risk-high';
    if (score >= 0.4) return 'risk-medium';
    return 'risk-low';
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    try {
        const date = new Date(dateStr);
        return date.toLocaleString();
    } catch {
        return dateStr;
    }
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
