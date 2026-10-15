import { toast } from '../components/toast.js';
import { renderStatusBadge } from '../components/badge.js';

let currentFilter = 'all';
let allApprovalItems = [];

/**
 * Returns the user's active timezone from the UI selector or browser default.
 */
export function getActiveUserTimezone() {
  const select = document.getElementById('calendar-tz-select');
  return (select && select.value) ? select.value : (Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');
}

/**
 * Formats an ISO datetime string into the user's active timezone with timezone indicator.
 * Fallback to 'Timestamp unavailable' if value is missing or invalid.
 */
export function formatCardTimestamp(isoStr, preferredTz) {
  if (!isoStr) return 'Timestamp unavailable';
  try {
    let cleanStr = String(isoStr).trim();
    if (!cleanStr.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(cleanStr)) {
      cleanStr += 'Z';
    }
    const d = new Date(cleanStr);
    if (isNaN(d.getTime())) return 'Timestamp unavailable';
    const tz = preferredTz || getActiveUserTimezone();
    const formatted = d.toLocaleString('en-US', {
      timeZone: tz,
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
    return `${formatted} (${tz})`;
  } catch (e) {
    return 'Timestamp unavailable';
  }
}

/**
 * Approvals & HITL Review View Manager
 */
export function initApprovalsView() {
  setupFilterTabs();
  loadApprovals();

  // Listen to timezone changes if select exists
  const tzSelect = document.getElementById('calendar-tz-select');
  if (tzSelect && !tzSelect.dataset.approvalsBound) {
    tzSelect.dataset.approvalsBound = 'true';
    tzSelect.addEventListener('change', () => {
      renderApprovalCards();
    });
  }
}

export function setupFilterTabs() {
  document.querySelectorAll('.approval-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.approval-filter-btn').forEach(b => {
        b.classList.remove('btn-primary');
        b.classList.add('btn-secondary');
      });
      btn.classList.remove('btn-secondary');
      btn.classList.add('btn-primary');

      currentFilter = btn.dataset.filter || 'all';
      renderApprovalCards();
    });
  });
}

/**
 * Classifies an item into its primary status bucket for mutually consistent filtering.
 * Buckets: 'pending', 'approved', 'rejected', 'published'
 */
export function getItemStatusBucket(item) {
  const reqStatus = (item.status || '').toUpperCase();
  const pubState = (item.publication_state || '').toUpperCase();
  const postStatus = (item.post_status || '').toUpperCase();

  // If approved and fully published -> Published bucket
  if ((reqStatus === 'APPROVED' || postStatus === 'PUBLISHED') && pubState === 'PUBLISHED') {
    return 'published';
  }

  // If pending human review
  if (reqStatus === 'PENDING' || postStatus === 'AWAITING_HUMAN_APPROVAL') {
    return 'pending';
  }

  // If rejected
  if (reqStatus === 'REJECTED' || postStatus === 'REJECTED') {
    return 'rejected';
  }

  // If approved (unscheduled, scheduled, partially published, or publish failed)
  if (reqStatus === 'APPROVED' || postStatus === 'APPROVED' || postStatus === 'SCHEDULED') {
    return 'approved';
  }

  return 'all';
}

/**
 * Loads pending and historical approval requests from the database via REST API.
 */
