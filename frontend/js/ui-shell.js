/* UI-only helper: remembers and applies the collapsed sidebar rail on desktop.
   Touches no application state, API, or data. */
(function () {
  var KEY = 'sidebar-collapsed';
  var body = document.body;
  var btn = document.getElementById('sidebar-collapse-btn');

  function apply(collapsed) {
    body.classList.toggle('sidebar-collapsed', collapsed);
    if (btn) {
      var label = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
      btn.setAttribute('aria-label', label);
      btn.setAttribute('title', label);
      btn.setAttribute('aria-expanded', String(!collapsed));
    }
  }

  var saved = false;
  try { saved = localStorage.getItem(KEY) === '1'; } catch (e) { /* storage unavailable */ }
  apply(saved);

  if (btn) {
    btn.addEventListener('click', function () {
      var next = !body.classList.contains('sidebar-collapsed');
      apply(next);
      try { localStorage.setItem(KEY, next ? '1' : '0'); } catch (e) { /* ignore */ }
    });
  }
})();
