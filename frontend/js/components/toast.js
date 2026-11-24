/**
 * Reusable Toast Notification System with Deduplication and Bounded Stacking
 */
class ToastManager {
  constructor() {
    this.container = document.querySelector('.toast-container');
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.className = 'toast-container';
      document.body.appendChild(this.container);
    }
    this.activeToasts = new Map(); // key -> { element, timeoutId }
    this.maxVisible = 3;
  }

  show(message, type = 'info', duration = 4000) {
    if (!message || typeof message !== 'string') return;
    const cleanMsg = message.trim();
    const key = `${type}:${cleanMsg}`;

    // Deduplication: If identical toast is already active, reset its timer and do not duplicate
    if (this.activeToasts.has(key)) {
      const existing = this.activeToasts.get(key);
      if (existing && existing.element && existing.element.isConnected) {
        clearTimeout(existing.timeoutId);
        existing.timeoutId = setTimeout(() => this._removeToast(key), duration);
        return;
      }
      this.activeToasts.delete(key);
    }

    // Bound maximum simultaneous toasts down the screen
    while (this.container.children.length >= this.maxVisible) {
      const oldest = this.container.firstElementChild;
      if (oldest && oldest._toastKey) {
        this._removeToast(oldest._toastKey);
      } else if (oldest) {
        oldest.remove();
      } else {
        break;
      }
    }

    const toastEl = document.createElement('div');
    toastEl.className = `toast toast-${type}`;
    toastEl._toastKey = key;

    const icon = type === 'success' ? '✅' : (type === 'error' ? '❌' : 'ℹ️');
    toastEl.innerHTML = `
      <span style="font-size: 1.1rem;">${icon}</span>
      <div style="flex: 1;">${cleanMsg}</div>
      <button style="opacity: 0.6; font-size: 1rem; cursor: pointer; background: transparent; border: none; color: inherit;" aria-label="Close">✕</button>
    `;

    const closeBtn = toastEl.querySelector('button');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => this._removeToast(key));
    }

    this.container.appendChild(toastEl);

    const timeoutId = setTimeout(() => this._removeToast(key), duration);
    this.activeToasts.set(key, { element: toastEl, timeoutId });
  }

  _removeToast(key) {
    const entry = this.activeToasts.get(key);
    if (entry) {
      clearTimeout(entry.timeoutId);
      this.activeToasts.delete(key);
      if (entry.element && entry.element.isConnected) {
        entry.element.style.transition = 'opacity 200ms ease, transform 200ms ease';
        entry.element.style.opacity = '0';
        entry.element.style.transform = 'translateX(50px)';
        setTimeout(() => entry.element.remove(), 200);
      }
    }
  }

  clear() {
    for (const key of Array.from(this.activeToasts.keys())) {
      this._removeToast(key);
    }
  }
}

export const toast = new ToastManager();
