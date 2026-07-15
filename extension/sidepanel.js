// ─── RE Radar – Side Panel Script ─────────────────────────────────────────────
'use strict';

// ── Translations ──────────────────────────────────────────────────────────────
const T = {
  de: {
    desc:            'Deutsche Immobilieninvestitionen',
    cityLbl:         'Stadt',
    maxLbl:          'Max. Angebote',
    budgetLbl:       'Budget (€)',
    budgetHolder:    'Kein Limit',
    searchBtn:       'Suche starten',
    stopBtn:         'Stopp',
    progInit:        'Initialisierung…',
    connecting:      'Verbindung zu Portalen…',
    emptyIdle:       'Wähle eine Stadt und klicke auf „Suche starten".<br>Angebote erscheinen während der Suche.',
    emptyNone:       'Keine Angebote gefunden.',
    stopped:         'Suche gestoppt.',
    clearConfirm:    'Alle gespeicherten Angebote entfernen?',
    clearEmpty:      'Wähle eine Stadt und klicke auf „Suche starten".<br>Angebote erscheinen während der Suche.',
    count:           (n) => `${n} Angebot${n !== 1 ? 'e' : ''}`,
    dashboard:       'Dashboard ↗',
    clear:           'Löschen',
    toggleLabel:     'EN',
    yield:           '% Rendite',
    net:             '% netto',
    tenantedYes:     'vermietet',
    tenantedNo:      'bezugsfrei',
    energyPrefix:    'Klasse ',
  },
  en: {
    desc:            'German real estate investment',
    cityLbl:         'City',
    maxLbl:          'Max listings',
    budgetLbl:       'Budget (€)',
    budgetHolder:    'No limit',
    searchBtn:       'Search Online',
    stopBtn:         'Stop',
    progInit:        'Initialising…',
    connecting:      'Connecting to portals…',
    emptyIdle:       'Pick a city and click Search Online.<br>Listings stream in as they\'re found.',
    emptyNone:       'No listings found.',
    stopped:         'Search stopped.',
    clearConfirm:    'Remove all stored listings?',
    clearEmpty:      'Pick a city and click Search Online.<br>Listings stream in as they\'re found.',
    count:           (n) => `${n} listing${n !== 1 ? 's' : ''}`,
    dashboard:       'Dashboard ↗',
    clear:           'Clear',
    toggleLabel:     'DE',
    yield:           '% yield',
    net:             '% net',
    tenantedYes:     'vermietet',
    tenantedNo:      'bezugsfrei',
    energyPrefix:    'Klasse ',
  },
};

// ── DOM refs ──────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

const btnSearch   = $('btnSearch');
const btnStop     = $('btnStop');
const selCity     = $('selCity');
const inpMax      = $('inpMax');
const inpBudget   = $('inpBudget');
const progWrap    = $('prog');
const progBar     = $('progBar');
const progMsg     = $('progMsg');
const progPct     = $('progPct');
const progDot     = $('progDot');
const results     = $('results');
const emptyMsg    = $('emptyMsg');
const countLabel  = $('countLabel');
const clearBtn    = $('clearLink');
const langToggle  = $('langToggle');

let port      = null;
let listings  = [];
let searching = false;
let lang      = 'de';   // default German

// ── i18n ─────────────────────────────────────────────────────────────────────
function t(key, ...args) {
  const val = T[lang][key];
  return typeof val === 'function' ? val(...args) : val;
}

function applyLang() {
  document.documentElement.lang = lang;
  $('hdrDesc').textContent        = t('desc');
  $('lblCity').textContent         = t('cityLbl');
  $('lblMax').textContent          = t('maxLbl');
  $('lblBudget').textContent       = t('budgetLbl');
  inpBudget.placeholder            = t('budgetHolder');
  $('btnSearchText').textContent   = t('searchBtn');
  $('btnStopText').textContent     = t('stopBtn');
  $('lnkDash').textContent         = t('dashboard');
  clearBtn.textContent             = t('clear');
  langToggle.textContent           = t('toggleLabel');
  countLabel.textContent           = t('count', listings.length);
  if (emptyMsg.style.display !== 'none') {
    $('emptyText').innerHTML = t('emptyIdle');
  }
}

langToggle.addEventListener('click', () => {
  lang = lang === 'de' ? 'en' : 'de';
  chrome.storage.local.set({ lang });
  applyLang();
  // Re-render cards so yield/net labels update
  if (listings.length) rerenderAll();
});

// ── Restore prefs ─────────────────────────────────────────────────────────────
chrome.storage.local.get(['lastCity', 'lang'], ({ lastCity, lang: savedLang }) => {
  if (lastCity)   selCity.value = lastCity;
  if (savedLang)  lang = savedLang;
  applyLang();
});

// ── Background port ───────────────────────────────────────────────────────────
function connectPort() {
  port = chrome.runtime.connect({ name: 'radar' });
  port.onMessage.addListener(onBgMsg);
  port.onDisconnect.addListener(() => { port = null; });
  port.postMessage({ action: 'getStored' });
}
connectPort();

function onBgMsg(msg) {
  switch (msg.type) {
    case 'progress':
      setProgress(msg.msg, msg.pct ?? null);
      break;
    case 'listing':
      if (!listings.some((l) => l.id === msg.listing.id)) {
        listings.push(msg.listing);
        renderCard(msg.listing);
        updateCount();
      }
      break;
    case 'done':
      setIdle();
      setProgress(msg.msg, 100);
      if (listings.length === 0) {
        emptyMsg.style.display = 'block';
        $('emptyText').innerHTML = `<span style="font-size:28px;display:block;margin-bottom:8px;opacity:.6">🔍</span>${t('emptyNone')}`;
      }
      break;
    case 'storedListings':
      if (msg.listings?.length) {
        listings = msg.listings;
        rerenderAll();
      }
      break;
  }
}

