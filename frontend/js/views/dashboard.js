import { switchTab } from '../app.js';
import { toast } from '../components/toast.js';

/**
 * Dashboard View Manager - Connects dynamic counts and recent operations feed.
 */
export async function initDashboardView() {
  const quickCreateBtn = document.getElementById('dashboard-quick-create-btn');
  if (quickCreateBtn && !quickCreateBtn.dataset.bound) {
    quickCreateBtn.dataset.bound = 'true';
    quickCreateBtn.addEventListener('click', () => {
      switchTab('studio');
      toast.show('Switched to Content Studio', 'info', 1500);
    });
  }

  await loadDashboardData();
}

export async function loadDashboardData() {
  try {
    const [postsRes, pendingRes, historyRes, schedsRes, activityRes] = await Promise.all([
      fetch('/api/v1/posts?limit=100').catch(() => null),
      fetch('/api/v1/approvals/pending').catch(() => null),
      fetch('/api/v1/approvals/history').catch(() => null),
      fetch('/api/v1/schedules').catch(() => null),
      fetch('/api/v1/health/activity?limit=5').catch(() => null),
    ]);

    const posts = postsRes && postsRes.ok ? await postsRes.json() : [];
    const pending = pendingRes && pendingRes.ok ? await pendingRes.json() : [];
    const history = historyRes && historyRes.ok ? await historyRes.json() : [];
    const schedsData = schedsRes && schedsRes.ok ? await schedsRes.json() : {};
    const schedules = schedsData.data || [];
    const activities = activityRes && activityRes.ok ? await activityRes.json() : [];

    // KPI 1: Total Posts
    const totalPostsEl = document.getElementById('kpi-total-posts');
    if (totalPostsEl) totalPostsEl.textContent = posts.length || 0;

    // KPI 2: Pending Approvals
    const pendingEl = document.getElementById('kpi-pending-posts');
    if (pendingEl) pendingEl.textContent = pending.length || 0;

    // KPI 3: Scheduled in Queue
    const activeScheduled = schedules.filter(s => (s.status || '').toUpperCase() === 'SCHEDULED');
    const scheduledEl = document.getElementById('kpi-scheduled-posts');
    if (scheduledEl) scheduledEl.textContent = activeScheduled.length || 0;

    // KPI 4: Successfully Published
    const publishedHistory = history.filter(h => (h.publication_state || '').toUpperCase() === 'PUBLISHED');
    const publishedEl = document.getElementById('kpi-published-posts');
    if (publishedEl) publishedEl.textContent = publishedHistory.length || 0;

    // Render Recent Operations feed
    renderDashboardActivities(activities);
  } catch (err) {
    console.warn('Dashboard data loading error:', err);
  }
}

function renderDashboardActivities(activities) {
  const container = document.getElementById('dashboard-recent-activities');
  if (!container) return;

  if (!activities || activities.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: var(--space-6); color: var(--text-muted); font-size: var(--text-sm);">
        <p style="font-size: 1.8rem; margin-bottom: var(--space-2);">📋</p>
        <p style="font-weight: 600;">No recent operations recorded yet.</p>
        <p style="font-size: var(--text-xs); margin-top: var(--space-1);">Generate content in the Studio or approve posts to see activity here.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = activities.slice(0, 4).map(act => {
    let badgeClass = 'badge-indigo';
    let icon = '⚡';
    const action = act.action || 'ACTIVITY';

    if (action.includes('PUBLISHED')) {
      badgeClass = 'badge-emerald';
      icon = '🚀';
    } else if (action.includes('APPROVED')) {
      badgeClass = 'badge-emerald';
      icon = '✅';
    } else if (action.includes('REJECTED')) {
      badgeClass = 'badge-danger';
      icon = '❌';
    } else if (action.includes('SCHEDULED')) {
      badgeClass = 'badge-cyan';
      icon = '🗓';
    } else if (action.includes('CANCELLED')) {
      badgeClass = 'badge-gray';
      icon = '🚫';
    }

    const timeStr = act.created_at ? new Date(act.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';

    return `
      <div style="display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) 0; border-bottom: 1px solid var(--border-subtle);">
        <div>
          <div style="font-weight: 600; font-size: var(--text-sm); display: flex; align-items: center; gap: var(--space-2);">
            <span>${icon}</span>
            <span>${escapeHtml(action)} ${act.post_id ? `(#${act.post_id})` : ''}</span>
          </div>
          <div style="font-size: var(--text-xs); color: var(--text-muted); margin-top: 2px;">
            ${escapeHtml(act.details || 'System event recorded')}
          </div>
        </div>
        <div style="text-align: right;">
          <span class="badge ${badgeClass}">${escapeHtml(action)}</span>
          ${timeStr ? `<div style="font-size: 10px; color: var(--text-muted); margin-top: 2px;">${timeStr}</div>` : ''}
        </div>
      </div>
    `;
  }).join('');
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

window.loadDashboardData = loadDashboardData;
