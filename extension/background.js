// ─── RE Radar – Background Service Worker ────────────────────────────────────
// Orchestrates portal searches, tab management, and listing extraction.
// Uses chrome.scripting.executeScript to inject self-contained functions into
// portal pages — no Browserless, no bot detection, uses the user's real session.

'use strict';

// ── City → state mapping ──────────────────────────────────────────────────────
const CITY_STATE = {
  'berlin': 'BE', 'münchen': 'BY', 'munich': 'BY', 'hamburg': 'HH',
  'frankfurt': 'HE', 'frankfurt am main': 'HE', 'köln': 'NW', 'cologne': 'NW',
  'düsseldorf': 'NW', 'dusseldorf': 'NW', 'stuttgart': 'BW', 'leipzig': 'SN',
  'dresden': 'SN', 'hannover': 'NI', 'bremen': 'HB', 'nürnberg': 'BY',
  'nuremberg': 'BY', 'augsburg': 'BY', 'mainz': 'RP', 'freiburg': 'BW',
  'bonn': 'NW', 'mannheim': 'BW', 'dortmund': 'NW', 'essen': 'NW',
  'wiesbaden': 'HE', 'karlsruhe': 'BW', 'münster': 'NW', 'erfurt': 'TH',
  'rostock': 'MV', 'magdeburg': 'ST', 'halle': 'ST', 'chemnitz': 'SN',
};

const GRUNDERWERBSTEUER = {
  'BE': 6.0, 'BY': 3.5, 'BW': 5.0, 'BB': 6.5, 'HB': 5.0, 'HH': 4.5,
  'HE': 6.0, 'MV': 6.0, 'NI': 5.0, 'NW': 6.5, 'RP': 5.0, 'SH': 6.5,
  'SL': 6.5, 'SN': 3.5, 'ST': 5.0, 'TH': 6.5,
};

const MPB_CITIES = new Set([
  'berlin', 'münchen', 'munich', 'hamburg', 'frankfurt', 'frankfurt am main',
  'stuttgart', 'köln', 'cologne', 'düsseldorf', 'düsseldorf', 'leipzig',
  'dresden', 'hannover', 'nürnberg', 'nuremberg', 'augsburg', 'mannheim',
  'karlsruhe', 'freiburg', 'bonn', 'dortmund', 'essen', 'mainz', 'wiesbaden',
]);

// ── Portal configs ─────────────────────────────────────────────────────────────
function slugify(city) {
  return city.toLowerCase()
    .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue')
    .replace(/ß/g, 'ss').replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
}

const PORTALS = [
  {
    name: 'ohne-makler',
    url: (city) => `https://www.ohne-makler.net/immobilien/wohnung-kaufen/${slugify(city)}/`,
    patterns: ['/immobilie/'],
  },
  {
    name: 'immowelt',
    url: (city) => `https://www.immowelt.de/suche/${slugify(city)}/wohnungen/kaufen`,
    patterns: ['/expose/'],
  },
  {
    name: 'immonet',
    url: (city) => `https://www.immonet.de/wohnung-kaufen/${slugify(city)}.html`,
    patterns: ['/angebot/'],
  },
];

// ── Pre-configured API key (config.js, never committed to git) ───────────────
try { importScripts('config.js'); } catch (_) { /* file not present — that's fine */ }

// ── Side panel: open on toolbar icon click ────────────────────────────────────
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => {});
});

// ── Port (persistent connection to popup) ─────────────────────────────────────
let port = null;

chrome.runtime.onConnect.addListener((p) => {
  if (p.name !== 'radar') return;
  port = p;
  p.onMessage.addListener(onMessage);
  p.onDisconnect.addListener(() => { port = null; });
});

function send(type, payload = {}) {
  if (!port) return;
  try { port.postMessage({ type, ...payload }); } catch (_) {}
}

async function onMessage(msg) {
  if (msg.action === 'startSearch') await runSearch(msg.params);
  if (msg.action === 'getStored')   await sendStored();
  if (msg.action === 'clearStored') await chrome.storage.local.remove('re_radar_listings');
}

async function sendStored() {
  const { re_radar_listings: lst = [] } = await chrome.storage.local.get('re_radar_listings');
  send('storedListings', { listings: lst });
}

// ── Keep service worker alive while popup is open ────────────────────────────
// (Holding a port connection prevents the SW from being killed mid-search)

