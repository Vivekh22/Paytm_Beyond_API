/**
 * GapScope Application Orchestrator
 * Wires state, events, hash routing, the live SSE stream and the evidence drawer.
 */

import { CONFIG } from './config.js';
import { startScan, streamScan, getReport, getExamples, allowFinding } from './api.js';
import {
  esc,
  formatDate,
  formatNum,
  renderVerdictHero,
  renderCompetitors,
  renderReceiptsSection,
  renderOpportunities,
  renderNewsSection,
  renderFindingsSection,
  renderDrawerContent
} from './render.js';
import { renderScoreGauge, renderTrendLineChart, destroyChart } from './charts.js';

// Application State
const state = {
  mode: 1, // 1: validate, 2: investigate, 3: discover, 4: protect
  examples: [],
  query: '',
  activeReport: null,
  activeStreamController: null,
  drawer: {
    isOpen: false,
    title: '',
    subtitle: '',
    items: [],
    activeFilter: 'all'
  }
};

// DOM Cache
const dom = {
  heroStartBtn: document.getElementById('heroStartBtn'),
  heroSeeResultBtn: document.getElementById('heroSeeResultBtn'),
  searchHub: document.getElementById('searchHub'),
  modeBtn1: document.getElementById('modeBtn1'),
  modeBtn2: document.getElementById('modeBtn2'),
  modeBtn3: document.getElementById('modeBtn3'),
  modeBtn4: document.getElementById('modeBtn4'),
  modeHint: document.getElementById('modeHint'),
  protectFieldsWrapper: document.getElementById('protectFieldsWrapper'),
  officialDomainsInput: document.getElementById('officialDomainsInput'),
  officialPhonesInput: document.getElementById('officialPhonesInput'),
  officialAppsInput: document.getElementById('officialAppsInput'),
  examplesLabel: document.getElementById('examplesLabel'),
  findingsSection: document.getElementById('findingsSection'),
  scanForm: document.getElementById('scanForm'),
  textInputWrapper: document.getElementById('textInputWrapper'),
  scanQueryInput: document.getElementById('scanQueryInput'),
  categoryGridWrapper: document.getElementById('categoryGridWrapper'),
  categoryChips: document.getElementById('categoryChips'),
  catOtherBtn: document.getElementById('catOtherBtn'),
  otherCategoryInputRow: document.getElementById('otherCategoryInputRow'),
  otherCategoryInput: document.getElementById('otherCategoryInput'),
  confirmOtherCatBtn: document.getElementById('confirmOtherCatBtn'),
  examplePillsContainer: document.getElementById('examplePillsContainer'),
  
  // Credit Meter
  creditMeterText: document.getElementById('creditMeterText'),

  // Progress
  progressArea: document.getElementById('progressArea'),
  progressStatusHeader: document.getElementById('progressStatusHeader'),
  progressPercentage: document.getElementById('progressPercentage'),
  scanProgressBar: document.getElementById('scanProgressBar'),
  progressStepList: document.getElementById('progressStepList'),
  
  // Error
  scanErrorCard: document.getElementById('scanErrorCard'),
  scanErrorMessage: document.getElementById('scanErrorMessage'),
  retryScanBtn: document.getElementById('retryScanBtn'),

  // Report
  reportContainer: document.getElementById('reportContainer'),
  reportWarnings: document.getElementById('reportWarnings'),
  reportWarningsContent: document.getElementById('reportWarningsContent'),
  verdictSection: document.getElementById('verdictSection'),
  trendCard: document.getElementById('trendCard'),
  trendChangeBadge: document.getElementById('trendChangeBadge'),
  trendKeywordMeta: document.getElementById('trendKeywordMeta'),
  competitorsCard: document.getElementById('competitorsCard'),
  competitorsCountBadge: document.getElementById('competitorsCountBadge'),
  competitorsList: document.getElementById('competitorsList'),
  receiptsSection: document.getElementById('receiptsSection'),
  opportunitiesSection: document.getElementById('opportunitiesSection'),
  newsSection: document.getElementById('newsSection'),
  footerMetaSources: document.getElementById('footerMetaSources'),
  footerMetaTimestamp: document.getElementById('footerMetaTimestamp'),
  copyShareLinkBtn: document.getElementById('copyShareLinkBtn'),
  printReportBtn: document.getElementById('printReportBtn'),

  // Drawer
  evidenceDrawer: document.getElementById('evidenceDrawer'),
  drawerBackdrop: document.getElementById('drawerBackdrop'),
  closeDrawerBtn: document.getElementById('closeDrawerBtn'),
  drawerTitle: document.getElementById('drawerTitle'),
  drawerSubtitle: document.getElementById('drawerSubtitle'),
  drawerSourceFilters: document.getElementById('drawerSourceFilters'),
  drawerEvidenceList: document.getElementById('drawerEvidenceList'),
  drawerItemsCount: document.getElementById('drawerItemsCount'),

  // Toast
  toast: document.getElementById('toast'),
  toastMessage: document.getElementById('toastMessage')
};

