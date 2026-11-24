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

// Cyber Magic Dynamic Timezone Welcome Greeting & Inspiring Quotes
var CYBER_MAGIC_QUOTES = [
  "SocioGen AI is primed to ideate, synthesize, and orchestrate high-impact multi-channel content campaigns.",
  "AI content pipelines are active and operating at peak quality assurance across all connected channels.",
  "Autonomous agents are standing by to generate, review, and schedule thought-leadership posts.",
  "Plan, craft, and automate social media workflows with human-in-the-loop confidence and security."
];
var quoteIndex = 0;

function updateDynamicGreeting() {
  var titleEl = document.getElementById('dashboard-greeting-title');
  var quoteEl = document.getElementById('dashboard-welcome-quote');
  var now = new Date();
  var hours = now.getHours();
  var greeting = "Good evening";
  var emoji = "✨";

  if (hours >= 5 && hours < 12) {
    greeting = "Good morning";
    emoji = "🌅";
  } else if (hours >= 12 && hours < 17) {
    greeting = "Good afternoon";
    emoji = "☀️";
  } else if (hours >= 17 && hours < 22) {
    greeting = "Good evening";
    emoji = "🌇";
  } else {
    greeting = "Good night";
    emoji = "🌙";
  }

  if (titleEl) {
    titleEl.textContent = greeting + ", Operator " + emoji;
  }
  if (quoteEl) {
    quoteEl.textContent = CYBER_MAGIC_QUOTES[quoteIndex % CYBER_MAGIC_QUOTES.length];
  }
}

// Current Dashboard Graph State
var currentRange = '7D';
var currentHeightKey = 'standard';