// ── Tab utilities ─────────────────────────────────────────────────────────────
function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function openTab(url) {
  return new Promise((resolve) => chrome.tabs.create({ url, active: false }, resolve));
}

function waitForLoad(tabId, timeout = 18000) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    }, timeout);
    function listener(id, info) {
      if (id === tabId && info.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(listener);
        clearTimeout(timer);
        setTimeout(resolve, 5000); // extra time for JS rendering (SPAs need more)
      }
    }
    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function closeTab(tabId) {
  try { await chrome.tabs.remove(tabId); } catch (_) {}
}

async function execScript(tabId, func, args = []) {
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func,
      args,
    });
    return results?.[0]?.result ?? null;
  } catch (e) {
    console.warn('[RE Radar] executeScript failed:', e.message);
    return null;
  }
}

// ── Injected functions (must be self-contained — no outer scope refs) ─────────

function __getUrls(patterns) {
  const found = new Set();
  // Standard anchor tags
  for (const a of document.querySelectorAll('a[href]')) {
    const h = a.href;
    if (patterns.some((p) => h.includes(p))) found.add(h);
  }
  // SPA-style data attributes (some portals render links without <a> tags)
  if (found.size === 0) {
    for (const el of document.querySelectorAll('[data-href],[data-url],[data-link]')) {
      for (const attr of ['data-href', 'data-url', 'data-link']) {
        const h = el.getAttribute(attr);
        if (h && patterns.some((p) => h.includes(p))) {
          try { found.add(new URL(h, location.href).href); } catch (_) {}
        }
      }
    }
  }
  return [...found];
}