/**
 * Show a quick toast notification
 */
function showToast(message = 'Copied to clipboard') {
  if (!dom.toast) return;
  dom.toast.textContent = message;
  dom.toast.classList.remove('hidden');
  setTimeout(() => {
    dom.toast.classList.add('hidden');
  }, 2400);
}

/**
 * Update Credit Meter UI
 */
function updateCreditMeter(credits = {}) {
  const serpLive = Number(credits.serpapi_live) || 0;
  const serpCached = Number(credits.serpapi_cached) || 0;
  const youLive = Number(credits.youcom_live) || 0;
  const youCached = Number(credits.youcom_cached) || 0;

  const totalCalls = serpLive + serpCached + youLive + youCached;
  const totalCached = serpCached + youCached;

  const text = `${totalCalls} calls · ${totalCached} cached`;
  if (dom.creditMeterText) dom.creditMeterText.textContent = text;
  const mobile = document.getElementById('creditMeterTextMobile');
  if (mobile) mobile.textContent = text;
}

/**
 * Switch Active Mode (1, 2, or 3)
 */
const MODE_META = {
  1: { slug: 'validate', name: 'Validate an idea', placeholder: 'e.g. UPI expense tracker for college students',
       label: 'Describe your idea', hint: 'Describe an idea. You get a 0–100 score, BUILD / PIVOT / KILL, and the complaints competitors ignore.' },
  2: { slug: 'investigate', name: 'Investigate a business', placeholder: 'e.g. Dunzo, Cult.fit, Swiggy Instamart',
       label: 'Name a business or app', hint: 'Name a company or app. You get GROWING / STAGNATING / DECLINING, a month-by-month timeline and what users love and hate.' },
  3: { slug: 'discover', name: 'Discover an opportunity', placeholder: '',
       label: 'Pick a category', hint: 'Pick a category. GapScope scans its top 5 apps and finds the complaints they share.' },
  4: { slug: 'protect', name: 'Protect a brand', placeholder: 'e.g. Blue Dart, IRCTC, your college name',
       label: 'Brand or organisation name', hint: 'Name a brand. GapScope finds numbers, job posts, websites and apps using its name that don’t match its official records.' }
};
const SLUG_TO_MODE = { validate: 1, investigate: 2, discover: 3, protect: 4 };

