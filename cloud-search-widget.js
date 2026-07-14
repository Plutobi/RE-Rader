/**
 * RE Radar — Cloud Search Widget
 * ═══════════════════════════════════════════════════════════════
 * Drop this file next to index.html and add ONE line before </body>:
 *
 *   <script src="cloud-search-widget.js"></script>
 *
 * Then set RE_RADAR_API below to your Railway / Render backend URL.
 * For local testing, keep it as http://localhost:8000
 */

const RE_RADAR_API = "https://re-rader.onrender.com";

// ─────────────────────────────────────────────────────────────────
//  Page starts blank — listings only load after a Search Online.
//  (Auto-load disabled; was causing pre-populated listings on start)
// ─────────────────────────────────────────────────────────────────
// window.addEventListener('load', ...) — DISABLED

// Exposed so the search widget can update listings after a job completes
window.reloadAgentListings = function (data) {
  if (typeof window.listings === 'undefined') return;
  // Keep user-added (localStorage) listings, replace cloud ones
  const localIds = new Set(
    JSON.parse(localStorage.getItem('re_radar_v3') || '[]').map(l => l.id)
  );
  const local = window.listings.filter(l => localIds.has(l.id));
  window.listings = [...local, ...data];
  if (typeof render === 'function') render();
  if (typeof updateLayout === 'function') updateLayout();
};

