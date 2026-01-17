const API_BASE = '/api';

let currentIncidentId = null;
let currentPIRMarkdown = null;

document.addEventListener('DOMContentLoaded', () => {
  // nav
  document.querySelectorAll('.nav-link').forEach(btn => {
    btn.addEventListener('click', () => showView(btn.dataset.view));
  });

  // dashboard
  document.getElementById('refresh-btn').addEventListener('click', loadIncidents);

  // new incident
  document.getElementById('new-incident-form').addEventListener('submit', onCreateIncident);
  document.getElementById('new-demo-btn').addEventListener('click', fillDemoIncident);

  // detail view
  document.getElementById('back-btn').addEventListener('click', () => showView('home'));
  document.getElementById('btn-triage').addEventListener('click', () => runTriage(currentIncidentId));
  document.getElementById('btn-approve').addEventListener('click', () => approveIncident(currentIncidentId));
  document.getElementById('btn-override').addEventListener('click', () => overrideIncidentPrompt(currentIncidentId));
  document.getElementById('btn-resolve').addEventListener('click', () => resolveIncidentPrompt(currentIncidentId));
  document.getElementById('btn-pir').addEventListener('click', () => generatePIR(currentIncidentId));
  document.getElementById('btn-copy-pir').addEventListener('click', copyPIR);
  document.getElementById('btn-download-pir').addEventListener('click', downloadPIR);

  // start
  loadIncidents();
});

/* -------------------------
   View + Rendering
-------------------------- */
function showView(viewName) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));

  document.getElementById(`${viewName}-view`).classList.add('active');
  const navBtn = document.querySelector(`.nav-link[data-view="${viewName}"]`);
  if (navBtn) navBtn.classList.add('active');

  if (viewName === 'home') loadIncidents();
}

function renderEmptyState(el) {
  el.innerHTML = `
    <div class="card stack">
      <h3>No incidents yet</h3>
      <p class="muted">Click <b>New Incident</b> to create one, then run triage.</p>
    </div>
  `;
}

function formatDate(isoOrTs) {
  if (!isoOrTs) return '';
  try {
    const d = new Date(isoOrTs);
    return d.toLocaleString();
  } catch {
    return String(isoOrTs);
  }
}