function __extractData() {
  // Parse German number format: "340.000" → 340000, "1.234,56" → 1234.56
  function num(s) {
    if (!s) return null;
    const c = String(s).replace(/[^\d,.]/g, '').trim();
    if (!c) return null;
    let n = c;
    if (n.includes('.') && n.includes(',')) {
      // Both present: whichever comes first is the thousands separator
      n = n.indexOf('.') < n.indexOf(',')
        ? n.replace(/\./g, '').replace(',', '.')   // 1.234,56 → 1234.56
        : n.replace(/,/g, '');                      // 1,234.56 → 1234.56
    } else if (n.includes(',') && !n.includes('.')) {
      // Comma only: thousands if followed by exactly 3 digits, else decimal
      n = /,\d{3}$/.test(n) ? n.replace(/,/g, '') : n.replace(',', '.');
    } else if (n.includes('.') && !n.includes(',')) {
      // Dot only: German thousands separator if exactly 3 digits follow (e.g. 340.000)
      n = /\.\d{3}$/.test(n) ? n.replace(/\./g, '') : n;
    }
    const f = parseFloat(n);
    return isNaN(f) ? null : f;
  }

  // Find a number following a label; allow up to 80 chars (incl. newlines) between them.
  // minVal / maxVal guard against grabbing the wrong field (e.g. rent instead of price).
  function findNum(labels, minVal = 0, maxVal = Infinity) {
    const txt = document.body.innerText || '';
    for (const lbl of labels) {
      const re = new RegExp(lbl + '[\\s\\S]{0,80}?([\\d]{1,3}(?:[.,][\\d]{3})*(?:[.,]\\d{1,2})?)', 'im');
      const m = txt.match(re);
      if (m) {
        const v = num(m[1]);
        if (v != null && v >= minVal && v <= maxVal) return v;
      }
    }
    return null;
  }

  function findText(labels) {
    const txt = document.body.innerText || '';
    for (const lbl of labels) {
      const re = new RegExp(lbl + '[\\s\\S]{0,40}?([A-H][+]?|[12]\\d{3})', 'im');
      const m = txt.match(re);
      if (m && m[1]) return m[1].trim();
    }
    return null;
  }

  const txt = document.body.innerText || '';
  const url = location.href;

  // Price must be a purchase price (> €20k); area in m²; rooms < 30
  const price    = findNum(['Kaufpreis', 'Verkaufspreis', 'Angebotspreis'], 20000, 10000000);
  // Area: try labelled first (min 15 — rules out balconies/terraces), then scan all "XX m²" in page
  const area = findNum(['Wohnfläche', 'Nutzfläche', 'Wohnfl'], 15, 2000)
    || (() => {
      const hits = [...txt.matchAll(/(\d{1,3}(?:[.,]\d+)?)\s*m[²2]/g)]
        .map((m) => num(m[1])).filter((v) => v != null && v >= 15 && v <= 2000);
      return hits.length ? Math.max(...hits) : null;
    })();
  if (!price && !area) return null;

  const coldRent  = findNum(['Kaltmiete', 'Nettokaltmiete', 'Miete netto'], 50, 20000);
  const warmRent  = findNum(['Warmmiete', 'Gesamtmiete'], 50, 30000);
  const hausgeld  = findNum(['Hausgeld', 'Wohngeld'], 10, 5000);
  const ruecklage = findNum(['Rücklage', 'Instandhaltungsrücklage', 'Rücklagenanteil'], 1, 200000);
  const rooms     = findNum(['Zimmer', 'Zimmeranzahl'], 0.5, 30);
  const yearBuilt = findText(['Baujahr']);
  const energy    = findText(['Energieeffizienzklasse', 'Energieklasse', 'Klasse']);

  const tenanted = /vermietet/i.test(txt) ? 'yes'
    : /bezugsfrei|leerstehend|nicht vermietet|frei ab/i.test(txt) ? 'no'
    : 'unknown';

  const maklergebuehr = /provisionsfrei|ohne Makler|ohne Provision/i.test(txt) ? 0
    : (() => { const m = txt.match(/Provision[:\s]*([0-9,.]+)\s*%/i); return m ? parseFloat(m[1].replace(',','.')) : null; })();

  // Name: first non-empty line of h1 (avoids grabbing nested price/area nodes)
  const h1Raw = document.querySelector('h1')?.innerText?.trim() || '';
  const name = (
    h1Raw.split(/\n/).map((l) => l.trim()).find((l) => l.length > 3)
    || document.title?.replace(/\s*[|–\-].*$/, '').trim()
    || 'Inserat'
  ).slice(0, 120);

  // Address: try DOM selectors, then German postal code pattern (e.g. "53842 Troisdorf")
  const addrEl = document.querySelector(
    '[class*="address" i], [class*="location" i], [class*="ort" i], [data-testid*="address"], [data-testid*="location"]'
  );
  const postalMatch = txt.match(/(\d{5})\s+([A-ZÄÖÜ][^\n,]{2,30})/);
  const address = (
    addrEl?.innerText?.trim()
    || (postalMatch ? postalMatch[0] : '')
    || ''
  ).replace(/\s+/g, ' ').slice(0, 100);

  // City: from URL first, then from postal code match
  const cityMatch = url.match(
    /\/(berlin|hamburg|m[uü][e]?nchen|frankfurt|k[oö]ln|d[uü]sseldorf|stuttgart|leipzig|dresden|hannover|bremen|n[uü]rnberg|augsburg|mainz|freiburg|bonn|mannheim|dortmund|essen|troisdorf|bonn|n[uü]rnberg)\//i
  );
  const city = cityMatch
    ? cityMatch[1].charAt(0).toUpperCase() + cityMatch[1].slice(1)
    : (postalMatch ? postalMatch[2].split(/[\s\/,]/)[0] : '');

  return {
    name, address, city, price, area, rooms, yearBuilt,
    coldRent, warmRent, hausgeld, ruecklage,
    energy, tenanted, maklergebuehr,
    sourceUrl: url,
    source: location.hostname.replace('www.', ''),
    createdAt: new Date().toISOString(),
    // Raw text for optional Claude enrichment (first 4000 chars)
    _rawText: (document.body.innerText || '').slice(0, 4000),
  };
}

// ── Scoring & metrics — aligned to index.html baseline ───────────────────────

// Matches baseline ENERGY_SCORE exactly
const ENERGY_SCORE = { 'A+': 20, 'A': 18, 'B': 15, 'C': 12, 'D': 9, 'E': 6, 'F': 3, 'G': 1, 'H': 0 };