function switchMode(newMode) {
  state.mode = [1, 2, 3, 4].includes(Number(newMode)) ? Number(newMode) : 1;
  const meta = MODE_META[state.mode];

  // Styling is driven by aria-selected (Tailwind aria-selected: variants in index.html)
  [dom.modeBtn1, dom.modeBtn2, dom.modeBtn3, dom.modeBtn4].forEach((btn, i) => {
    if (!btn) return;
    btn.setAttribute('aria-selected', i + 1 === state.mode ? 'true' : 'false');
    btn.tabIndex = i + 1 === state.mode ? 0 : -1;
  });
  document.querySelectorAll('.nav-mode').forEach(a => {
    a.setAttribute('aria-current', Number(a.getAttribute('data-mode')) === state.mode ? 'true' : 'false');
  });

  if (dom.modeHint) dom.modeHint.textContent = meta.hint;
  const isDiscover = state.mode === 3;
  dom.textInputWrapper.classList.toggle('hidden', isDiscover);
  dom.categoryGridWrapper.classList.toggle('hidden', !isDiscover);
  if (dom.protectFieldsWrapper) dom.protectFieldsWrapper.classList.toggle('hidden', state.mode !== 4);
  if (!isDiscover) {
    dom.scanQueryInput.placeholder = meta.placeholder;
    dom.scanQueryInput.setAttribute('aria-label', meta.label);
  }

  dom.otherCategoryInputRow.classList.add('hidden');
  renderExamplePills();
}

function splitList(v) {
  return String(v || '').split(',').map(x => x.trim()).filter(Boolean);
}

function readOfficialRecords() {
  if (!dom.officialDomainsInput) return null;
  const official = {
    domains: splitList(dom.officialDomainsInput.value),
    phones: splitList(dom.officialPhonesInput.value),
    app_ids: splitList(dom.officialAppsInput.value)
  };
  return (official.domains.length || official.phones.length || official.app_ids.length) ? official : null;
}

/**
 * Render Example Pills under search
 */
async function loadExamplePills() {
  state.examples = await getExamples();
  renderExamplePills();
}

function renderExamplePills() {
  if (!dom.examplePillsContainer) return;
  const examples = (state.examples || []).filter(ex => Number(ex.mode) === state.mode);
  if (dom.examplesLabel) dom.examplesLabel.textContent = examples.length ? `Examples · ${MODE_META[state.mode].name}` : '';
  dom.examplePillsContainer.innerHTML = examples.map(ex => `
    <button type="button" class="example-pill inline-flex min-h-[40px] items-center gap-2 rounded-full border border-stone-400 bg-white px-3.5 text-sm font-medium hover:border-stone-950"
      data-mode="${esc(ex.mode)}"
      data-query="${esc(ex.query)}">
      <span>${esc(ex.label)}</span>
      ${ex.cached ? '<span class="rounded bg-orange-500 px-1.5 py-px font-mono text-[11px] font-semibold text-stone-950" title="Saved result: loads without new API calls">instant</span>' : ''}
    </button>
  `).join('');

  dom.examplePillsContainer.querySelectorAll('.example-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      const mode = Number(pill.getAttribute('data-mode'));
      const query = pill.getAttribute('data-query');
      switchMode(mode);
      dom.scanQueryInput.value = query;
      executeScan(mode, query);
    });
  });
}

const SPINNER = '<span class="gs-spin block h-4 w-4 rounded-full border-2 border-stone-300 border-t-orange-500"></span>';
const CHECK = '<span class="flex h-5 w-5 items-center justify-center rounded-full bg-stone-950 text-[11px] font-bold text-white">✓</span>';

function markStepsDone() {
  dom.progressStepList.querySelectorAll('.step-icon').forEach(el => { el.innerHTML = CHECK; });
}

function sourceFromStep(step = '') {
  const s = String(step).toLowerCase();
  if (s.includes('you')) return 'You.com';
  if (s.includes('keyword') || s.includes('cluster') || s.includes('gemini')) return 'Gemini';
  if (s.includes('score')) return 'Python';
  if (s) return 'SerpApi';
  return '';
}

/**
 * Handle Live SSE Progress events
 */