// Multi-Height, Multi-Range Path Formulations (Fully Expanded Across X & Y Axes)
var DASHBOARD_CHART_DATA = {
  '7D': {
    metrics: { reach: '16.4K', eng: '9.2K', clicks: '4.8K' },
    yAxis: ['20K', '15K', '10K', '5K', '0'],
    xAxis: ['Mon', 'Tue', 'Wed', 'Thu (Peak)', 'Fri', 'Sat', 'Sun'],
    focalLabel: 'Thu (Peak Dispatch)',
    focalReach: '16.4K', focalEng: '9.2K', focalClicks: '4.8K', focalX: 400,
    scales: {
      160: {
        grid: [25, 60, 95, 125, 150],
        fillReach: 'M 0 150 L 0 92 C 130 60, 260 106, 400 53 C 530 15, 660 46, 800 30 L 800 150 Z',
        fillEng: 'M 0 150 L 0 114 C 130 89, 260 128, 400 82 C 530 43, 660 75, 800 57 L 800 150 Z',
        fillClicks: 'M 0 150 L 0 128 C 130 110, 260 135, 400 106 C 530 78, 660 99, 800 85 L 800 150 Z',
        lineReach: 'M 0 92 C 130 60, 260 106, 400 53 C 530 15, 660 46, 800 30',
        lineEng: 'M 0 114 C 130 89, 260 128, 400 82 C 530 43, 660 75, 800 57',
        lineClicks: 'M 0 128 C 130 110, 260 135, 400 106 C 530 78, 660 99, 800 85',
        yReach: 53, yEng: 82, yClicks: 106, baselineY: 150
      },
      220: {
        grid: [35, 85, 135, 185, 210],
        fillReach: 'M 0 210 L 0 130 C 130 85, 260 150, 400 75 C 530 20, 660 65, 800 42 L 800 210 Z',
        fillEng: 'M 0 210 L 0 160 C 130 125, 260 180, 400 115 C 530 60, 660 105, 800 80 L 800 210 Z',
        fillClicks: 'M 0 210 L 0 180 C 130 155, 260 190, 400 150 C 530 110, 660 140, 800 120 L 800 210 Z',
        lineReach: 'M 0 130 C 130 85, 260 150, 400 75 C 530 20, 660 65, 800 42',
        lineEng: 'M 0 160 C 130 125, 260 180, 400 115 C 530 60, 660 105, 800 80',
        lineClicks: 'M 0 180 C 130 155, 260 190, 400 150 C 530 110, 660 140, 800 120',
        yReach: 75, yEng: 115, yClicks: 150, baselineY: 210
      },
      300: {
        grid: [45, 115, 180, 245, 285],
        fillReach: 'M 0 285 L 0 176 C 130 115, 260 204, 400 102 C 530 27, 660 88, 800 57 L 800 285 Z',
        fillEng: 'M 0 285 L 0 217 C 130 170, 260 245, 400 156 C 530 81, 660 142, 800 108 L 800 285 Z',
        fillClicks: 'M 0 285 L 0 244 C 130 210, 260 258, 400 204 C 530 149, 660 190, 800 163 L 800 285 Z',
        lineReach: 'M 0 176 C 130 115, 260 204, 400 102 C 530 27, 660 88, 800 57',
        lineEng: 'M 0 217 C 130 170, 260 245, 400 156 C 530 81, 660 142, 800 108',
        lineClicks: 'M 0 244 C 130 210, 260 258, 400 204 C 530 149, 660 190, 800 163',
        yReach: 102, yEng: 156, yClicks: 204, baselineY: 285
      }
    }
  },
  '14D': {
    metrics: { reach: '34.8K', eng: '19.5K', clicks: '10.2K' },
    yAxis: ['40K', '30K', '20K', '10K', '0'],
    xAxis: ['Day 1', 'Day 3', 'Day 5', 'Day 7', 'Day 9', 'Day 11 (Peak)', 'Day 14'],
    focalLabel: 'Day 11 (Peak Cycle)',
    focalReach: '34.8K', focalEng: '19.5K', focalClicks: '10.2K', focalX: 620,
    scales: {
      160: {
        grid: [25, 60, 95, 125, 150],
        fillReach: 'M 0 150 L 0 105 C 120 80, 240 115, 380 65 C 500 36, 620 22, 800 47 L 800 150 Z',
        fillEng: 'M 0 150 L 0 123 C 120 98, 240 130, 380 87 C 500 58, 620 47, 800 69 L 800 150 Z',
        fillClicks: 'M 0 150 L 0 134 C 120 116, 240 141, 380 105 C 500 87, 620 72, 800 94 L 800 150 Z',
        lineReach: 'M 0 105 C 120 80, 240 115, 380 65 C 500 36, 620 22, 800 47',
        lineEng: 'M 0 123 C 120 98, 240 130, 380 87 C 500 58, 620 47, 800 69',
        lineClicks: 'M 0 134 C 120 116, 240 141, 380 105 C 500 87, 620 72, 800 94',
        yReach: 22, yEng: 47, yClicks: 72, baselineY: 150
      },
      220: {
        grid: [35, 85, 135, 185, 210],
        fillReach: 'M 0 210 L 0 145 C 120 110, 240 160, 380 90 C 500 50, 620 30, 800 65 L 800 210 Z',
        fillEng: 'M 0 210 L 0 170 C 120 135, 240 180, 380 120 C 500 80, 620 65, 800 95 L 800 210 Z',
        fillClicks: 'M 0 210 L 0 185 C 120 160, 240 195, 380 145 C 500 120, 620 100, 800 130 L 800 210 Z',
        lineReach: 'M 0 145 C 120 110, 240 160, 380 90 C 500 50, 620 30, 800 65',
        lineEng: 'M 0 170 C 120 135, 240 180, 380 120 C 500 80, 620 65, 800 95',
        lineClicks: 'M 0 185 C 120 160, 240 195, 380 145 C 500 120, 620 100, 800 130',
        yReach: 30, yEng: 65, yClicks: 100, baselineY: 210
      },
      300: {
        grid: [45, 115, 180, 245, 285],
        fillReach: 'M 0 285 L 0 198 C 120 150, 240 218, 380 122 C 500 68, 620 40, 800 88 L 800 285 Z',
        fillEng: 'M 0 285 L 0 231 C 120 184, 240 245, 380 163 C 500 109, 620 88, 800 129 L 800 285 Z',
        fillClicks: 'M 0 285 L 0 252 C 120 218, 240 265, 380 197 C 500 163, 620 136, 800 177 L 800 285 Z',
        lineReach: 'M 0 198 C 120 150, 240 218, 380 122 C 500 68, 620 40, 800 88',
        lineEng: 'M 0 231 C 120 184, 240 245, 380 163 C 500 109, 620 88, 800 129',
        lineClicks: 'M 0 252 C 120 218, 240 265, 380 197 C 500 163, 620 136, 800 177',
        yReach: 40, yEng: 88, yClicks: 136, baselineY: 285
      }
    }
  },
  '30D': {
    metrics: { reach: '82.1K', eng: '46.3K', clicks: '23.9K' },
    yAxis: ['100K', '75K', '50K', '25K', '0'],
    xAxis: ['Week 1', 'Week 2', 'Week 3 (Peak)', 'Week 4', 'Month Close'],
    focalLabel: 'Week 3 (Monthly High)',
    focalReach: '82.1K', focalEng: '46.3K', focalClicks: '23.9K', focalX: 480,
    scales: {
      160: {
        grid: [25, 60, 95, 125, 150],
        fillReach: 'M 0 150 L 0 115 C 150 86, 300 100, 480 32 C 600 25, 700 58, 800 40 L 800 150 Z',
        fillEng: 'M 0 150 L 0 130 C 150 105, 300 119, 480 61 C 600 50, 700 79, 800 65 L 800 150 Z',
        fillClicks: 'M 0 150 L 0 140 C 150 122, 300 133, 480 94 C 600 79, 700 104, 800 94 L 800 150 Z',
        lineReach: 'M 0 115 C 150 86, 300 100, 480 32 C 600 25, 700 58, 800 40',
        lineEng: 'M 0 130 C 150 105, 300 119, 480 61 C 600 50, 700 79, 800 65',
        lineClicks: 'M 0 140 C 150 122, 300 133, 480 94 C 600 79, 700 104, 800 94',
        yReach: 32, yEng: 61, yClicks: 94, baselineY: 150
      },
      220: {
        grid: [35, 85, 135, 185, 210],
        fillReach: 'M 0 210 L 0 160 C 150 120, 300 140, 480 45 C 600 35, 700 80, 800 55 L 800 210 Z',
        fillEng: 'M 0 210 L 0 180 C 150 145, 300 165, 480 85 C 600 70, 700 110, 800 90 L 800 210 Z',
        fillClicks: 'M 0 210 L 0 195 C 150 170, 300 185, 480 130 C 600 110, 700 145, 800 130 L 800 210 Z',
        lineReach: 'M 0 160 C 150 120, 300 140, 480 45 C 600 35, 700 80, 800 55',
        lineEng: 'M 0 180 C 150 145, 300 165, 480 85 C 600 70, 700 110, 800 90',
        lineClicks: 'M 0 195 C 150 170, 300 185, 480 130 C 600 110, 700 145, 800 130',
        yReach: 45, yEng: 85, yClicks: 130, baselineY: 210
      },
      300: {
        grid: [45, 115, 180, 245, 285],
        fillReach: 'M 0 285 L 0 218 C 150 163, 300 190, 480 61 C 600 48, 700 109, 800 75 L 800 285 Z',
        fillEng: 'M 0 285 L 0 245 C 150 197, 300 224, 480 116 C 600 95, 700 150, 800 122 L 800 285 Z',
        fillClicks: 'M 0 285 L 0 265 C 150 231, 300 252, 480 177 C 600 150, 700 197, 800 177 L 800 285 Z',
        lineReach: 'M 0 218 C 150 163, 300 190, 480 61 C 600 48, 700 109, 800 75',
        lineEng: 'M 0 245 C 150 197, 300 224, 480 116 C 600 95, 700 150, 800 122',
        lineClicks: 'M 0 265 C 150 231, 300 252, 480 177 C 600 150, 700 197, 800 177',
        yReach: 61, yEng: 116, yClicks: 177, baselineY: 285
      }
    }
  }
};