function calcMetrics(d, state) {
  const price  = d.price     || 0;
  const area   = d.area      || 0;
  const cold   = d.coldRent  || 0;
  const hg     = d.hausgeld  || 0;
  const umlag  = d.umlagefaehig ?? 65;          // per-listing, default 65%
  const rueck  = d.ruecklage || 0;
  const grest  = GRUNDERWERBSTEUER[state] || 6.0;
  const notar  = d.notarkosten || 1.5;
  const makler = d.maklergebuehr ?? 0;

  const nbk         = grest + notar + makler;
  const totalCost   = price ? price * (1 + nbk / 100) : 0;
  const annualRent  = cold ? cold * 12 : null;
  const nonRecovHaus = hg * (1 - umlag / 100);  // matches baseline: hausgeld*(1-umlag/100)
  const grossY      = (annualRent && price) ? (annualRent / price * 100) : null;
  const netY        = (annualRent && totalCost)
    ? ((annualRent - nonRecovHaus * 12) / totalCost * 100)
    : null;
  const psqm           = (price && area) ? price / area : null;
  const ruecklagePsqm  = (rueck && area) ? rueck / area : null;

  return { grossY, netY, psqm, totalCost, nbk, nonRecovHaus, ruecklagePsqm };
}

// Matches baseline riskFlags() logic
function calcRiskFlags(d, m) {
  const flags = [];

  if (!d.coldRent && !d.warmRent)
    flags.push({ t: 'No rent data', cls: 'risk' });
  else if (!d.coldRent && d.warmRent)
    flags.push({ t: 'Warm rent only — yield estimate', cls: 'risk' });

  if (m.grossY !== null && m.grossY < 3)
    flags.push({ t: `Low yield (${m.grossY.toFixed(1)}%)`, cls: 'risk' });

  if (!d.energy)
    flags.push({ t: 'Energy class unknown', cls: 'warn' });
  else if (['F', 'G', 'H'].includes(d.energy))
    flags.push({ t: `Energy ${d.energy} — renovation risk`, cls: 'warn' });

  if (m.ruecklagePsqm !== null) {
    if (m.ruecklagePsqm < 15)
      flags.push({ t: `Rücklage low (€${m.ruecklagePsqm.toFixed(0)}/m²)`, cls: 'risk' });
    else if (m.ruecklagePsqm < 30)
      flags.push({ t: `Rücklage moderate (€${m.ruecklagePsqm.toFixed(0)}/m²)`, cls: 'warn' });
  }

  if (m.nonRecovHaus > 350)
    flags.push({ t: `High hausgeld (€${Math.round(m.nonRecovHaus)}/mo non-recoverable)`, cls: 'warn' });

  if (d.tenanted === 'no')
    flags.push({ t: 'Vacant — no rental income', cls: 'warn' });

  if (d.mietpreisbremse)
    flags.push({ t: 'Mietpreisbremse — rent increases capped', cls: 'info' });

  return flags;
}

// Matches baseline score() function — same tiers, same component weights, same penalties
function calcScore(d, state) {
  const m = calcMetrics(d, state);

  // Yield (0–40 pts) — ≥7% tier added to match baseline
  let yS = 0;
  if (m.grossY !== null) {
    if (m.grossY >= 7)      yS = 40;
    else if (m.grossY >= 6) yS = 35;
    else if (m.grossY >= 5) yS = 28;
    else if (m.grossY >= 4) yS = 20;
    else if (m.grossY >= 3) yS = 12;
    else                    yS = 5;
  }

  // Energy (0–20 pts) — ENERGY_SCORE lookup with default 5 (matches baseline)
  const eS = d.energy ? (ENERGY_SCORE[d.energy] ?? 5) : 5;

  // Completeness (0–20 pts) — exact baseline weights
  let cS = 0;
  if (d.price)    cS += 4;
  if (d.area)     cS += 4;
  if (d.coldRent) cS += 5;
  if (d.energy)   cS += 4;
  if (d.hausgeld) cS += 3;

  // Price/sqm (0–20 pts) — baseline uses relative; we use calibrated absolute thresholds
  let pS = 10;
  if (m.psqm !== null) {
    if (m.psqm < 1500)      pS = 20;
    else if (m.psqm < 2500) pS = 16;
    else if (m.psqm < 4000) pS = 12;
    else if (m.psqm < 5500) pS = 8;
    else if (m.psqm < 7500) pS = 4;
    else                    pS = 1;
  }

  // Risk flag penalties — matches baseline: -4 per risk, -1 per warn
  const flags = calcRiskFlags(d, m);
  const pen = flags.filter(f => f.cls === 'risk').length * 4
            + flags.filter(f => f.cls === 'warn').length;

  return Math.max(0, Math.min(100, Math.round(yS + eS + cS + pS - pen)));
}

// ── Main search orchestration ─────────────────────────────────────────────────

let abortSearch = false;

// Keep-alive alarm: fires every 25s to prevent service worker from sleeping
// during a long search (MV3 workers idle out after ~30s of inactivity).
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'keepAlive') { /* just wakes the worker */ }
});