function handleProgressEvent(data) {
  if (data.type === 'progress') {
    const pct = Math.min(100, Math.max(0, data.pct || 0));
    dom.progressPercentage.textContent = `${pct}%`;
    dom.scanProgressBar.style.width = `${pct}%`;
    dom.progressStatusHeader.textContent = data.message || 'Scanning market evidence...';

    markStepsDone();
    const stepItem = document.createElement('li');
    stepItem.className = 'progress-step flex items-center gap-[18px] border-t border-stone-200 py-3.5';
    const sourceLabel = data.source || sourceFromStep(data.step);
    const n = dom.progressStepList.children.length + 1;
    stepItem.innerHTML = `
      <span class="w-[22px] flex-none font-mono text-sm font-semibold">${n}</span>
      <span class="step-icon flex h-5 w-5 flex-none items-center justify-center" aria-hidden="true">${SPINNER}</span>
      <span class="min-w-0 flex-1 text-[15px]">${esc(data.message)}</span>
      ${sourceLabel ? `<span class="flex-none rounded-full border border-stone-400 px-2.5 py-1 font-mono text-xs">${esc(sourceLabel)}</span>` : ''}
    `;
    dom.progressStepList.appendChild(stepItem);
  } else if (data.type === 'done') {
    markStepsDone();
    dom.progressArea.setAttribute('aria-busy', 'false');
    dom.progressStatusHeader.textContent = 'Done. Building the report…';
    dom.progressPercentage.textContent = '100%';
    dom.scanProgressBar.style.width = '100%';
    setTimeout(() => {
      dom.progressArea.classList.add('hidden');
      renderReport(data.report);
    }, 450);
  } else if (data.type === 'error') {
    dom.progressArea.classList.add('hidden');
    dom.scanErrorCard.classList.remove('hidden');
    dom.scanErrorMessage.textContent = data.message || 'An unexpected error occurred during scan.';
  }
}

/**
 * Execute a new Scan
 */
async function executeScan(mode, query) {
  if (!query || !query.trim()) {
    showToast(mode === 3 ? 'Pick a category first' : 'Type something to scan first');
    const target = mode === 3 ? dom.categoryChips.querySelector('.cat-chip') : dom.scanQueryInput;
    if (target) target.focus();
    return;
  }

  const cleanQuery = query.trim();
  state.query = cleanQuery;
  state.mode = mode;

  if (state.activeStreamController) {
    state.activeStreamController.abort();
    state.activeStreamController = null;
  }

  history.replaceState(null, '', `#mode=${mode}&q=${encodeURIComponent(cleanQuery)}`);

  dom.scanErrorCard.classList.add('hidden');
  dom.reportContainer.classList.add('hidden');
  dom.progressArea.classList.remove('hidden');
  dom.progressPercentage.textContent = '0%';
  dom.scanProgressBar.style.width = '0%';
  dom.progressStepList.innerHTML = '';
  dom.progressStatusHeader.textContent = 'Connecting to SerpApi and You.com…';
  dom.progressArea.setAttribute('aria-busy', 'true');

  dom.progressArea.scrollIntoView({ behavior: 'smooth', block: 'start' });

  try {
    const scanResponse = await startScan(mode, cleanQuery, mode === 4 ? readOfficialRecords() : null);
    const scanId = scanResponse.scan_id || `scan_${Date.now()}`;
    
    state.activeStreamController = streamScan(scanId, handleProgressEvent, {
      mode,
      query: cleanQuery
    });
  } catch (err) {
    dom.progressArea.classList.add('hidden');
    dom.scanErrorCard.classList.remove('hidden');
    dom.scanErrorMessage.textContent = err.message || 'Failed to start market scan.';
  }
}

/**
 * Full Report Renderer
 */