var HEIGHT_MAP = {
  'compact': { px: '160px', viewHeight: 160 },
  'standard': { px: '220px', viewHeight: 220 },
  'expanded': { px: '300px', viewHeight: 300 }
};

// High-precision binary search to calculate exact Y coordinate along any SVG path at given X
function getSvgPathYAtX(pathEl, targetX) {
  if (!pathEl || typeof pathEl.getTotalLength !== 'function') return null;
  var totalLen = pathEl.getTotalLength();
  if (!totalLen || totalLen <= 0) return null;
  var low = 0;
  var high = totalLen;
  var pt = null;
  for (var i = 0; i < 14; i++) {
    var mid = (low + high) / 2;
    pt = pathEl.getPointAtLength(mid);
    if (!pt) break;
    if (pt.x < targetX) {
      low = mid;
    } else {
      high = mid;
    }
  }
  return pt ? Math.round(pt.y * 10) / 10 : null;
}

// Render Dashboard Graph across both X and Y axes
function renderDashboardChart() {
  var rangeCfg = DASHBOARD_CHART_DATA[currentRange] || DASHBOARD_CHART_DATA['7D'];
  var heightCfg = HEIGHT_MAP[currentHeightKey] || HEIGHT_MAP['standard'];
  var h = heightCfg.viewHeight;
  var scale = rangeCfg.scales[h] || rangeCfg.scales[220];

  // Update KPI Metrics
  var reachEl = document.getElementById('metric-total-reach');
  var engEl = document.getElementById('metric-engagement');
  var clicksEl = document.getElementById('metric-clicks');
  if (reachEl) reachEl.textContent = rangeCfg.metrics.reach;
  if (engEl) engEl.textContent = rangeCfg.metrics.eng;
  if (clicksEl) clicksEl.textContent = rangeCfg.metrics.clicks;

  // Update Y-Axis Scale
  var yAxisEl = document.getElementById('dashboard-chart-y-axis');
  if (yAxisEl && rangeCfg.yAxis) {
    yAxisEl.innerHTML = rangeCfg.yAxis.map(function (v) { return '<span>' + v + '</span>'; }).join('');
    yAxisEl.style.height = heightCfg.px;
  }

  // Update X-Axis
  var xAxisEl = document.getElementById('dashboard-chart-x-axis');
  if (xAxisEl && rangeCfg.xAxis) {
    xAxisEl.innerHTML = rangeCfg.xAxis.map(function (v) { return '<span>' + v + '</span>'; }).join('');
  }

  // Update Container Height & SVG viewBox
  var svgContainer = document.getElementById('dashboard-svg-container');
  var svg = document.getElementById('performance-chart-svg');
  if (svgContainer) svgContainer.style.height = heightCfg.px;
  if (svg) svg.setAttribute('viewBox', '0 0 800 ' + h);

  // Update 5 Gridlines across Y Axis
  var g1 = document.getElementById('dash-grid-1');
  var g2 = document.getElementById('dash-grid-2');
  var g3 = document.getElementById('dash-grid-3');
  var g4 = document.getElementById('dash-grid-4');
  var gBase = document.getElementById('dash-grid-baseline');
  if (g1) { g1.setAttribute('y1', scale.grid[0]); g1.setAttribute('y2', scale.grid[0]); }
  if (g2) { g2.setAttribute('y1', scale.grid[1]); g2.setAttribute('y2', scale.grid[1]); }
  if (g3) { g3.setAttribute('y1', scale.grid[2]); g3.setAttribute('y2', scale.grid[2]); }
  if (g4) { g4.setAttribute('y1', scale.grid[3]); g4.setAttribute('y2', scale.grid[3]); }
  if (gBase) { gBase.setAttribute('y1', scale.grid[4]); gBase.setAttribute('y2', scale.grid[4]); }

  // Update Spline Paths & Fills
  var pFillReach = document.getElementById('path-fill-reach');
  var pFillEng = document.getElementById('path-fill-eng');
  var pFillClicks = document.getElementById('path-fill-clicks');
  var pLineReach = document.getElementById('path-line-reach');
  var pLineEng = document.getElementById('path-line-eng');
  var pLineClicks = document.getElementById('path-line-clicks');

  if (pFillReach) pFillReach.setAttribute('d', scale.fillReach);
  if (pFillEng) pFillEng.setAttribute('d', scale.fillEng);
  if (pFillClicks) pFillClicks.setAttribute('d', scale.fillClicks);
  if (pLineReach) pLineReach.setAttribute('d', scale.lineReach);
  if (pLineEng) pLineEng.setAttribute('d', scale.lineEng);
  if (pLineClicks) pLineClicks.setAttribute('d', scale.lineClicks);

  // Update Focal Points & Guideline
  var fLine = document.getElementById('chart-focal-line');
  var ptReach = document.getElementById('point-reach');
  var ptEng = document.getElementById('point-eng');
  var ptClicks = document.getElementById('point-clicks');
  var tooltip = document.getElementById('dashboard-chart-tooltip');

  if (fLine) {
    fLine.setAttribute('x1', rangeCfg.focalX);
    fLine.setAttribute('x2', rangeCfg.focalX);
    fLine.setAttribute('y1', Math.round(h * 0.09));
    fLine.setAttribute('y2', scale.baselineY);
  }
  var initYR = getSvgPathYAtX(pLineReach, rangeCfg.focalX) || scale.yReach;
  var initYE = getSvgPathYAtX(pLineEng, rangeCfg.focalX) || scale.yEng;
  var initYC = getSvgPathYAtX(pLineClicks, rangeCfg.focalX) || scale.yClicks;
  if (ptReach) { ptReach.setAttribute('cx', rangeCfg.focalX); ptReach.setAttribute('cy', initYR); }
  if (ptEng) { ptEng.setAttribute('cx', rangeCfg.focalX); ptEng.setAttribute('cy', initYE); }
  if (ptClicks) { ptClicks.setAttribute('cx', rangeCfg.focalX); ptClicks.setAttribute('cy', initYC); }

  if (tooltip) {
    tooltip.style.left = ((rangeCfg.focalX / 800) * 100) + '%';
    var dLabel = document.getElementById('tooltip-day-label');
    var rVal = document.getElementById('tooltip-reach-val');
    var eVal = document.getElementById('tooltip-eng-val');
    var cVal = document.getElementById('tooltip-clicks-val');
    if (dLabel) dLabel.textContent = rangeCfg.focalLabel;
    if (rVal) rVal.textContent = rangeCfg.focalReach;
    if (eVal) eVal.textContent = rangeCfg.focalEng;
    if (cVal) cVal.textContent = rangeCfg.focalClicks;
  }
}

