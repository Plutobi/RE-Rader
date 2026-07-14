// RE Radar — Dashboard Sync Content Script
// Runs on plutobi.github.io/RE-Rader when the tab loads.
// Pulls listings from chrome.storage.local and merges them into
// the page's localStorage so the dashboard can display them.

(function () {
  const STORAGE_KEY = 're_radar_v3';

  chrome.storage.local.get('re_radar_listings', ({ re_radar_listings }) => {
    if (!re_radar_listings || !re_radar_listings.length) return;

    // Read what the dashboard already has
    let existing = [];
    try { existing = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); } catch (_) {}

    // Merge — skip any IDs already present
    const existingIds = new Set(existing.map((l) => l.id).filter(Boolean));
    const fresh = re_radar_listings.filter((l) => l.id && !existingIds.has(l.id));

    if (!fresh.length) return; // nothing new — don't touch the page

    const merged = [...existing, ...fresh].slice(-300);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));

    // Reload so the dashboard reads the updated localStorage on startup.
    // On second load fresh.length === 0 so no infinite loop.
    window.location.reload();
  });
})();
