/**
 * Reusable Loading States & Spinners
 */

export function showButtonSpinner(buttonElement, loadingText = 'Processing...') {
  if (!buttonElement) return;
  buttonElement.dataset.originalHtml = buttonElement.innerHTML;
  buttonElement.disabled = true;
  buttonElement.innerHTML = `<span class="spinner"></span> <span>${loadingText}</span>`;
}

export function hideButtonSpinner(buttonElement) {
  if (!buttonElement) return;
  buttonElement.disabled = false;
  if (buttonElement.dataset.originalHtml) {
    buttonElement.innerHTML = buttonElement.dataset.originalHtml;
  }
}

export function renderSkeletonRows(count = 3, height = '40px') {
  return Array.from({ length: count })
    .map(() => `<div class="skeleton" style="height: ${height}; width: 100%; margin-bottom: 8px;"></div>`)
    .join('');
}