// ─────────────────────────────────────────────────────────────────
//  Inject the widget HTML + CSS
// ─────────────────────────────────────────────────────────────────
(function () {
  const style = document.createElement("style");
  style.textContent = `
    #re-cloud-btn {
      position: fixed;
      bottom: 28px;
      right: 28px;
      z-index: 9000;
      background: #6366f1;
      color: #fff;
      border: none;
      border-radius: 50px;
      padding: 12px 22px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      box-shadow: 0 4px 20px rgba(99,102,241,.45);
      display: flex;
      align-items: center;
      gap: 8px;
      transition: transform .15s, box-shadow .15s;
    }
    #re-cloud-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 28px rgba(99,102,241,.55); }
    #re-cloud-btn svg   { width:16px; height:16px; }

    #re-cloud-modal {
      display: none;
      position: fixed;
      inset: 0;
      z-index: 9100;
      background: rgba(0,0,0,.55);
      backdrop-filter: blur(3px);
      align-items: center;
      justify-content: center;
    }
    #re-cloud-modal.open { display: flex; }

    #re-cloud-panel {
      background: #1e1e2e;
      border: 1px solid #333;
      border-radius: 16px;
      padding: 28px 32px;
      width: 480px;
      max-width: 96vw;
      color: #e2e8f0;
      font-family: inherit;
      box-shadow: 0 24px 60px rgba(0,0,0,.6);
    }
    #re-cloud-panel h2 {
      margin: 0 0 20px;
      font-size: 18px;
      font-weight: 700;
      color: #a5b4fc;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .rc-row { display: flex; gap: 10px; margin-bottom: 12px; }
    .rc-field { flex: 1; }
    .rc-field label {
      display: block;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .05em;
      color: #94a3b8;
      margin-bottom: 5px;
    }
    .rc-field input, .rc-field select {
      width: 100%;
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 8px;
      color: #e2e8f0;
      padding: 9px 12px;
      font-size: 14px;
      box-sizing: border-box;
    }
    .rc-field input:focus, .rc-field select:focus {
      outline: none;
      border-color: #6366f1;
    }

    /* ── Progress bar ── */
    #rc-progress-wrap {
      display: none;
      margin: 14px 0 4px;
    }
    #rc-progress-track {
      background: #0f172a;
      border-radius: 6px;
      height: 8px;
      overflow: hidden;
      border: 1px solid #1e293b;
    }
    #rc-progress-bar {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, #6366f1, #a5b4fc);
      border-radius: 6px;
      transition: width 0.7s cubic-bezier(.4,0,.2,1);
    }
    #rc-stage {
      font-size: 11px;
      color: #64748b;
      margin-top: 6px;
      min-height: 14px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    #rc-stage::before {
      content: '';
      width: 6px; height: 6px;
      border-radius: 50%;
      background: #6366f1;
      flex-shrink: 0;
      animation: rc-pulse 1.2s ease-in-out infinite;
    }
    #rc-stage.done::before { background: #4ade80; animation: none; }
    #rc-stage.err::before  { background: #f87171; animation: none; }
    @keyframes rc-pulse {
      0%,100% { opacity: 1; transform: scale(1); }
      50%      { opacity: .4; transform: scale(.6); }
    }

    #rc-log {
      background: #0f172a;
      border: 1px solid #1e293b;
      border-radius: 8px;
      padding: 12px;
      height: 130px;
      overflow-y: auto;
      font-family: monospace;
      font-size: 12px;
      color: #94a3b8;
      margin: 10px 0;
      display: none;
    }
    #rc-log .ok   { color: #4ade80; }
    #rc-log .info { color: #60a5fa; }
    #rc-log .warn { color: #fbbf24; }
    #rc-log .err  { color: #f87171; }

    .rc-actions { display: flex; gap: 10px; margin-top: 4px; }
    #rc-search-btn {
      flex: 1;
      padding: 11px;
      background: #6366f1;
      color: #fff;
      border: none;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: background .15s;
    }
    #rc-search-btn:hover:not(:disabled) { background: #4f46e5; }
    #rc-search-btn:disabled { background: #334155; cursor: default; }
    #rc-close-btn {
      padding: 11px 18px;
      background: transparent;
      color: #64748b;
      border: 1px solid #334155;
      border-radius: 8px;
      font-size: 14px;
      cursor: pointer;
    }
    #rc-close-btn:hover { color: #e2e8f0; border-color: #475569; }

    #rc-status { font-size: 12px; color: #64748b; margin-top: 10px; text-align: center; min-height: 16px; }
  `;
  document.head.appendChild(style);

  // ── FAB button ───────────────────────────────────────────────
  const fab = document.createElement("button");
  fab.id = "re-cloud-btn";
  fab.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
    </svg>
    Search Online`;
  document.body.appendChild(fab);

  // ── Modal ────────────────────────────────────────────────────
  const CITIES = [
    "Berlin","Hamburg","München","Frankfurt","Köln","Düsseldorf","Stuttgart",
    "Leipzig","Dresden","Hannover","Bremen","Nürnberg","Augsburg","Mainz",
    "Freiburg","Bonn","Mannheim","Heidelberg","Münster","Dortmund","Essen",
    "Wiesbaden","Kiel","Erfurt","Magdeburg","Rostock","Potsdam","Saarbrücken",
    "Aachen","Karlsruhe",
  ];

  const modal = document.createElement("div");
  modal.id = "re-cloud-modal";
  modal.innerHTML = `
    <div id="re-cloud-panel">
      <h2>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#a5b4fc" stroke-width="2">
          <path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/>
        </svg>
        Search German Real Estate
      </h2>

      <div class="rc-row">
        <div class="rc-field" style="flex:2">
          <label>City</label>
          <select id="rc-city">
            ${CITIES.map(c => `<option value="${c.toLowerCase()}">${c}</option>`).join("")}
          </select>
        </div>
        <div class="rc-field">
          <label>Max listings</label>
          <input id="rc-max" type="number" value="4" min="1" max="10">
        </div>
        <div class="rc-field">
          <label>Budget (€)</label>
          <input id="rc-budget" type="number" value="" placeholder="no limit">
        </div>
      </div>

      <div class="rc-field" style="margin-bottom:4px">
        <label>Custom goal (optional)</label>
        <input id="rc-goal" type="text" placeholder="e.g. Find 3 provisionsfrei flats under €300k with confirmed Kaltmiete">
      </div>

      <div id="rc-progress-wrap">
        <div id="rc-progress-track"><div id="rc-progress-bar"></div></div>
        <div id="rc-stage"></div>
      </div>

      <div id="rc-log"></div>
      <div id="rc-status"></div>

      <div class="rc-actions">
        <button id="rc-search-btn">Start Search</button>
        <button id="rc-close-btn">Close</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  // ─────────────────────────────────────────────────────────────
  //  Logic
  // ─────────────────────────────────────────────────────────────
  const logEl      = document.getElementById("rc-log");
  const statusEl   = document.getElementById("rc-status");
  const searchBtn  = document.getElementById("rc-search-btn");
  const progressWrap = document.getElementById("rc-progress-wrap");
  const progressBar  = document.getElementById("rc-progress-bar");
  const stageEl      = document.getElementById("rc-stage");
  let   pollTimer    = null;
  let   _pct         = 0;

  // ── Progress helpers ─────────────────────────────────────────
  const STAGES = [
    { match: /agent starting|connecting/i,            pct: 5,  label: "Connecting…"             },
    { match: /searching|navigate_to_portal|search_portal/i, pct: 15, label: "Searching portals…" },
    { match: /immobilienscout|immowelt|immonet|ohne-makler/i, pct: 25, label: "Reading search results…" },
    { match: /reading listing|open_listing|fetch_listing/i, pct: 40, label: "Opening listings…"  },
    { match: /missing data|flag_missing/i,            pct: 65, label: "Flagging missing data…"  },
    { match: /SAVED|save_listing/i,                   pct: 80, label: "Saving listings…"         },
    { match: /DONE|completed|run complete/i,          pct: 100, label: "Complete!"               },
  ];

  function advanceProgress(logLine) {
    for (const s of STAGES) {
      if (s.match.test(logLine) && s.pct > _pct) {
        _pct = s.pct;
        progressBar.style.width = _pct + "%";
        stageEl.textContent     = s.label;
        stageEl.className       = _pct === 100 ? "done" : "";
        break;
      }
    }
  }

  function resetProgress() {
    _pct = 0;
    progressBar.style.width = "0%";
    stageEl.textContent     = "";
    stageEl.className       = "";
    progressWrap.style.display = "none";
  }

  function showProgress() {
    progressWrap.style.display = "block";
  }

  function openModal()  { modal.classList.add("open"); }
  function closeModal() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    modal.classList.remove("open");
    logEl.style.display  = "none";
    logEl.innerHTML      = "";
    statusEl.textContent = "";
    searchBtn.disabled   = false;
    searchBtn.textContent = "Start Search";
    resetProgress();
  }

  fab.addEventListener("click", openModal);
  document.getElementById("rc-close-btn").addEventListener("click", closeModal);
  modal.addEventListener("click", e => { if (e.target === modal) closeModal(); });

  // Expose so hero/topbar buttons can open the modal without the FAB
  window._openCloudModal = openModal;

  function addLog(msg, cls = "info") {
    const line = document.createElement("div");
    line.className = cls;
    line.textContent = msg.replace(/\x1b\[[0-9;]*m/g, "");
    logEl.appendChild(line);
    logEl.scrollTop = logEl.scrollHeight;
    advanceProgress(msg);   // ← update progress bar from every log line
  }

  function setStatus(msg) { statusEl.textContent = msg; }

  async function startSearch() {
    const city   = document.getElementById("rc-city").value;
    const max    = parseInt(document.getElementById("rc-max").value) || 4;
    const budget = parseInt(document.getElementById("rc-budget").value) || 0;
    const goal   = document.getElementById("rc-goal").value.trim();

    logEl.innerHTML      = "";
    logEl.style.display  = "block";
    searchBtn.disabled   = true;
    searchBtn.textContent = "Running…";
    setStatus("");
    showProgress();
    advanceProgress("agent starting");   // kick bar to 5%

    let jobId;
    try {
      const res  = await fetch(`${RE_RADAR_API}/search`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ city, max_listings: max, budget, goal }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      jobId = data.job_id;
      addLog(`Job started — id: ${jobId}`, "ok");
      setStatus("Agent is running…");
    } catch (e) {
      addLog(`Could not start search: ${e.message}`, "err");
      setStatus("Error — is the backend running?");
      searchBtn.disabled  = false;
      searchBtn.textContent = "Start Search";
      return;
    }

    // ── Poll for progress ──────────────────────────────────────
    let lastLogLen = 0;
    pollTimer = setInterval(async () => {
      try {
        const r   = await fetch(`${RE_RADAR_API}/jobs/${jobId}`);
        const job = await r.json();

        // Stream new log lines
        const newLines = job.log.slice(lastLogLen);
        lastLogLen = job.log.length;
        newLines.forEach(l => {
          const cls = l.includes("SAVED") || l.includes("DONE") ? "ok"
                    : l.includes("ERROR") || l.includes("failed") ? "err"
                    : l.includes("Missing") ? "warn"
                    : "info";
          addLog(l, cls);
        });

        if (job.status === "completed") {
          clearInterval(pollTimer); pollTimer = null;
          // Snap bar to 100%
          _pct = 100;
          progressBar.style.width = "100%";
          stageEl.textContent = `Found ${job.listings.length} listing(s) — updating dashboard…`;
          stageEl.className   = "done";
          searchBtn.textContent = "Done ✓";
          setStatus("");
          // Brief pause so user sees 100%, then reload listings
          setTimeout(() => reloadListings(), 1400);
        } else if (job.status === "failed") {
          clearInterval(pollTimer); pollTimer = null;
          addLog(`Job failed: ${job.error}`, "err");
          stageEl.textContent = "Search failed — see log above.";
          stageEl.className   = "err";
          setStatus("");
          searchBtn.disabled   = false;
          searchBtn.textContent = "Retry";
        }
      } catch (_) { /* network blip — keep polling */ }
    }, 2500);
  }

  searchBtn.addEventListener("click", startSearch);

  // ─────────────────────────────────────────────────────────────
  //  Reload listings from API and inject into the page
  //  (falls back gracefully if the page structure is unknown)
  // ─────────────────────────────────────────────────────────────
  async function reloadListings() {
    try {
      const res  = await fetch(`${RE_RADAR_API}/listings`);
      const data = await res.json();

      // If the page exposes a global reload function, call it
      if (typeof window.reloadAgentListings === "function") {
        window.reloadAgentListings(data);
        closeModal();
        return;
      }

      // Otherwise inject into the AGENT_LISTINGS variable in the page's script
      // (works when index.html sets window.AGENT_LISTINGS or similar)
      if (typeof window.AGENT_LISTINGS !== "undefined") {
        window.AGENT_LISTINGS = data;
      }

      // Last resort: full page reload (listings are now in listings.json on the server)
      addLog("Listings updated — refreshing page…", "ok");
      setTimeout(() => window.location.reload(), 800);
      closeModal();
    } catch (e) {
      addLog(`Could not reload listings: ${e.message}`, "warn");
      setStatus("Search complete — reload the page manually to see new listings.");
      searchBtn.disabled    = false;
      searchBtn.textContent = "Start Search";
    }
  }
})();
