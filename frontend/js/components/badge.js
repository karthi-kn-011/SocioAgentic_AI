/**
 * Reusable Badge and Status Indicator Helper
 */

export function renderStatusBadge(status) {
  const map = {
    'DRAFT': { class: 'badge-indigo', icon: '📝', text: 'DRAFT' },
    'REVIEWING': { class: 'badge-cyan', icon: '🤖', text: 'REVIEWING' },
    'PENDING_APPROVAL': { class: 'badge-amber', icon: '⏳', text: 'PENDING APPROVAL' },
    'APPROVED': { class: 'badge-emerald', icon: '✅', text: 'APPROVED' },
    'SCHEDULED': { class: 'badge-cyan', icon: '🕒', text: 'SCHEDULED' },
    'PUBLISHING': { class: 'badge-indigo', icon: '⚡', text: 'PUBLISHING' },
    'PUBLISHED': { class: 'badge-emerald', icon: '🚀', text: 'PUBLISHED' },
    'REJECTED': { class: 'badge-rose', icon: '❌', text: 'REJECTED' },
    'FAILED': { class: 'badge-rose', icon: '⚠️', text: 'FAILED' }
  };

  const item = map[status] || { class: 'badge-indigo', icon: '●', text: status };
  return `<span class="badge ${item.class}">${item.icon} ${item.text}</span>`;
}

export function renderPlatformBadge(platform) {
  const map = {
    'TWITTER': { icon: '🐦', label: 'X / Twitter' },
    'LINKEDIN': { icon: '💼', label: 'LinkedIn' },
    'META_FACEBOOK': { icon: '📱', label: 'Facebook' },
    'META_INSTAGRAM': { icon: '📷', label: 'Instagram' }
  };
  const item = map[platform] || { icon: '🌐', label: platform };
  return `<span class="badge badge-indigo" style="font-size: 0.7rem;">${item.icon} ${item.label}</span>`;
}
