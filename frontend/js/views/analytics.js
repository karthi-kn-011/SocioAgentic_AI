import { toast } from '../components/toast.js';

let cachedPublishLogs = [];

/**
 * Analytics View Manager (Data-Driven from Backend Analytics Service)
 */
export async function initAnalyticsView() {
  const exportBtn = document.getElementById('export-analytics-btn');
  if (exportBtn && !exportBtn.dataset.bound) {
    exportBtn.dataset.bound = 'true';
    exportBtn.addEventListener('click', () => {
      exportPublicationLogsCSV();
    });
  }

  if (typeof window.isUserAuthenticated === 'function' && !window.isUserAuthenticated()) {
    return;
  }

  await loadAnalyticsData();
}

export async function loadAnalyticsData() {
  const tbody = document.getElementById('analytics-table-body');
  try {
    const [overviewRes, pubsRes] = await Promise.all([
      fetch('/api/v1/analytics/overview'),
      fetch('/api/v1/analytics/publications?limit=100'),
    ]);

    if (!overviewRes.ok) throw new Error(`Overview HTTP ${overviewRes.status}`);
    if (!pubsRes.ok) throw new Error(`Publications HTTP ${pubsRes.status}`);

    const overview = await overviewRes.json();
    const pubsData = await pubsRes.json();
    const publicationLogs = pubsData.items || [];
    cachedPublishLogs = publicationLogs;

    // Metrics calculation from Analytics Overview
    // Real Platform Breakdown Data Binding
    if (overview.platform_breakdown) {
      const pMap = overview.platform_breakdown;
      const tw = pMap['TWITTER'] || pMap['X'] || 0;
      const li = pMap['LINKEDIN'] || 0;
      const fb = pMap['META_FACEBOOK'] || pMap['FACEBOOK'] || 0;
      const ig = pMap['META_INSTAGRAM'] || pMap['INSTAGRAM'] || 0;

      const elTw = document.getElementById('dist-count-twitter');
      const elLi = document.getElementById('dist-count-linkedin');
      const elFb = document.getElementById('dist-count-facebook');
      const elIg = document.getElementById('dist-count-instagram');

      if (elTw) elTw.textContent = `${tw} ${tw === 1 ? 'post' : 'posts'}`;
      if (elLi) elLi.textContent = `${li} ${li === 1 ? 'post' : 'posts'}`;
      if (elFb) elFb.textContent = `${fb} ${fb === 1 ? 'post' : 'posts'}`;
      if (elIg) elIg.textContent = `${ig} ${ig === 1 ? 'post' : 'posts'}`;
    }

    const totalPubsEl = document.getElementById('analytics-total-pubs');
    if (totalPubsEl) totalPubsEl.textContent = overview.total_publications;

    const successRateEl = document.getElementById('analytics-success-rate');
    const successBadgeEl = document.getElementById('analytics-success-badge');
    if (successRateEl) {
      if (overview.total_publications === 0) {
        successRateEl.textContent = 'N/A';
        if (successBadgeEl) successBadgeEl.textContent = 'No Attempts Yet';
      } else {
        successRateEl.textContent = `${overview.success_rate}%`;
        if (successBadgeEl) successBadgeEl.textContent = `${overview.successful_publications} Delivered`;
      }
    }

    const failedEl = document.getElementById('analytics-failed-pubs');
    const failBadgeEl = document.getElementById('analytics-failure-badge');
    if (failedEl) {
      failedEl.textContent = overview.failed_publications;
      if (failBadgeEl) {
        failBadgeEl.textContent = overview.failed_publications === 0 ? 'Healthy (0 Errors)' : `${overview.failed_publications} Errors`;
      }
    }

    // Dynamic Average AI Quality
    const aiQualityEl = document.getElementById('analytics-ai-quality');
    const aiQualityBadge = document.getElementById('analytics-ai-badge');
    if (aiQualityEl) {
      if (overview.average_ai_score !== null && overview.average_ai_score !== undefined) {
        aiQualityEl.textContent = `${overview.average_ai_score}%`;
        if (aiQualityBadge) {
          aiQualityBadge.textContent = 'Audited';
          aiQualityBadge.className = 'badge badge-indigo';
        }
      } else {
        aiQualityEl.textContent = 'N/A';
        if (aiQualityBadge) {
          aiQualityBadge.textContent = 'No Data';
          aiQualityBadge.className = 'badge badge-gray';
        }
      }
    }

    renderAnalyticsTable(publicationLogs);
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
    const isSuccess = item.status === 'SUCCESS' || item.status === 'SIMULATED';
    const badgeClass = isSuccess ? 'badge-emerald' : 'badge-danger';
    const timeFormatted = item.published_at
      ? new Date(item.published_at).toLocaleString()
      : (item.attempted_at ? new Date(item.attempted_at).toLocaleString() : 'N/A');

    const scheduleLabel = item.schedule_id ? `#${item.schedule_id} (Post #${item.post_id})` : `#${item.id} (Post #${item.post_id})`;
    const modeBadge = item.is_mock
      ? '<span class="badge badge-cyan" style="font-size: 10px;">SIMULATED (Sandbox)</span>'
      : '<span class="badge badge-emerald" style="font-size: 10px;">LIVE (Production)</span>';

    return `
      <tr>
        <td>${escapeHtml(scheduleLabel)}</td>
        <td><span class="badge badge-indigo">${escapeHtml(item.platform || 'Social')}</span></td>
        <td><span class="badge ${badgeClass}">${escapeHtml(item.status)}</span></td>
        <td>${modeBadge}</td>
        <td><code style="font-family: var(--font-mono); font-size: 11px;">${item.external_post_id ? escapeHtml(item.external_post_id.slice(0, 22)) : (item.is_mock ? 'id_simulated' : '-')}</code></td>
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

  let csvContent = "data:text/csv;charset=utf-8,Log_ID,Post_ID,Schedule_ID,Platform,Status,Execution_Mode,External_ID,Attempted_At,Published_At\n";
  cachedPublishLogs.forEach(l => {
    const mode = l.is_mock ? 'MOCK' : 'LIVE';
    csvContent += `${l.id},${l.post_id || ''},${l.schedule_id || ''},${l.platform || ''},${l.status || ''},${mode},${l.external_post_id || ''},${l.attempted_at || ''},${l.published_at || ''}\n`;
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