async function runSearch({ city, budget, maxListings }) {
  abortSearch = false;
  chrome.alarms.create('keepAlive', { periodInMinutes: 0.4 }); // every 24s
  send('progress', { msg: `Searching ${city}…`, pct: 2 });

  const cityLow = city.toLowerCase();
  const state   = CITY_STATE[cityLow] || 'BE';
  const mpb     = MPB_CITIES.has(cityLow);
  const allUrls = [];
  let pct = 5;

  // ── Step 1: collect listing URLs from portal search pages ──────────────────
  for (const portal of PORTALS) {
    if (abortSearch) break;
    const searchUrl = portal.url(city);
    send('progress', { msg: `Opening ${portal.name}…`, pct });
    pct = Math.min(35, pct + 10);

    let tab;
    try {
      send('progress', { msg: `${portal.name}: opening ${searchUrl}`, pct });
      tab = await openTab(searchUrl);
      await waitForLoad(tab.id);

      const urls = await execScript(tab.id, __getUrls, [portal.patterns]);
      if (urls === null) {
        send('progress', { msg: `${portal.name}: script blocked — check extension permissions`, pct });
      } else if (urls.length === 0) {
        // One retry with extra wait — some SPAs render links late
        await sleep(3000);
        const retry = await execScript(tab.id, __getUrls, [portal.patterns]);
        if (retry?.length) {
          send('progress', { msg: `${portal.name}: found ${retry.length} links (retry)`, pct });
          allUrls.push(...retry);
        } else {
          send('progress', { msg: `${portal.name}: 0 links found (pattern: ${portal.patterns.join(',')})`, pct });
        }
      } else {
        send('progress', { msg: `${portal.name}: found ${urls.length} links`, pct });
        allUrls.push(...urls);
      }
    } catch (e) {
      send('progress', { msg: `${portal.name}: error — ${e.message}`, pct });
    } finally {
      if (tab) await closeTab(tab.id);
    }

    if (allUrls.length >= maxListings * 6) break;
  }

  const unique = [...new Set(allUrls)];
  if (unique.length === 0) {
    send('done', { listings: [], msg: 'No listing links found. Try a different city or check that you are logged in.' });
    return;
  }

  send('progress', { msg: `Collected ${unique.length} links — opening each listing…`, pct: 38 });

  // ── Step 2: open each listing, extract + score ─────────────────────────────
  const saved  = [];
  let   opened = 0;

  for (const url of unique) {
    if (abortSearch || saved.length >= maxListings) break;

    const progPct = 38 + Math.round((opened / Math.min(unique.length, maxListings * 4)) * 58);
    send('progress', { msg: `Listing ${opened + 1}/${Math.min(unique.length, maxListings * 4)}…`, pct: progPct });

    let tab;
    try {
      tab = await openTab(url);
      await waitForLoad(tab.id);

      let data = await execScript(tab.id, __extractData);

      // ── Optional Claude enrichment ──────────────────────────────────────────
      if (data) {
        // Priority: config.js pre-configured key → chrome.storage key (settings panel)
        const { claude_api_key: storedKey } = await chrome.storage.local.get('claude_api_key');
        const apiKey = (typeof self.RE_RADAR_KEY === 'string' && self.RE_RADAR_KEY) || storedKey || null;
        if (apiKey) {
          send('progress', { msg: `AI enriching listing…`, pct: progPct });
          const enriched = await enrichWithClaude(data._rawText || '', apiKey);
          // Merge: Claude values override regex only where Claude found something
          const FIELDS = ['name','address','city','price','area','rooms','coldRent',
                          'hausgeld','energy','yearBuilt','tenanted','maklergebuehr'];
          for (const f of FIELDS) {
            if (enriched[f] != null) data[f] = enriched[f];
          }
        }
        delete data._rawText; // don't store raw text in listings
      }

      if (data && data.price && data.area) {
        if (budget && data.price > budget) {
          send('progress', { msg: `Skipped (€${Math.round(data.price/1000)}k > budget)`, pct: progPct });
          opened++;
          await closeTab(tab.id);
          await sleep(200);
          continue;
        }

        // Enrich with defaults before scoring
        const enrichBase = {
          ...data,
          id: url.replace(/https?:\/\/(?:www\.)?/, '').replace(/[^a-zA-Z0-9]/g, '-').slice(0, 80),
          city: data.city || city,
          state,
          mietpreisbremse: mpb,
          grunderwerbsteuer: GRUNDERWERBSTEUER[state] || 6.0,
          notarkosten: data.notarkosten || 1.5,
          umlagefaehig: data.umlagefaehig || 65,
          updatedAt: new Date().toISOString(),
        };
        const metrics  = calcMetrics(enrichBase, state);
        const riskFlags = calcRiskFlags(enrichBase, metrics);
        const listing = {
          ...enrichBase,
          _score:      calcScore(enrichBase, state),
          _grossYield: metrics.grossY,
          _netYield:   metrics.netY,
          _psqm:       metrics.psqm,
          _totalCost:  metrics.totalCost,
          _nbk:        metrics.nbk,
          _riskFlags:  riskFlags,
        };

        saved.push(listing);
        send('listing', { listing });
        send('progress', { msg: `✓ Saved: ${data.name?.slice(0, 55)}`, pct: progPct });
      }
    } catch (e) {
      // silently skip
    } finally {
      if (tab) await closeTab(tab.id);
    }

    opened++;
    await sleep(300); // polite delay
  }

  // ── Persist to chrome.storage ─────────────────────────────────────────────
  const { re_radar_listings: existing = [] } = await chrome.storage.local.get('re_radar_listings');
  const merged = [...existing, ...saved].slice(-300);
  await chrome.storage.local.set({ re_radar_listings: merged });

  // ── Push to RE Radar dashboard (GitHub Pages) ─────────────────────────────
  if (saved.length > 0) {
    await pushToDashboard(saved);
  }

  chrome.alarms.clear('keepAlive');
  send('done', {
    listings: saved,
    msg: `Done — ${saved.length} listing${saved.length !== 1 ? 's' : ''} found.`,
    pct: 100,
  });
}

