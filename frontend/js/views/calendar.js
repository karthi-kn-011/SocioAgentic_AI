import { toast } from '../components/toast.js';

let currentDate = new Date();
let selectedDate = new Date();
let currentViewMode = 'month'; // 'month' | 'list'
let cachedSchedules = [];
let selectedDailyScheduleId = null;
let currentCalendarTimezone = 'Asia/Kolkata';

const PLATFORM_COLORS = {
  TWITTER: '#1d9bf0',
  LINKEDIN: '#0a66c2',
  FACEBOOK: '#1877f2',
  INSTAGRAM: '#e1306c',
};

const PLATFORM_ICONS = {
  TWITTER: '🐦',
  LINKEDIN: '💼',
  FACEBOOK: '📱',
  INSTAGRAM: '📷',
};

/**
 * Set active calendar display timezone (e.g. 'Asia/Kolkata', 'UTC').
 */
export function setCalendarTimezone(tz) {
  currentCalendarTimezone = tz || 'Asia/Kolkata';
  renderCalendar();
}

/**
 * Helper to compute YYYY-MM-DD key for a schedule in the target display timezone.
 */
export function getScheduleDayKey(item, targetTz) {
  if (!item || !item.scheduled_at) return '';
  let str = item.scheduled_at;
  if (!str.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(str)) {
    str += 'Z';
  }
  const dt = new Date(str);
  if (isNaN(dt.getTime())) return '';
  const tz = targetTz || currentCalendarTimezone || item.timezone || 'UTC';
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: tz,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    }).format(dt);
  } catch (e) {
    const y = dt.getUTCFullYear();
    const m = String(dt.getUTCMonth() + 1).padStart(2, '0');
    const d = String(dt.getUTCDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }
}

/**
 * Format a schedule's time display using the calendar's display timezone.
 */
