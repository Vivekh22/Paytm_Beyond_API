/**
 * GapScope rendering engine
 * Pure functions: report JSON -> HTML strings, in finprob.com's design language
 * (stone neutrals, orange-500 accent, Bricolage display type, JetBrains Mono meta).
 *
 * Rules enforced here:
 *  - Every piece of API text goes through esc() before insertion.
 *  - A quote is only rendered if its ID resolves in report.evidence. Unknown IDs are skipped.
 *  - ai_suggested items never render quotes.
 */

import { CONFIG } from './config.js';

const MONO = 'font-mono';
const DISPLAY = 'font-display';

/* ------------------------------------------------------------------ helpers */

export function esc(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** "2026-10-02" -> "2 Oct 2026"; "2026-10" -> "Oct 2026" */
export function formatDate(dateStr) {
  if (!dateStr) return '';
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const ym = /^(\d{4})-(\d{2})$/.exec(String(dateStr));
  if (ym) return `${months[Number(ym[2]) - 1] || ym[2]} ${ym[1]}`;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return esc(dateStr);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

/** Indian number formatting (1,00,000) */
export function formatNum(n) {
  if (n === null || n === undefined || n === '') return '0';
  const num = Number(n);
  return isNaN(num) ? esc(n) : num.toLocaleString('en-IN');
}

/** Only allow http(s) links from API data */
function safeUrl(url) {
  if (!url) return '';
  try {
    const u = new URL(url, window.location.href);
    return (u.protocol === 'http:' || u.protocol === 'https:') ? u.href : '';
  } catch (e) {
    return '';
  }
}

/** Resolve evidence IDs against the pool, skipping unknown IDs silently */
export function resolveEvidence(ids = [], pool = {}) {
  return (ids || []).map(id => pool[id]).filter(Boolean);
}

/**
 * Highlight the complaint clause inside a quote (finprob <mark>).
 * Text is escaped first; only the first matching phrase is marked.
 */
const TRIGGER_PHRASES = [
  'mis-tagging', 'mis-tagged', 'misclassified', 'misclassifies', 'wrong category',
  'stopped syncing', 'sync stopped', 'fails to sync', 'sync failures', 'not syncing',
  'permissions blocked', 'revoked', 'demanding SMS', 'SMS access', 'SMS permission',
  'duplicate entries', 'auto-cancelling', 'auto-cancelled', 'cancelled', 'ghost deliveries',
  'refund', 'stuck', 'trapped', 'unhelpful bot', 'no response',
  'hidden convenience fee', 'hidden fee', 'convenience fee', 'platform fee', 'surcharge',
  'loan spam', 'instant loan', 'personal loan', 'loan marketing', 'too many ads',
  'spreadsheet', 'manually', 'by hand', 'crashes', 'unreliable', 'useless', 'worst'
];
export function highlightQuoteSnippet(text) {
  if (!text) return '';
  const escaped = esc(text);
  for (const phrase of TRIGGER_PHRASES) {
    const re = new RegExp(`(${phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'i');
    if (re.test(escaped)) return escaped.replace(re, '<mark>$1</mark>');
  }
  return escaped;
}

function sourceMeta(key) {
  return CONFIG.SOURCE_METAS[key] || { name: key || 'Web', letter: 'W', pillClass: 'border-stone-400 text-stone-700', textClass: 'text-stone-700' };
}

/** Outlined mono pill: [P1 Play Store] */
export function renderSourceTag(sourceKey, index = null) {
  const m = sourceMeta(sourceKey);
  const code = index !== null ? `${m.letter}${index + 1}` : m.letter;
  return `<span class="inline-flex items-center gap-1.5 whitespace-nowrap rounded border px-1.5 py-0.5 ${MONO} text-[11px] font-semibold ${m.pillClass}"><span>${esc(code)}</span><span class="font-medium">${esc(m.name)}</span></span>`;
}

function chip(text, extra = 'border-stone-400') {
  return `<span class="whitespace-nowrap rounded-full border ${extra} px-2.5 py-1">${text}</span>`;
}

function numberDot(n, dark = false) {
  const cls = dark ? 'bg-white text-stone-950' : 'bg-stone-950 text-white';
  return `<span aria-hidden="true" class="flex h-[26px] w-[26px] flex-none items-center justify-center rounded-full ${cls} ${MONO} text-[13px] font-semibold">${n}</span>`;
}

function sectionHead(eyebrow, title, sub = '', right = '') {
  return `
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div class="flex max-w-[44em] flex-col gap-3">
        <p class="${MONO} text-[13px] font-medium uppercase tracking-[0.08em] text-stone-600">${eyebrow}</p>
        <h2 class="${DISPLAY} text-3xl font-extrabold leading-[1.05] tracking-[-0.03em] sm:text-4xl lg:text-5xl">${title}</h2>
        ${sub ? `<p class="text-lg text-stone-700">${sub}</p>` : ''}
      </div>
      ${right}
    </div>`;
}

const AI_TAG = `<span class="inline-block rounded-md border border-stone-300 bg-stone-100 px-2.5 py-1.5 ${MONO} text-xs text-stone-700" title="No live post supports this; treat as a hypothesis">AI-suggested: no matching post was found for this one</span>`;

function verdictTone(label) {
  const L = String(label || '').toUpperCase();
  if (L === 'BUILD' || L === 'GROWING') return { text: 'text-green-400', pill: 'bg-green-500 text-stone-950', hex: '#22C55E', arrow: L === 'GROWING' ? '↗' : '✓' };
  if (L === 'KILL' || L === 'DECLINING') return { text: 'text-red-400', pill: 'bg-red-500 text-white', hex: '#EF4444', arrow: L === 'DECLINING' ? '↘' : '✕' };
  return { text: 'text-orange-400', pill: 'bg-orange-500 text-stone-950', hex: '#F97316', arrow: L === 'STAGNATING' ? '→' : '↻' };
}

/* ------------------------------------------------------------------ verdict */

export function renderVerdictHero(report) {
  const { verdict, mode, query } = report;
  if (!verdict) return '';

  const label = String(verdict.label || '').toUpperCase();
  const score = Number(verdict.score ?? 0);
  const tone = verdictTone(label);
  const modeName = mode === 1 ? 'Validate an idea' : mode === 2 ? 'Investigate a business' : 'Discover an opportunity';

  let visual = '';
  if (mode === 1) {
    visual = `
      <p class="${MONO} text-[13px] font-semibold uppercase tracking-[0.08em] text-orange-300">Viability score</p>
      <div class="relative mx-auto h-[130px] w-full max-w-[260px]">
        <canvas id="gaugeCanvas" aria-label="Viability score ${score} out of 100" role="img"></canvas>
        <div class="pointer-events-none absolute inset-x-0 bottom-0 flex flex-col items-center">
          <span class="${DISPLAY} text-[64px] font-extrabold leading-[0.85] tracking-[-0.04em] tabular-nums">${score}</span>
          <span class="${MONO} text-xs text-stone-400">out of 100</span>
        </div>
      </div>
      <div class="flex flex-wrap items-center justify-center gap-2">
        <span class="rounded px-2.5 py-1 ${MONO} text-sm font-semibold ${tone.pill}">${tone.arrow} ${esc(label)}</span>
        <span class="${MONO} text-xs text-stone-400">≥65 build · 40–64 pivot · &lt;40 kill</span>
      </div>`;
  } else if (mode === 2) {
    visual = `
      <p class="${MONO} text-[13px] font-semibold uppercase tracking-[0.08em] text-orange-300">Trajectory</p>
      <div class="flex items-end gap-3">
        <span class="${DISPLAY} text-[6rem] font-extrabold leading-[0.8] ${tone.text}" aria-hidden="true">${tone.arrow}</span>
        <span class="${DISPLAY} pb-1 text-4xl font-extrabold tracking-[-0.03em] lg:text-5xl">${esc(label)}</span>
      </div>
      <span class="self-start rounded-full border border-stone-600 px-2.5 py-1 ${MONO} text-xs text-stone-200">signal score ${score}/100</span>`;
  } else {
    const nOpp = (report.opportunities || []).length;
    const nApps = (report.competitors || []).length;
    const fq = (report.clusters || []).reduce((a, c) => a + (Number(c.frequency?.count) || 0), 0);
    visual = `
      <p class="${MONO} text-[13px] font-semibold uppercase tracking-[0.08em] text-orange-300">Opportunities found</p>
      <div class="flex items-end gap-4">
        <span class="${DISPLAY} bg-orange-500 px-[0.1em] pb-[0.02em] pt-[0.08em] text-[6rem] font-extrabold leading-[0.8] tracking-[-0.06em] text-stone-950 lg:text-[8rem]">${nOpp}</span>
        <span class="${DISPLAY} pb-1.5 text-xl font-bold leading-[1.1] lg:text-[26px]">concepts across ${formatNum(nApps)} apps</span>
      </div>
      <span class="self-start rounded-full border border-stone-600 px-2.5 py-1 ${MONO} text-xs text-stone-200">${formatNum(fq)} complaints analysed</span>`;
  }

  const rows = (verdict.breakdown || []).map((f, i) => {
    const s = Number(f.score) || 0;
    const max = Number(f.max) || 10;
    const pct = Math.min(100, Math.max(0, Math.round((s / max) * 100)));
    const ids = f.evidence_ids || [];
    const n = resolveEvidence(ids, report.evidence || {}).length;
    return `
      <div class="flex flex-col gap-2 border-t border-stone-300 py-4">
        <div class="flex items-baseline justify-between gap-3">
          <strong class="text-[17px]">${esc(f.factor)}</strong>
          <span class="${MONO} text-sm font-semibold tabular-nums">${s}<span class="text-stone-500">/${max}</span></span>
        </div>
        <div class="h-1.5 w-full bg-stone-200" aria-hidden="true"><div class="h-1.5 bg-stone-950" style="width:${pct}%"></div></div>
        <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <span class="text-[15px] text-stone-700">${esc(f.explanation)}</span>
          ${n ? `<button type="button" class="btn-factor-evidence ${MONO} text-xs font-semibold underline underline-offset-4 hover:text-orange-700" data-evidence-ids="${esc(JSON.stringify(ids))}" data-title="${esc(f.factor)}">${n} receipt${n === 1 ? '' : 's'} ↗</button>` : ''}
        </div>
      </div>`;
  }).join('');

  return `
    <div class="flex flex-col gap-8">
      <div class="flex flex-col gap-4">
        <p class="${MONO} text-[13px] font-medium uppercase tracking-[0.08em] text-stone-600">${esc(modeName)} · “${esc(query)}”</p>
        <h2 class="${DISPLAY} max-w-[22em] text-3xl font-extrabold leading-[1.05] tracking-[-0.03em] sm:text-4xl lg:text-5xl">${esc(verdict.headline)}</h2>
      </div>
      <div class="grid overflow-hidden rounded-[18px] border-2 border-stone-950 lg:grid-cols-[5fr_7fr]">
        <div class="flex flex-col justify-center gap-5 bg-stone-950 p-6 text-white lg:p-9">${visual}</div>
        <div class="flex flex-col bg-white p-6 lg:p-9">
          <div class="flex items-baseline justify-between gap-3 pb-3">
            <span class="${MONO} text-[13px] font-semibold uppercase tracking-[0.08em]">How the score adds up</span>
            <span class="${MONO} text-xs text-stone-500">fixed formula</span>
          </div>
          ${rows || `<p class="border-t border-stone-300 py-4 text-[15px] text-stone-600">No breakdown returned for this scan.</p>`}
        </div>
      </div>
    </div>`;
}

/* -------------------------------------------------------------- competitors */

export function renderCompetitors(competitors = []) {
  if (!competitors || !competitors.length) {
    return `<p class="border-t border-stone-300 py-4 text-[15px] text-stone-600">No Play Store competitors found. The report relies on You.com web research.</p>`;
  }
  return competitors.map(c => {
    const name = c.name || 'Unknown';
    const icon = safeUrl(c.icon);
    const url = safeUrl(c.url);
    const iconHTML = icon
      ? `<img src="${esc(icon)}" alt="" loading="lazy" class="h-10 w-10 flex-none rounded-md border border-stone-200 object-cover" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'flex h-10 w-10 flex-none items-center justify-center rounded-md bg-stone-950 font-mono text-[17px] font-semibold text-white',textContent:${esc(JSON.stringify(name.charAt(0).toUpperCase()))}}))">`
      : `<span class="flex h-10 w-10 flex-none items-center justify-center rounded-md bg-stone-950 ${MONO} text-[17px] font-semibold text-white">${esc(name.charAt(0).toUpperCase())}</span>`;
    const meta = [
      c.rating ? `${Number(c.rating).toFixed(1)}★` : null,
      c.installs ? esc(c.installs) : null,
      c.reviews_scanned ? `${formatNum(c.reviews_scanned)} reviews scanned` : null
    ].filter(Boolean).join(' · ');
    return `
      <div class="flex items-center gap-4 border-t border-stone-300 py-3.5">
        ${iconHTML}
        <div class="flex min-w-0 flex-1 flex-col gap-1">
          <div class="flex flex-wrap items-center gap-2"><strong class="truncate text-[17px]">${esc(name)}</strong>${renderSourceTag(c.source || 'play_store')}</div>
          <span class="${MONO} text-xs text-stone-600 tabular-nums">${meta}</span>
        </div>
        ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer" class="flex h-10 w-10 flex-none items-center justify-center rounded-full hover:bg-stone-100" aria-label="Open ${esc(name)} listing">↗</a>` : ''}
      </div>`;
  }).join('');
}

/* ------------------------------------------------------------ receipt cards */

function quoteBlock(q, idx) {
  const m = sourceMeta(q.source);
  const url = safeUrl(q.url);
  const meta = [
    q.entity ? esc(q.entity) : null,
    q.rating ? `${esc(q.rating)}★` : null,
    q.likes ? `${formatNum(q.likes)} votes` : null,
    q.date ? formatDate(q.date) : null
  ].filter(Boolean).join(' · ');
  return `
    <div class="flex flex-col gap-1.5 rounded-[10px] border border-stone-200 px-3.5 py-3">
      <span class="flex flex-wrap items-center gap-x-2.5 gap-y-1 ${MONO} text-xs text-stone-600">
        <strong class="${m.textClass}">${esc(m.letter)}${idx + 1} ${esc(m.name)}</strong><span>${meta}</span>
      </span>
      <span class="text-sm leading-normal">“${highlightQuoteSnippet(q.text)}”</span>
      ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer" class="self-start ${MONO} text-xs font-semibold underline underline-offset-4 hover:text-orange-700">View original ↗</a>` : ''}
    </div>`;
}

export function renderClusterCard(cluster, evidencePool = {}, mode = 1, clusterIndex = 0) {
  const ai = cluster.ai_suggested === true;
  const sev = String(cluster.severity || 'medium').toLowerCase();
  const sevDot = sev === 'high' ? 'bg-red-600' : sev === 'low' ? 'bg-stone-400' : 'bg-amber-500';

  const freq = cluster.frequency || {};
  const ids = cluster.evidence_ids || [];
  const resolved = ai ? [] : resolveEvidence(ids, evidencePool);
  const count = Number(freq.count) || resolved.length;
  const total = Number(freq.total) || 0;
  const pct = total > 0 ? Math.min(100, Math.round((count / total) * 100)) : 0;
  const freqLabel = freq.label || (total ? `${count} of ${total} reviews` : `${count} posts`);

  const apps = cluster.apps_affected || [];
  const totalApps = cluster.apps_total || null;
  const appsLine = apps.length
    ? (mode === 3 ? `Seen in ${apps.length}${totalApps ? ` of ${totalApps}` : ''} apps` : `${apps.length} app${apps.length === 1 ? '' : 's'}`)
    : '';

  const quotes = resolved.slice(0, 3);
  const remaining = resolved.length - quotes.length;
  let step = 1;

  const quotesRow = ai
    ? `<div class="flex items-center gap-3.5 border-t border-dashed border-stone-300 pt-[18px]">${numberDot(++step)}${AI_TAG}</div>`
    : quotes.length
      ? `<div class="flex items-start gap-3.5">${numberDot(++step)}<div class="flex min-w-0 flex-1 flex-col gap-2.5">${quotes.map(quoteBlock).join('')}
          ${remaining > 0 ? `<button type="button" class="btn-open-cluster-drawer self-start ${MONO} text-xs font-semibold underline underline-offset-4 hover:text-orange-700" data-cluster-id="${esc(cluster.id)}" data-cluster-title="${esc(cluster.title)}" data-evidence-ids="${esc(JSON.stringify(ids))}">+ ${remaining} more receipt${remaining === 1 ? '' : 's'} →</button>` : ''}
        </div></div>`
      : `<div class="flex items-center gap-3.5">${numberDot(++step)}<span class="text-[15px] text-stone-600">No quotes could be matched to this cluster.</span></div>`;

  return `
    <article id="card_${esc(cluster.id)}" class="receipt-card card-print flex flex-col gap-5 rounded-[14px] border ${ai ? 'border-dashed border-stone-400' : 'border-stone-300'} bg-white p-5 shadow-[0_24px_48px_-36px_rgba(12,10,9,0.5)] lg:p-7" ${ai ? 'title="No live post supports this; treat as a hypothesis"' : ''}>
      <div class="flex items-start gap-3.5">
        ${numberDot(1)}
        <div class="flex min-w-0 flex-1 flex-col gap-2">
          <div class="flex flex-wrap items-center gap-2 ${MONO} text-xs text-stone-600">
            <span class="inline-flex items-center gap-1.5"><span class="h-2 w-2 rounded-full ${sevDot}" aria-hidden="true"></span>severity ${esc(sev)}</span>
            ${ai ? `<span class="rounded border border-dashed border-stone-500 px-1.5 py-0.5 font-semibold text-stone-800">AI-suggested</span>` : ''}
          </div>
          <h3 class="${DISPLAY} text-[19px] font-bold leading-tight tracking-[-0.01em] lg:text-[23px]">${esc(cluster.title)}</h3>
          <p class="text-[15px] leading-relaxed text-stone-700">${esc(cluster.summary)}</p>
        </div>
      </div>
      ${quotesRow}
      <div class="flex items-start gap-3.5">
        ${numberDot(++step)}
        <div class="flex min-w-0 flex-1 flex-col gap-2.5">
          <div class="flex flex-wrap gap-2 ${MONO} text-xs">
            ${chip(esc(freqLabel), 'border-stone-950 font-semibold')}
            ${appsLine ? chip(esc(appsLine)) : ''}
            ${!ai && resolved.length ? chip(`${resolved.length} receipt${resolved.length === 1 ? '' : 's'}`) : ''}
          </div>
          ${total ? `<div class="h-1 w-full max-w-[240px] bg-stone-200" aria-hidden="true"><div class="h-1 bg-orange-500" style="width:${pct}%"></div></div>` : ''}
          ${apps.length ? `<div class="flex flex-wrap gap-1.5">${apps.map(a => `<span class="rounded border border-stone-300 bg-stone-100 px-1.5 py-0.5 ${MONO} text-[11px] text-stone-700">${esc(a)}</span>`).join('')}</div>` : ''}
        </div>
      </div>
    </article>`;
}

export function renderReceiptsSection(report) {
  const clusters = report.clusters || [];
  const pool = report.evidence || {};
  const mode = report.mode || 1;

  if (!clusters.length) {
    return `
      <div class="flex flex-col gap-2 rounded-[14px] border border-dashed border-stone-400 p-8">
        <h3 class="${DISPLAY} text-2xl font-bold">Not enough live evidence</h3>
        <p class="text-[15px] text-stone-700">Not enough live evidence; try a broader term.</p>
      </div>`;
  }

  if (mode === 2) {
    const pain = clusters.filter(c => c.group !== 'strength');
    const strength = clusters.filter(c => c.group === 'strength');
    const col = (title, dot, list) => `
      <div class="flex flex-col gap-5">
        <div class="flex items-center justify-between gap-3 border-b-2 border-stone-950 pb-3">
          <span class="inline-flex items-center gap-2 ${MONO} text-[13px] font-semibold uppercase tracking-[0.08em]"><span class="h-2.5 w-2.5 rounded-full ${dot}" aria-hidden="true"></span>${title}</span>
          <span class="${MONO} text-xs text-stone-600">${list.length} cluster${list.length === 1 ? '' : 's'}</span>
        </div>
        ${list.length ? list.map((c, i) => renderClusterCard(c, pool, mode, i)).join('') : `<p class="text-[15px] text-stone-600">Nothing found in this group.</p>`}
      </div>`;
    return `
      <div class="flex flex-col gap-10">
        ${sectionHead('What users say', 'Why people leave, and why they <span class="box-decoration-clone bg-orange-500 px-[0.12em] text-stone-950">stay.</span>', '1★ complaints next to 5★ praise, from Play Store reviews, Reddit and the web.')}
        <div class="grid items-start gap-8 lg:grid-cols-2">
          ${col('Why users leave', 'bg-red-600', pain)}
          ${col('Why users stay', 'bg-green-600', strength)}
        </div>
      </div>`;
  }

  const title = mode === 3
    ? 'Complaints that repeat <span class="box-decoration-clone bg-orange-500 px-[0.12em] text-stone-950">across apps.</span>'
    : 'Every pain comes with its <span class="box-decoration-clone bg-orange-500 px-[0.12em] text-stone-950">receipts.</span>';
  const sub = mode === 3
    ? 'A frustration seen in several competitors is a gap none of them has fixed.'
    : 'Clustered from 1★ Play Store reviews, Reddit threads and You.com forum results.';

  return `
    <div class="flex flex-col gap-10">
      ${sectionHead(`Pain clusters · ${clusters.length}`, title, sub)}
      <div class="grid items-start gap-5 lg:grid-cols-2">
        ${clusters.map((c, i) => renderClusterCard(c, pool, mode, i)).join('')}
      </div>
    </div>`;
}

/* ------------------------------------------------------------ opportunities */

export function renderOpportunities(opportunities = [], evidencePool = {}, clusters = []) {
  if (!opportunities || !opportunities.length) return '';
  const titleOf = id => (clusters.find(c => c.id === id) || {}).title || id;

  const cards = opportunities.map((o, i) => {
    const q = resolveEvidence(o.evidence_ids || [], evidencePool)[0];
    const solves = o.addresses_cluster_ids || [];
    return `
      <div class="card-print flex flex-col gap-4 rounded-xl border ${o.ai_suggested ? 'border-dashed border-stone-600' : 'border-stone-800'} bg-stone-900 p-[22px]">
        <div class="flex items-baseline justify-between gap-3 ${MONO} text-[13px]">
          <span class="text-stone-400">${String(i + 1).padStart(2, '0')}</span>
          <span class="text-orange-300">${o.ai_suggested ? 'AI-suggested' : `solves ${solves.length} problem${solves.length === 1 ? '' : 's'}`}</span>
        </div>
        <strong class="${DISPLAY} text-2xl leading-tight tracking-[-0.01em]">${esc(o.title)}</strong>
        <span class="text-[15px] leading-relaxed text-stone-300">${esc(o.pitch)}</span>
        ${o.target_user ? `<span class="text-sm text-stone-300"><strong class="text-white">For.</strong> ${esc(o.target_user)}</span>` : ''}
        ${q && !o.ai_suggested ? `
          <div class="flex flex-col gap-1.5 rounded-[10px] border border-stone-700 px-3.5 py-3">
            <span class="${MONO} text-xs text-stone-400">${esc(sourceMeta(q.source).name)}${q.entity ? ` · ${esc(q.entity)}` : ''}${q.rating ? ` · ${esc(q.rating)}★` : ''}</span>
            <span class="text-sm leading-normal text-stone-200">“${esc(String(q.text || '').slice(0, 160))}${String(q.text || '').length > 160 ? '…' : ''}”</span>
          </div>` : ''}
        ${solves.length ? `
          <div class="mt-auto flex flex-col gap-2 border-t border-stone-800 pt-4">
            <span class="${MONO} text-xs uppercase tracking-[0.06em] text-stone-400">Solves →</span>
            <div class="flex flex-wrap gap-2">
              ${solves.map(cid => `<button type="button" class="btn-jump-to-cluster rounded-full border border-stone-600 px-2.5 py-1 text-left ${MONO} text-xs text-stone-200 hover:border-orange-300 hover:text-orange-300" data-target-cluster="card_${esc(cid)}">${esc(titleOf(cid))}</button>`).join('')}
            </div>
          </div>` : ''}
      </div>`;
  }).join('');

  return `
    <div class="rounded-[18px] bg-stone-950 text-white">
      <div class="flex flex-col gap-10 p-6 sm:p-8 lg:p-12">
        <div class="flex max-w-[44em] flex-col gap-3">
          <p class="${MONO} text-[13px] font-medium uppercase tracking-[0.08em] text-orange-300">What to build · ${opportunities.length}</p>
          <h2 class="${DISPLAY} text-3xl font-extrabold leading-[1.05] tracking-[-0.03em] sm:text-4xl lg:text-5xl">From a complaint to a concept.</h2>
          <p class="text-lg text-stone-300">Each concept points to the clusters it solves. Click one to jump to its receipts.</p>
        </div>
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">${cards}</div>
      </div>
    </div>`;
}

/* --------------------------------------------------------------------- news */

export function renderNewsSection(newsItems = [], evidencePool = {}) {
  const items = (newsItems || [])
    .map(n => ({ n, ev: evidencePool[n.evidence_id] }))
    .filter(x => x.ev); // never show unresolved items
  if (!items.length) return '';

  const rows = items.map(({ n, ev }, idx) => {
    const s = n.sentiment || 'neutral';
    const dot = s === 'positive' ? 'bg-green-600' : s === 'negative' ? 'bg-red-600' : 'bg-stone-400';
    const url = safeUrl(ev.url);
    const headline = esc(ev.title || ev.text || 'Untitled');
    return `
      <li class="flex gap-[18px] border-t border-stone-200 py-5">
        <span class="mt-2 h-2 w-2 flex-none rounded-full ${dot}" title="Sentiment: ${esc(s)}"></span>
        <div class="flex min-w-0 flex-1 flex-col gap-1.5">
          ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer" class="text-[17px] font-semibold leading-snug hover:text-orange-700 hover:underline underline-offset-4">${headline} <span aria-hidden="true">↗</span></a>` : `<strong class="text-[17px] leading-snug">${headline}</strong>`}
          <span class="flex flex-wrap items-center gap-2 ${MONO} text-xs text-stone-600">${renderSourceTag(ev.source, idx)}<span>${esc(ev.entity || '')}${ev.date ? ` · ${formatDate(ev.date)}` : ''}</span><span>· ${esc(s)}</span></span>
        </div>
      </li>`;
  }).join('');

  return `
    <div class="flex flex-col gap-8">
      ${sectionHead('Google News · You.com', 'What the press and the web are saying.')}
      <ol class="flex flex-col border-b border-stone-200">${rows}</ol>
    </div>`;
}

/* ------------------------------------------------------------------- drawer */

export function renderDrawerContent(evidenceList = []) {
  if (!evidenceList || !evidenceList.length) {
    return `<p class="py-8 text-center text-[15px] text-stone-600">No receipts match this filter.</p>`;
  }
  return evidenceList.map((ev, idx) => {
    const m = sourceMeta(ev.source);
    const url = safeUrl(ev.url);
    const meta = [
      ev.entity ? esc(ev.entity) : null,
      ev.author ? esc(ev.author) : null,
      ev.rating ? `${esc(ev.rating)}★` : null,
      (ev.likes !== undefined && ev.likes !== null) ? `${formatNum(ev.likes)} votes` : null,
      ev.date ? formatDate(ev.date) : null
    ].filter(Boolean).join(' · ');
    return `
      <div class="flex flex-col gap-2 rounded-[10px] border border-stone-200 px-4 py-3.5">
        <span class="flex flex-wrap items-center gap-x-2.5 gap-y-1 ${MONO} text-xs text-stone-600">
          <strong class="${m.textClass}">${esc(m.letter)}${idx + 1} ${esc(m.name)}</strong><span>${meta}</span>
        </span>
        ${ev.title ? `<strong class="text-[15px] leading-snug">${esc(ev.title)}</strong>` : ''}
        <p class="text-[15px] leading-relaxed">“${highlightQuoteSnippet(ev.text)}”</p>
        ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer" class="self-start ${MONO} text-xs font-semibold underline underline-offset-4 hover:text-orange-700">View original ↗</a>` : ''}
      </div>`;
  }).join('');
}