function renderReport(report) {
  state.activeReport = report;

  // 1. Credit Meter
  if (report.credits) {
    updateCreditMeter(report.credits);
  }

  // 2. Warnings Banner
  if (report.warnings && report.warnings.length) {
    dom.reportWarningsContent.innerHTML = report.warnings.map(w => `<p>${esc(w)}</p>`).join('');
    dom.reportWarnings.classList.remove('hidden');
  } else {
    dom.reportWarnings.classList.add('hidden');
  }

  // 3. Verdict Hero
  dom.verdictSection.innerHTML = renderVerdictHero(report);

  // If Mode 1: Render half-circle Gauge
  if (report.mode === 1) {
    const score = report.verdict ? report.verdict.score : 50;
    const label = report.verdict ? report.verdict.label : 'PIVOT';
    setTimeout(() => {
      renderScoreGauge('gaugeCanvas', score, label);
    }, 50);
  }

  // 4. Trend Card
  if (report.trend && report.trend.points && report.trend.points.length) {
    dom.trendCard.classList.remove('hidden');
    const direction = (report.trend.direction || 'flat').toLowerCase();
    const changePct = report.trend.change_pct !== undefined ? Math.abs(report.trend.change_pct) : 0;
    
    let badgeClass = 'border-stone-400 text-stone-700';
    let arrow = '→';
    if (direction === 'rising') {
      badgeClass = 'border-orange-500 bg-orange-500 text-stone-950 font-semibold';
      arrow = '▲';
    } else if (direction === 'falling') {
      badgeClass = 'border-red-600 text-red-700 font-semibold';
      arrow = '▼';
    }

    dom.trendChangeBadge.className = `rounded-full border px-2.5 py-1 font-mono text-xs tabular-nums ${badgeClass}`;
    dom.trendChangeBadge.textContent = `${arrow} ${Number(changePct).toFixed(1).replace(/\.0$/, '')}% ${direction}`;
    // textContent is already safe; no esc() needed here
    dom.trendKeywordMeta.textContent = `“${report.trend.keyword || ''}” · geo=${report.trend.geo || 'IN'}`;

    setTimeout(() => {
      renderTrendLineChart('trendChartCanvas', report.trend);
    }, 60);
  } else {
    dom.trendCard.classList.add('hidden');
  }

  // 5. Competitors List
  const competitors = report.competitors || [];
  dom.competitorsCountBadge.textContent = `${competitors.length} found`;
  dom.competitorsList.innerHTML = renderCompetitors(competitors);

  // Market context (trend + competitors) only when there is something to show
  const marketCtx = document.getElementById('marketContextSection');
  if (marketCtx) marketCtx.classList.toggle('hidden', report.mode === 4 || (!report.trend && !competitors.length));

  // 6a. Protect findings (Mode 4)
  if (dom.findingsSection) {
    if (report.mode === 4) {
      dom.findingsSection.innerHTML = renderFindingsSection(report);
      dom.findingsSection.classList.remove('hidden');
    } else {
      dom.findingsSection.innerHTML = '';
      dom.findingsSection.classList.add('hidden');
    }
  }

  // 6b. Receipts / Clusters Section
  dom.receiptsSection.innerHTML = report.mode === 4 ? '' : renderReceiptsSection(report);

  // 7. Opportunities Section
  if (report.opportunities && report.opportunities.length) {
    dom.opportunitiesSection.innerHTML = renderOpportunities(report.opportunities, report.evidence || {}, report.clusters || []);
    dom.opportunitiesSection.classList.remove('hidden');
  } else {
    dom.opportunitiesSection.classList.add('hidden');
  }

  // 8. News & Web Intelligence
  if (report.news && report.news.length) {
    dom.newsSection.innerHTML = renderNewsSection(report.news, report.evidence || {});
    dom.newsSection.classList.remove('hidden');
  } else {
    dom.newsSection.classList.add('hidden');
  }

  // 9. Footer Metadata
  const totalEvidence = Object.keys(report.evidence || {}).length;
  dom.footerMetaSources.textContent = `${formatNum(totalEvidence)} sources`;
  dom.footerMetaTimestamp.textContent = `generated ${formatDate(report.generated_at || new Date().toISOString())}`;

  dom.reportContainer.classList.remove('hidden');
  attachReportInteractions(report);
  attachFindingActions(report);
  dom.reportContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/**
 * Protect (Mode 4): copy report text, mark a finding as allowed
 */
function attachFindingActions(report) {
  if (!dom.findingsSection || report.mode !== 4) return;
  dom.findingsSection.querySelectorAll('.btn-copy-report').forEach(btn => {
    btn.addEventListener('click', () => {
      const text = btn.getAttribute('data-report-text') || '';
      navigator.clipboard.writeText(text).then(() => showToast('Report text copied')).catch(() => showToast('Copy failed'));
    });
  });
  dom.findingsSection.querySelectorAll('.btn-allow-finding').forEach(btn => {
    btn.addEventListener('click', async () => {
      try {
        await allowFinding(report.query, btn.getAttribute('data-type'), btn.getAttribute('data-value'));
        const card = btn.closest('article');
        if (card) card.remove();
        showToast('Marked as allowed: hidden from future scans');
      } catch (err) {
        showToast(err.message || 'Could not save');
      }
    });
  });
}

/**
 * Interactive handlers inside the rendered report
 */
function attachReportInteractions(report) {
  const evidencePool = report.evidence || {};

  document.querySelectorAll('.btn-open-cluster-drawer').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const clusterTitle = btn.getAttribute('data-cluster-title') || 'Cluster Evidence';
      const evidenceIds = JSON.parse(btn.getAttribute('data-evidence-ids') || '[]');
      
      const items = evidenceIds
        .map(id => evidencePool[id])
        .filter(Boolean);

      openDrawer(`Receipts: ${clusterTitle}`, `${items.length} verified items in this cluster`, items);
    });
  });

  document.querySelectorAll('.btn-factor-evidence').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const factorTitle = btn.getAttribute('data-title') || 'Factor Evidence';
      const evidenceIds = JSON.parse(btn.getAttribute('data-evidence-ids') || '[]');

      const items = evidenceIds
        .map(id => evidencePool[id])
        .filter(Boolean);

      openDrawer(`Factor Evidence: ${factorTitle}`, `${items.length} verified items supporting this score`, items);
    });
  });

  document.querySelectorAll('.btn-jump-to-cluster').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const targetId = btn.getAttribute('data-target-cluster');
      const targetEl = document.getElementById(targetId);
      if (targetEl) {
        targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        targetEl.classList.remove('cluster-highlighted');
        void targetEl.offsetWidth;
        targetEl.classList.add('cluster-highlighted');
      }
    });
  });
}

