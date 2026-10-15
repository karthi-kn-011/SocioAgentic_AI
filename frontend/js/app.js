import { toast } from './components/toast.js';
import { openModal, closeModal } from './components/modal.js';
import { initDashboardView } from './views/dashboard.js';
import { initStudioView } from './views/studio.js';
import { initApprovalsView } from './views/approvals.js';
import { initCalendarView } from './views/calendar.js';
import { initAccountsView } from './views/accounts.js';
import { initAnalyticsView } from './views/analytics.js';
import { initActivityView } from './views/activity.js';

// Expose globals for HTML inline events
window.toast = toast;
window.openModal = openModal;
window.closeModal = closeModal;

// --- Tab Navigation ---
export function switchTab(tabId) {
  // Update sidebar active link
  document.querySelectorAll('.nav-item').forEach(item => {
    if (item.dataset.tab === tabId) {
      item.classList.add('active');
    } else {
      item.classList.remove('active');
    }
  });

  // Update visible pane
  document.querySelectorAll('.view-pane').forEach(pane => {
    if (pane.id === `view-${tabId}`) {
      pane.classList.add('active');
    } else {
      pane.classList.remove('active');
    }
  });

  // Update header title
  const titles = {
    'dashboard': 'Dashboard Overview',
    'studio': 'Create Content (AI Studio)',
    'approvals': 'Review / Approvals Queue',
    'calendar': 'Content Calendar',
    'accounts': 'Social Accounts & Integrations',
    'analytics': 'Analytics & Performance',
    'activity': 'System Activity & Audit Log',
    'settings': 'Settings & System Health'
  };
  const titleEl = document.getElementById('page-title');
  if (titleEl && titles[tabId]) {
    titleEl.textContent = titles[tabId];
  }

  // Auto-close sidebar on mobile if open
  const sidebar = document.querySelector('.sidebar');
  if (sidebar && sidebar.classList.contains('open')) {
    sidebar.classList.remove('open');
  }

  // Auto-refresh dynamic queues when opened
  if (tabId === 'dashboard' && window.loadDashboardData) {
    window.loadDashboardData();
  }
  if (tabId === 'approvals' && window.refreshApprovalsList) {
    window.refreshApprovalsList();
  }
  if (tabId === 'calendar') {
    initCalendarView();
  }
  if (tabId === 'analytics' && window.loadAnalyticsData) {
    window.loadAnalyticsData();
  }
  if (tabId === 'activity' && window.loadActivityLogs) {
    window.loadActivityLogs();
  }
}

export function toggleSidebar() {
  const sidebar = document.querySelector('.sidebar');
  if (sidebar) {
    sidebar.classList.toggle('open');
  }
}

window.switchTab = switchTab;
window.toggleSidebar = toggleSidebar;


// --- Theme Management ---
export function toggleTheme() {
  const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
  const newTheme = currentTheme === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', newTheme);
  localStorage.setItem('theme', newTheme);
  
  const labelEl = document.getElementById('theme-label');
  if (labelEl) {
    labelEl.textContent = newTheme === 'light' ? '☀️ Light Mode' : '🌙 Dark Mode';
  }
  toast.show(`Switched to ${newTheme} mode`, 'info', 2000);
}

window.toggleTheme = toggleTheme;

// --- System Health Verification ---
export async function checkBackendHealth() {
  const pill = document.getElementById('system-health-pill');
  try {
    const res = await fetch('/api/v1/health');
    if (res.ok) {
      const data = await res.json();
      if (pill) {
        pill.className = 'badge badge-emerald';
        pill.innerHTML = `🟢 Backend: ${data.status.toUpperCase()} (${data.environment})`;
      }
    } else {
      if (pill) {
        pill.className = 'badge badge-rose';
        pill.innerHTML = '🔴 Backend: HTTP ' + res.status;
      }
    }
  } catch (err) {
    if (pill) {
      pill.className = 'badge badge-amber';
      pill.innerHTML = '🟡 Backend: Connecting...';
    }
  }

  // Refresh dynamic views if present
  if (window.refreshApprovalsList) window.refreshApprovalsList();
  if (window.loadSchedules && window.renderCalendar) {
    window.loadSchedules().then(() => window.renderCalendar());
  }
}

window.checkBackendHealth = checkBackendHealth;

// --- Initialize App & Views ---
document.addEventListener('DOMContentLoaded', () => {
  // Restore saved theme
  const savedTheme = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', savedTheme);
  const labelEl = document.getElementById('theme-label');
  if (labelEl) {
    labelEl.textContent = savedTheme === 'light' ? '☀️ Light Mode' : '🌙 Dark Mode';
  }

  // Setup sidebar nav click listeners
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      const tab = item.dataset.tab;
      if (tab) switchTab(tab);
    });
  });

  // Initialize View Modules
  initDashboardView();
  initStudioView();
  initApprovalsView();
  initCalendarView();
  initAccountsView();
  initAnalyticsView();
  initActivityView();

  // Initial health check
  checkBackendHealth();
});
