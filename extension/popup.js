// ─── RE Radar – Popup Script ──────────────────────────────────────────────────
'use strict';

const $ = (id) => document.getElementById(id);

const btnSearch  = $('btnSearch');
const btnStop    = $('btnStop');
const selCity    = $('selCity');
const inpMax     = $('inpMax');
const inpBudget  = $('inpBudget');
const progWrap   = $('prog');
const progBar    = $('progBar');
const progMsg    = $('progMsg');
const progPct    = $('progPct');
const progDot    = $('progDot');
const results    = $('results');
const emptyMsg   = $('emptyMsg');
const countLabel = $('countLabel');
const clearLink  = $('clearLink');

let port      = null;
let listings  = [];
let searching = false;

// ── Restore last city ─────────────────────────────────────────────────────────
chrome.storage.local.get('lastCity', ({ lastCity }) => {
  if (lastCity) selCity.value = lastCity;
});

// ── Background port ───────────────────────────────────────────────────────────
function connectPort() {
  port = chrome.runtime.connect({ name: 'radar' });
  port.onMessage.addListener(onBgMsg);
  port.onDisconnect.addListener(() => {
    port = null;
    // Don't reset to idle — search keeps running in the background service worker.
    // When popup reopens, connectPort() fires getStored and shows completed results.
  });
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
      progDot.style.animationPlayState = 'paused';
      if (listings.length === 0) {
        emptyMsg.style.display = 'block';
        emptyMsg.innerHTML = `<span>🔍</span>${msg.msg || 'No listings found.'}`;
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
  const city       = selCity.value.trim();
  const maxListings = parseInt(inpMax.value, 10) || 5;
  const budget      = inpBudget.value ? parseInt(inpBudget.value, 10) : null;

  if (!city) return;

  chrome.storage.local.set({ lastCity: city });
  listings = [];
  results.querySelectorAll('.card').forEach((c) => c.remove());
  emptyMsg.style.display = 'none';
  updateCount();
  setBusy();
  setProgress(`Connecting to portals…`, 2);
  progDot.style.animationPlayState = 'running';

  if (!port) connectPort();
  port.postMessage({ action: 'startSearch', params: { city, maxListings, budget } });
});

// ── Stop ──────────────────────────────────────────────────────────────────────
btnStop.addEventListener('click', () => {
  chrome.runtime.sendMessage({ action: 'abort' });
  setProgress('Search stopped.', null);
  setIdle();
});

// ── Clear ─────────────────────────────────────────────────────────────────────
clearLink.addEventListener('click', (e) => {
  e.preventDefault();
  if (!confirm('Remove all stored listings?')) return;
  if (port) port.postMessage({ action: 'clearStored' });
  listings = [];
  results.querySelectorAll('.card').forEach((c) => c.remove());
  emptyMsg.style.display = 'block';
  emptyMsg.innerHTML = `<span>🏠</span>Pick a city and click Search Online.<br>Listings stream in as they're found.`;
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
  const n = listings.length;
  countLabel.textContent = `${n} listing${n !== 1 ? 's' : ''}`;
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
  if (s == null) return 'rgba(255,255,255,.08)';
  return s >= 60 ? 'var(--green)' : s >= 35 ? 'var(--yellow)' : 'var(--red)';
}

function renderCard(l) {
  emptyMsg.style.display = 'none';

  const score = l._score ?? null;
  const gy    = l._grossYield;
  const ny    = l._netYield;
  const psqm  = l._psqm;

  const sourcePill = `<span class="pill pill-a">${esc(l.source || 'portal')}</span>`;
  const tenantPill = l.tenanted === 'yes'
    ? `<span class="pill pill-g">vermietet</span>`
    : l.tenanted === 'no'
    ? `<span class="pill">bezugsfrei</span>`
    : '';
  const energyPill = l.energy ? `<span class="pill">Klasse ${esc(l.energy)}</span>` : '';

  const stats = [
    fmtEur(l.price)  ? `<span><strong>${fmtEur(l.price)}</strong></span>` : '',
    l.area           ? `<span>${fmt(l.area)} m²</span>` : '',
    gy != null       ? `<span class="yield">${gy.toFixed(1)}% yield</span>` : '',
    ny != null       ? `<span class="net">${ny.toFixed(1)}% net</span>` : '',
    psqm != null     ? `<span>${fmtEur(psqm)}/m²</span>` : '',
    l.coldRent       ? `<span>${fmtEur(l.coldRent)}/mo rent</span>` : '',
    l.rooms          ? `<span>${fmt(l.rooms, 1)} Zi</span>` : '',
  ].filter(Boolean).join('');

  const card = document.createElement('div');
  card.className = 'card';
  card.style.setProperty('--clr', scoreColor(score));
  card.dataset.url = l.sourceUrl || '';

  card.innerHTML = `
    <div class="c-top">
      <div class="c-name">${esc(l.name || 'Listing')}</div>
      ${score != null ? `<div class="c-score ${scoreClass(score)}">⭐ ${score}</div>` : ''}
    </div>
    <div class="c-pills">${sourcePill}${tenantPill}${energyPill}</div>
    <div class="c-row">${stats}</div>
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
