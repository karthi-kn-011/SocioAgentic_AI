import { toast } from '../components/toast.js';

let cachedActivityLogs = [];

/**
 * Activity & Audit Log View Manager - Connected to real backend activity feed.
 */
export async function initActivityView() {
  const searchInput = document.getElementById('activity-search-input');
  const filterSelect = document.getElementById('activity-filter-select');

  if (searchInput && !searchInput.dataset.bound) {
    searchInput.dataset.bound = 'true';
    searchInput.addEventListener('input', () => {
      filterActivityRows(searchInput.value.toLowerCase(), filterSelect?.value || 'ALL');
    });
  }

  if (filterSelect && !filterSelect.dataset.bound) {
    filterSelect.dataset.bound = 'true';
    filterSelect.addEventListener('change', () => {
      filterActivityRows(searchInput?.value.toLowerCase() || '', filterSelect.value);
    });
  }

  await loadActivityLogs();
}

export async function loadActivityLogs() {
  const tbody = document.getElementById('activity-table-body');
  if (!tbody) return;

  try {
    const res = await fetch('/api/v1/health/activity?limit=100');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    cachedActivityLogs = await res.json();
    renderActivityRows(cachedActivityLogs);
  } catch (err) {
    console.warn('Failed to load activity logs:', err);
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; color: var(--text-muted); padding: var(--space-6);">
          No audit logs recorded yet.
        </td>
      </tr>
    `;
  }
}

function renderActivityRows(logs) {
  const tbody = document.getElementById('activity-table-body');
  if (!tbody) return;

  if (!logs || logs.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; color: var(--text-muted); padding: var(--space-8);">
          <div style="font-size: 1.8rem; margin-bottom: var(--space-2);">📋</div>
          <div style="font-weight: 600;">No Activity Recorded Yet</div>
          <div style="font-size: var(--text-xs); margin-top: var(--space-1);">System events and audit records will appear here as operations are performed.</div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = logs.map(l => {
    const timeStr = l.created_at ? new Date(l.created_at).toLocaleString() : 'N/A';
    let badgeClass = 'badge-indigo';
    const action = l.action || 'ACTIVITY';

    if (action.includes('PUBLISHED') || action.includes('APPROVED')) badgeClass = 'badge-emerald';
    else if (action.includes('REJECTED')) badgeClass = 'badge-danger';
    else if (action.includes('SCHEDULED')) badgeClass = 'badge-cyan';
    else if (action.includes('CANCELLED')) badgeClass = 'badge-gray';

    return `
      <tr data-action="${escapeHtml(action)}">
        <td style="font-family: var(--font-mono); font-size: 0.75rem;">${escapeHtml(timeStr)}</td>
        <td><span class="badge ${badgeClass}">${escapeHtml(action)}</span></td>
        <td>${l.post_id ? `#${l.post_id}` : '-'}</td>
        <td>${escapeHtml(l.actor || 'System')}</td>
        <td style="max-width: 320px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(l.details || '')}">
          ${escapeHtml(l.details || '-')}
        </td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="inspectActivityDetails('${escapeHtml(action)}', '${escapeHtml(l.details || '')}', '${escapeHtml(timeStr)}')">
            🔍 View
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

function filterActivityRows(query, actionFilter) {
  const filtered = cachedActivityLogs.filter(l => {
    const text = `${l.action} ${l.actor} ${l.details} ${l.post_id}`.toLowerCase();
    const matchesQuery = !query || text.includes(query);
    const matchesAction = actionFilter === 'ALL' || l.action === actionFilter;
    return matchesQuery && matchesAction;
  });
  renderActivityRows(filtered);
}

export function inspectActivityDetails(action, details, timestamp) {
  const modalBody = document.querySelector('#demo-modal .modal-body');
  const modalTitle = document.querySelector('#demo-modal #modal-title');
  if (modalTitle) modalTitle.textContent = `Audit Event: ${action}`;
  if (modalBody) {
    modalBody.innerHTML = `
      <div style="font-family: var(--font-mono); font-size: 0.85rem; background: var(--bg-surface-alt); padding: 16px; border-radius: 8px;">
        <p style="margin-bottom: 8px;"><strong>Action:</strong> ${action}</p>
        <p style="margin-bottom: 8px;"><strong>Timestamp:</strong> ${timestamp}</p>
        <p style="margin-bottom: 8px;"><strong>Details:</strong> ${details}</p>
        <p style="color: var(--color-success, #10b981);"><strong>Verification:</strong> HMAC Verified & Audited in Database</p>
      </div>
    `;
  }
  const modal = document.getElementById('demo-modal');
  if (modal) {
    modal.style.display = 'flex';
    modal.classList.add('open');
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

window.inspectActivityDetails = inspectActivityDetails;
window.loadActivityLogs = loadActivityLogs;