/**
 * Open Evidence Drawer with specific items
 */
function openDrawer(title, subtitle, items) {
  state.drawer.isOpen = true;
  state.drawer.title = title;
  state.drawer.subtitle = subtitle;
  state.drawer.items = items;
  state.drawer.activeFilter = 'all';

  dom.drawerTitle.textContent = title;
  dom.drawerSubtitle.textContent = subtitle;

  renderDrawerFilters();
  renderDrawerItems();

  state.drawer.returnFocus = document.activeElement;
  dom.evidenceDrawer.classList.remove('hidden');
  document.body.classList.add('overflow-hidden');
  dom.closeDrawerBtn.focus();
}

/** Keep Tab focus inside the open drawer */
function trapDrawerFocus(e) {
  if (!state.drawer.isOpen || e.key !== 'Tab') return;
  const focusables = [...dom.evidenceDrawer.querySelectorAll('button, a[href], input, [tabindex]:not([tabindex="-1"])')]
    .filter(el => el.offsetParent !== null);
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

/**
 * Close Evidence Drawer
 */
function closeDrawer() {
  state.drawer.isOpen = false;
  dom.evidenceDrawer.classList.add('hidden');
  document.body.classList.remove('overflow-hidden');
  if (state.drawer.returnFocus && state.drawer.returnFocus.focus) state.drawer.returnFocus.focus();
}

/**
 * Render filter pills inside the drawer
 */
function renderDrawerFilters() {
  const items = state.drawer.items;
  
  const counts = { all: items.length };
  items.forEach(it => {
    const s = it.source || 'other';
    counts[s] = (counts[s] || 0) + 1;
  });

  const filterConfigs = [
    { key: 'all', label: 'All Sources' },
    { key: 'play_store', label: 'Play Store' },
    { key: 'reddit', label: 'Reddit' },
    { key: 'google_news', label: 'Google News' },
    { key: 'you_web', label: 'You.com Web' },
    { key: 'you_news', label: 'You.com News' }
  ];

  dom.drawerSourceFilters.innerHTML = filterConfigs
    .filter(fc => fc.key === 'all' || (counts[fc.key] && counts[fc.key] > 0))
    .map(fc => {
      const active = state.drawer.activeFilter === fc.key;
      const pillClass = active
        ? 'border-stone-950 bg-stone-950 text-white'
        : 'border-stone-400 hover:border-stone-950';

      return `
        <button type="button" class="drawer-filter-btn inline-flex min-h-[36px] items-center gap-1.5 rounded-full border px-3 font-mono text-xs ${pillClass}" data-filter="${fc.key}" aria-pressed="${active}">
          <span>${esc(fc.label)}</span>
          <span class="opacity-70">${counts[fc.key] || 0}</span>
        </button>
      `;
    }).join('');

  dom.drawerSourceFilters.querySelectorAll('.drawer-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      state.drawer.activeFilter = btn.getAttribute('data-filter');
      renderDrawerFilters();
      renderDrawerItems();
    });
  });
}