function escapeHtml(str) {
  return String(str ?? '').replace(/[&<>"']/g, s => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[s]));
}

function severityClass(sev) {
  const s = String(sev || '').toUpperCase();
  if (s === 'P1') return 'sev sev-p1';
  if (s === 'P2') return 'sev sev-p2';
  if (s === 'P3') return 'sev sev-p3';
  return 'sev sev-p4';
}

/* -------------------------
   Dashboard
-------------------------- */
async function loadIncidents() {
  const listEl = document.getElementById('incidents-list');
  listEl.innerHTML = `<p class="muted">Loading…</p>`;

  const r = await fetch(`${API_BASE}/incidents?limit=50`);
  if (!r.ok) {
    listEl.innerHTML = `<p class="muted">Failed to load incidents: ${escapeHtml(await r.text())}</p>`;
    return;
  }
  const data = await r.json();
  const incidents = data.incidents || data || [];

  if (!incidents.length) return renderEmptyState(listEl);

  listEl.innerHTML = incidents.map(i => `
    <div class="card incident-row" onclick="openIncident('${i.id}')">
      <div class="row space-between">
        <div class="row gap">
          <span class="${severityClass(i.severity)}">${escapeHtml(i.severity || '—')}</span>
          <div>
            <div class="title">${escapeHtml(i.title || '(no title)')}</div>
            <div class="muted small">
              ${escapeHtml(i.component || '')}
              ${i.environment ? ' • ' + escapeHtml(i.environment) : ''}
              ${i.created_at ? ' • ' + escapeHtml(formatDate(i.created_at)) : ''}
              ${typeof i.risk_score === 'number' ? ' • Risk: ' + Math.round(i.risk_score*100) + '%' : ''}
            </div>
          </div>
        </div>
        <span class="pill">${escapeHtml(i.status || 'NEW')}</span>
      </div>

      <div class="row wrap gap actions" onclick="event.stopPropagation()">
        <button onclick="runTriage('${i.id}')">Triage</button>
        <button onclick="approveIncident('${i.id}')">Approve</button>
        <button onclick="overrideIncidentPrompt('${i.id}')">Override</button>
        <button onclick="resolveIncidentPrompt('${i.id}')">Resolve</button>
        <button onclick="generatePIR('${i.id}')">PIR</button>
      </div>
    </div>
  `).join('');
}

window.openIncident = openIncident;
async function openIncident(id) {
  currentIncidentId = id;
  currentPIRMarkdown = null;
  document.getElementById('pir-preview').textContent = 'No PIR generated yet.';
  document.getElementById('pir-preview').classList.add('muted');

  showView('detail');

  await Promise.all([
    loadIncidentDetail(id),
    loadAudit(id)
  ]);
}

async function loadIncidentDetail(id) {
  const r = await fetch(`${API_BASE}/incidents/${id}`);
  if (!r.ok) {
    document.getElementById('detail-title').textContent = 'Failed to load incident';
    document.getElementById('detail-meta').innerHTML = `<p class="muted">${escapeHtml(await r.text())}</p>`;
    return;
  }
  const i = await r.json();

  document.getElementById('detail-title').textContent = i.title || 'Incident';

  document.getElementById('detail-meta').innerHTML = `
    <div class="grid2">
      <div><div class="muted small">ID</div><div>${escapeHtml(i.id)}</div></div>
      <div><div class="muted small">Status</div><div><span class="pill">${escapeHtml(i.status || 'NEW')}</span></div></div>
      <div><div class="muted small">Component</div><div>${escapeHtml(i.component || '—')}</div></div>
      <div><div class="muted small">Environment</div><div>${escapeHtml(i.environment || '—')}</div></div>
      <div><div class="muted small">Reporter</div><div>${escapeHtml(i.reporter || '—')}</div></div>
      <div><div class="muted small">Created</div><div>${escapeHtml(formatDate(i.created_at))}</div></div>
    </div>
    <div>
      <div class="muted small">Description</div>
      <div>${escapeHtml(i.description || '')}</div>
    </div>
  `;

  renderTriage(i.triage);
}

function renderTriage(t) {
  const triageEl = document.getElementById('triage-results');
  const actionsEl = document.getElementById('recommended-actions');

  if (!t) {
    triageEl.textContent = 'No triage yet.';
    triageEl.classList.add('muted');
    actionsEl.textContent = 'Run triage to see actions.';
    actionsEl.classList.add('muted');
    return;
  }

  const riskPct = (typeof t.risk_score === 'number') ? Math.round(t.risk_score * 100) : null;

  triageEl.classList.remove('muted');
  triageEl.innerHTML = `
    <div class="grid2">
      <div><div class="muted small">Severity</div><div><span class="${severityClass(t.severity)}">${escapeHtml(t.severity || '—')}</span></div></div>
      <div><div class="muted small">Incident Type</div><div>${escapeHtml(t.category || t.incident_type || '—')}</div></div>
      <div><div class="muted small">Confidence</div><div>${escapeHtml(t.confidence != null ? Math.round(t.confidence*100)+'%' : '—')}</div></div>
      <div><div class="muted small">Risk Score</div><div>${riskPct != null ? riskPct+'%' : '—'}</div></div>
      <div><div class="muted small">Owner Team</div><div>${escapeHtml(t.owner_team || '—')}</div></div>
      <div><div class="muted small">Needs Human Review</div><div>${escapeHtml(String(!!t.needs_human_review).toUpperCase())}</div></div>
    </div>
    <div>
      <div class="muted small">Summary</div>
      <div>${escapeHtml(t.summary || '')}</div>
    </div>
  `;

  const steps = (t.runbook && Array.isArray(t.runbook.steps)) ? t.runbook.steps : (t.recommended_steps || []);
  if (!steps.length) {
    actionsEl.textContent = 'No recommended steps returned.';
    actionsEl.classList.add('muted');
    return;
  }
  actionsEl.classList.remove('muted');
  actionsEl.innerHTML = `
    <ol>
      ${steps.map(s => `<li>${escapeHtml(s)}</li>`).join('')}
    </ol>
  `;
}

/* -------------------------
   New Incident
-------------------------- */
function fillDemoIncident() {
  document.getElementById('new-title').value = 'Production API returning 500 errors';
  document.getElementById('new-description').value = 'Checkout API is returning 500 errors for ~30% of requests. Started ~10 minutes after a deployment.';
  document.getElementById('new-component').value = 'checkout-api';
  document.getElementById('new-environment').value = 'prod';
  document.getElementById('new-reporter').value = 'test-user';
}

async function onCreateIncident(e) {
  e.preventDefault();

  const payload = {
    title: document.getElementById('new-title').value.trim(),
    description: document.getElementById('new-description').value.trim(),
    component: document.getElementById('new-component').value.trim(),
    environment: document.getElementById('new-environment').value,
    reporter: document.getElementById('new-reporter').value.trim() || 'anonymous'
  };

  const r = await fetch(`${API_BASE}/incidents`, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(payload)
  });

  if (!r.ok) return alert(await r.text());
  const created = await r.json();
  await openIncident(created.id || created.incident_id || created.key);
}

/* -------------------------
   Actions (Buttons)
-------------------------- */
window.runTriage = runTriage;
async function runTriage(id) {
  if (!id) return;
  const r = await fetch(`${API_BASE}/incidents/${id}/triage`, { method: 'POST' });
  if (!r.ok) return alert(await r.text());
  await openIncident(id);
}

window.approveIncident = approveIncident;
async function approveIncident(id) {
  if (!id) return;
  const r = await fetch(`${API_BASE}/incidents/${id}/approve`, { method: 'POST' });
  if (!r.ok) return alert(await r.text());
  await openIncident(id);
}

window.resolveIncidentPrompt = resolveIncidentPrompt;
async function resolveIncidentPrompt(id) {
  if (!id) return;
  const note = prompt('Resolution notes (required):');
  if (!note) return;

  const r = await fetch(`${API_BASE}/incidents/${id}/resolve`, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ resolution_note: note })
  });
  if (!r.ok) return alert(await r.text());
  await openIncident(id);
}