// Chart Time-Range Toggle
window.setChartRange = function (range, btn) {
  var container = btn.closest('.chart-time-tabs');
  if (container) {
    container.querySelectorAll('.btn').forEach(function (b) { b.classList.remove('active'); });
  }
  btn.classList.add('active');
  currentRange = range;

  var svg = document.getElementById('performance-chart-svg');
  if (svg) {
    svg.style.transition = 'opacity 0.15s ease';
    svg.style.opacity = '0.35';
    setTimeout(function () {
      renderDashboardChart();
      svg.style.opacity = '1';
    }, 150);
  } else {
    renderDashboardChart();
  }
};

// Chart Height / Sizing Toggle
window.setChartHeight = function (sizeKey, btn) {
  var container = btn.closest('.chart-size-tabs');
  if (container) {
    container.querySelectorAll('.btn').forEach(function (b) { b.classList.remove('active'); });
  }
  btn.classList.add('active');
  currentHeightKey = sizeKey;

  renderDashboardChart();

  try {
    localStorage.setItem('scg-chart-height', sizeKey);
  } catch (e) { /* ignore */ }
};

// Interactive Hover on Dashboard SVG
function initDashboardChartInteractivity() {
  var container = document.getElementById('dashboard-svg-container');
  var svg = document.getElementById('performance-chart-svg');
  var tooltip = document.getElementById('dashboard-chart-tooltip');
  if (!container || !svg || !tooltip) return;

  container.addEventListener('mousemove', function (e) {
    var rect = container.getBoundingClientRect();
    var relX = (e.clientX - rect.left) / rect.width;
    relX = Math.max(0.04, Math.min(0.96, relX));

    var svgX = Math.round(relX * 800);
    var h = (HEIGHT_MAP[currentHeightKey] || HEIGHT_MAP['standard']).viewHeight;

    var fLine = document.getElementById('chart-focal-line');
    var ptReach = document.getElementById('point-reach');
    var ptEng = document.getElementById('point-eng');
    var ptClicks = document.getElementById('point-clicks');

    var pLineReach = document.getElementById('path-line-reach');
    var pLineEng = document.getElementById('path-line-eng');
    var pLineClicks = document.getElementById('path-line-clicks');

    // Exact curve evaluation along current X
    var yR = getSvgPathYAtX(pLineReach, svgX);
    var yE = getSvgPathYAtX(pLineEng, svgX);
    var yC = getSvgPathYAtX(pLineClicks, svgX);

    if (fLine) { fLine.setAttribute('x1', svgX); fLine.setAttribute('x2', svgX); }
    if (ptReach && yR !== null) { ptReach.setAttribute('cx', svgX); ptReach.setAttribute('cy', yR); }
    if (ptEng && yE !== null) { ptEng.setAttribute('cx', svgX); ptEng.setAttribute('cy', yE); }
    if (ptClicks && yC !== null) { ptClicks.setAttribute('cx', svgX); ptClicks.setAttribute('cy', yC); }

    tooltip.style.left = (relX * 100) + '%';
  });
}