// ── Search ────────────────────────────────────────────────────────────────────
btnSearch.addEventListener('click', () => {
  const city        = selCity.value.trim();
  const maxListings = parseInt(inpMax.value, 10) || 5;
  const budget      = inpBudget.value ? parseInt(inpBudget.value, 10) : null;
  if (!city) return;

  chrome.storage.local.set({ lastCity: city });
  listings = [];
  results.querySelectorAll('.card').forEach((c) => c.remove());
  emptyMsg.style.display = 'none';
  updateCount();
  setBusy();
  setProgress(t('connecting'), 2);

  if (!port) connectPort();
  port.postMessage({ action: 'startSearch', params: { city, maxListings, budget } });
});

// ── Stop ──────────────────────────────────────────────────────────────────────
btnStop.addEventListener('click', () => {
  chrome.runtime.sendMessage({ action: 'abort' });
  setProgress(t('stopped'), null);
  setIdle();
});

// ── Clear ─────────────────────────────────────────────────────────────────────
clearBtn.addEventListener('click', () => {
  if (!confirm(t('clearConfirm'))) return;
  if (port) port.postMessage({ action: 'clearStored' });
  listings = [];
  results.querySelectorAll('.card').forEach((c) => c.remove());
  emptyMsg.style.display = 'block';
  $('emptyText').innerHTML = t('clearEmpty');
  updateCount();
  progWrap.classList.remove('on');
});

// ── State helpers ─────────────────────────────────────────────────────────────
function setBusy() {
  searching = true;
  btnSearch.disabled = true;
  btnStop.classList.add('on');
  progWrap.classList.add('on');
}
function setIdle() {
  searching = false;
  btnSearch.disabled = false;
  btnStop.classList.remove('on');
}
function setProgress(msg, pct) {
  if (msg) progMsg.textContent = msg;
  if (pct != null) {
    progBar.style.width = Math.min(100, pct) + '%';
    progPct.textContent = Math.min(100, Math.round(pct)) + '%';
  }
}
function updateCount() {
  countLabel.textContent = t('count', listings.length);
}

// ── Card rendering ────────────────────────────────────────────────────────────
function fmtEur(n) {
  if (n == null) return null;
  if (n >= 1_000_000) return '€' + (n / 1_000_000).toFixed(2).replace(/\.?0+$/, '') + 'M';
  if (n >= 1000)      return '€' + Math.round(n / 1000) + 'k';
  return '€' + Math.round(n);
}
function fmt(n, d = 0) {
  if (n == null) return null;
  return n.toLocaleString('de-DE', { maximumFractionDigits: d });
}
function esc(s) {
  return String(s || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function scoreClass(s) {
  if (s == null) return '';
  return s >= 60 ? 's-hi' : s >= 35 ? 's-md' : 's-lo';
}
function scoreColor(s) {
  if (s == null) return 'rgba(255,255,255,.1)';
  return s >= 60 ? '#34d399' : s >= 35 ? '#fbbf24' : '#f87171';
}

function renderCard(l) {
  emptyMsg.style.display = 'none';

  const score = l._score ?? null;
  const gy    = l._grossYield;
  const ny    = l._netYield;
  const psqm  = l._psqm;

  const sourcePill = `<span class="pill pill-a">${esc(l.source || 'portal')}</span>`;
  const tenantPill = l.tenanted === 'yes'
    ? `<span class="pill pill-g">${t('tenantedYes')}</span>`
    : l.tenanted === 'no'
    ? `<span class="pill">${t('tenantedNo')}</span>`
    : '';
  const energyPill = l.energy
    ? `<span class="pill">${t('energyPrefix')}${esc(l.energy)}</span>`
    : '';

  const stats = [
    fmtEur(l.price) ? `<span><strong>${fmtEur(l.price)}</strong></span>` : '',
    l.area          ? `<span>${fmt(l.area)} m²</span>` : '',
    gy != null      ? `<span class="yield">${gy.toFixed(1)}${t('yield')}</span>` : '',
    ny != null      ? `<span class="net">${ny.toFixed(1)}${t('net')}</span>` : '',
    psqm != null    ? `<span>${fmtEur(psqm)}/m²</span>` : '',
    l.coldRent      ? `<span>${fmtEur(l.coldRent)}/mo</span>` : '',
    l.rooms         ? `<span>${fmt(l.rooms, 1)} Zi</span>` : '',
  ].filter(Boolean).join('');

  const card = document.createElement('div');
  card.className = 'card';
  card.style.setProperty('--clr', scoreColor(score));
  card.dataset.id = l.id || '';

  card.innerHTML = `
    <div class="c-top">
      <div class="c-name">${esc(l.name || 'Listing')}</div>
      ${score != null ? `<div class="c-score ${scoreClass(score)}">⭐ ${score}</div>` : ''}
    </div>
    <div class="c-pills">${sourcePill}${tenantPill}${energyPill}</div>
    ${stats ? `<div class="c-row">${stats}</div>` : ''}
  `;

  card.addEventListener('click', () => {
    if (l.sourceUrl) chrome.tabs.create({ url: l.sourceUrl, active: true });
  });

  results.appendChild(card);
  results.scrollTop = results.scrollHeight;
}

function rerenderAll() {
  results.querySelectorAll('.card').forEach((c) => c.remove());
  emptyMsg.style.display = listings.length ? 'none' : 'block';
  listings.forEach(renderCard);
  updateCount();
}