export function formatScheduleTime(item, targetTz) {
  if (!item || !item.scheduled_at) return 'N/A';
  let str = item.scheduled_at;
  if (!str.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(str)) {
    str += 'Z';
  }
  const dt = new Date(str);
  if (isNaN(dt.getTime())) return 'N/A';
  const tz = targetTz || currentCalendarTimezone || item.timezone || 'UTC';
  try {
    return dt.toLocaleTimeString([], {
      timeZone: tz,
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch (e) {
    return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
}

/**
 * Format date and time with timezone for details display.
 */
export function formatScheduleDateTime(item, targetTz) {
  if (!item || !item.scheduled_at) return 'N/A';
  let str = item.scheduled_at;
  if (!str.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(str)) {
    str += 'Z';
  }
  const dt = new Date(str);
  if (isNaN(dt.getTime())) return 'N/A';
  const tz = targetTz || currentCalendarTimezone || item.timezone || 'UTC';
  try {
    return dt.toLocaleString([], {
      timeZone: tz,
      weekday: 'short',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    }) + ` (${tz})`;
  } catch (e) {
    return dt.toLocaleString() + ` (${tz})`;
  }
}

/**
 * Initialize calendar view.
 */
export async function initCalendarView() {
  await loadSchedules();
  renderCalendar();
}

/**
 * Fetch schedules from the backend API.
 */
export async function loadSchedules() {
  try {
    const res = await fetch('/api/v1/schedules');
    if (res.ok) {
      const data = await res.json();
      cachedSchedules = data.data || [];
    } else {
      console.error('Failed to fetch schedules');
    }
  } catch (err) {
    console.error('Network error fetching schedules:', err);
  }
}

/**
 * Set view mode ('month' or 'list')
 */
export function setCalendarViewMode(mode) {
  currentViewMode = mode;
  const btnMonth = document.getElementById('btn-calendar-month-view');
  const btnList = document.getElementById('btn-calendar-list-view');

  if (btnMonth && btnList) {
    if (mode === 'month') {
      btnMonth.classList.add('active');
      btnList.classList.remove('active');
    } else {
      btnMonth.classList.remove('active');
      btnList.classList.add('active');
    }
  }
  renderCalendar();
}

/**
 * Navigate calendar months (-1 for prev, +1 for next, 0 for today).
 */
export function navigateCalendar(direction) {
  if (direction === 0) {
    currentDate = new Date();
    selectedDate = new Date();
  } else {
    currentDate.setMonth(currentDate.getMonth() + direction);
    // If selected date is outside the new month, adjust to 1st of that month
    selectedDate = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
  }
  selectedDailyScheduleId = null;
  renderCalendar();
}

/**
 * Main render function dispatching between month view and list view.
 */
export function renderCalendar() {
  const monthTitle = document.getElementById('calendar-month-title');
  const monthName = currentDate.toLocaleString('default', { month: 'long', year: 'numeric' });
  if (monthTitle) {
    monthTitle.innerHTML = `📅 Content Calendar &mdash; <span style="color: var(--color-primary);">${monthName}</span>`;
  }

  const grid = document.getElementById('calendar-grid');
  const selectedDayPanel = document.getElementById('selected-day-panel');
  const listContainer = document.getElementById('calendar-list-container');

  if (selectedDayPanel) selectedDayPanel.style.display = 'none';

  if (currentViewMode === 'month') {
    if (grid) grid.style.display = 'grid';
    if (listContainer) listContainer.style.display = 'none';
    renderMonthGrid();
  } else {
    if (grid) grid.style.display = 'none';
    if (listContainer) listContainer.style.display = 'block';
    renderListView();
  }
}

/**
 * Select a specific calendar day (retained for backward compatibility).
 */
export function selectCalendarDay(date) {
  let dateKey = '';
  if (typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
    dateKey = date;
    const parts = date.split('-');
    selectedDate = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  } else {
    selectedDate = new Date(date);
    const year = selectedDate.getFullYear();
    const month = String(selectedDate.getMonth() + 1).padStart(2, '0');
    const d = String(selectedDate.getDate()).padStart(2, '0');
    dateKey = `${year}-${month}-${d}`;
  }

  document.querySelectorAll('.calendar-cell').forEach(c => c.classList.remove('selected-day'));
  const cell = document.querySelector(`.calendar-cell[data-date="${dateKey}"]`);
  if (cell) cell.classList.add('selected-day');

  // Trigger floating popover for this day if it has schedules
  const matchingSchedules = cachedSchedules.filter(s => getScheduleDayKey(s, currentCalendarTimezone) === dateKey);
  if (matchingSchedules.length > 0 && cell) {
    showSchedulePopover(cell, dateKey, matchingSchedules);
  }
}

/**
 * Select a day and immediately highlight a specific task.
 */
export function selectCalendarDayWithTask(date, scheduleId) {
  openScheduleDetailModal(scheduleId);
}

// Hover popover timers
let popoverHoverTimer = null;
let popoverHideTimer = null;
let activePopoverDateKey = null;

/**
 * Renders the 7-column Monday-first month grid with balanced fixed-height cells.
 */
function renderMonthGrid() {
  const grid = document.getElementById('calendar-grid');
  if (!grid) return;

  grid.innerHTML = '';

  // Monday to Sunday standard week header
  const daysOfWeek = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  daysOfWeek.forEach(day => {
    const header = document.createElement('div');
    header.className = 'calendar-header-day';
    header.textContent = day;
    grid.appendChild(header);
  });

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  // First day of current month (0=Sun, 1=Mon, ..., 6=Sat)
  const firstDay = new Date(year, month, 1).getDay();
  // Monday-first index: Mon=0, Tue=1, ..., Sun=6
  const leadingDaysCount = (firstDay + 6) % 7;

  const totalDays = new Date(year, month + 1, 0).getDate();
  const prevMonthTotalDays = new Date(year, month, 0).getDate();

  const today = new Date();
  const isCurrentMonth = today.getFullYear() === year && today.getMonth() === month;

  // Pre-index schedules by dateKey in currentCalendarTimezone
  const schedulesByDay = new Map();
  cachedSchedules.forEach(s => {
    const key = getScheduleDayKey(s, currentCalendarTimezone);
    if (key) {
      if (!schedulesByDay.has(key)) schedulesByDay.set(key, []);
      schedulesByDay.get(key).push(s);
    }
  });

  // Sort each day's schedules chronologically
  schedulesByDay.forEach(list => {
    list.sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at));
  });

  // Helper to attach hover/click listeners
  function attachCellListeners(cell, dateKey, schedules) {
    if (!schedules || schedules.length === 0) return;

    cell.addEventListener('mouseenter', () => {
      clearTimeout(popoverHideTimer);
      clearTimeout(popoverHoverTimer);
      popoverHoverTimer = setTimeout(() => {
        showSchedulePopover(cell, dateKey, schedules);
      }, 70);
    });

    cell.addEventListener('mouseleave', (e) => {
      clearTimeout(popoverHoverTimer);
      const popover = document.getElementById('calendar-schedule-popover');
      if (popover && e.relatedTarget && (popover === e.relatedTarget || popover.contains(e.relatedTarget))) {
        return; // Moving into popover
      }
      scheduleHidePopover();
    });

    cell.addEventListener('click', (e) => {
      if (e.target.closest('.calendar-micro-chip')) return; // Handled by chip click
      showSchedulePopover(cell, dateKey, schedules);
    });
  }

  // 1. Leading cells from previous month
  const prevMonthYear = month === 0 ? year - 1 : year;
  const prevMonthIndex = month === 0 ? 11 : month - 1;
  for (let i = leadingDaysCount - 1; i >= 0; i--) {
    const prevDayNum = prevMonthTotalDays - i;
    const prevDate = new Date(prevMonthYear, prevMonthIndex, prevDayNum);
    const dateKey = `${prevMonthYear}-${String(prevMonthIndex + 1).padStart(2, '0')}-${String(prevDayNum).padStart(2, '0')}`;
    
    const cell = document.createElement('div');
    cell.className = 'calendar-cell other-month';
    cell.dataset.date = dateKey;

    const matchingSchedules = schedulesByDay.get(dateKey) || [];
    cell.innerHTML = buildCellHtml(prevDayNum, matchingSchedules, prevDate, dateKey);
    attachCellListeners(cell, dateKey, matchingSchedules);
    grid.appendChild(cell);
  }

  // 2. Days of current month
  for (let d = 1; d <= totalDays; d++) {
    const cell = document.createElement('div');
    const cellDate = new Date(year, month, d);
    const dateKey = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    cell.dataset.date = dateKey;

    const isToday = isCurrentMonth && today.getDate() === d;
    const isPast = new Date(year, month, d, 23, 59, 59, 999) < today;

    cell.className = `calendar-cell ${isToday ? 'today' : ''} ${isPast ? 'past-day' : ''}`;

    const matchingSchedules = schedulesByDay.get(dateKey) || [];
    cell.innerHTML = buildCellHtml(d, matchingSchedules, cellDate, dateKey);
    attachCellListeners(cell, dateKey, matchingSchedules);
    grid.appendChild(cell);
  }

  // 3. Trailing cells to fill the complete 7-column grid
  const totalCellsSoFar = leadingDaysCount + totalDays;
  const targetTotalCells = totalCellsSoFar <= 35 ? 35 : 42; // standard 5 or 6 rows
  const trailingDaysCount = targetTotalCells - totalCellsSoFar;

  const nextMonthYear = month === 11 ? year + 1 : year;
  const nextMonthIndex = month === 11 ? 0 : month + 1;
  for (let d = 1; d <= trailingDaysCount; d++) {
    const nextDate = new Date(nextMonthYear, nextMonthIndex, d);
    const dateKey = `${nextMonthYear}-${String(nextMonthIndex + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;

    const cell = document.createElement('div');
    cell.className = 'calendar-cell other-month';
    cell.dataset.date = dateKey;

    const matchingSchedules = schedulesByDay.get(dateKey) || [];
    cell.innerHTML = buildCellHtml(d, matchingSchedules, nextDate, dateKey);
    attachCellListeners(cell, dateKey, matchingSchedules);
    grid.appendChild(cell);
  }

  setupPopoverHoverEvents();
}

/**
 * Setup hover event listeners on the popover container itself.
 */
function setupPopoverHoverEvents() {
  const popover = document.getElementById('calendar-schedule-popover');
  if (!popover || popover._hoverInitialized) return;

  popover.addEventListener('mouseenter', () => {
    clearTimeout(popoverHideTimer);
  });

  popover.addEventListener('mouseleave', () => {
    scheduleHidePopover();
  });

  popover._hoverInitialized = true;
}

function scheduleHidePopover() {
  clearTimeout(popoverHideTimer);
  popoverHideTimer = setTimeout(() => {
    hideSchedulePopover();
  }, 140);
}

/**
 * Builds HTML inside a calendar cell (header, micro-chips, mathematically precise +N more).
 */
function buildCellHtml(dayNum, schedules, dateObj, dateKey) {
  const visibleLimit = 2;
  const totalCount = schedules.length;
  const visibleSchedules = schedules.slice(0, visibleLimit);
  const moreCount = totalCount - visibleLimit;

  let microChipsHtml = '';
  let mobileDotsHtml = '';

  visibleSchedules.forEach(item => {
    const platformKey = (item.platform || 'TWITTER').toUpperCase();
    const color = PLATFORM_COLORS[platformKey] || 'var(--color-primary)';
    const icon = PLATFORM_ICONS[platformKey] || '📢';
    const timeStr = formatScheduleTime(item, currentCalendarTimezone);
    const titleSnippet = escapeHtml(item.post_theme || item.post_topic || item.post_content || 'Post').substring(0, 14);

    microChipsHtml += `
      <div class="calendar-micro-chip"
           data-schedule-id="${item.id}"
           onclick="event.stopPropagation(); window.openScheduleDetailModal && window.openScheduleDetailModal(${item.id})"
           style="border-left-color: ${color};"
           title="${escapeHtml(item.post_content || item.post_theme || 'Post')} (${item.status})">
        <span>${icon}</span>
        <span style="font-weight: 600; opacity: 0.9;">${timeStr}</span>
        <span style="overflow: hidden; text-overflow: ellipsis;">${titleSnippet}</span>
      </div>
    `;
  });

  // Mathematically precise +N more calculation
  if (moreCount > 0) {
    microChipsHtml += `
      <div class="calendar-micro-more"
           onclick="event.stopPropagation(); window.triggerPopoverForDate && window.triggerPopoverForDate(event, '${dateKey}')">
        +${moreCount} more
      </div>
    `;
  }

  // Mobile dots (up to 3 indicator dots)
  schedules.slice(0, 3).forEach(item => {
    const platformKey = (item.platform || 'TWITTER').toUpperCase();
    const color = PLATFORM_COLORS[platformKey] || 'var(--color-primary)';
    mobileDotsHtml += `<span class="calendar-dot" style="background-color: ${color};"></span>`;
  });

  return `
    <div class="calendar-cell-header">
      <span class="calendar-date-num">${dayNum}</span>
      ${totalCount > 0 ? `<span class="calendar-count-badge">${totalCount}</span>` : ''}
    </div>
    <div class="calendar-events-wrapper">
      ${microChipsHtml}
    </div>
    <div class="calendar-mobile-dots">
      ${mobileDotsHtml}
    </div>
  `;
}

/**
 * Trigger popover display explicitly for a given date key (e.g. clicking +N more).
 */
export function triggerPopoverForDate(event, dateKey) {
  if (event) event.stopPropagation();
  const cell = document.querySelector(`.calendar-cell[data-date="${dateKey}"]`);
  const matchingSchedules = cachedSchedules.filter(s => getScheduleDayKey(s, currentCalendarTimezone) === dateKey);
  matchingSchedules.sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at));
  if (matchingSchedules.length > 0 && cell) {
    showSchedulePopover(cell, dateKey, matchingSchedules);
  }
}

/**
 * Show floating schedule preview popover near anchor element with smart positioning.
 */
export function showSchedulePopover(anchorEl, dateKey, schedules) {
  const popover = document.getElementById('calendar-schedule-popover');
  const titleEl = document.getElementById('popover-date-title');
  const countBadgeEl = document.getElementById('popover-count-badge');
  const listEl = document.getElementById('popover-schedule-list');

  if (!popover || !listEl || !schedules || schedules.length === 0) return;

  clearTimeout(popoverHideTimer);
  activePopoverDateKey = dateKey;

  // Format date header nicely
  let formattedDate = dateKey;
  try {
    const parts = dateKey.split('-');
    const dt = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    formattedDate = dt.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
  } catch (e) {}

  if (titleEl) titleEl.textContent = `Scheduled Posts (${formattedDate})`;
  if (countBadgeEl) countBadgeEl.textContent = `${schedules.length} post${schedules.length === 1 ? '' : 's'}`;

  // Populate selectable options
  let itemsHtml = '';
  schedules.forEach(item => {
    const platformKey = (item.platform || 'TWITTER').toUpperCase();
    const color = PLATFORM_COLORS[platformKey] || 'var(--color-primary)';
    const icon = PLATFORM_ICONS[platformKey] || '📢';
    const timeStr = formatScheduleTime(item, currentCalendarTimezone);
    const title = escapeHtml(item.post_theme || item.post_topic || `${item.platform || 'Post'} Publication #${item.id}`);

    let statusBadgeClass = 'badge-indigo';
    if (item.status === 'PUBLISHED') statusBadgeClass = 'badge-emerald';
    else if (item.status === 'PUBLISHING') statusBadgeClass = 'badge-amber';
    else if (item.status === 'PUBLISH_FAILED') statusBadgeClass = 'badge-danger';
    else if (item.status === 'CANCELLED') statusBadgeClass = 'badge-gray';

    itemsHtml += `
      <div class="popover-schedule-item"
           data-schedule-id="${item.id}"
           onclick="event.stopPropagation(); window.openScheduleDetailModal && window.openScheduleDetailModal(${item.id})"
           role="button"
           tabindex="0"
           style="border-left: 3px solid ${color};">
        <div class="popover-item-top">
          <span class="popover-item-time">🕒 ${timeStr}</span>
          <span class="badge ${statusBadgeClass}" style="font-size: 10px; padding: 1px 6px;">${item.status}</span>
        </div>
        <div class="popover-item-title">${title}</div>
        <div class="popover-item-footer">
          <span>${icon} ${escapeHtml(item.platform || 'TWITTER')}</span>
          <span style="font-size: 10px; color: var(--color-primary); font-weight: 600;">View Details &rarr;</span>
        </div>
      </div>
    `;
  });

  listEl.innerHTML = itemsHtml;

  // Make popover temporarily display block to measure dimensions
  popover.style.display = 'block';
  popover.classList.remove('popover-hiding');

  // Smart Collision Detection & Positioning
  const anchorRect = anchorEl.getBoundingClientRect();
  const popoverWidth = 295;
  const popoverHeight = Math.min(popover.offsetHeight || 220, 320);

  // Horizontal calculation: center or align with anchor, ensure within viewport
  let left = anchorRect.left + (anchorRect.width / 2) - (popoverWidth / 2);
  if (left + popoverWidth > window.innerWidth - 16) {
    left = window.innerWidth - popoverWidth - 16;
  }
  if (left < 16) {
    left = 16;
  }

  // Vertical calculation: prefer bottom; if overflowing viewport bottom, place top
  let top = anchorRect.bottom + 8;
  if (top + popoverHeight > window.innerHeight - 16) {
    top = anchorRect.top - popoverHeight - 8;
    if (top < 16) {
      top = Math.max(16, (window.innerHeight - popoverHeight) / 2);
    }
  }

  popover.style.left = `${Math.round(left)}px`;
  popover.style.top = `${Math.round(top)}px`;

  requestAnimationFrame(() => {
    popover.classList.add('popover-visible');
  });
}

/**
 * Hides the floating schedule popover with smooth exit animation.
 */
export function hideSchedulePopover(immediate = false) {
  const popover = document.getElementById('calendar-schedule-popover');
  if (!popover) return;

  clearTimeout(popoverHoverTimer);
  clearTimeout(popoverHideTimer);
  activePopoverDateKey = null;

  if (immediate) {
    popover.classList.remove('popover-visible', 'popover-hiding');
    popover.style.display = 'none';
  } else {
    popover.classList.add('popover-hiding');
    popover.classList.remove('popover-visible');
    setTimeout(() => {
      if (popover.classList.contains('popover-hiding')) {
        popover.style.display = 'none';
        popover.classList.remove('popover-hiding');
      }
    }, 140);
  }
}

// Modal view transition state
let currentActiveScheduleId = null;
let modalCurrentView = 'detail'; // 'detail' | 'reschedule'
let isModalTransitioning = false;

/**
 * Full-Screen Modern SaaS Schedule Detail Modal.
 * Opens when a schedule is selected from popover or clicked directly.
 */
export async function openScheduleDetailModal(scheduleId) {
  hideSchedulePopover(true);
  currentActiveScheduleId = scheduleId;
  modalCurrentView = 'detail';
  isModalTransitioning = false;

  const backdrop = document.getElementById('schedule-detail-modal-backdrop');
  const viewDetail = document.getElementById('modal-view-detail');
  const viewReschedule = document.getElementById('modal-view-reschedule');
  const viewLogs = document.getElementById('modal-view-logs');

  if (viewDetail) {
    viewDetail.style.display = 'flex';
    viewDetail.className = 'modal-view-pane active';
  }
  if (viewReschedule) {
    viewReschedule.style.display = 'none';
    viewReschedule.className = 'modal-view-pane';
  }
  if (viewLogs) {
    viewLogs.style.display = 'none';
    viewLogs.className = 'modal-view-pane';
  }

  const titleEl = document.getElementById('modal-schedule-title');
  const metaEl = document.getElementById('modal-schedule-meta');
  const iconEl = document.getElementById('modal-platform-icon');
  const statusEl = document.getElementById('modal-status-badge');
  const bodyEl = document.getElementById('schedule-modal-body');
  const footerEl = document.getElementById('schedule-modal-footer');

  if (!backdrop) return;

  let item = cachedSchedules.find(s => s.id === scheduleId);
  if (!item) {
    try {
      const res = await fetch(`/api/v1/schedules/${scheduleId}`);
      if (res.ok) {
        item = await res.json();
      }
    } catch (e) {
      console.error('Error fetching schedule details:', e);
    }
  }

  if (!item) {
    toast.show('Schedule details not found.', 'warning');
    return;
  }

  const platformKey = (item.platform || 'TWITTER').toUpperCase();
  const icon = PLATFORM_ICONS[platformKey] || '📢';
  const timeFormatted = formatScheduleDateTime(item, currentCalendarTimezone);
  const content = item.post_content || item.post_theme || 'No content available';
  const charCount = content.length;
  const title = item.post_theme || item.post_topic || `${item.platform || 'Post'} Publication #${item.id}`;

  if (iconEl) iconEl.textContent = icon;
  if (titleEl) titleEl.textContent = title;
  if (metaEl) metaEl.textContent = `Schedule #${item.id} • Post #${item.post_id || 'N/A'} • Scheduled: ${timeFormatted}`;

  let badgeClass = 'badge-indigo';
  if (item.status === 'PUBLISHED') badgeClass = 'badge-emerald';
  else if (item.status === 'PUBLISHING') badgeClass = 'badge-amber';
  else if (item.status === 'PUBLISH_FAILED') badgeClass = 'badge-danger';
  else if (item.status === 'CANCELLED') badgeClass = 'badge-gray';

  if (statusEl) {
    statusEl.className = `badge ${badgeClass}`;
    statusEl.textContent = item.status;
  }

  const targetPlatforms = (item.target_platforms && item.target_platforms.length > 0)
    ? item.target_platforms
    : [item.platform || 'TWITTER'];

  const platformBadgesHtml = targetPlatforms.map(p => {
    const pKey = (p || '').toUpperCase();
    const pIcon = PLATFORM_ICONS[pKey] || '📢';
    const isActive = pKey === platformKey;
    return `
      <span class="badge ${isActive ? 'badge-primary' : 'badge-gray'}" style="display: inline-flex; align-items: center; gap: 4px; font-size: 11px; padding: 3px 8px; ${isActive ? 'border: 1px solid var(--color-primary); font-weight: 700;' : ''}">
        ${pIcon} ${escapeHtml(p)}
        ${isActive ? '<span style="font-size: 9px; opacity: 0.85; margin-left: 2px;">(Active Task)</span>' : ''}
      </span>
    `;
  }).join(' ');

  // Multi-platform content copy renderer
  let contentCardHtml = '';
  if (targetPlatforms.length <= 1) {
    contentCardHtml = `
      <!-- 2. Post Content Card (Single Platform) -->
      <div class="modal-card">
        <div class="modal-card-header">
          <span class="modal-card-title">📝 ${icon} ${escapeHtml(targetPlatforms[0] || item.platform || 'TWITTER')} Content Copy</span>
          <span class="badge badge-gray" style="font-size: 11px;">${charCount} characters</span>
        </div>
        <div class="modal-post-copy-box">${escapeHtml(content)}</div>
      </div>
    `;
  } else {
    contentCardHtml = `
      <!-- 2. Multi-Platform Content Card -->
      <div class="modal-card">
        <div class="modal-card-header" style="flex-wrap: wrap; gap: var(--space-2); justify-content: space-between; align-items: center;">
          <span class="modal-card-title">📝 Platform-Specific Content Copies</span>
          <div class="btn-group" id="detail-platform-tab-btns" style="display: flex; gap: var(--space-1); flex-wrap: wrap;">
            ${targetPlatforms.map(p => {
              const pKey = (p || '').toUpperCase();
              const pIcon = PLATFORM_ICONS[pKey] || '📢';
              const isSelected = pKey === platformKey;
              return `
                <button class="btn btn-secondary btn-sm ${isSelected ? 'active' : ''}"
                        id="tab-btn-detail-${escapeHtml(pKey)}"
                        onclick="window.switchDetailPlatformTab && window.switchDetailPlatformTab('${escapeHtml(pKey)}')">
                  ${pIcon} ${escapeHtml(p)}
                </button>
              `;
            }).join('')}
            <button class="btn btn-secondary btn-sm" id="tab-btn-detail-ALL" onclick="window.switchDetailPlatformTab && window.switchDetailPlatformTab('ALL')">
              📋 View All (${targetPlatforms.length})
            </button>
          </div>
        </div>

        <div style="margin-top: var(--space-3);">
          ${targetPlatforms.map(p => {
            const pKey = (p || '').toUpperCase();
            const pIcon = PLATFORM_ICONS[pKey] || '📢';
            const pContent = (item.platform_contents && item.platform_contents[pKey]) 
              ? item.platform_contents[pKey] 
              : ((item.platform_contents && item.platform_contents[p]) 
                ? item.platform_contents[p] 
                : (pKey === platformKey ? item.post_content : null));
            const pCharCount = pContent ? pContent.length : 0;
            const isSelected = pKey === platformKey;
            return `
              <div class="detail-platform-pane" id="detail-pane-${escapeHtml(pKey)}" style="display: ${isSelected ? 'block' : 'none'};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
                  <div style="font-weight: 700; font-size: var(--text-xs); color: var(--text-secondary); display: flex; align-items: center; gap: var(--space-2);">
                    <span>${pIcon} <strong>${escapeHtml(p)}</strong> Format</span>
                    ${pKey === platformKey ? '<span class="badge badge-indigo" style="font-size: 10px;">Current Schedule Task</span>' : ''}
                  </div>
                  ${pContent ? `<span class="badge badge-gray" style="font-size: 11px;">${pCharCount} characters</span>` : ''}
                </div>
                ${pContent ? `
                  <div class="modal-post-copy-box">${escapeHtml(pContent)}</div>
                ` : `
                  <div class="alert alert-warning" style="font-size: var(--text-xs); margin: 0; padding: var(--space-3); line-height: 1.4;">
                    ⚠️ No platform-specific content found for <strong>${escapeHtml(p)}</strong>.
                  </div>
                `}
              </div>
            `;
          }).join('')}

          <div class="detail-platform-pane" id="detail-pane-ALL" style="display: none;">
            <div style="display: flex; flex-direction: column; gap: var(--space-3);">
              ${targetPlatforms.map(p => {
                const pKey = (p || '').toUpperCase();
                const pIcon = PLATFORM_ICONS[pKey] || '📢';
                const pContent = (item.platform_contents && item.platform_contents[pKey]) 
                  ? item.platform_contents[pKey] 
                  : ((item.platform_contents && item.platform_contents[p]) 
                    ? item.platform_contents[p] 
                    : (pKey === platformKey ? item.post_content : null));
                const pCharCount = pContent ? pContent.length : 0;
                return `
                  <div style="background: var(--bg-surface-alt, #f8fafc); border: 1px solid var(--border-subtle, #e2e8f0); border-radius: 8px; padding: var(--space-3);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
                      <span style="font-weight: 700; font-size: var(--text-xs); color: var(--color-primary);">${pIcon} ${escapeHtml(p)}</span>
                      ${pContent ? `<span class="badge badge-gray" style="font-size: 10px;">${pCharCount} chars</span>` : ''}
                    </div>
                    ${pContent ? `
                      <div style="font-size: 13px; line-height: 1.5; white-space: pre-wrap; color: var(--text-primary); font-family: inherit;">${escapeHtml(pContent)}</div>
                    ` : `
                      <div style="color: var(--color-warning); font-size: 12px;">⚠️ No platform-specific content found for ${escapeHtml(p)}</div>
                    `}
                  </div>
                `;
              }).join('')}
            </div>
          </div>
        </div>
      </div>
    `;
  }

  if (bodyEl) {
    bodyEl.innerHTML = `
      <!-- 1. Schedule Overview Card -->
      <div class="modal-card">
        <div class="modal-card-header">
          <span class="modal-card-title">📅 Schedule Overview</span>
          <span class="badge ${badgeClass}">${item.status}</span>
        </div>
        <div class="modal-overview-grid">
          <div class="modal-overview-item" style="grid-column: 1 / -1;">
            <div class="modal-item-lbl">Selected Target Channels (${targetPlatforms.length})</div>
            <div class="modal-item-val" style="display: flex; gap: var(--space-2); flex-wrap: wrap; margin-top: 4px;">
              ${platformBadgesHtml}
            </div>
          </div>
          <div class="modal-overview-item">
            <div class="modal-item-lbl">Current Task Channel</div>
            <div class="modal-item-val">${icon} <strong>${escapeHtml(item.platform || 'TWITTER')}</strong></div>
          </div>
          <div class="modal-overview-item">
            <div class="modal-item-lbl">Scheduled Date & Time</div>
            <div class="modal-item-val" style="font-size: 12.5px;">${timeFormatted}</div>
          </div>
          <div class="modal-overview-item">
            <div class="modal-item-lbl">Target Timezone</div>
            <div class="modal-item-val">${escapeHtml(item.timezone || currentCalendarTimezone || 'UTC')}</div>
          </div>
          <div class="modal-overview-item">
            <div class="modal-item-lbl">Execution Retries</div>
            <div class="modal-item-val">${item.retry_count || 0} retry attempt${item.retry_count === 1 ? '' : 's'}</div>
          </div>
        </div>
      </div>

      ${contentCardHtml}

      <!-- 3. Publication Details Card -->
      ${item.published_at ? `
        <div class="modal-card" style="border-left: 4px solid var(--color-success, #10b981);">
          <div class="modal-card-header">
            <span class="modal-card-title">🚀 Publication Execution Details</span>
            <span class="badge badge-emerald">PUBLISHED</span>
          </div>
          <div class="modal-overview-grid">
            <div class="modal-overview-item">
              <div class="modal-item-lbl">Published Timestamp</div>
              <div class="modal-item-val" style="font-size: 12.5px;">${new Date(item.published_at).toLocaleString()}</div>
            </div>
            <div class="modal-overview-item">
              <div class="modal-item-lbl">Publishing Engine</div>
              <div class="modal-item-val">MockPublisher (Simulated)</div>
            </div>
            ${item.idempotency_key ? `
              <div class="modal-overview-item">
                <div class="modal-item-lbl">Idempotency Key</div>
                <div class="modal-item-val" style="font-size: 11px; font-family: monospace;">${escapeHtml(item.idempotency_key)}</div>
              </div>
            ` : ''}
          </div>
        </div>
      ` : ''}

      ${item.last_error ? `
        <div class="modal-card" style="border-left: 4px solid var(--color-danger, #ef4444);">
          <div class="modal-card-header">
            <span class="modal-card-title" style="color: var(--color-danger);">⚠️ Execution Error</span>
            <span class="badge badge-danger">FAILED</span>
          </div>
          <div style="font-size: 13px; color: var(--color-danger); line-height: 1.5;">${escapeHtml(item.last_error)}</div>
        </div>
      ` : ''}
    `;
  }

  // State-accurate actions in footer
  if (footerEl) {
    let actionsHtml = `
      <button class="btn btn-secondary btn-sm" onclick="window.closeScheduleDetailModal && window.closeScheduleDetailModal()">Close</button>
      <button class="btn btn-secondary btn-sm" onclick="window.openLogsModal(${item.id})">📜 Audit Logs</button>
    `;

    if (item.status === 'SCHEDULED') {
      actionsHtml = `
        <button class="btn btn-danger btn-sm" onclick="window.cancelSchedule(${item.id})">❌ Cancel Schedule</button>
        <button class="btn btn-secondary btn-sm" onclick="window.openRescheduleModal(${item.id}, '${item.scheduled_at}', '${item.timezone || 'UTC'}')">✏️ Reschedule</button>
        <button class="btn btn-secondary btn-sm" onclick="window.openLogsModal(${item.id})">📜 Audit Logs</button>
        <button class="btn btn-success btn-sm" onclick="window.publishNow(${item.id})">⚡ Publish Now</button>
        <button class="btn btn-secondary btn-sm" onclick="window.closeScheduleDetailModal && window.closeScheduleDetailModal()">Close</button>
      `;
    } else if (item.status === 'PUBLISH_FAILED') {
      actionsHtml = `
        <button class="btn btn-danger btn-sm" onclick="window.cancelSchedule(${item.id})">❌ Cancel Schedule</button>
        <button class="btn btn-secondary btn-sm" onclick="window.openRescheduleModal(${item.id}, '${item.scheduled_at}', '${item.timezone || 'UTC'}')">✏️ Reschedule</button>
        <button class="btn btn-secondary btn-sm" onclick="window.openLogsModal(${item.id})">📜 Audit Logs</button>
        <button class="btn btn-success btn-sm" onclick="window.publishNow(${item.id})">⚡ Retry Publish</button>
        <button class="btn btn-secondary btn-sm" onclick="window.closeScheduleDetailModal && window.closeScheduleDetailModal()">Close</button>
      `;
    }

    footerEl.innerHTML = actionsHtml;
  }

  // Open modal with smooth animation
  backdrop.style.display = 'flex';
  requestAnimationFrame(() => {
    backdrop.classList.add('open', 'modal-backdrop-open');
    backdrop.classList.remove('modal-closing');
  });
  document.body.style.overflow = 'hidden';

  // Backdrop click to close
  backdrop.onclick = (e) => {
    if (e.target === backdrop) {
      closeScheduleDetailModal();
    }
  };

  // ESC key listener
  window.addEventListener('keydown', handleModalEscapeKey);
}

function handleModalEscapeKey(e) {
  if (e.key === 'Escape' || e.key === 'Esc') {
    if (modalCurrentView === 'reschedule') {
      transitionToDetailView();
    } else {
      closeScheduleDetailModal();
    }
  }
}

/**
 * Closes the schedule detail modal with smooth exit animation.
 */
export function closeScheduleDetailModal() {
  const backdrop = document.getElementById('schedule-detail-modal-backdrop');
  if (!backdrop) return;

  window.removeEventListener('keydown', handleModalEscapeKey);

  backdrop.classList.add('modal-closing');
  backdrop.classList.remove('open', 'modal-backdrop-open');

  setTimeout(() => {
    backdrop.style.display = 'none';
    backdrop.classList.remove('modal-closing');
    document.body.style.overflow = '';
    currentActiveScheduleId = null;
    modalCurrentView = 'detail';
    isModalTransitioning = false;

    // Clean reset of all view panes so subsequent modal opens start fresh
    const viewDetail = document.getElementById('modal-view-detail');
    const viewReschedule = document.getElementById('modal-view-reschedule');
    const viewLogs = document.getElementById('modal-view-logs');
    if (viewDetail) {
      viewDetail.style.display = 'flex';
      viewDetail.className = 'modal-view-pane active';
    }
    if (viewReschedule) {
      viewReschedule.style.display = 'none';
      viewReschedule.className = 'modal-view-pane';
    }
    if (viewLogs) {
      viewLogs.style.display = 'none';
      viewLogs.className = 'modal-view-pane';
    }
  }, 200);
}

/**
 * Renders the queue list view of all scheduled items.
 */
function renderListView() {
  const container = document.getElementById('calendar-list-container');
  if (!container) return;

  if (cachedSchedules.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: var(--space-8); color: var(--text-muted);">
        <p style="font-size: 32px; margin-bottom: var(--space-2);">📅</p>
        <p style="font-weight: 600;">No posts currently scheduled.</p>
        <p style="font-size: var(--text-xs); margin-top: var(--space-1);">Approve posts in the Review queue to schedule them here.</p>
      </div>
    `;
    return;
  }

  // Sort upcoming first
  const sorted = [...cachedSchedules].sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at));

  let html = `<div style="display: flex; flex-direction: column; gap: var(--space-4);">`;

  sorted.forEach(item => {
    const platformKey = (item.platform || 'TWITTER').toUpperCase();
    const color = PLATFORM_COLORS[platformKey] || 'var(--color-primary)';
    const icon = PLATFORM_ICONS[platformKey] || '📢';
    const dateFormatted = formatScheduleDateTime(item, currentCalendarTimezone);

    let statusBadgeClass = 'badge-indigo';
    if (item.status === 'PUBLISHED') statusBadgeClass = 'badge-emerald';
    else if (item.status === 'PUBLISHING') statusBadgeClass = 'badge-amber';
    else if (item.status === 'PUBLISH_FAILED') statusBadgeClass = 'badge-danger';
    else if (item.status === 'CANCELLED') statusBadgeClass = 'badge-gray';

    const targetPlatforms = (item.target_platforms && item.target_platforms.length > 0)
      ? item.target_platforms
      : [item.platform || 'TWITTER'];

    html += `
      <div class="card schedule-card" id="schedule-card-${item.id}" data-schedule-id="${item.id}"
           onclick="window.openScheduleDetailModal && window.openScheduleDetailModal(${item.id})"
           style="border-left: 4px solid ${color}; cursor: pointer;">
        <div class="card-header" style="justify-content: space-between; align-items: center; padding: var(--space-3) var(--space-4); flex-wrap: wrap; gap: var(--space-2);">
          <div style="display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap;">
            <span style="font-size: 18px;">${icon}</span>
            <span style="font-weight: 700; font-size: var(--text-sm);">${item.platform || 'Social'}</span>
            <span class="badge ${statusBadgeClass}">${item.status}</span>
            ${item.retry_count > 0 ? `<span class="badge badge-amber">Retries: ${item.retry_count}</span>` : ''}
            ${targetPlatforms.length > 1 ? `
              <span class="badge badge-gray" style="font-size: 10px;">Targets: ${targetPlatforms.map(p => `${PLATFORM_ICONS[(p||'').toUpperCase()] || ''} ${p}`).join(', ')}</span>
            ` : ''}
          </div>
          <div style="font-size: var(--text-xs); color: var(--text-muted); font-weight: 600;">
            🕒 ${dateFormatted}
          </div>
        </div>
        <div class="card-body" style="padding: var(--space-3) var(--space-4);">
          <p style="font-size: var(--text-sm); color: var(--text-primary); white-space: pre-wrap; margin-bottom: var(--space-3); line-height: 1.5;">
            ${escapeHtml(item.post_content || item.post_theme || 'Scheduled Post Content')}
          </p>
          
          ${item.last_error ? `
            <div class="alert alert-danger" style="margin-bottom: var(--space-3); padding: var(--space-2) var(--space-3); font-size: var(--text-xs);">
              <span>⚠️</span>
              <span><strong>Last Error:</strong> ${escapeHtml(item.last_error)}</span>
            </div>
          ` : ''}

          <div style="display: flex; gap: var(--space-2); justify-content: flex-end; flex-wrap: wrap; border-top: 1px solid var(--border-color); pt: var(--space-2); margin-top: var(--space-2);"
               onclick="event.stopPropagation();">
            <button class="btn btn-secondary btn-sm" onclick="window.openScheduleDetailModal(${item.id})">
              🔍 Details
            </button>
            <button class="btn btn-secondary btn-sm" onclick="window.openLogsModal(${item.id})">
              📜 Audit Logs
            </button>
            ${item.status === 'SCHEDULED' || item.status === 'PUBLISH_FAILED' ? `
              <button class="btn btn-success btn-sm" onclick="window.publishNow(${item.id})">
                ⚡ Publish Now
              </button>
              <button class="btn btn-secondary btn-sm" onclick="window.openRescheduleModal(${item.id}, '${item.scheduled_at}', '${item.timezone || 'UTC'}')">
                ✏️ Reschedule
              </button>
              <button class="btn btn-danger btn-sm" onclick="window.cancelSchedule(${item.id})">
                ❌ Cancel
              </button>
            ` : ''}
          </div>
        </div>
      </div>
    `;
  });

  html += `</div>`;
  container.innerHTML = html;
}

/**
 * Reusable Post Details Modal (for Queue view or modal inspection).
 */
export async function openPostDetailsModal(scheduleId) {
  const modal = document.getElementById('post-details-modal');
  const titleEl = document.getElementById('post-details-title');
  const subtitleEl = document.getElementById('post-details-subtitle');
  const iconEl = document.getElementById('post-details-platform-icon');
  const statusEl = document.getElementById('post-details-status-badge');
  const bodyEl = document.getElementById('post-details-body');
  const footerEl = document.getElementById('post-details-footer');

  if (!modal) return;

  let item = cachedSchedules.find(s => s.id === scheduleId);
  if (!item) {
    try {
      const res = await fetch(`/api/v1/schedules/${scheduleId}`);
      if (res.ok) {
        item = await res.json();
      }
    } catch (e) {
      console.error('Error fetching schedule details:', e);
    }
  }

  if (!item) {
    toast.show('Schedule details not found.', 'warning');
    return;
  }

  const platformKey = (item.platform || 'TWITTER').toUpperCase();
  const icon = PLATFORM_ICONS[platformKey] || '📢';
  const timeFormatted = formatScheduleDateTime(item, currentCalendarTimezone);
  const content = item.post_content || item.post_theme || 'No content';
  const charCount = content.length;

  if (iconEl) iconEl.textContent = icon;
  if (titleEl) titleEl.textContent = item.post_theme || item.post_topic || `${item.platform || 'Post'} Publication #${item.id}`;
  if (subtitleEl) subtitleEl.textContent = `Schedule #${item.id} • Post #${item.post_id || 'N/A'}`;

  let badgeClass = 'badge-indigo';
  if (item.status === 'PUBLISHED') badgeClass = 'badge-emerald';
  else if (item.status === 'PUBLISHING') badgeClass = 'badge-amber';
  else if (item.status === 'PUBLISH_FAILED') badgeClass = 'badge-danger';
  else if (item.status === 'CANCELLED') badgeClass = 'badge-gray';

  if (statusEl) {
    statusEl.className = `badge ${badgeClass}`;
    statusEl.textContent = item.status;
  }

  if (bodyEl) {
    bodyEl.innerHTML = `
      <div class="post-details-meta-grid">
        <div class="post-details-meta-item">
          <div class="post-details-meta-label">📅 Scheduled At</div>
          <div class="post-details-meta-val">${timeFormatted}</div>
        </div>
        <div class="post-details-meta-item">
          <div class="post-details-meta-label">🌐 Target Platform</div>
          <div class="post-details-meta-val">${icon} ${escapeHtml(item.platform || 'TWITTER')}</div>
        </div>
        <div class="post-details-meta-item">
          <div class="post-details-meta-label">⏱️ Timezone</div>
          <div class="post-details-meta-val">${escapeHtml(item.timezone || 'UTC')}</div>
        </div>
        <div class="post-details-meta-item">
          <div class="post-details-meta-label">🔄 Retries / Status</div>
          <div class="post-details-meta-val">${item.retry_count || 0} retries • ${item.status}</div>
        </div>
      </div>

      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
        <div style="font-weight: 700; font-size: var(--text-xs); text-transform: uppercase; color: var(--text-secondary);">
          📝 Full Post Copy Preview
        </div>
        <span class="badge badge-gray" style="font-size: 11px;">${charCount} characters</span>
      </div>

      <div class="post-details-content-box">${escapeHtml(content)}</div>

      ${item.published_at ? `
        <div class="alert alert-success" style="margin-bottom: var(--space-3); font-size: var(--text-xs);">
          <span>✅</span>
          <span><strong>Published At:</strong> ${new Date(item.published_at).toLocaleString()} (via MockPublisher simulation)</span>
        </div>
      ` : ''}

      ${item.last_error ? `
        <div class="alert alert-danger" style="margin-bottom: var(--space-3); font-size: var(--text-xs);">
          <span>⚠️</span>
          <span><strong>Last Execution Error:</strong> ${escapeHtml(item.last_error)}</span>
        </div>
      ` : ''}
    `;
  }

  if (footerEl) {
    let actionsHtml = `
      <button class="btn btn-secondary btn-sm" onclick="window.closePostDetailsModal && window.closePostDetailsModal()">Close</button>
      <button class="btn btn-secondary btn-sm" onclick="window.openLogsModal(${item.id})">📜 Audit Logs</button>
    `;

    if (item.status === 'SCHEDULED') {
      actionsHtml = `
        <button class="btn btn-danger btn-sm" onclick="window.cancelSchedule(${item.id}); window.closePostDetailsModal();">❌ Cancel Schedule</button>
        <button class="btn btn-secondary btn-sm" onclick="window.closePostDetailsModal(); window.openRescheduleModal(${item.id}, '${item.scheduled_at}', '${item.timezone || 'UTC'}');">✏️ Reschedule</button>
        <button class="btn btn-secondary btn-sm" onclick="window.openLogsModal(${item.id})">📜 Audit Logs</button>
        <button class="btn btn-success btn-sm" onclick="window.publishNow(${item.id}); window.closePostDetailsModal();">⚡ Publish Now</button>
        <button class="btn btn-secondary btn-sm" onclick="window.closePostDetailsModal && window.closePostDetailsModal()">Close</button>
      `;
    } else if (item.status === 'PUBLISH_FAILED') {
      actionsHtml = `
        <button class="btn btn-danger btn-sm" onclick="window.cancelSchedule(${item.id}); window.closePostDetailsModal();">❌ Cancel</button>
        <button class="btn btn-secondary btn-sm" onclick="window.closePostDetailsModal(); window.openRescheduleModal(${item.id}, '${item.scheduled_at}', '${item.timezone || 'UTC'}');">✏️ Reschedule</button>
        <button class="btn btn-secondary btn-sm" onclick="window.openLogsModal(${item.id})">📜 Audit Logs</button>
        <button class="btn btn-success btn-sm" onclick="window.publishNow(${item.id}); window.closePostDetailsModal();">⚡ Retry Publish</button>
        <button class="btn btn-secondary btn-sm" onclick="window.closePostDetailsModal && window.closePostDetailsModal()">Close</button>
      `;
    }

    footerEl.innerHTML = actionsHtml;
  }

  modal.style.display = 'flex';
  modal.classList.add('open');
  document.body.style.overflow = 'hidden';
}

export function closePostDetailsModal() {
  const modal = document.getElementById('post-details-modal');
  if (modal) {
    modal.classList.remove('open');
    modal.style.display = 'none';
    document.body.style.overflow = '';
  }
}

/**
 * Immediately publishes a scheduled post via the publisher engine.
 */
export async function publishNow(scheduleId) {
  if (!confirm('Publish this post immediately via the publisher engine?')) return;

  try {
    const res = await fetch(`/api/v1/schedules/${scheduleId}/publish-now`, {
      method: 'POST'
    });

    if (res.ok) {
      const data = await res.json();
      toast.show(data.message || 'Post published successfully!', 'success');
      await loadSchedules();
      renderCalendar();
      if (window.refreshApprovalsList) window.refreshApprovalsList();
      const backdrop = document.getElementById('schedule-detail-modal-backdrop');
      if (backdrop && backdrop.classList.contains('modal-backdrop-open')) {
        openScheduleDetailModal(scheduleId);
      }
    } else {
      const err = await res.json();
      toast.show(err.detail || 'Publication failed.', 'error');
      await loadSchedules();
      renderCalendar();
      if (window.refreshApprovalsList) window.refreshApprovalsList();
    }
  } catch (err) {
    console.error('Error triggering publish-now:', err);
    toast.show('Network error while publishing post.', 'error');
  }
}

/**
 * Cancels a scheduled post and returns it to APPROVED status.
 */
export async function cancelSchedule(scheduleId) {
  if (!confirm('Are you sure you want to cancel this scheduled post? It will return to Approved status.')) return;

  try {
    const res = await fetch(`/api/v1/schedules/${scheduleId}`, {
      method: 'DELETE'
    });

    if (res.ok) {
      toast.show('Schedule cancelled. Post returned to Approved queue.', 'success');
      await loadSchedules();
      renderCalendar();
      if (window.refreshApprovalsList) window.refreshApprovalsList();
      closeScheduleDetailModal();
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
 * Smooth transition from Detail View to Reschedule View within continuous modal backdrop.
 */
export async function transitionToRescheduleView(scheduleId, currentDateIso, timezone) {
  if (isModalTransitioning) return;
  isModalTransitioning = true;

  const targetId = scheduleId || currentActiveScheduleId;
  currentActiveScheduleId = targetId;

  const viewDetail = document.getElementById('modal-view-detail');
  const viewReschedule = document.getElementById('modal-view-reschedule');
  if (!viewDetail || !viewReschedule) {
    isModalTransitioning = false;
    return;
  }

  // 1. Fetch & populate reschedule view data
  let item = cachedSchedules.find(s => s.id === targetId);
  if (!item && targetId) {
    try {
      const res = await fetch(`/api/v1/schedules/${targetId}`);
      if (res.ok) item = await res.json();
    } catch (e) {
      console.error('Error fetching schedule for reschedule view:', e);
    }
  }

  if (item) {
    const platformKey = (item.platform || 'TWITTER').toUpperCase();
    const icon = PLATFORM_ICONS[platformKey] || '📢';
    const postTitle = item.post_theme || item.post_topic || `${item.platform || 'Post'} Publication #${item.id}`;
    const targetTz = item.timezone || timezone || currentCalendarTimezone || 'UTC';
    
    let str = item.scheduled_at || currentDateIso;
    if (str && !str.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(str)) {
      str += 'Z';
    }
    const dt = new Date(str);

    // Format date and time in target timezone
    let dateStr = '';
    let timeStr = '';
    let dateFormatted = '';
    let timeFormatted = '';

    if (!isNaN(dt.getTime())) {
      try {
        dateStr = new Intl.DateTimeFormat('en-CA', { timeZone: targetTz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(dt);
        timeStr = new Intl.DateTimeFormat('en-GB', { timeZone: targetTz, hour: '2-digit', minute: '2-digit', hour12: false }).format(dt);
        dateFormatted = dt.toLocaleDateString(undefined, { timeZone: targetTz, weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
        timeFormatted = dt.toLocaleTimeString(undefined, { timeZone: targetTz, hour: '2-digit', minute: '2-digit', hour12: false });
      } catch (e) {
        dateStr = dt.toISOString().slice(0, 10);
        timeStr = dt.toISOString().slice(11, 16);
        dateFormatted = dt.toDateString();
        timeFormatted = timeStr;
      }
    }

    // Current schedule info
    const currTitleEl = document.getElementById('reschedule-curr-title');
    const currPlatformEl = document.getElementById('reschedule-curr-platform');
    const currDateEl = document.getElementById('reschedule-curr-date');
    const currTimeEl = document.getElementById('reschedule-curr-time');
    const currTzEl = document.getElementById('reschedule-curr-tz');
    const currStatusEl = document.getElementById('reschedule-curr-status');

    if (currTitleEl) currTitleEl.textContent = postTitle;
    if (currPlatformEl) currPlatformEl.innerHTML = `${icon} ${escapeHtml(item.platform || 'TWITTER')}`;
    if (currDateEl) currDateEl.textContent = dateFormatted || 'N/A';
    if (currTimeEl) currTimeEl.textContent = timeFormatted || 'N/A';
    if (currTzEl) currTzEl.textContent = targetTz;
    if (currStatusEl) currStatusEl.textContent = item.status || 'SCHEDULED';

    // Form inputs
    const idInput = document.getElementById('reschedule-id');
    const dateInput = document.getElementById('reschedule-date-input');
    const timeInput = document.getElementById('reschedule-time-input');
    const tzSelect = document.getElementById('reschedule-timezone-select');

    if (idInput) idInput.value = item.id;

    const today = new Date();
    const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    if (dateInput) {
      dateInput.min = todayStr;
      if (dateStr) dateInput.value = dateStr;
    }
    if (timeInput) {
      if (timeStr) timeInput.value = timeStr;
    }
    if (tzSelect) {
      tzSelect.value = targetTz;
    }
  }

  // 2. Animate Detail View Exit: opacity: 1 -> 0, transform: translateY(0) -> translateY(-8px) scale(0.98)
  viewDetail.classList.add('view-exit-to-reschedule');

  setTimeout(() => {
    // 3. Swap display
    viewDetail.style.display = 'none';
    viewDetail.className = 'modal-view-pane';

    // 4. Mount Reschedule View at initial keyframe: opacity: 0, transform: translateY(12px) scale(0.98)
    viewReschedule.style.display = 'flex';
    viewReschedule.className = 'modal-view-pane view-enter-from-detail-start';

    // Force reflow
    void viewReschedule.offsetHeight;

    // 5. Trigger Reschedule Enter transition: opacity -> 1, transform: translateY(0) scale(1)
    viewReschedule.classList.remove('view-enter-from-detail-start');
    viewReschedule.classList.add('active', 'view-enter-from-detail-active');

    setTimeout(() => {
      viewReschedule.classList.remove('view-enter-from-detail-active');
      modalCurrentView = 'reschedule';
      isModalTransitioning = false;
      const dateInput = document.getElementById('reschedule-date-input');
      if (dateInput) dateInput.focus();
    }, 240);

  }, 220);
}

/**
 * Reverse transition from Reschedule or Logs view back to Detail view.
 */
export function transitionToDetailView() {
  if (isModalTransitioning) return;
  isModalTransitioning = true;

  const viewDetail = document.getElementById('modal-view-detail');
  const viewReschedule = document.getElementById('modal-view-reschedule');
  const viewLogs = document.getElementById('modal-view-logs');
  if (!viewDetail) {
    isModalTransitioning = false;
    return;
  }

  const activePane = (modalCurrentView === 'logs') ? viewLogs : viewReschedule;
  if (!activePane) {
    isModalTransitioning = false;
    return;
  }

  // 1. Animate active pane Exit: opacity: 1 -> 0, transform: translateY(0) -> translateY(12px) scale(0.98)
  activePane.classList.add('view-exit-to-detail');

  setTimeout(() => {
    // 2. Swap display
    if (viewReschedule) {
      viewReschedule.style.display = 'none';
      viewReschedule.className = 'modal-view-pane';
    }
    if (viewLogs) {
      viewLogs.style.display = 'none';
      viewLogs.className = 'modal-view-pane';
    }

    // 3. Mount Detail View at initial keyframe: opacity: 0, transform: translateY(-8px) scale(0.98)
    viewDetail.style.display = 'flex';
    viewDetail.className = 'modal-view-pane view-enter-from-reschedule-start';

    // Force reflow
    void viewDetail.offsetHeight;

    // 4. Trigger Detail Enter transition: opacity -> 1, transform: translateY(0) scale(1)
    viewDetail.classList.remove('view-enter-from-reschedule-start');
    viewDetail.classList.add('active', 'view-enter-from-reschedule-active');

    setTimeout(() => {
      viewDetail.classList.remove('view-enter-from-reschedule-active');
      modalCurrentView = 'detail';
      isModalTransitioning = false;
    }, 240);

  }, 200);
}

export function openRescheduleModal(scheduleId, currentDateIso, timezone) {
  transitionToRescheduleView(scheduleId, currentDateIso, timezone);
}

export function closeRescheduleModal() {
  transitionToDetailView();
}

export async function confirmReschedule() {
  const idInput = document.getElementById('reschedule-id');
  const dateInput = document.getElementById('reschedule-date-input');
  const timeInput = document.getElementById('reschedule-time-input');
  const tzSelect = document.getElementById('reschedule-timezone-select');
  const btn = document.getElementById('confirm-reschedule-btn');

  const scheduleId = idInput ? Number(idInput.value) : null;
  const dateStr = dateInput ? dateInput.value : '';
  const timeStr = timeInput ? timeInput.value : '';
  const timezone = tzSelect ? tzSelect.value : 'UTC';

  if (!scheduleId || !dateStr || !timeStr) {
    toast.show('Please select a valid date and time.', 'warning');
    return;
  }

  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

  // Guardrail: date cannot be in the past
  if (dateStr < todayStr) {
    toast.show('Cannot reschedule to a past date. Please pick today or a future date.', 'warning');
    return;
  }

  let isoStr = `${dateStr}T${timeStr}:00`;
  const newDate = new Date(isoStr);
  if (isNaN(newDate.getTime())) {
    toast.show('Invalid date/time entered.', 'warning');
    return;
  }

  // Guardrail: if today, time cannot be in the past
  if (dateStr === todayStr && newDate.getTime() <= Date.now()) {
    toast.show('Selected time has already passed. Please choose a future time.', 'warning');
    return;
  }

  if (timezone === 'UTC') {
    isoStr += 'Z';
  } else {
    isoStr = newDate.toISOString();
  }

  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Updating...';
  }

  try {
    const res = await fetch(`/api/v1/schedules/${scheduleId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scheduled_at: isoStr,
        timezone: timezone
      })
    });

    if (res.ok) {
      toast.show('✓ Post rescheduled successfully', 'success');
      closeScheduleDetailModal();
      await loadSchedules();
      renderCalendar();
      if (window.refreshApprovalsList) window.refreshApprovalsList();
    } else {
      const err = await res.json();
      toast.show(err.detail || 'Failed to reschedule.', 'error');
    }
  } catch (err) {
    console.error('Error rescheduling:', err);
    toast.show('Network error while rescheduling.', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Confirm Reschedule';
    }
  }
}

/**
 * Renders the formatted audit log entries inside #schedule-logs-body.
 */
function renderAuditLogsList(logs, targetId) {
  const body = document.getElementById('schedule-logs-body');
  if (!body) return;

  if (!logs || logs.length === 0) {
    body.innerHTML = `
      <div style="text-align: center; padding: var(--space-8); color: var(--text-muted);">
        <p style="font-size: 32px; margin-bottom: var(--space-2);">📜</p>
        <p style="font-weight: 600;">No publication attempts recorded yet.</p>
        <p style="font-size: var(--text-xs); margin-top: var(--space-1);">Schedule #${targetId} is awaiting publisher execution or retry.</p>
      </div>
    `;
    return;
  }

  let logsHtml = `<div style="display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-1);">`;
  logs.forEach(l => {
    const timeStr = l.attempted_at ? new Date(l.attempted_at).toLocaleString() : 'N/A';
    const isSuccess = l.status === 'SUCCESS' || l.status === 'SIMULATED';
    const badgeClass = isSuccess ? 'badge-emerald' : 'badge-danger';

    logsHtml += `
      <div class="modal-card" style="margin-bottom: 0; border-left: 4px solid ${isSuccess ? 'var(--color-success, #10b981)' : 'var(--color-danger, #ef4444)'};">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2); flex-wrap: wrap; gap: var(--space-2);">
          <div style="display: flex; align-items: center; gap: var(--space-2);">
            <span class="badge ${badgeClass}">${escapeHtml(l.status)}</span>
            <span style="font-weight: 700; font-size: var(--text-xs);">${escapeHtml(l.provider || 'MockPublisher')}</span>
            ${l.is_mock ? `<span class="badge badge-cyan" style="font-size: 10px;">SIMULATED</span>` : ''}
          </div>
          <span style="font-size: 11px; color: var(--text-muted);">🕒 ${timeStr}</span>
        </div>
        
        ${l.external_post_id ? `
          <div style="font-size: var(--text-xs); color: var(--text-secondary); margin-bottom: 4px;">
            <strong>External ID:</strong> <code style="font-family: var(--font-mono); background: var(--bg-surface-alt); padding: 1px 5px; border-radius: 4px;">${escapeHtml(l.external_post_id)}</code>
          </div>
        ` : ''}

        ${l.error_message ? `
          <div style="font-size: var(--text-xs); color: var(--color-danger); margin-bottom: 4px; background: rgba(239, 68, 68, 0.08); padding: var(--space-2); border-radius: 6px;">
            <strong>Error:</strong> ${escapeHtml(l.error_message)}
          </div>
        ` : ''}

        ${l.response_payload ? `
          <details style="margin-top: var(--space-2); font-size: 11px;">
            <summary style="cursor: pointer; color: var(--color-primary); font-weight: 600;">View Raw Payload</summary>
            <pre style="background: var(--bg-surface-alt, #f8fafc); border: 1px solid var(--border-subtle, #e2e8f0); padding: var(--space-3); border-radius: 6px; overflow-x: auto; margin-top: 6px; font-family: var(--font-mono); font-size: 11px; line-height: 1.4;">${escapeHtml(JSON.stringify(l.response_payload, null, 2))}</pre>
          </details>
        ` : ''}
      </div>
    `;
  });
  logsHtml += `</div>`;
  body.innerHTML = logsHtml;
}

/**
 * Smooth transition from Detail View to Publication Audit Logs View within continuous modal backdrop.
 */
export async function transitionToLogsView(scheduleId) {
  if (isModalTransitioning) return;
  isModalTransitioning = true;

  const targetId = scheduleId || currentActiveScheduleId;
  currentActiveScheduleId = targetId;

  const viewDetail = document.getElementById('modal-view-detail');
  const viewLogs = document.getElementById('modal-view-logs');
  const body = document.getElementById('schedule-logs-body');
  const subtitleEl = document.getElementById('logs-view-modal-subtitle');

  if (!viewDetail || !viewLogs) {
    isModalTransitioning = false;
    return;
  }

  if (subtitleEl) {
    subtitleEl.textContent = `Publication audit history for Schedule #${targetId || 'N/A'}`;
  }

  if (body) {
    body.innerHTML = `<div style="text-align: center; padding: var(--space-6); color: var(--text-muted);">⏳ Loading audit trail...</div>`;
  }

  // Fetch logs asynchronously
  fetch(`/api/v1/schedules/${targetId}/logs`)
    .then(async res => {
      if (res.ok) {
        const logs = await res.json();
        renderAuditLogsList(logs, targetId);
      } else {
        if (body) body.innerHTML = `<div style="color: var(--color-danger); padding: var(--space-4); text-align: center;">Failed to load audit logs.</div>`;
      }
    })
    .catch(err => {
      console.error('Error fetching logs:', err);
      if (body) body.innerHTML = `<div style="color: var(--color-danger); padding: var(--space-4); text-align: center;">Network error fetching logs.</div>`;
    });

  // 1. Animate Detail View Exit: opacity: 1 -> 0, transform: translateY(0) -> translateY(-8px) scale(0.98)
  viewDetail.classList.add('view-exit-to-reschedule');

  setTimeout(() => {
    // 2. Swap display
    viewDetail.style.display = 'none';
    viewDetail.className = 'modal-view-pane';

    // 3. Mount Logs View at initial keyframe: opacity: 0, transform: translateY(12px) scale(0.98)
    viewLogs.style.display = 'flex';
    viewLogs.className = 'modal-view-pane view-enter-from-detail-start';

    // Force reflow
    void viewLogs.offsetHeight;

    // 4. Trigger Logs Enter transition: opacity -> 1, transform: translateY(0) scale(1)
    viewLogs.classList.remove('view-enter-from-detail-start');
    viewLogs.classList.add('active', 'view-enter-from-detail-active');

    setTimeout(() => {
      viewLogs.classList.remove('view-enter-from-detail-active');
      modalCurrentView = 'logs';
      isModalTransitioning = false;
    }, 240);

  }, 220);
}

/**
 * Publication audit logs modal handler (routes smoothly through continuous modal).
 */
export async function openLogsModal(scheduleId) {
  const targetId = scheduleId || currentActiveScheduleId;
  const backdrop = document.getElementById('schedule-detail-modal-backdrop');
  if (!backdrop) return;

  const isOpen = backdrop.classList.contains('modal-backdrop-open') || backdrop.classList.contains('open');
  if (isOpen && modalCurrentView === 'detail') {
    transitionToLogsView(targetId);
  } else {
    // Open schedule detail modal first to prepare details, then transition smoothly to logs
    await openScheduleDetailModal(targetId);
    transitionToLogsView(targetId);
  }
}

export function closeLogsModal() {
  if (modalCurrentView === 'logs') {
    transitionToDetailView();
  } else {
    closeScheduleDetailModal();
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function selectDailyTask(scheduleId) {
  openScheduleDetailModal(scheduleId);
}

export function renderSelectedDayPanel() {
  // Deprecated in favor of modern hover popover and full-screen detail modal
}

export function switchDetailPlatformTab(selectedPlatform) {
  const normTarget = (selectedPlatform || '').toUpperCase();
  document.querySelectorAll('.detail-platform-pane').forEach(el => {
    el.style.display = 'none';
  });
  document.querySelectorAll('#detail-platform-tab-btns button').forEach(btn => {
    btn.classList.remove('active');
  });

  const activePane = document.getElementById(`detail-pane-${normTarget}`);
  if (activePane) activePane.style.display = 'block';

  const activeBtn = document.getElementById(`tab-btn-detail-${normTarget}`);
  if (activeBtn) activeBtn.classList.add('active');
}

// Window bindings for inline onclick handlers
window.setCalendarViewMode = setCalendarViewMode;
window.setCalendarTimezone = setCalendarTimezone;
window.navigateCalendar = navigateCalendar;
window.selectCalendarDay = selectCalendarDay;
window.selectCalendarDayWithTask = selectCalendarDayWithTask;
window.selectDailyTask = selectDailyTask;
window.renderSelectedDayPanel = renderSelectedDayPanel;
window.publishNow = publishNow;
window.cancelSchedule = cancelSchedule;
window.openRescheduleModal = openRescheduleModal;
window.closeRescheduleModal = closeRescheduleModal;
window.confirmReschedule = confirmReschedule;
window.openLogsModal = openLogsModal;
window.closeLogsModal = closeLogsModal;
window.openPostDetailsModal = openScheduleDetailModal;
window.closePostDetailsModal = closeScheduleDetailModal;
window.openScheduleDetailModal = openScheduleDetailModal;
window.closeScheduleDetailModal = closeScheduleDetailModal;
window.showSchedulePopover = showSchedulePopover;
window.hideSchedulePopover = hideSchedulePopover;
window.triggerPopoverForDate = triggerPopoverForDate;
window.transitionToRescheduleView = transitionToRescheduleView;
window.transitionToLogsView = transitionToLogsView;
window.transitionToDetailView = transitionToDetailView;
window.switchDetailPlatformTab = switchDetailPlatformTab;
window.loadSchedules = loadSchedules;
window.renderCalendar = renderCalendar;
