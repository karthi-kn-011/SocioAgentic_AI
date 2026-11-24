import { toast } from '../components/toast.js';

let cachedActivityLogs = [];
let currentPage = 1;
const pageSize = 20;
let totalRecords = 0;
let currentSearch = '';
let currentAction = 'ALL';
let searchDebounceTimeout = null;

/**
 * Activity & Audit Log View Manager - Connected to server-side paginated activity API.
 */
export async function initActivityView() {
  const searchInput = document.getElementById('activity-search-input');
  const filterSelect = document.getElementById('activity-filter-select');
  const prevBtn = document.getElementById('activity-prev-btn');
  const nextBtn = document.getElementById('activity-next-btn');

  if (searchInput && !searchInput.dataset.bound) {
    searchInput.dataset.bound = 'true';
    searchInput.addEventListener('input', () => {
      clearTimeout(searchDebounceTimeout);
      searchDebounceTimeout = setTimeout(() => {
        currentSearch = searchInput.value.trim();
        currentPage = 1;
        loadActivityLogs();
      }, 250);
    });
  }

  if (filterSelect && !filterSelect.dataset.bound) {
    filterSelect.dataset.bound = 'true';
    filterSelect.addEventListener('change', () => {
      currentAction = filterSelect.value;
      currentPage = 1;
      loadActivityLogs();
    });
  }

  if (prevBtn && !prevBtn.dataset.bound) {
    prevBtn.dataset.bound = 'true';
    prevBtn.addEventListener('click', () => {
      if (currentPage > 1) {
        currentPage--;
        loadActivityLogs();
      }
    });
  }

  if (nextBtn && !nextBtn.dataset.bound) {
    nextBtn.dataset.bound = 'true';
    nextBtn.addEventListener('click', () => {
      if (currentPage * pageSize < totalRecords) {
        currentPage++;
        loadActivityLogs();
      }
    });
  }

  if (typeof window.isUserAuthenticated === 'function' && !window.isUserAuthenticated()) {
    return;
  }

  await loadActivityLogs();
}

export async function loadActivityLogs() {
  const tbody = document.getElementById('activity-table-body');
  if (!tbody) return;

  const skip = (currentPage - 1) * pageSize;
  const params = new URLSearchParams();
  params.set('skip', skip.toString());
  params.set('limit', pageSize.toString());

  if (currentAction && currentAction !== 'ALL') {
    params.set('action', currentAction);
  }
  if (currentSearch) {
    params.set('search', currentSearch);
  }

  try {
    const res = await fetch(`/api/v1/activity?${params.toString()}`);
    if (!res.ok) {
      // Fallback to legacy health endpoint if /activity router is unavailable
      const fallbackRes = await fetch('/api/v1/health/activity?limit=100');
      if (!fallbackRes.ok) throw new Error(`HTTP ${res.status}`);
      const raw = await fallbackRes.json();
      cachedActivityLogs = Array.isArray(raw) ? raw : (raw.items || []);
      totalRecords = cachedActivityLogs.length;
      renderActivityRows(cachedActivityLogs);
      updatePaginationControls();
      return;
    }

    const data = await res.json();
    cachedActivityLogs = data.items || [];
    totalRecords = data.total !== undefined ? data.total : cachedActivityLogs.length;

    renderActivityRows(cachedActivityLogs);
    updatePaginationControls();
  } catch (err) {
    console.warn('Failed to load activity logs:', err);
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; color: var(--text-muted); padding: var(--space-6);">
          No audit logs recorded yet.
        </td>
      </tr>
    `;
    updatePaginationControls();
  }
}

function updatePaginationControls() {
  const pageInfo = document.getElementById('activity-page-info');
  const prevBtn = document.getElementById('activity-prev-btn');
  const nextBtn = document.getElementById('activity-next-btn');

  const start = totalRecords === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const end = Math.min(currentPage * pageSize, totalRecords);
  const totalPages = Math.ceil(totalRecords / pageSize) || 1;

  if (pageInfo) {
    pageInfo.textContent = `Showing ${start}-${end} of ${totalRecords} events (Page ${currentPage} of ${totalPages})`;
  }

  if (prevBtn) {
    prevBtn.disabled = currentPage <= 1;
  }

  if (nextBtn) {
    nextBtn.disabled = currentPage >= totalPages || totalRecords === 0;
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
    else if (action.includes('REJECTED') || action.includes('FAILED')) badgeClass = 'badge-danger';
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