window.overrideIncidentPrompt = overrideIncidentPrompt;
async function overrideIncidentPrompt(id) {
  if (!id) return;
  const severity = prompt('Override severity (P1/P2/P3/P4) — optional:') || null;
  const category = prompt('Override category (deployment/database/network/application/security/infrastructure/unknown) — optional:') || null;
  const reason = prompt('Reason for override (required):');
  if (!reason) return;

  const r = await fetch(`${API_BASE}/incidents/${id}/override`, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ severity, category, reason })
  });
  if (!r.ok) return alert(await r.text());
  await openIncident(id);
}

window.generatePIR = generatePIR;
async function generatePIR(id) {
  if (!id) return;
  const r = await fetch(`${API_BASE}/incidents/${id}/pir`, { method: 'POST' });
  if (!r.ok) return alert(await r.text());
  const data = await r.json();

  currentPIRMarkdown = data.pir_markdown || data.markdown || data.pir || null;
  if (!currentPIRMarkdown) {
    alert('PIR generated, but no markdown returned by API. Check backend response.');
    return;
  }

  const pre = document.getElementById('pir-preview');
  pre.classList.remove('muted');
  pre.textContent = currentPIRMarkdown;

  await loadAudit(id);
}

/* -------------------------
   PIR helpers
-------------------------- */
function copyPIR() {
  if (!currentPIRMarkdown) return alert('No PIR to copy yet. Click "Generate PIR".');
  navigator.clipboard.writeText(currentPIRMarkdown).then(
    () => alert('PIR copied to clipboard.'),
    () => alert('Clipboard copy failed (browser permission).')
  );
}

function downloadPIR() {
  if (!currentPIRMarkdown) return alert('No PIR to download yet. Click "Generate PIR".');
  const blob = new Blob([currentPIRMarkdown], { type: 'text/markdown' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `pir-${currentIncidentId || 'incident'}.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/* -------------------------
   Audit Trail
-------------------------- */
async function loadAudit(id) {
  const el = document.getElementById('audit-timeline');
  el.textContent = 'Loading…';
  el.classList.add('muted');

  const r = await fetch(`${API_BASE}/incidents/${id}/audit`);
  if (!r.ok) {
    el.textContent = `Failed to load audit: ${await r.text()}`;
    return;
  }
  const data = await r.json();
  const events = data.events || data.audit || data || [];

  if (!events.length) {
    el.textContent = 'No audit entries yet.';
    return;
  }

  el.classList.remove('muted');
  el.innerHTML = `
    <ul class="timeline">
      ${events.map(ev => `
        <li>
          <div class="row space-between">
            <b>${escapeHtml(ev.event_type || ev.type || 'event')}</b>
            <span class="muted small">${escapeHtml(formatDate(ev.created_at || ev.ts))}</span>
          </div>
          ${ev.details ? `<div class="muted small">${escapeHtml(JSON.stringify(ev.details))}</div>` : ''}
        </li>
      `).join('')}
    </ul>
  `;
}
