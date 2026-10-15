import { toast } from '../components/toast.js';

let cachedPublishLogs = [];

/**
 * Analytics View Manager (Data-Driven from Backend Schedules & Publication Logs)
 */
export async function initAnalyticsView() {
  const exportBtn = document.getElementById('export-analytics-btn');
  if (exportBtn && !exportBtn.dataset.bound) {
    exportBtn.dataset.bound = 'true';
    exportBtn.addEventListener('click', () => {
      exportPublicationLogsCSV();
    });
  }

  await loadAnalyticsData();
}

export async function loadAnalyticsData() {
  const tbody = document.getElementById('analytics-table-body');
  try {
    const res = await fetch('/api/v1/schedules');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const schedules = data.data || [];

    // Filter to schedules that have had execution attempts (PUBLISHED or PUBLISH_FAILED)
    const executed = schedules.filter(s => s.status === 'PUBLISHED' || s.status === 'PUBLISH_FAILED');
    const successful = executed.filter(s => s.status === 'PUBLISHED');
    const failed = executed.filter(s => s.status === 'PUBLISH_FAILED');

    cachedPublishLogs = executed;

    // Metrics calculation
    const totalPubsEl = document.getElementById('analytics-total-pubs');
    if (totalPubsEl) totalPubsEl.textContent = executed.length;

    const successRateEl = document.getElementById('analytics-success-rate');
    const successBadgeEl = document.getElementById('analytics-success-badge');
    if (successRateEl) {
      if (executed.length === 0) {
        successRateEl.textContent = 'N/A';
        if (successBadgeEl) successBadgeEl.textContent = 'No Attempts Yet';
      } else {
        const rate = Math.round((successful.length / executed.length) * 100);
        successRateEl.textContent = `${rate}%`;
        if (successBadgeEl) successBadgeEl.textContent = `${successful.length} Dispatched`;
      }
    }

    const failedEl = document.getElementById('analytics-failed-pubs');
    const failBadgeEl = document.getElementById('analytics-failure-badge');
    if (failedEl) {
      failedEl.textContent = failed.length;
      if (failBadgeEl) {
        failBadgeEl.textContent = failed.length === 0 ? 'Healthy (0 Errors)' : `${failed.length} Errors`;
      }
    }

    renderAnalyticsTable(executed);
  } catch (err) {
    console.warn('Failed to load analytics data:', err);
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align: center; color: var(--text-muted); padding: var(--space-6);">
            No publication logs available yet.
          </td>
        </tr>
      `;
    }
  }
}

function renderAnalyticsTable(logs) {
  const tbody = document.getElementById('analytics-table-body');
  if (!tbody) return;

  if (!logs || logs.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; color: var(--text-muted); padding: var(--space-8);">
          <div style="font-size: 1.8rem; margin-bottom: var(--space-2);">📑</div>
          <div style="font-weight: 600;">No Publications Executed Yet</div>
          <div style="font-size: var(--text-xs); margin-top: var(--space-1);">Publication attempts and delivery logs will appear here once scheduled posts are executed.</div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = logs.map(item => {
    const isSuccess = item.status === 'PUBLISHED';
    const badgeClass = isSuccess ? 'badge-emerald' : 'badge-danger';
    const timeFormatted = item.published_at ? new Date(item.published_at).toLocaleString() : (item.scheduled_at ? new Date(item.scheduled_at).toLocaleString() : 'N/A');

    return `
      <tr>
        <td>#${item.id}</td>
        <td><span class="badge badge-indigo">${escapeHtml(item.platform || 'Social')}</span></td>
        <td><span class="badge ${badgeClass}">${escapeHtml(item.status)}</span></td>
        <td><span class="badge badge-cyan" style="font-size: 10px;">SIMULATED (Sandbox)</span></td>
        <td><code style="font-family: var(--font-mono); font-size: 11px;">${item.idempotency_key ? escapeHtml(item.idempotency_key.slice(0, 18)) : 'id_simulated'}</code></td>
        <td style="font-size: var(--text-xs);">${timeFormatted}</td>
      </tr>
    `;
  }).join('');
}

function exportPublicationLogsCSV() {
  if (cachedPublishLogs.length === 0) {
    toast.show('No publication records available to export.', 'info');
    return;
  }

  let csvContent = "data:text/csv;charset=utf-8,Schedule_ID,Post_ID,Platform,Status,Scheduled_At,Published_At\n";
  cachedPublishLogs.forEach(s => {
    csvContent += `${s.id},${s.post_id || ''},${s.platform || ''},${s.status || ''},${s.scheduled_at || ''},${s.published_at || ''}\n`;
  });

  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", "social_agent_publish_logs.csv");
  document.body.appendChild(link);
  link.click();
  link.remove();

  toast.show('Publication logs exported to CSV successfully!', 'success');
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

window.loadAnalyticsData = loadAnalyticsData;
