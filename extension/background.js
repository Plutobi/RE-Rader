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
    url: (city) => `https://www.immonet.de/immobilienbewertung/wohnung-kaufen-in-${slugify(city)}.html`,
    patterns: ['/angebot/'],
  },
];

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
        setTimeout(resolve, 2500); // extra time for JS rendering
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
  const found = [];
  for (const a of document.querySelectorAll('a[href]')) {
    const h = a.href;
    if (patterns.some((p) => h.includes(p)) && !found.includes(h)) {
      found.push(h);
    }
  }
  return found;
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
  const area     = findNum(['Wohnfläche', 'Nutzfläche', 'Fläche ca', 'Fläche'], 5, 5000);
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

  const name = (document.querySelector('h1')?.textContent?.trim()
    || document.title?.replace(/\s*[-|].*$/, '').trim()
    || 'Inserat').slice(0, 120);

  const address = (
    document.querySelector('[class*="address" i]')?.textContent?.trim()
    || document.querySelector('[class*="location" i], [class*="ort" i]')?.textContent?.trim()
    || ''
  ).replace(/\s+/g, ' ').slice(0, 100);

  // Detect city from URL
  const cityMatch = url.match(
    /\/(berlin|hamburg|m[uü][e]?nchen|frankfurt|k[oö]ln|d[uü]sseldorf|stuttgart|leipzig|dresden|hannover|bremen|n[uü]rnberg|augsburg|mainz|freiburg|bonn|mannheim|dortmund|essen)\//i
  );
  const city = cityMatch ? cityMatch[1].charAt(0).toUpperCase() + cityMatch[1].slice(1) : '';

  return {
    name, address, city, price, area, rooms, yearBuilt,
    coldRent, warmRent, hausgeld, ruecklage,
    energy, tenanted, maklergebuehr,
    sourceUrl: url,
    source: location.hostname.replace('www.', ''),
    createdAt: new Date().toISOString(),
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

async function runSearch({ city, budget, maxListings }) {
  abortSearch = false;
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
      tab = await openTab(searchUrl);
      await waitForLoad(tab.id);

      const urls = await execScript(tab.id, __getUrls, [portal.patterns]);
      if (urls?.length) {
        send('progress', { msg: `${portal.name}: found ${urls.length} links`, pct });
        allUrls.push(...urls);
      } else {
        send('progress', { msg: `${portal.name}: no listing links found`, pct });
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

      const data = await execScript(tab.id, __extractData);

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

// Allow popup to abort an ongoing search
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.action === 'abort') abortSearch = true;
});
