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

// --- Operator Authentication State ---
let isOperatorAuthenticated = false;
export function isUserAuthenticated() {
  return isOperatorAuthenticated;
}
window.isUserAuthenticated = isUserAuthenticated;

// --- CSRF & Global Fetch Interceptor ---
export function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^|;\\s*)(' + name + ')=([^;]*)'));
  return match ? decodeURIComponent(match[3]) : null;
}

const originalFetch = window.fetch;
window.fetch = async function(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
    const csrfToken = getCookie('XSRF-TOKEN');
    if (csrfToken) {
      if (!options.headers) {
        options.headers = {};
      }
      if (options.headers instanceof Headers) {
        if (!options.headers.has('X-CSRF-Token')) options.headers.set('X-CSRF-Token', csrfToken);
      } else if (Array.isArray(options.headers)) {
        options.headers.push(['X-CSRF-Token', csrfToken]);
      } else {
        options.headers['X-CSRF-Token'] = csrfToken;
      }
    }
  }

  const response = await originalFetch.call(this, url, options);

  // If session expired during operation, show login modal
  if (response.status === 401 && !url.includes('/api/v1/auth/login') && !url.includes('/api/v1/auth/session')) {
    isOperatorAuthenticated = false;
    showOperatorLoginModal('Session expired. Please authenticate to continue.');
  }

  return response;
};

// --- Operator Authentication Lifecycle ---
export async function checkAuthSession() {
  try {
    const res = await originalFetch('/api/v1/auth/session');
    if (res.ok) {
      const data = await res.json();
      if (data.authenticated && data.user) {
        setOperatorLoggedInState(data.user);
        return true;
      }
    }
  } catch (err) {
    console.warn('Session verification error:', err);
  }
  showOperatorLoginModal();
  return false;
}

export function setOperatorLoggedInState(username) {
  isOperatorAuthenticated = true;
  const modal = document.getElementById('operator-login-modal');
  if (modal) {
    modal.style.display = 'none';
    modal.classList.remove('open');
  }

  const badge = document.getElementById('operator-session-badge');
  const userLabel = document.getElementById('operator-name-display');
  const logoutBtn = document.getElementById('operator-logout-btn');

  if (badge && userLabel && logoutBtn) {
    userLabel.textContent = username;
    badge.style.display = 'inline-flex';
    logoutBtn.style.display = 'inline-flex';
  }
}

export function showOperatorLoginModal(errorMsg = '') {
  isOperatorAuthenticated = false;
  const modal = document.getElementById('operator-login-modal');
  const errorAlert = document.getElementById('login-error-alert');
  const badge = document.getElementById('operator-session-badge');
  const logoutBtn = document.getElementById('operator-logout-btn');

  if (badge) badge.style.display = 'none';
  if (logoutBtn) logoutBtn.style.display = 'none';

  if (errorAlert) {
    if (errorMsg) {
      errorAlert.textContent = errorMsg;
      errorAlert.style.display = 'block';
    } else {
      errorAlert.style.display = 'none';
    }
  }

  if (modal) {
    modal.style.display = 'flex';
    modal.classList.add('open');
  }
}

export async function handleOperatorLogout() {
  isOperatorAuthenticated = false;
  try {
    await fetch('/api/v1/auth/logout', { method: 'POST' });
    toast.show('Signed out successfully', 'info');
  } catch (e) {
    // Ignore error on logout
  }
  showOperatorLoginModal();
}

window.handleOperatorLogout = handleOperatorLogout;
window.checkAuthSession = checkAuthSession;
window.showOperatorLoginModal = showOperatorLoginModal;

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

  // Auto-refresh dynamic queues when opened (only if authenticated)
  if (isOperatorAuthenticated) {
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

  // Dynamic view refreshes are handled on auth lifecycle and tab navigation
}

window.checkBackendHealth = checkBackendHealth;

// --- Initialize App & Views ---
document.addEventListener('DOMContentLoaded', async () => {
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

  // Setup login form listener
  const loginForm = document.getElementById('operator-login-form');
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const usernameInput = document.getElementById('login-username');
      const passwordInput = document.getElementById('login-password');
      const errorAlert = document.getElementById('login-error-alert');
      const submitBtn = document.getElementById('login-submit-btn');

      if (!usernameInput || !passwordInput) return;

      if (submitBtn) submitBtn.disabled = true;
      if (errorAlert) errorAlert.style.display = 'none';

      try {
        const res = await originalFetch('/api/v1/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: usernameInput.value.trim(),
            password: passwordInput.value,
          })
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          const msg = errData.detail || 'Authentication failed. Please verify credentials.';
          showOperatorLoginModal(msg);
          return;
        }

        const data = await res.json();
        setOperatorLoggedInState(data.user);
        toast.show(`Welcome, ${data.user}`, 'success');

        // Re-load current active tab
        if (window.loadDashboardData) window.loadDashboardData();
        if (window.refreshApprovalsList) window.refreshApprovalsList();
      } catch (err) {
        showOperatorLoginModal('Network error during authentication.');
      } finally {
        if (submitBtn) submitBtn.disabled = false;
        passwordInput.value = '';
      }
    });
  }

  // Initial session & health check
  checkBackendHealth();
  const authenticated = await checkAuthSession();
  if (authenticated) {
    if (window.loadDashboardData) window.loadDashboardData();
    if (window.refreshApprovalsList) window.refreshApprovalsList();
  }
});
