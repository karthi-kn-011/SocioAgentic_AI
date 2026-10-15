import { toast } from '../components/toast.js';

/**
 * Social Accounts & Integrations View Manager
 */
export function initAccountsView() {
  document.querySelectorAll('.connect-account-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const platform = btn.dataset.platform;
      toast.show(`Initiating OAuth 2.0 PKCE flow for ${platform}... (Sandbox Simulator Active)`, 'info', 2500);
      
      setTimeout(() => {
        btn.textContent = '✅ Connected (Sandbox)';
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-secondary');
        const card = btn.closest('.account-card');
        const statusPill = card?.querySelector('.account-status-pill');
        if (statusPill) {
          statusPill.className = 'badge badge-emerald account-status-pill';
          statusPill.textContent = '● ACTIVE';
        }
        toast.show(`Successfully authenticated @${platform.toLowerCase()}_brand!`, 'success');
      }, 800);
    });
  });
}
