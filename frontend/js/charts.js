/**
 * GapScope Chart.js Controller
 * Manages Chart.js instances, half-circle score gauge, and smooth trend line chart.
 * Uses finprob.com's stone + orange-500 palette and instance destruction to prevent canvas collisions.
 */

const activeCharts = new Map();

/**
 * Safely destroy any existing chart on a canvas
 * @param {string|HTMLCanvasElement} canvasTarget 
 */
export function destroyChart(canvasTarget) {
  const canvas = typeof canvasTarget === 'string' ? document.getElementById(canvasTarget) : canvasTarget;
  if (!canvas) return;

  const existingChart = activeCharts.get(canvas);
  if (existingChart) {
    try {
      existingChart.destroy();
    } catch (e) {
      console.warn('[GapScope] Chart destroy warning:', e);
    }
    activeCharts.delete(canvas);
  }
}

/**
 * Render Half-Circle Doughnut Score Gauge (Mode 1)
 * @param {string} canvasId 
 * @param {number} score 0–100
 * @param {string} label BUILD / PIVOT / KILL
 */
export function renderScoreGauge(canvasId, score = 0, label = 'PIVOT') {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  destroyChart(canvas);

  const normalizedScore = Math.min(100, Math.max(0, Number(score) || 0));
  const remaining = 100 - normalizedScore;

  // Drawn on the dark (stone-950) verdict panel
  let barColor = '#F97316'; // orange-500: PIVOT
  const upper = String(label).toUpperCase();
  if (upper === 'BUILD' || upper === 'GROWING') {
    barColor = '#22C55E';
  } else if (upper === 'KILL' || upper === 'DECLINING') {
    barColor = '#EF4444';
  }

  const ctx = canvas.getContext('2d');
  const chart = new window.Chart(ctx, {
    type: 'doughnut',
    data: {
      datasets: [{
        data: [normalizedScore, remaining],
        backgroundColor: [barColor, '#292524'],
        borderWidth: 0,
        borderRadius: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      circumference: 180,
      rotation: 270,
      cutout: '80%',
      animation: {
        animateRotate: true,
        duration: 800
      },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false }
      }
    }
  });

  activeCharts.set(canvas, chart);
  return chart;
}

/**
 * Render Google Trends Timeseries Line Chart
 * @param {string} canvasId 
 * @param {object} trendData { points: [{date, value}], keyword, change_pct, direction }
 */
export function renderTrendLineChart(canvasId, trendData) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  destroyChart(canvas);

  if (!trendData || !trendData.points || !trendData.points.length) {
    return;
  }

  const points = trendData.points;
  const labels = points.map(p => {
    const parts = String(p.date).split('-');
    if (parts.length === 2) {
      const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      const mIdx = parseInt(parts[1], 10) - 1;
      const yrShort = parts[0].slice(-2);
      return `${monthNames[mIdx] || parts[1]} '${yrShort}`;
    }
    return p.date;
  });

  const values = points.map(p => Number(p.value) || 0);
  const ctx = canvas.getContext('2d');

  // Gradient fill underneath
  const gradient = ctx.createLinearGradient(0, 0, 0, 220);
  const direction = (trendData.direction || 'flat').toLowerCase();

  let strokeColor = '#F97316'; // orange-500
  let fillColorStart = 'rgba(249, 115, 22, 0.22)';
  let fillColorEnd = 'rgba(249, 115, 22, 0.0)';

  if (direction === 'falling') {
    strokeColor = '#DC2626';
    fillColorStart = 'rgba(220, 38, 38, 0.16)';
    fillColorEnd = 'rgba(220, 38, 38, 0.0)';
  } else if (direction === 'flat') {
    strokeColor = '#0C0A09';
    fillColorStart = 'rgba(12, 10, 9, 0.10)';
    fillColorEnd = 'rgba(12, 10, 9, 0.0)';
  }

  gradient.addColorStop(0, fillColorStart);
  gradient.addColorStop(1, fillColorEnd);

  const chart = new window.Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: `Interest: "${trendData.keyword || 'Search Query'}"`,
        data: values,
        borderColor: strokeColor,
        borderWidth: 2,
        backgroundColor: gradient,
        fill: true,
        tension: 0.35,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointBackgroundColor: strokeColor,
        pointBorderColor: '#FFFFFF',
        pointBorderWidth: 1.5
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        intersect: false,
        mode: 'index'
      },
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          backgroundColor: '#0C0A09',
          titleFont: { size: 12, family: 'JetBrains Mono', weight: '600' },
          bodyFont: { size: 12, family: 'Inter' },
          padding: 10,
          cornerRadius: 6,
          displayColors: false,
          callbacks: {
            title: (items) => items[0].label,
            label: (item) => `Interest ${item.formattedValue} / 100`
          }
        }
      },
      scales: {
        x: {
          grid: {
            display: false,
            drawBorder: false
          },
          ticks: {
            font: { family: 'JetBrains Mono', size: 11 },
            color: '#57534E',
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 7
          }
        },
        y: {
          min: 0,
          max: 100,
          grid: {
            color: '#F5F5F4',
            drawBorder: false
          },
          ticks: {
            font: { family: 'JetBrains Mono', size: 10 },
            color: '#A8A29E',
            stepSize: 25,
            callback: (val) => `${val}`
          }
        }
      }
    }
  });

  activeCharts.set(canvas, chart);
  return chart;
}