// Inject listings into the RE Radar tab if it's open
async function pushToDashboard(listings) {
  try {
    const tabs = await chrome.tabs.query({ url: '*://plutobi.github.io/RE-Rader/*' });
    for (const tab of tabs) {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: (data) => {
          // Merge into the RE Radar dashboard listings
          const key = 're_radar_v3';
          let stored = [];
          try { stored = JSON.parse(localStorage.getItem(key) || '[]'); } catch (_) {}
          const ids = new Set(stored.map((l) => l.id));
          const fresh = data.filter((l) => !ids.has(l.id));
          const merged = [...stored, ...fresh].slice(-300);
          localStorage.setItem(key, JSON.stringify(merged));
          // Trigger reload if the page exposes a reload function
          if (typeof window._reradarReload === 'function') window._reradarReload();
          else window.location.reload();
        },
        args: [listings],
      });
    }
  } catch (_) {
    // Dashboard tab not open — silently ignore
  }
}

// ── Claude AI enrichment ───────────────────────────────────────────────────────
// Sends raw page text to Claude Haiku to extract fields that regex misses.
// API key is stored in chrome.storage.local — never hardcoded.
// Returns a partial object; null fields are ignored (regex value kept).
async function enrichWithClaude(rawText, apiKey) {
  const prompt = `Extract German real estate listing data from this page text. Return ONLY a JSON object, no explanation. Use null for fields not found.

Fields:
- name: clean property title (no price or size info)
- address: full street address including house number
- city: city name
- price: purchase price in euros (number)
- area: living area in m² (number, realistic range 15-500)
- rooms: number of rooms (number, range 0.5-20)
- coldRent: monthly cold rent in euros (number)
- hausgeld: monthly service charge in euros (number)
- energy: energy class, one of A+/A/B/C/D/E/F/G/H
- yearBuilt: construction year (number)
- tenanted: "yes" if currently rented, "no" if vacant, "unknown"
- maklergebuehr: broker fee in % (0 if provisionsfrei or ohne Provision)

German number format: "340.000" = 340000, "1.234,56" = 1234.56

Page text:
${rawText}`;

  try {
    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 512,
        messages: [{ role: 'user', content: prompt }],
      }),
    });
    if (!res.ok) return {};
    const json = await res.json();
    const text = json.content?.[0]?.text || '{}';
    const match = text.match(/\{[\s\S]*\}/);
    return match ? JSON.parse(match[0]) : {};
  } catch (_) {
    return {};
  }
}

// Allow popup to abort an ongoing search
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.action === 'abort') abortSearch = true;
});