/**
 * Filter & render evidence items into drawer
 */
function renderDrawerItems() {
  const filter = state.drawer.activeFilter;
  const filtered = filter === 'all' ? 
    state.drawer.items : 
    state.drawer.items.filter(it => it.source === filter);

  dom.drawerEvidenceList.innerHTML = renderDrawerContent(filtered);
  dom.drawerItemsCount.textContent = `${filtered.length} of ${state.drawer.items.length} receipts`;
}

/**
 * Initialize URL hash routing
 */
function initHashRoute() {
  const hash = window.location.hash.replace(/^#/, '');
  if (!hash) return false;

  if (SLUG_TO_MODE[hash]) {
    openModeInput(SLUG_TO_MODE[hash]);
    return true;
  }

  const params = new URLSearchParams(hash);
  const mode = Number(params.get('mode')) || 1;
  const q = params.get('q');

  if (q) {
    switchMode(mode);
    dom.scanQueryInput.value = q;
    executeScan(mode, q);
    return true;
  }
  return false;
}

/**
 * Wire Global Event Handlers
 */
function goToScan() {
  dom.searchHub.scrollIntoView({ behavior: 'smooth', block: 'center' });
  const target = state.mode === 3 ? dom.categoryChips.querySelector('.cat-chip') : dom.scanQueryInput;
  setTimeout(() => target && target.focus({ preventScroll: true }), 350);
}

// Jump straight to a mode's input field (header links, #validate etc.)
function openModeInput(mode) {
  switchMode(mode);
  history.replaceState(null, '', `#${MODE_META[state.mode].slug}`);
  goToScan();
}

function setupEventHandlers() {
  // Header / mobile navigation: one link per mode, straight to its input field
  document.querySelectorAll('.nav-mode').forEach(a => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      openModeInput(Number(a.getAttribute('data-mode')));
    });
  });
  window.addEventListener('hashchange', () => {
    const slug = window.location.hash.replace(/^#/, '');
    if (SLUG_TO_MODE[slug]) openModeInput(SLUG_TO_MODE[slug]);
  });

  document.querySelectorAll('.js-start-scan').forEach(btn => btn.addEventListener('click', goToScan));

  // Mode bubbles, scoring cards and footer links that preselect a mode
  document.querySelectorAll('.mode-jump').forEach(btn => {
    btn.addEventListener('click', () => {
      switchMode(Number(btn.getAttribute('data-mode')) || 1);
      goToScan();
    });
  });

  // Demo: open the cached PIVOT example
  const runDemo = () => {
    switchMode(1);
    dom.scanQueryInput.value = 'UPI expense tracker for college students';
    executeScan(1, 'UPI expense tracker for college students');
  };
  if (dom.heroSeeResultBtn) dom.heroSeeResultBtn.addEventListener('click', runDemo);
  const scoringDemoBtn = document.getElementById('scoringDemoBtn');
  if (scoringDemoBtn) scoringDemoBtn.addEventListener('click', runDemo);

  // Mobile menu
  const menuBtn = document.getElementById('mobileMenuBtn');
  const menu = document.getElementById('mobileMenu');
  if (menuBtn && menu) {
    const setMenu = open => {
      menu.classList.toggle('hidden', !open);
      menuBtn.setAttribute('aria-expanded', String(open));
      menuBtn.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    };
    menuBtn.addEventListener('click', () => setMenu(menu.classList.contains('hidden')));
    menu.querySelectorAll('.mobile-link').forEach(a => a.addEventListener('click', () => setMenu(false)));
  }

  // Dismiss warnings
  const dismissWarningsBtn = document.getElementById('dismissWarningsBtn');
  if (dismissWarningsBtn) dismissWarningsBtn.addEventListener('click', () => dom.reportWarnings.classList.add('hidden'));

  // Arrow-key navigation within the mode tablist
  const tabs = [dom.modeBtn1, dom.modeBtn2, dom.modeBtn3, dom.modeBtn4];
  tabs.forEach((btn, i) => {
    btn.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      e.preventDefault();
      const j = (i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length;
      switchMode(j + 1);
      tabs[j].focus();
    });
  });

  // Mode segmented control buttons
  dom.modeBtn1.addEventListener('click', () => switchMode(1));
  dom.modeBtn2.addEventListener('click', () => switchMode(2));
  dom.modeBtn3.addEventListener('click', () => switchMode(3));
  dom.modeBtn4.addEventListener('click', () => switchMode(4));

  // Category chip selection in Mode 3
  dom.categoryChips.querySelectorAll('.cat-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      if (chip.id === 'catOtherBtn') {
        const opening = !dom.otherCategoryInputRow.classList.toggle('hidden');
        chip.setAttribute('aria-expanded', String(opening));
        if (opening) dom.otherCategoryInput.focus();
        return;
      }
      const cat = chip.getAttribute('data-category');
      executeScan(3, cat);
    });
  });

  // Other category confirmation
  dom.confirmOtherCatBtn.addEventListener('click', () => {
    const val = dom.otherCategoryInput.value.trim();
    if (val) executeScan(3, val);
  });
  dom.otherCategoryInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      dom.confirmOtherCatBtn.click();
    }
  });

  // Main Form Submit
  dom.scanForm.addEventListener('submit', (e) => {
    e.preventDefault();
    if (state.mode === 3) {
      showToast('Pick a category first');
      return;
    }
    const q = dom.scanQueryInput.value;
    executeScan(state.mode, q);
  });

  // Retry scan button on error
  dom.retryScanBtn.addEventListener('click', () => {
    executeScan(state.mode, state.query);
  });

  // Drawer Close handlers
  dom.closeDrawerBtn.addEventListener('click', closeDrawer);
  dom.drawerBackdrop.addEventListener('click', closeDrawer);
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && state.drawer.isOpen) {
      closeDrawer();
    }
    trapDrawerFocus(e);
  });

  // Copy share link button
  dom.copyShareLinkBtn.addEventListener('click', () => {
    if (!state.activeReport) return;
    const shareUrl = `${window.location.origin}${window.location.pathname.replace('index.html', '')}report.html?id=${encodeURIComponent(state.activeReport.scan_id || 'live')}`;
    navigator.clipboard.writeText(shareUrl).then(() => {
      showToast('Share link copied');
    }).catch(() => {
      showToast('Link copied: ' + shareUrl);
    });
  });

  // Print Report button
  dom.printReportBtn.addEventListener('click', () => {
    window.print();
  });
}

/**
 * Application Entry Point
 */
async function init() {
  setupEventHandlers();
  await loadExamplePills();

  const routed = initHashRoute();
  if (!routed) {
    switchMode(1);
  }
}

document.addEventListener('DOMContentLoaded', init);
