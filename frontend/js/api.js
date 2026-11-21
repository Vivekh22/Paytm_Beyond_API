/**
 * GapScope API & Streaming Client
 * Supports both live SSE streaming and realistic mock simulations.
 */

import { CONFIG } from './config.js';

/**
 * Fetch mock report data for a specific mode
 * @param {number|string} mode 1, 2, or 3
 */
export async function getMock(mode) {
  const modeNum = Number(mode) || 1;
  const mockPath = `mock/report_mode${modeNum}.json`;
  try {
    const res = await fetch(mockPath);
    if (!res.ok) {
      throw new Error(`Failed to load ${mockPath} (HTTP ${res.status})`);
    }
    const report = await res.json();
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
  if (CONFIG.USE_MOCK) {
    // Generate a simulated scan id
    const scanId = `mock_${mode}_${Math.random().toString(36).substring(2, 8)}`;
    return { scan_id: scanId, mode, query };
  }

  const res = await fetch(`${CONFIG.API_BASE}/api/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: Number(mode), query: query.trim() })
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.error || errData.message || `Scan start failed (HTTP ${res.status})`);
  }

  return await res.json();
}

/**
 * Stream scan progress via EventSource (or simulated stream in mock mode)
 * @param {string} scanId 
 * @param {function} onEvent Callback receiving parsed SSE payload
 * @param {object} meta { mode, query }
 * @returns {object} Controller with abort()
 */
export function streamScan(scanId, onEvent, meta = {}) {
  const mode = meta.mode || 1;

  if (CONFIG.USE_MOCK) {
    let cancelled = false;
    const timeouts = [];

    const mockSteps = [
      { step: 'keywords', message: 'Extracting market search keywords via Gemini 2.5 Flash', pct: 15, source: 'Gemini' },
      { step: 'trends', message: 'Querying Google Trends (geo=IN, 12 months) via SerpApi', pct: 32, source: 'SerpApi' },
      { step: 'play_store', message: 'Scanning Google Play Store top apps & 1★/5★ reviews', pct: 54, source: 'SerpApi' },
      { step: 'reddit_news', message: 'Searching Reddit discussions & Google News headlines', pct: 72, source: 'SerpApi' },
      { step: 'youcom_web', message: 'Gathering competitor funding & market context via You.com Search API', pct: 88, source: 'You.com' },
      { step: 'clustering', message: 'Verifying evidence IDs & computing deterministic scoring formula', pct: 98, source: 'Python' }
    ];

    // Schedule progressive feedback
    mockSteps.forEach((s, idx) => {
      const delay = (idx + 1) * 380;
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
    const finalDelay = (mockSteps.length + 1) * 380;
    const finalT = setTimeout(async () => {
      if (cancelled) return;
      try {
        const report = await getMock(mode);
        // Overwrite query in report if user provided one
        if (meta.query) {
          report.query = meta.query;
        }
        report.scan_id = scanId;
        report.generated_at = new Date().toISOString();
        onEvent({ type: 'done', report });
      } catch (err) {
        onEvent({ type: 'error', message: err.message || 'Failed to assemble mock report' });
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
  const eventSource = new EventSource(url);

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

  eventSource.onerror = (e) => {
    console.error('[GapScope] EventSource encountered error:', e);
    eventSource.close();
    onEvent({ type: 'error', message: 'Connection to scan stream was lost or closed.' });
  };

  return {
    abort: () => {
      eventSource.close();
    }
  };
}

/**
 * Fetch an existing report by scan ID
 * @param {string} scanId 
 */
export async function getReport(scanId) {
  if (CONFIG.USE_MOCK || scanId.startsWith('mock_')) {
    // Determine mode from scanId e.g. mock_2_xxx -> mode 2
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
