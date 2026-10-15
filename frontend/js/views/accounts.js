import { toast } from '../components/toast.js';

let activeMessageListener = null;

/**
 * Social Accounts & Integrations View Manager
 * Handles real OAuth authorization popup, trusted origin message validation,
 * dynamic status querying, and account disconnection.
 */
export function initAccountsView() {
  loadAccountsStatus();

  document.querySelectorAll('.connect-account-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const platform = btn.dataset.platform;
      const action = btn.dataset.action || 'connect';

      if (action === 'disconnect') {
        await handleDisconnect(platform);
      } else {
        await handleConnect(platform);
      }
    });
  });
}

/**
 * Queries the backend for live connection and credential status for all platforms.
 */
export async function loadAccountsStatus() {
  try {
    const res = await fetch('/api/v1/auth/accounts');
    if (!res.ok) {
      console.warn('Failed to load accounts status:', res.status);
      return;
    }
    const data = await res.json();
    if (!data.success || !data.accounts) return;

    Object.entries(data.accounts).forEach(([platformKey, info]) => {
      updateAccountCardUI(platformKey, info);
    });
  } catch (err) {
    console.error('Error fetching social accounts status:', err);
  }
}

/**
 * Updates DOM elements for a given platform's card.
 */
function updateAccountCardUI(platform, info) {
  const btn = document.querySelector(`.connect-account-btn[data-platform="${platform}"]`);
  if (!btn) return;

  const card = btn.closest('.account-card');
  const statusPill = card?.querySelector('.account-status-pill');

  if (info.connected) {
    btn.dataset.action = 'disconnect';
    btn.textContent = 'Disconnect Account';
    btn.classList.remove('btn-primary');
    btn.classList.add('btn-secondary');

    if (statusPill) {
      statusPill.className = 'badge badge-emerald account-status-pill';
      const name = info.account_name ? `@${info.account_name}` : 'Connected';
      statusPill.textContent = `● ACTIVE (${name})`;
    }
  } else {
    btn.dataset.action = 'connect';
    btn.textContent = 'Connect Account';
    btn.classList.remove('btn-secondary');
    btn.classList.add('btn-primary');

    if (statusPill) {
      statusPill.className = 'badge badge-zinc account-status-pill';
      statusPill.textContent = '○ NOT CONNECTED';
    }
  }
}

/**
 * Initiates the OAuth flow for a platform.
 */
async function handleConnect(platform) {
  if (platform === 'TWITTER') {
    try {
      toast.show('Generating PKCE authorization request...', 'info', 2000);
      const res = await fetch('/api/v1/auth/twitter/authorize');
      if (!res.ok) {
        throw new Error(`Failed to generate authorization URL (status: ${res.status})`);
      }
      const data = await res.json();
      if (!data.authorization_url) {
        throw new Error('No authorization URL returned from server.');
      }

      openOAuthPopup(data.authorization_url, 'TWITTER');
    } catch (err) {
      console.error('Twitter authorization error:', err);
      toast.show(`Failed to start X authorization: ${err.message}`, 'error', 4000);
    }
  } else if (platform === 'LINKEDIN') {
    try {
      toast.show('Generating LinkedIn authorization request...', 'info', 2000);
      const res = await fetch('/api/v1/auth/linkedin/authorize');
      if (!res.ok) {
        throw new Error(`Failed to generate authorization URL (status: ${res.status})`);
      }
      const data = await res.json();
      if (!data.authorization_url) {
        throw new Error('No authorization URL returned from server.');
      }

      openOAuthPopup(data.authorization_url, 'LINKEDIN');
    } catch (err) {
      console.error('LinkedIn authorization error:', err);
      toast.show(`Failed to start LinkedIn authorization: ${err.message}`, 'error', 4000);
    }
  } else if (platform === 'META_FACEBOOK') {
    try {
      toast.show('Generating Facebook Page authorization request...', 'info', 2000);
      const res = await fetch('/api/v1/auth/facebook/authorize');
      if (!res.ok) {
        throw new Error(`Failed to generate authorization URL (status: ${res.status})`);
      }
      const data = await res.json();
      if (!data.authorization_url) {
        throw new Error('No authorization URL returned from server.');
      }

      openOAuthPopup(data.authorization_url, 'META_FACEBOOK');
    } catch (err) {
      console.error('Facebook authorization error:', err);
      toast.show(`Failed to start Facebook Page authorization: ${err.message}`, 'error', 4000);
    }
  } else if (platform === 'META_INSTAGRAM') {
    try {
      toast.show('Generating Instagram Business authorization request...', 'info', 2000);
      const res = await fetch('/api/v1/auth/instagram/authorize');
      if (!res.ok) {
        throw new Error(`Failed to generate authorization URL (status: ${res.status})`);
      }
      const data = await res.json();
      if (!data.authorization_url) {
        throw new Error('No authorization URL returned from server.');
      }

      openOAuthPopup(data.authorization_url, 'META_INSTAGRAM');
    } catch (err) {
      console.error('Instagram authorization error:', err);
      toast.show(`Failed to start Instagram authorization: ${err.message}`, 'error', 4000);
    }
  } else {
    toast.show(`${platform} OAuth integration will be available in the upcoming phase.`, 'info', 3000);
  }
}

