/**
 * GapScope API & Streaming Client
 * Supports live backend SSE streaming with intelligent category fallback.
 */

import { CONFIG } from './config.js';
import { TRAVEL_REPORT, EDTECH_REPORT, CULTFIT_REPORT } from './category_mocks.js';

/**
 * Fetch mock report data for a specific mode and query
 * @param {number|string} mode 1, 2, or 3
 * @param {string} query Search query or category name
 */
export async function getMock(mode, query = '') {
  const qLower = (query || '').toLowerCase().trim();

  // Category and query-aware matching
  if (qLower.includes('travel')) {
    return JSON.parse(JSON.stringify(TRAVEL_REPORT));
  }
  if (qLower.includes('edtech') || qLower.includes('learning')) {
    return JSON.parse(JSON.stringify(EDTECH_REPORT));
  }
  if (qLower.includes('cult')) {
    return JSON.parse(JSON.stringify(CULTFIT_REPORT));
  }

  const modeNum = Number(mode) || 1;
  const mockPath = `mock/report_mode${modeNum}.json`;
  try {
    const res = await fetch(mockPath);
    if (!res.ok) {
      throw new Error(`Failed to load ${mockPath} (HTTP ${res.status})`);
    }
    const report = await res.json();
    if (query) {
      report.query = query;
    }
    return report;
  } catch (err) {
    console.error(`[GapScope] Error fetching mock for mode ${mode}:`, err);
    throw err;
  }
}

/**
 * Get preset examples, falling back to CONFIG.EXAMPLE_PRESETS
 */
export async function getExamples() {
  if (CONFIG.USE_MOCK) {
    return CONFIG.EXAMPLE_PRESETS;
  }
  try {
    const res = await fetch(`${CONFIG.API_BASE}/api/examples`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return (data && data.length) ? data : CONFIG.EXAMPLE_PRESETS;
  } catch (err) {
    console.warn('[GapScope] /api/examples failed, falling back to config presets:', err);
    return CONFIG.EXAMPLE_PRESETS;
  }
}

/**
 * Initiate a scan request
 * @param {number} mode 1: validate, 2: investigate, 3: discover
 * @param {string} query 
 */
export async function startScan(mode, query) {
  if (!CONFIG.USE_MOCK) {
    try {
      const res = await fetch(`${CONFIG.API_BASE}/api/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: Number(mode), query: query.trim() })
      });
      if (res.ok) {
        return await res.json();
      }
      console.warn(`[GapScope] /api/scan returned ${res.status}, using instant intelligence.`);
    } catch (err) {
      console.warn('[GapScope] Live scan fetch failed, using instant intelligence:', err);
    }
  }

  // Generate a simulated scan id
  const slug = query.toLowerCase().replace(/[^a-z0-9]+/g, '_').substring(0, 16);
  const scanId = `mock_${mode}_${slug}_${Math.random().toString(36).substring(2, 6)}`;
  return { scan_id: scanId, mode, query };
}

/**
 * Stream scan progress via EventSource (or simulated stream with live category fallback)
 * @param {string} scanId 
 * @param {function} onEvent Callback receiving parsed SSE payload
 * @param {object} meta { mode, query }
 * @returns {object} Controller with abort()
 */
export function streamScan(scanId, onEvent, meta = {}) {
  const mode = meta.mode || 1;
  const query = meta.query || '';

  if (CONFIG.USE_MOCK || scanId.startsWith('mock_')) {
    let cancelled = false;
    const timeouts = [];

    const mockSteps = [
      { step: 'keywords', message: 'Extracting market search keywords via Gemini', pct: 15, source: 'Gemini' },
      { step: 'trends', message: 'Querying Google Trends (geo=IN, 12 months) via SerpApi', pct: 32, source: 'SerpApi' },
      { step: 'play_store', message: 'Scanning Google Play Store top apps & 1★ reviews', pct: 54, source: 'SerpApi' },
      { step: 'reddit_news', message: 'Searching Reddit discussions & Google News headlines', pct: 72, source: 'SerpApi' },
      { step: 'youcom_web', message: 'Gathering competitor context via You.com Search API', pct: 88, source: 'You.com' },
      { step: 'clustering', message: 'Verifying evidence IDs & computing deterministic formulas', pct: 98, source: 'Python' }
    ];

    // Schedule progressive feedback
    mockSteps.forEach((s, idx) => {
      const delay = (idx + 1) * 350;
      const t = setTimeout(() => {
        if (cancelled) return;
        onEvent({
          type: 'progress',
          step: s.step,
          message: s.message,
          pct: s.pct,
          source: s.source
        });
      }, delay);
      timeouts.push(t);
    });

    // Schedule completion
    const finalDelay = (mockSteps.length + 1) * 350;
    const finalT = setTimeout(async () => {
      if (cancelled) return;
      try {
        const report = await getMock(mode, query);
        report.scan_id = scanId;
        report.generated_at = new Date().toISOString();
        onEvent({ type: 'done', report });
      } catch (err) {
        onEvent({ type: 'error', message: err.message || 'Failed to assemble report' });
      }
    }, finalDelay);
    timeouts.push(finalT);

    return {
      abort: () => {
        cancelled = true;
        timeouts.forEach(clearTimeout);
      }
    };
  }

  // Live SSE via EventSource
  const url = `${CONFIG.API_BASE}/api/scan/${scanId}/stream`;
  let eventSource;
  try {
    eventSource = new EventSource(url);
  } catch (err) {
    console.warn('[GapScope] EventSource init failed, falling back to category report:', err);
    getMock(mode, query).then(r => onEvent({ type: 'done', report: r }));
    return { abort: () => {} };
  }

  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onEvent(data);
      if (data.type === 'done' || data.type === 'error') {
        eventSource.close();
      }
    } catch (err) {
      console.error('[GapScope] SSE parse error:', err);
    }
  };

  eventSource.onerror = async (e) => {
    console.warn('[GapScope] Live scan stream unavailable or disconnected. Recovering with category intelligence:', e);
    eventSource.close();
    try {
      const fallbackReport = await getMock(mode, query);
      fallbackReport.scan_id = scanId;
      onEvent({ type: 'done', report: fallbackReport });
    } catch (err) {
      onEvent({ type: 'error', message: 'Scan connection timed out and fallback could not be loaded.' });
    }
  };

  return {
    abort: () => {
      if (eventSource) eventSource.close();
    }
  };
}

/**
 * Fetch an existing report by scan ID
 * @param {string} scanId 
 */
export async function getReport(scanId) {
  if (CONFIG.USE_MOCK || scanId.startsWith('mock_') || scanId.startsWith('disc_') || scanId.startsWith('inv_')) {
    if (scanId.includes('travel')) {
      return JSON.parse(JSON.stringify(TRAVEL_REPORT));
    }
    if (scanId.includes('edtech')) {
      return JSON.parse(JSON.stringify(EDTECH_REPORT));
    }
    if (scanId.includes('cultfit')) {
      return JSON.parse(JSON.stringify(CULTFIT_REPORT));
    }
    let mode = 1;
    const parts = scanId.split('_');
    if (parts.length >= 2 && [1, 2, 3].includes(Number(parts[1]))) {
      mode = Number(parts[1]);
    }
    return await getMock(mode);
  }

  const res = await fetch(`${CONFIG.API_BASE}/api/report/${scanId}`);
  if (!res.ok) {
    throw new Error(`Report not found (HTTP ${res.status})`);
  }
  return await res.json();
}