// Interactive Hover for Analytics Graphs (Responsive & Dynamic Tracking)
function initAnalyticsInteractivity() {
  // Graph 1: Social Media Performance Trends (Hero)
  var heroVp = document.getElementById('analytics-hero-viewport');
  var heroLine = document.getElementById('analytics-hero-line');
  var heroPtGreen = document.getElementById('analytics-hero-pt-green');
  var heroPtBlue = document.getElementById('analytics-hero-pt-blue');
  var heroPathGreen = document.getElementById('analytics-hero-path-green');
  var heroPathBlue = document.getElementById('analytics-hero-path-blue');
  var heroTooltip = document.getElementById('analytics-hero-tooltip');
  var heroDate = document.getElementById('analytics-hero-tooltip-header');
  var heroConv = document.getElementById('analytics-hero-tooltip-conv');
  var heroEng = document.getElementById('analytics-hero-tooltip-eng');

  var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  if (heroVp && heroLine && heroPtGreen && heroPtBlue && heroTooltip) {
    heroVp.addEventListener('mousemove', function (e) {
      var rect = heroVp.getBoundingClientRect();
      var relX = (e.clientX - rect.left) / rect.width;
      relX = Math.max(0.01, Math.min(0.99, relX));
      var svgX = Math.round(relX * 800);

      heroLine.setAttribute('x1', svgX);
      heroLine.setAttribute('x2', svgX);

      // Exact curve evaluation on the green and blue paths
      var greenY = getSvgPathYAtX(heroPathGreen, svgX);
      var blueY = getSvgPathYAtX(heroPathBlue, svgX);

      if (greenY !== null && heroPtGreen) {
        heroPtGreen.setAttribute('cx', svgX);
        heroPtGreen.setAttribute('cy', greenY);
      }
      if (blueY !== null && heroPtBlue) {
        heroPtBlue.setAttribute('cx', svgX);
        heroPtBlue.setAttribute('cy', blueY);
      }

      heroTooltip.style.left = (relX * 100) + '%';
      var mIndex = Math.min(11, Math.floor(relX * 12));
      if (heroDate) heroDate.textContent = months[mIndex] + ' 14, 2026';
      if (heroConv && greenY !== null) {
        var rate1 = Math.max(10, Math.min(60, ((220 - greenY) / 200) * 50 + 10));
        heroConv.textContent = rate1.toFixed(1) + '%';
      }
      if (heroEng && blueY !== null) {
        var rate2 = Math.max(10, Math.min(60, ((220 - blueY) / 200) * 50 + 10));
        heroEng.textContent = rate2.toFixed(1) + '%';
      }
    });
  }

  // Graph 2: Content Performance by Channel Wave
  var waveVp = document.getElementById('analytics-wave-viewport');
  var waveLine = document.getElementById('analytics-wave-line');
  var wavePt = document.getElementById('analytics-wave-pt');
  var wavePathGreen = document.getElementById('analytics-wave-path-green');
  var wavePathBlue = document.getElementById('analytics-wave-path-blue');
  var waveTooltip = document.getElementById('analytics-wave-tooltip');
  var waveHeader = document.getElementById('analytics-wave-tooltip-header');
  var waveVal = document.getElementById('analytics-wave-tooltip-val');

  if (waveVp && waveLine && wavePt && waveTooltip) {
    waveVp.addEventListener('mousemove', function (e) {
      var rect = waveVp.getBoundingClientRect();
      var relX = (e.clientX - rect.left) / rect.width;
      relX = Math.max(0.01, Math.min(0.99, relX));
      var svgX = Math.round(relX * 500);

      waveLine.setAttribute('x1', svgX);
      waveLine.setAttribute('x2', svgX);

      // Exact curve evaluation on the organic reach wave
      var waveY = getSvgPathYAtX(wavePathGreen, svgX);
      if (waveY !== null && wavePt) {
        wavePt.setAttribute('cx', svgX);
        wavePt.setAttribute('cy', waveY);
      }

      waveTooltip.style.left = (relX * 100) + '%';
      if (waveVal && waveY !== null) {
        var count = Math.round(1000 + (150 - waveY) * 22);
        waveVal.textContent = count.toLocaleString() + ' Interactions';
      }
      if (waveHeader) waveHeader.textContent = 'Day ' + Math.round(relX * 90 + 1) + ', 2026';
    });
  }

  // Graph 3: Platform-Wise Performance Distribution (Lollipop Bars Interactivity)
  var columns = document.querySelectorAll('.platform-dist-column');
  columns.forEach(function (col) {
    col.style.transition = 'transform 0.2s ease, filter 0.2s ease';
    col.style.cursor = 'pointer';
    col.addEventListener('mouseenter', function () {
      col.style.transform = 'translateY(-4px)';
      col.style.filter = 'drop-shadow(0 6px 12px rgba(79, 70, 229, 0.25))';
    });
    col.addEventListener('mouseleave', function () {
      col.style.transform = 'translateY(0)';
      col.style.filter = 'none';
    });
  });
}

document.addEventListener('DOMContentLoaded', function () {
  updateDynamicGreeting();
  initDashboardChartInteractivity();
  initAnalyticsInteractivity();

  // Restore saved chart height preference if present
  try {
    var savedHeight = localStorage.getItem('scg-chart-height');
    if (savedHeight && HEIGHT_MAP[savedHeight]) {
      currentHeightKey = savedHeight;
      var btn = document.querySelector('.chart-size-tabs button[data-size="' + savedHeight + '"]');
      if (btn) {
        var container = btn.closest('.chart-size-tabs');
        if (container) {
          container.querySelectorAll('.btn').forEach(function (b) { b.classList.remove('active'); });
        }
        btn.classList.add('active');
      }
    }
  } catch (e) { /* ignore */ }

  renderDashboardChart();
});

setInterval(function () {
  quoteIndex++;
  updateDynamicGreeting();
}, 60000);