export async function loadApprovals() {
  const container = document.getElementById('approvals-list-container');
  if (!container) return;

  try {
    const [pendingRes, historyRes] = await Promise.all([
      fetch('/api/v1/approvals/pending'),
      fetch('/api/v1/approvals/history')
    ]);

    if (!pendingRes.ok) {
      console.warn(`Pending approvals fetch returned status ${pendingRes.status}`);
    }
    if (!historyRes.ok) {
      console.warn(`Approval history fetch returned status ${historyRes.status}`);
      toast.show('Failed to fetch approval history from backend.', 'error');
    }

    const pending = pendingRes.ok ? await pendingRes.json() : [];
    const history = historyRes.ok ? await historyRes.json() : [];

    // Combine and sort by newest approval request id first
    const combined = [...pending, ...history];
    combined.sort((a, b) => (Number(b.id) || 0) - (Number(a.id) || 0));

    // Deduplicate by post_id so newest approval state per post takes precedence
    const seenPostIds = new Set();
    const uniqueItems = [];

    for (const item of combined) {
      const key = item.post_id || `app-${item.id}`;
      if (!seenPostIds.has(key)) {
        seenPostIds.add(key);
        uniqueItems.push(item);
      }
    }

    allApprovalItems = uniqueItems;

    // Compute mutually exclusive bucket counts
    const counts = {
      all: allApprovalItems.length,
      pending: allApprovalItems.filter(i => getItemStatusBucket(i) === 'pending').length,
      approved: allApprovalItems.filter(i => getItemStatusBucket(i) === 'approved').length,
      rejected: allApprovalItems.filter(i => getItemStatusBucket(i) === 'rejected').length,
      published: allApprovalItems.filter(i => getItemStatusBucket(i) === 'published').length,
    };

    // Update filter tab button labels with accurate live counts
    const allBtn = document.querySelector('.approval-filter-btn[data-filter="all"]');
    if (allBtn) allBtn.textContent = `All Posts (${counts.all})`;

    const pendingBtn = document.querySelector('.approval-filter-btn[data-filter="pending"]');
    if (pendingBtn) pendingBtn.textContent = `⏳ Pending (${counts.pending})`;

    const approvedBtn = document.querySelector('.approval-filter-btn[data-filter="approved"]');
    if (approvedBtn) approvedBtn.textContent = `✅ Approved (${counts.approved})`;

    const rejectedBtn = document.querySelector('.approval-filter-btn[data-filter="rejected"]');
    if (rejectedBtn) rejectedBtn.textContent = `❌ Rejected (${counts.rejected})`;

    const publishedBtn = document.querySelector('.approval-filter-btn[data-filter="published"]');
    if (publishedBtn) publishedBtn.textContent = `🚀 Published (${counts.published})`;

    // Update sidebar / header pending badges
    const pendingCountEl = document.getElementById('sidebar-pending-badge') || document.getElementById('pending-count');
    if (pendingCountEl) {
      pendingCountEl.textContent = counts.pending;
    }

    // Update Dashboard KPI badges if present
    const kpiPending = document.getElementById('kpi-pending-posts');
    if (kpiPending) kpiPending.textContent = counts.pending;
    const kpiPublished = document.getElementById('kpi-published-posts');
    if (kpiPublished) kpiPublished.textContent = counts.published;

    renderApprovalCards();
  } catch (err) {
    console.error('Failed to load approvals:', err);
    container.innerHTML = `
      <div class="alert alert-danger" style="margin: var(--space-4);">
        <span>⚠️</span>
        <span>Failed to connect to backend approvals service. Please ensure the server is running.</span>
      </div>
    `;
  }
}

/**
 * Renders the approval cards based on the active filter.
 */