/**
 * Handles account disconnection.
 */
async function handleDisconnect(platform) {
  if (platform === 'TWITTER') {
    try {
      const res = await fetch('/api/v1/auth/twitter/disconnect', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        toast.show('X (Twitter) account disconnected.', 'success', 3000);
        await loadAccountsStatus();
      } else {
        toast.show('Failed to disconnect account.', 'error', 3000);
      }
    } catch (err) {
      console.error('Error disconnecting Twitter account:', err);
      toast.show('Network error while disconnecting account.', 'error', 3000);
    }
  } else if (platform === 'LINKEDIN') {
    try {
      const res = await fetch('/api/v1/auth/linkedin/disconnect', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        toast.show('LinkedIn account disconnected.', 'success', 3000);
        await loadAccountsStatus();
      } else {
        toast.show('Failed to disconnect LinkedIn account.', 'error', 3000);
      }
    } catch (err) {
      console.error('Error disconnecting LinkedIn account:', err);
      toast.show('Network error while disconnecting LinkedIn account.', 'error', 3000);
    }
  } else if (platform === 'META_FACEBOOK') {
    try {
      const res = await fetch('/api/v1/auth/facebook/disconnect', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        toast.show('Facebook Page disconnected.', 'success', 3000);
        await loadAccountsStatus();
      } else {
        toast.show('Failed to disconnect Facebook Page.', 'error', 3000);
      }
    } catch (err) {
      console.error('Error disconnecting Facebook Page:', err);
      toast.show('Network error while disconnecting Facebook Page.', 'error', 3000);
    }
  } else if (platform === 'META_INSTAGRAM') {
    try {
      const res = await fetch('/api/v1/auth/instagram/disconnect', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        toast.show('Instagram Business account disconnected.', 'success', 3000);
        await loadAccountsStatus();
      } else {
        toast.show('Failed to disconnect Instagram Business account.', 'error', 3000);
      }
    } catch (err) {
      console.error('Error disconnecting Instagram Business account:', err);
      toast.show('Network error while disconnecting Instagram Business account.', 'error', 3000);
    }
  } else {
    toast.show(`${platform} account is not currently connected.`, 'info', 2000);
  }
}

/**
 * Opens an OAuth popup with strict bidirectional origin validation.
 */
function openOAuthPopup(authUrl, platform) {
  // Clean up any existing active listener
  if (activeMessageListener) {
    window.removeEventListener('message', activeMessageListener);
    activeMessageListener = null;
  }

  const width = 600;
  const height = 720;
  const left = window.screenX + (window.outerWidth - width) / 2;
  const top = window.screenY + (window.outerHeight - height) / 2;
  const popup = window.open(
    authUrl,
    `oauth_${platform}`,
    `width=${width},height=${height},left=${left},top=${top},scrollbars=yes,status=no,resizable=yes`
  );

  activeMessageListener = function (event) {
    // 1. Strict Origin Validation: Never accept messages from untrusted origins
    if (event.origin !== window.location.origin) {
      console.warn('Discarded message from untrusted origin:', event.origin);
      return;
    }

    // 2. Validate Message Schema
    const payload = event.data;
    if (!payload || payload.type !== 'SOCIAL_AGENT_OAUTH_CALLBACK') {
      return;
    }

    if (payload.platform !== platform) {
      return;
    }

    // 3. Remove listener and close popup
    window.removeEventListener('message', activeMessageListener);
    activeMessageListener = null;

    if (popup && !popup.closed) {
      try {
        popup.close();
      } catch (e) {
        // Ignore popup close permissions errors
      }
    }

    // 4. Update UI
    if (payload.status === 'SUCCESS') {
      toast.show(`Successfully authenticated @${payload.accountName || platform}!`, 'success', 4000);
      loadAccountsStatus();
    } else {
      toast.show(`Authentication failed: ${payload.error || 'User cancelled'}`, 'error', 5000);
      loadAccountsStatus();
    }
  };

  window.addEventListener('message', activeMessageListener);
}