export function renderApprovalCards() {
  const container = document.getElementById('approvals-list-container');
  if (!container) return;

  let filtered = allApprovalItems;
  if (currentFilter !== 'all') {
    filtered = allApprovalItems.filter(item => getItemStatusBucket(item) === currentFilter);
  }

  if (filtered.length === 0) {
    const filterLabels = {
      all: 'All',
      pending: 'Pending',
      approved: 'Approved',
      rejected: 'Rejected',
      published: 'Published'
    };
    container.innerHTML = `
      <div style="text-align: center; padding: var(--space-8); color: var(--text-muted); background: var(--bg-surface); border-radius: var(--radius-lg); border: 1px dashed var(--border-subtle);">
        <div style="font-size: 2.5rem; margin-bottom: var(--space-2);">🎉</div>
        <div style="font-weight: 600; font-size: var(--text-md); color: var(--text-primary); margin-bottom: var(--space-1);">
          No ${filterLabels[currentFilter] || currentFilter.toUpperCase()} Posts in Queue
        </div>
        <div style="font-size: var(--text-sm);">All human-in-the-loop decisions are up to date.</div>
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(item => createApprovalCardHtml(item)).join('');
}

function createApprovalCardHtml(item) {
  const isPending = item.status === 'PENDING';
  const isRejected = item.status === 'REJECTED';
  const isApproved = item.status === 'APPROVED';

  const pubState = (item.publication_state || 'UNSCHEDULED').toUpperCase();
  const isFullyPublished = isApproved && pubState === 'PUBLISHED';
  const isPartiallyPublished = isApproved && pubState === 'PARTIALLY_PUBLISHED';
  const isPublishFailed = isApproved && (pubState === 'PUBLISH_FAILED' || pubState === 'PARTIALLY_FAILED');
  const isScheduled = isApproved && pubState === 'SCHEDULED';
  const isUnscheduled = isApproved && pubState === 'UNSCHEDULED';

  const tz = getActiveUserTimezone();
  const score = item.review_score ?? 90;

  // Header status badge
  let headerBadgeHtml = '';
  if (isFullyPublished) {
    headerBadgeHtml = '<span class="badge badge-emerald">🚀 PUBLISHED</span>';
  } else if (isPartiallyPublished) {
    headerBadgeHtml = '<span class="badge badge-cyan">🚀 PARTIALLY PUBLISHED</span>';
  } else if (isPublishFailed) {
    headerBadgeHtml = '<span class="badge badge-danger">⚠️ PUBLISH FAILED</span>';
  } else if (isScheduled) {
    headerBadgeHtml = '<span class="badge badge-indigo">🗓 SCHEDULED</span>';
  } else if (isUnscheduled) {
    headerBadgeHtml = '<span class="badge badge-emerald">✅ APPROVED (UNSCHEDULED)</span>';
  } else if (isRejected) {
    headerBadgeHtml = '<span class="badge badge-danger">❌ REJECTED</span>';
  } else {
    headerBadgeHtml = renderStatusBadge(item.status);
  }

  // Exact Timestamps formatted per active timezone
  const requestedTsFormatted = formatCardTimestamp(item.requested_at || item.created_at, tz);
  const reviewedTsFormatted = formatCardTimestamp(item.reviewed_at, tz);
  const scheduledTsFormatted = formatCardTimestamp(item.scheduled_at, tz);
  const publishedTsFormatted = formatCardTimestamp(item.published_at, tz);

  // Subtitle metadata depending on status
  let subtitleMeta = '';
  if (isPending) {
    subtitleMeta = `⏳ Submitted: ${requestedTsFormatted} • Theme: <strong>${escapeHtml(item.theme || 'Thought Leadership')}</strong> • Tone: ${escapeHtml(item.tone || 'Professional & Engaging')}`;
  } else if (isUnscheduled) {
    subtitleMeta = `✅ Approved: ${reviewedTsFormatted} by ${escapeHtml(item.reviewer || 'Human')} • Ready for scheduling`;
  } else if (isScheduled) {
    subtitleMeta = `🗓 Scheduled for: ${scheduledTsFormatted} • Approved: ${reviewedTsFormatted}`;
  } else if (isPartiallyPublished) {
    subtitleMeta = `🚀 Partially Published: ${publishedTsFormatted} • Approved: ${reviewedTsFormatted}`;
  } else if (isPublishFailed) {
    subtitleMeta = `⚠️ Attempted: ${scheduledTsFormatted || reviewedTsFormatted} • Approved: ${reviewedTsFormatted}`;
  } else if (isFullyPublished) {
    subtitleMeta = `🚀 Published: ${publishedTsFormatted} • Approved: ${reviewedTsFormatted}`;
  } else if (isRejected) {
    subtitleMeta = `❌ Rejected: ${reviewedTsFormatted} by ${escapeHtml(item.reviewer || 'Human')}`;
  } else {
    subtitleMeta = `Requested: ${requestedTsFormatted}`;
  }

  // Platform copies
  const variants = item.platform_contents || {};
  const platformsHtml = Object.keys(variants).map(p => {
    const v = variants[p];
    const text = typeof v === 'object' ? (v?.content || '') : String(v || '');
    const color = p === 'TWITTER' ? '#1d9bf0' : (p === 'LINKEDIN' ? '#0a66c2' : (p === 'META_FACEBOOK' ? '#1877f2' : '#e1306c'));
    const label = p === 'TWITTER' ? '🐦 X / Twitter' : (p === 'LINKEDIN' ? '💼 LinkedIn' : (p === 'META_FACEBOOK' ? '📱 Facebook' : '📷 Instagram'));
    return `
      <div style="background-color: var(--bg-surface-alt); padding: var(--space-3); border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
          <span style="font-weight: 700; font-size: var(--text-xs); color: ${color};">${label} Copy</span>
          <span style="font-size: var(--text-xs); color: var(--text-muted);">${text.length} chars</span>
        </div>
        <textarea class="form-textarea" style="min-height: 100px; font-size: var(--text-xs); font-family: var(--font-sans);" readonly>${escapeHtml(text)}</textarea>
      </div>
    `;
  }).join('');

  // Target platforms tags display for published/scheduled
  const publishedTargets = item.published_targets || [];
  const scheduledTargets = item.scheduled_targets || [];
  const failedTargets = item.failed_targets || [];

  return `
    <div class="approval-card" id="approval-card-${item.id}" data-post-id="${item.post_id}" data-status="${item.status.toLowerCase()}" style="margin-bottom: var(--space-4);">
      <div class="approval-header">
        <div>
          <div style="display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-1); flex-wrap: wrap;">
            <span style="font-weight: 700; font-size: var(--text-md);">${escapeHtml(item.topic || 'Untitled Post')}</span>
            <span class="approval-status-slot">${headerBadgeHtml}</span>
            <span class="badge badge-purple">v${item.generation_version || 1}</span>
            ${item.regeneration_count > 0 ? `<span class="badge badge-cyan">Regen #${item.regeneration_count}</span>` : ''}
          </div>
          <div style="font-size: var(--text-xs); color: var(--text-muted);">
            ${subtitleMeta}
          </div>
        </div>
        <div class="score-badge-circle" title="AI Review Score">${score}</div>
      </div>

      <!-- AI Feedback Summary -->
      ${item.review_feedback ? `
        <div style="margin-bottom: var(--space-3); padding: var(--space-2) var(--space-3); background: rgba(16, 185, 129, 0.08); border-left: 3px solid var(--color-success); border-radius: var(--radius-sm); font-size: var(--text-xs);">
          <strong>AI Reviewer:</strong> ${escapeHtml(item.review_feedback)}
        </div>
      ` : ''}

      <!-- Rejection notice if rejected -->
      ${item.rejection_reason ? `
        <div style="margin-bottom: var(--space-3); padding: var(--space-2) var(--space-3); background: rgba(239, 68, 68, 0.08); border-left: 3px solid var(--color-danger); border-radius: var(--radius-sm); font-size: var(--text-xs); color: var(--color-danger);">
          <strong>Rejection Reason:</strong> ${escapeHtml(item.rejection_reason)} (Reviewer: ${escapeHtml(item.reviewer || 'Human')} • Rejected: ${reviewedTsFormatted})
        </div>
      ` : ''}

      <!-- Schedule Banner if Scheduled -->
      ${isScheduled ? `
        <div style="margin-bottom: var(--space-3); padding: var(--space-2) var(--space-3); background: rgba(99, 102, 241, 0.08); border-left: 3px solid var(--color-primary); border-radius: var(--radius-sm); font-size: var(--text-xs); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--space-2);">
          <div>
            <strong>🗓 Scheduled Publication:</strong> ${scheduledTsFormatted}
            ${scheduledTargets.length ? `<span style="margin-left: 8px;">• Targets: <strong>${escapeHtml(scheduledTargets.join(', '))}</strong></span>` : ''}
          </div>
          ${item.schedule_id ? `<span class="badge badge-indigo">Schedule #${item.schedule_id}</span>` : ''}
        </div>
      ` : ''}

      <!-- Partially Published Banner -->
      ${isPartiallyPublished ? `
        <div style="margin-bottom: var(--space-3); padding: var(--space-2) var(--space-3); background: rgba(6, 182, 212, 0.08); border-left: 3px solid var(--color-cyan); border-radius: var(--radius-sm); font-size: var(--text-xs); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--space-2);">
          <div>
            <strong>🚀 Partially Published:</strong> ${publishedTsFormatted}
            <div style="margin-top: 2px;">
              <span>✅ Delivered: <strong>${escapeHtml(publishedTargets.join(', '))}</strong></span>
              ${scheduledTargets.length ? `<span style="margin-left: 10px;">⏳ Pending: <strong>${escapeHtml(scheduledTargets.join(', '))}</strong></span>` : ''}
              ${failedTargets.length ? `<span style="margin-left: 10px; color: var(--color-danger);">⚠️ Failed: <strong>${escapeHtml(failedTargets.join(', '))}</strong></span>` : ''}
            </div>
          </div>
          <span class="badge badge-cyan">Partial Delivery</span>
        </div>
      ` : ''}

      <!-- Publish Failed Banner -->
      ${isPublishFailed ? `
        <div style="margin-bottom: var(--space-3); padding: var(--space-2) var(--space-3); background: rgba(239, 68, 68, 0.08); border-left: 3px solid var(--color-danger); border-radius: var(--radius-sm); font-size: var(--text-xs); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--space-2);">
          <div>
            <strong>⚠️ Publication Failed:</strong> One or more platform targets encountered delivery errors.
            ${failedTargets.length ? `<div style="margin-top: 2px; color: var(--color-danger);">Failed Targets: <strong>${escapeHtml(failedTargets.join(', '))}</strong></div>` : ''}
          </div>
          <span class="badge badge-danger">Attention Required</span>
        </div>
      ` : ''}

      <!-- Fully Published Banner if Published -->
      ${isFullyPublished ? `
        <div style="margin-bottom: var(--space-3); padding: var(--space-2) var(--space-3); background: rgba(16, 185, 129, 0.08); border-left: 3px solid var(--color-success); border-radius: var(--radius-sm); font-size: var(--text-xs); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--space-2);">
          <div>
            <strong>🚀 Fully Published:</strong> ${publishedTsFormatted}
            ${publishedTargets.length ? `<span style="margin-left: 8px;">• Targets: <strong>${escapeHtml(publishedTargets.join(', '))}</strong></span>` : ''}
            ${item.external_post_id ? `<span style="margin-left: 8px;">• External ID: <code>${escapeHtml(item.external_post_id)}</code></span>` : ''}
          </div>
          <span class="badge badge-emerald">Live Across All Channels</span>
        </div>
      ` : ''}

      <!-- Platform Copy Preview Grid -->
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--space-3); margin-bottom: var(--space-4);">
        ${platformsHtml || '<div style="color: var(--text-muted); font-size: var(--text-xs);">No platform variants available.</div>'}
      </div>

      <!-- Action Buttons (Strict State Machine) -->
      <div class="approval-actions" id="actions-${item.id}">
        ${isPending ? `
          <button class="btn btn-success btn-sm" onclick="window.approveApproval(${item.id})">
            ✅ Approve Post
          </button>
          <button class="btn btn-danger btn-sm" onclick="window.openRejectModal(${item.id})">
            ❌ Reject with Reason
          </button>
          <button class="btn btn-secondary btn-sm" onclick="window.regenerateApproval(${item.id})">
            🔄 Regenerate Angle
          </button>
          <button class="btn btn-secondary btn-sm" onclick="window.dispatchSlackApproval(${item.id})">
            💬 Dispatch Slack
          </button>
        ` : isUnscheduled ? `
          <div style="display: flex; gap: var(--space-3); align-items: center; justify-content: space-between; flex-wrap: wrap; width: 100%;">
            <span style="font-size: var(--text-xs); color: var(--text-muted);">
              Approved on ${reviewedTsFormatted} by ${escapeHtml(item.reviewer || 'Human')}
            </span>
            <button class="btn btn-primary btn-sm" onclick="window.openScheduleModal(${item.post_id}, '${escapeHtml(item.topic || 'Post').replace(/'/g, "\\'")}')">
              📅 Schedule Post
            </button>
          </div>
        ` : isScheduled ? `
          <div style="display: flex; gap: var(--space-2); align-items: center; justify-content: space-between; flex-wrap: wrap; width: 100%;">
            <span style="font-size: var(--text-xs); color: var(--text-muted);">
              Scheduled for ${scheduledTsFormatted} • Approved by ${escapeHtml(item.reviewer || 'Human')}
            </span>
            <div style="display: flex; gap: var(--space-2); flex-wrap: wrap;">
              <button class="btn btn-success btn-sm" onclick="window.publishNowFromApprovals(${item.schedule_id})">
                ⚡ Publish Now
              </button>
              <button class="btn btn-danger btn-sm" onclick="window.cancelScheduleFromApprovals(${item.schedule_id})">
                ❌ Cancel Schedule
              </button>
              ${item.schedule_id ? `
                <button class="btn btn-secondary btn-sm" onclick="window.openLogsModal(${item.schedule_id})">
                  📜 View Logs
                </button>
              ` : ''}
            </div>
          </div>
        ` : isPartiallyPublished ? `
          <div style="display: flex; gap: var(--space-2); align-items: center; justify-content: space-between; flex-wrap: wrap; width: 100%;">
            <span style="font-size: var(--text-xs); color: var(--color-cyan);">
              Partially published • Some channels pending/failed
            </span>
            <div style="display: flex; gap: var(--space-2); flex-wrap: wrap;">
              ${item.schedule_id ? `
                <button class="btn btn-success btn-sm" onclick="window.publishNowFromApprovals(${item.schedule_id})">
                  ⚡ Publish Remaining
                </button>
                <button class="btn btn-danger btn-sm" onclick="window.cancelScheduleFromApprovals(${item.schedule_id})">
                  ❌ Cancel Schedule
                </button>
                <button class="btn btn-secondary btn-sm" onclick="window.openLogsModal(${item.schedule_id})">
                  📜 View Logs
                </button>
              ` : ''}
            </div>
          </div>
        ` : isPublishFailed ? `
          <div style="display: flex; gap: var(--space-2); align-items: center; justify-content: space-between; flex-wrap: wrap; width: 100%;">
            <span style="font-size: var(--text-xs); color: var(--color-danger);">
              ⚠️ Publication failed • Retry or cancel
            </span>
            <div style="display: flex; gap: var(--space-2); flex-wrap: wrap;">
              ${item.schedule_id ? `
                <button class="btn btn-success btn-sm" onclick="window.publishNowFromApprovals(${item.schedule_id})">
                  ⚡ Retry Publish
                </button>
                <button class="btn btn-danger btn-sm" onclick="window.cancelScheduleFromApprovals(${item.schedule_id})">
                  ❌ Cancel Schedule
                </button>
                <button class="btn btn-secondary btn-sm" onclick="window.openLogsModal(${item.schedule_id})">
                  📜 View Logs
                </button>
              ` : ''}
            </div>
          </div>
        ` : isFullyPublished ? `
          <div style="display: flex; gap: var(--space-2); align-items: center; justify-content: space-between; flex-wrap: wrap; width: 100%;">
            <span style="font-size: var(--text-xs); color: var(--text-muted);">
              Published successfully on ${publishedTsFormatted}
            </span>
            <div style="display: flex; gap: var(--space-2); flex-wrap: wrap;">
              ${item.schedule_id ? `
                <button class="btn btn-secondary btn-sm" onclick="window.openLogsModal(${item.schedule_id})">
                  📜 View Audit Logs
                </button>
              ` : ''}
            </div>
          </div>
        ` : isRejected ? `
          <div style="display: flex; gap: var(--space-3); align-items: center; justify-content: space-between; flex-wrap: wrap; width: 100%;">
            <span style="font-size: var(--text-xs); color: var(--color-danger);">
              Rejected on ${reviewedTsFormatted} by ${escapeHtml(item.reviewer || 'Human')}
            </span>
            <button class="btn btn-secondary btn-sm" onclick="window.regenerateApproval(${item.id})">
              🔄 Regenerate Angle
            </button>
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

/**
 * Approves a pending post.
 */
export async function approveApproval(approvalId) {
  const actionsDiv = document.getElementById(`actions-${approvalId}`);
  if (actionsDiv) actionsDiv.innerHTML = `<span style="font-size: var(--text-xs); color: var(--text-muted);">⏳ Processing approval...</span>`;

  try {
    const res = await fetch(`/api/v1/approvals/${approvalId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reviewer: 'Human Reviewer' })
    });

    if (res.ok) {
      toast.show(`Post approval #${approvalId} approved! Marked ready for scheduling.`, 'success');
      await loadApprovals();
    } else {
      const err = await res.json();
      toast.show(err.detail || 'Failed to approve post.', 'error');
      await loadApprovals();
    }
  } catch (err) {
    console.error('Error approving:', err);
    toast.show('Network error while approving post.', 'error');
    await loadApprovals();
  }
}

/**
 * Opens rejection modal for specifying a reason.
 */
export function openRejectModal(approvalId) {
  const modal = document.getElementById('rejection-modal');
  const idInput = document.getElementById('reject-approval-id');
  const reasonInput = document.getElementById('reject-reason-input');

  if (idInput) idInput.value = approvalId;
  if (reasonInput) reasonInput.value = '';
  if (modal) {
    modal.style.display = 'flex';
    modal.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
}

export function closeRejectionModal() {
  const modal = document.getElementById('rejection-modal');
  if (modal) {
    modal.classList.remove('open');
    modal.style.display = 'none';
    document.body.style.overflow = '';
  }
}

/**
 * Submits post rejection with mandatory reason.
 */
export async function confirmRejection() {
  const idInput = document.getElementById('reject-approval-id');
  const reasonInput = document.getElementById('reject-reason-input');
  const btn = document.getElementById('confirm-reject-btn');

  const approvalId = idInput ? idInput.value : null;
  const reason = reasonInput ? reasonInput.value.trim() : '';

  if (!reason) {
    toast.show('Please provide a reason for rejecting the post.', 'warning');
    reasonInput?.focus();
    return;
  }

  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`/api/v1/approvals/${approvalId}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rejection_reason: reason,
        reviewer: 'Human Reviewer'
      })
    });

    if (res.ok) {
      toast.show(`Post rejected with recorded reason.`, 'error');
      closeRejectionModal();
      await loadApprovals();
    } else {
      const err = await res.json();
      toast.show(err.detail || 'Rejection failed.', 'error');
    }
  } catch (err) {
    console.error('Error rejecting:', err);
    toast.show('Network error while submitting rejection.', 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

/**
 * Regenerates a post from the approval queue.
 */
export async function regenerateApproval(approvalId) {
  const actionsDiv = document.getElementById(`actions-${approvalId}`);
  if (actionsDiv) {
    actionsDiv.innerHTML = `
      <span style="font-size: var(--text-xs); color: var(--color-cyan); display: inline-flex; align-items: center; gap: 6px;">
        <span class="loading-spinner" style="width: 14px; height: 14px; border: 2px solid var(--color-cyan); border-top-color: transparent; border-radius: 50%; display: inline-block; animation: spin 0.8s linear infinite;"></span>
        Generating alternate angle via AI Engine...
      </span>
    `;
  }

  try {
    const res = await fetch(`/api/v1/approvals/${approvalId}/regenerate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reviewer: 'Human Reviewer' })
    });

    if (res.ok) {
      const data = await res.json();
      toast.show(`Post regenerated (Version ${data.details?.version || 2})! Alternate angle ready for review.`, 'success');
      await loadApprovals();
    } else {
      const err = await res.json();
      toast.show(err.detail || 'Regeneration failed.', 'error');
      await loadApprovals();
    }
  } catch (err) {
    console.error('Error regenerating:', err);
    toast.show('Network error during regeneration.', 'error');
    await loadApprovals();
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/**
 * Open scheduling modal for an approved post.
 */
export function openScheduleModal(postId, previewText) {
  const modal = document.getElementById('schedule-post-modal');
  const idInput = document.getElementById('schedule-post-id');
  const previewDiv = document.getElementById('schedule-post-preview');
  const dateInput = document.getElementById('schedule-date-input');
  const timeInput = document.getElementById('schedule-time-input');

  if (idInput) idInput.value = postId;
  if (previewDiv) previewDiv.innerHTML = `<strong>Topic / Content:</strong> ${escapeHtml(previewText || '')}`;

  // Populate target channels checkboxes from post metadata
  const item = allApprovalItems.find(i => i.post_id === postId);
  const platformsList = document.getElementById('schedule-platforms-list');
  if (platformsList && item) {
    const contents = item.platform_contents || {};
    const targets = (item.target_platforms && item.target_platforms.length > 0)
      ? item.target_platforms
      : Object.keys(contents);

    platformsList.innerHTML = targets.map(p => {
      const v = contents[p];
      const text = typeof v === 'object' ? (v?.content || '') : String(v || '');
      const hasContent = Boolean(text && text.trim().length > 0);
      const label = p === 'TWITTER' ? '🐦 Twitter / X' : (p === 'LINKEDIN' ? '💼 LinkedIn' : (p === 'META_FACEBOOK' ? '📱 Facebook' : (p === 'META_INSTAGRAM' ? '📷 Instagram' : p)));

      return `
        <label class="platform-chip ${hasContent ? 'checked' : ''}" style="cursor: pointer; display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 9999px; font-size: var(--text-xs); border: 1px solid ${hasContent ? 'var(--color-primary)' : 'var(--color-danger)'}; background: ${hasContent ? 'rgba(99, 102, 241, 0.1)' : 'rgba(239, 68, 68, 0.08)'}; color: ${hasContent ? 'var(--text-primary)' : 'var(--color-danger)'};">
          <input type="checkbox" name="schedule-target-platform" value="${p}" ${hasContent ? 'checked' : ''} style="margin: 0;">
          <span>${label}</span>
          ${!hasContent ? '<span style="font-size: 10px; background: rgba(239, 68, 68, 0.2); padding: 1px 6px; border-radius: 4px; font-weight: 600;">⚠️ No Content</span>' : ''}
        </label>
      `;
    }).join('');
  }

  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, '0');
  const dd = String(today.getDate()).padStart(2, '0');
  const todayStr = `${yyyy}-${mm}-${dd}`;

  // Enforce min date = today so past dates cannot be selected
  if (dateInput) {
    dateInput.min = todayStr;
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tmY = tomorrow.getFullYear();
    const tmM = String(tomorrow.getMonth() + 1).padStart(2, '0');
    const tmD = String(tomorrow.getDate()).padStart(2, '0');
    dateInput.value = `${tmY}-${tmM}-${tmD}`;
  }
  if (timeInput) timeInput.value = '10:00';

  if (modal) {
    modal.style.display = 'flex';
    modal.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
}

export function closeScheduleModal() {
  const modal = document.getElementById('schedule-post-modal');
  if (modal) {
    modal.classList.remove('open');
    modal.style.display = 'none';
    document.body.style.overflow = '';
  }
}

export async function confirmSchedule() {
  const idInput = document.getElementById('schedule-post-id');
  const dateInput = document.getElementById('schedule-date-input');
  const timeInput = document.getElementById('schedule-time-input');
  const tzSelect = document.getElementById('schedule-timezone-select');
  const btn = document.getElementById('confirm-schedule-btn');

  const postId = idInput ? Number(idInput.value) : null;
  const dateStr = dateInput ? dateInput.value : '';
  const timeStr = timeInput ? timeInput.value : '';
  const timezone = tzSelect ? tzSelect.value : 'UTC';

  if (!postId || !dateStr || !timeStr) {
    toast.show('Please select a valid publication date and time.', 'warning');
    return;
  }

  // Collect explicitly selected target platforms
  const selectedPlatforms = Array.from(
    document.querySelectorAll('input[name="schedule-target-platform"]:checked')
  ).map(cb => cb.value);

  if (selectedPlatforms.length === 0) {
    toast.show('Please select at least one target channel with valid content to schedule.', 'warning');
    return;
  }

  // Guardrail: date cannot be in the past
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  if (dateStr < todayStr) {
    toast.show('Cannot schedule for a past date. Please pick today or a future date.', 'warning');
    return;
  }

  // Combine into ISO 8601 string
  let isoStr = `${dateStr}T${timeStr}:00`;
  const scheduledDate = new Date(isoStr);
  if (isNaN(scheduledDate.getTime())) {
    toast.show('Invalid date or time entered.', 'warning');
    return;
  }

  // Guardrail: if scheduling for today, time must be in the future
  if (dateStr === todayStr && scheduledDate.getTime() <= Date.now()) {
    toast.show('Selected publication time has already passed. Please choose a future time.', 'warning');
    return;
  }

  if (timezone === 'UTC') {
    isoStr += 'Z';
  } else {
    isoStr = scheduledDate.toISOString();
  }

  if (btn) btn.disabled = true;

  try {
    const res = await fetch('/api/v1/schedules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        post_id: postId,
        scheduled_at: isoStr,
        timezone: timezone,
        target_platforms: selectedPlatforms
      })
    });

    if (res.ok) {
      const data = await res.json();
      window.lastScheduledId = data.id;
      toast.show(`Post #${postId} scheduled for ${dateStr} ${timeStr} (${timezone})!`, 'success');
      closeScheduleModal();
      await loadApprovals();
      if (window.loadSchedules && window.renderCalendar) {
        window.loadSchedules().then(() => window.renderCalendar());
      }
    } else {
      const err = await res.json();
      toast.show(err.detail || 'Failed to schedule post.', 'error');
    }
  } catch (err) {
    console.error('Error scheduling post:', err);
    toast.show('Network error while scheduling post.', 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

/**
 * Publishes a scheduled post directly from the approvals queue.
 */
export async function publishNowFromApprovals(scheduleId) {
  if (!scheduleId) {
    toast.show('Schedule ID not found for this post.', 'error');
    return;
  }
  if (!confirm('Publish this post immediately via the publisher engine?')) return;

  try {
    const res = await fetch(`/api/v1/schedules/${scheduleId}/publish-now`, {
      method: 'POST'
    });

    if (res.ok) {
      const data = await res.json();
      toast.show(data.message || 'Post published successfully!', 'success');
      await loadApprovals();
      if (window.loadSchedules && window.renderCalendar) {
        window.loadSchedules().then(() => window.renderCalendar());
      }
    } else {
      const err = await res.json();
      toast.show(err.detail || 'Publication failed.', 'error');
      await loadApprovals();
    }
  } catch (err) {
    console.error('Error triggering publish-now:', err);
    toast.show('Network error while publishing post.', 'error');
  }
}

/**
 * Cancels a scheduled post from the approvals queue, returning it to APPROVED state.
 */
export async function cancelScheduleFromApprovals(scheduleId) {
  if (!scheduleId) {
    toast.show('Schedule ID not found for this post.', 'error');
    return;
  }
  if (!confirm('Are you sure you want to cancel this scheduled post? It will return to Approved status.')) return;

  try {
    const res = await fetch(`/api/v1/schedules/${scheduleId}?cancel_all=true`, {
      method: 'DELETE'
    });

    if (res.ok) {
      toast.show('Schedule cancelled. Post returned to Approved queue.', 'success');
      await loadApprovals();
      if (window.loadSchedules && window.renderCalendar) {
        window.loadSchedules().then(() => window.renderCalendar());
      }
    } else {
      const err = await res.json();
      toast.show(err.detail || 'Failed to cancel schedule.', 'error');
    }
  } catch (err) {
    console.error('Error cancelling schedule:', err);
    toast.show('Network error while cancelling schedule.', 'error');
  }
}

/**
 * Dispatches or re-dispatches a Slack interactive approval card for a post.
 */
export async function dispatchSlackApproval(approvalId) {
  try {
    const res = await fetch(`/api/v1/slack/dispatch/${approvalId}`, {
      method: 'POST'
    });
    if (res.ok) {
      const data = await res.json();
      const modeText = data.mock ? 'Mock Mode' : data.channel;
      toast.show(`Slack approval card dispatched (${modeText})!`, 'success');
      await loadApprovals();
    } else {
      const err = await res.json();
      toast.show(err.detail || 'Failed to dispatch Slack card.', 'error');
    }
  } catch (err) {
    console.error('Error dispatching Slack approval:', err);
    toast.show('Network error while dispatching Slack card.', 'error');
  }
}

// Attach to window for DOM onclick events
window.dispatchSlackApproval = dispatchSlackApproval;
window.approveApproval = approveApproval;
window.openRejectModal = openRejectModal;
window.closeRejectionModal = closeRejectionModal;
window.confirmRejection = confirmRejection;
window.regenerateApproval = regenerateApproval;
window.refreshApprovalsList = loadApprovals;
window.loadApprovals = loadApprovals;
window.openScheduleModal = openScheduleModal;
window.closeScheduleModal = closeScheduleModal;
window.confirmSchedule = confirmSchedule;
window.publishNowFromApprovals = publishNowFromApprovals;
window.cancelScheduleFromApprovals = cancelScheduleFromApprovals;
window.getActiveUserTimezone = getActiveUserTimezone;
window.formatCardTimestamp = formatCardTimestamp;
window.getItemStatusBucket = getItemStatusBucket;
