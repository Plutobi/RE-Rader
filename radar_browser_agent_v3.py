#!/usr/bin/env python3
"""
RE Radar — Browser Agent  v3
═══════════════════════════════════════════════════════════════════
Upgrades v2 by replacing urllib with a real Playwright browser.

Claude now INTERACTS DIRECTLY WITH PAGES:
  • Opens a real Chromium browser (visible by default)
  • Navigates to German RE portals
  • Fills in city search forms and clicks Search
  • Reads JavaScript-rendered listing results
  • Opens individual listing pages
  • Extracts contact details from rendered HTML
  • Dismisses German cookie/DSGVO banners automatically

Requirements:
    pip install anthropic python-dotenv playwright
    playwright install chromium

Usage:
    python radar_browser_agent_v3.py
    python radar_browser_agent_v3.py --city hamburg --max 3
    python radar_browser_agent_v3.py --city münchen --headless
    python radar_browser_agent_v3.py --city berlin --budget 350000
"""

import os
import re
import sys
import json
import time
import argparse
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import anthropic
except ImportError:
    print("\n  ✗  anthropic not installed.  Run:  pip install anthropic\n")
    sys.exit(1)

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("\n  ✗  playwright not installed.")
    print("     Run:  pip install playwright && playwright install chromium\n")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────
MODEL          = "claude-sonnet-4-6"
DASHBOARD_FILE = "index.html"
INQUIRY_FILE   = "inquiry_emails.md"
MAX_TOOL_CALLS = 60
PAGE_TIMEOUT   = 30_000   # ms

# ─────────────────────────────────────────────────────────────────
#  GERMAN RE CONSTANTS
# ─────────────────────────────────────────────────────────────────
GRUNDERWERBSTEUER = {
    "BB": 6.5, "BE": 6.0, "BW": 5.0, "BY": 3.5, "HB": 5.0, "HE": 6.0,
    "HH": 4.5, "MV": 6.0, "NI": 5.0, "NW": 6.5, "RP": 5.0, "SH": 6.5,
    "SL": 6.5, "SN": 3.5, "ST": 5.0, "TH": 6.5,
}
CITY_STATE = {
    "berlin": "BE", "münchen": "BY", "munich": "BY", "hamburg": "HH",
    "frankfurt": "HE", "frankfurt am main": "HE", "köln": "NW",
    "cologne": "NW", "düsseldorf": "NW", "stuttgart": "BW",
    "leipzig": "SN", "dresden": "SN", "hannover": "NI", "bremen": "HB",
    "nürnberg": "BY", "augsburg": "BY", "mainz": "RP", "freiburg": "BW",
    "bonn": "NW", "mannheim": "BW", "heidelberg": "BW", "münster": "NW",
    "dortmund": "NW", "essen": "NW", "wiesbaden": "HE", "kiel": "SH",
    "erfurt": "TH", "magdeburg": "ST", "rostock": "MV", "potsdam": "BB",
    "saarbrücken": "SL", "aachen": "NW", "karlsruhe": "BW",
}
MPB_CITIES = {
    "berlin", "münchen", "hamburg", "frankfurt am main", "köln", "düsseldorf",
    "stuttgart", "heidelberg", "freiburg", "mainz", "darmstadt", "wiesbaden",
    "bonn", "münster", "regensburg", "augsburg", "potsdam", "rostock", "kiel",
    "mannheim", "karlsruhe", "tübingen", "konstanz", "ulm", "aachen",
    "bochum", "dortmund", "essen", "leipzig", "dresden", "erfurt",
}

# ─────────────────────────────────────────────────────────────────
#  CONSOLE HELPERS
# ─────────────────────────────────────────────────────────────────
def ok(m):        print(f"  \033[32m✓\033[0m  {m}")
def info(m):      print(f"  \033[34m→\033[0m  {m}")
def warn(m):      print(f"  \033[33m⚠\033[0m  {m}")
def err(m):       print(f"  \033[31m✗\033[0m  {m}")
def agent_say(m): print(f"\n  \033[35m◆ Claude:\033[0m  {m}")
def tool_log(m):  print(f"  \033[36m⚙\033[0m  {m}")
def hdr(m):       print(f"\n\033[1m{'─'*64}\n  {m}\n{'─'*64}\033[0m")

# ─────────────────────────────────────────────────────────────────
#  CITY SLUG  (for URL construction)
# ─────────────────────────────────────────────────────────────────
def _slug(city: str) -> str:
    return (city.lower()
            .replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")
            .replace("ß", "ss").replace(" ", "-"))

# ─────────────────────────────────────────────────────────────────
#  BROWSER SESSION
# ─────────────────────────────────────────────────────────────────
class BrowserSession:
    """Wraps a Playwright browser. One tab, stateful navigation."""

    COOKIE_BUTTONS = [
        "text=Alle ablehnen",
        "text=Ablehnen",
        "text=Nur notwendige Cookies",
        "text=Nur notwendige",
        "text=Notwendige Cookies akzeptieren",
        "text=Einstellungen speichern",
        "[data-testid='uc-deny-all-button']",
        "#onetrust-reject-all-handler",
        ".cmp-btn-deny",
    ]

    def __init__(self, headless: bool = False):
        self._pw   = None
        self._br   = None
        self.page  = None
        self.headless = headless

    def start(self):
        self._pw = sync_playwright().start()
        token = os.environ.get("BROWSERLESS_TOKEN")

        if token:
            # ── Cloud: connect to Browserless.io remote Chrome ──
            info("Connecting to cloud browser (Browserless.io)…")
            endpoint = f"wss://chrome.browserless.io?token={token}"
            self._br = self._pw.chromium.connect_over_cdp(endpoint)
            # Reuse existing context if available, else create one
            if self._br.contexts:
                ctx = self._br.contexts[0]
            else:
                ctx = self._br.new_context(locale="de-DE")
            self._remote = True
        else:
            # ── Local: launch a Chromium instance ───────────────
            info(f"Launching local browser (headless={self.headless})…")
            self._br = self._pw.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = self._br.new_context(
                locale="de-DE",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            self._remote = False

        self.page = ctx.new_page()
        ok("Browser ready")

    def dismiss_cookies(self):
        """Try every known cookie-banner pattern."""
        for sel in self.COOKIE_BUTTONS:
            try:
                self.page.click(sel, timeout=2500)
                time.sleep(0.4)
                return True
            except Exception:
                continue
        return False

    def go(self, url: str) -> str:
        """Navigate and return page text."""
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
            time.sleep(1.2)
            self.dismiss_cookies()
            time.sleep(0.5)
        except PWTimeout:
            return f"TIMEOUT loading {url}"
        except Exception as e:
            return f"ERROR: {e}"
        return self._text()

    def _text(self) -> str:
        """Get visible text of current page (strips scripts/styles)."""
        try:
            return self.page.evaluate("""() => {
                const bad = ['script','style','noscript','nav','footer','header','aside'];
                bad.forEach(t => document.querySelectorAll(t)
                    .forEach(el => el.remove()));
                return (document.body?.innerText || '').substring(0, 12000);
            }""")
        except Exception:
            return ""

    def get_links(self, patterns: list[str]) -> list[str]:
        """Return all href links whose URL contains any of the patterns."""
        try:
            hrefs = self.page.evaluate("""() =>
                [...document.querySelectorAll('a[href]')]
                .map(a => a.href)
            """)
        except Exception:
            return []
        seen, out = set(), []
        for h in hrefs:
            if any(p in h for p in patterns) and h not in seen:
                seen.add(h)
                out.append(h)
        return out

    def click_text(self, text: str) -> bool:
        try:
            self.page.click(f"text={text}", timeout=5000)
            time.sleep(1.0)
            self.dismiss_cookies()
            return True
        except Exception:
            return False

    def fill_and_submit(self, selector: str, value: str) -> bool:
        try:
            self.page.fill(selector, value, timeout=5000)
            self.page.press(selector, "Enter")
            time.sleep(2.0)
            return True
        except Exception:
            return False

    def current_url(self) -> str:
        try:
            return self.page.url
        except Exception:
            return ""

    def close(self):
        try:
            if self.page:
                self.page.close()
        except Exception:
            pass
        try:
            # Don't close the remote browser — just disconnect
            if not getattr(self, "_remote", False) and self._br:
                self._br.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────────
#  PORTAL SEARCH URL BUILDERS
# ─────────────────────────────────────────────────────────────────
PORTAL_URLS = {
    "immowelt":          lambda c: f"https://www.immowelt.de/suche/{_slug(c)}/wohnungen/kaufen",
    "immobilienscout24": lambda c: f"https://www.immobilienscout24.de/Suche/de/{_slug(c)}/wohnung-kaufen.html",
    "immonet":           lambda c: f"https://www.immonet.de/wohnungssuche/select.do?city={c}&assettype=1&parentcat=1",
    "ohne-makler":       lambda c: f"https://www.ohne-makler.net/immobilien/wohnung-kaufen/{_slug(c)}/",
    "kleinanzeigen":     lambda c: f"https://www.kleinanzeigen.de/s-wohnung-kaufen/{_slug(c)}/k0c196",
}

LISTING_PATTERNS = {
    "immowelt":          ["/expose/"],
    "immobilienscout24": ["/expose/"],
    "immonet":           ["/angebot/"],
    "ohne-makler":       ["/immobilie/"],
    "kleinanzeigen":     ["/s-anzeige/"],
}

# ─────────────────────────────────────────────────────────────────
#  INQUIRY EMAIL BUILDER  (same as v2)
# ─────────────────────────────────────────────────────────────────
MISSING_FIELD_QUESTIONS = {
    "Kaltmiete":         "Was ist die aktuelle monatliche Kaltmiete (netto, ohne Nebenkosten)?",
    "Hausgeld":          "Wie hoch ist das monatliche Hausgeld? Welcher Anteil ist umlagefähig?",
    "Rücklage":          "Wie hoch ist die aktuelle Instandhaltungsrücklage (Gesamtbetrag der WEG)?",
    "Protokolle":        "Könnten Sie mir bitte die Protokolle der letzten drei Eigentümerversammlungen zusenden?",
    "Wirtschaftsplan":   "Liegt ein aktueller Wirtschaftsplan der WEG vor?",
    "Energieausweis":    "Welche Energieeffizienzklasse weist der Energieausweis aus?",
    "Baujahr":           "In welchem Jahr wurde das Gebäude errichtet?",
    "Mieter":            "Ist die Wohnung aktuell vermietet? Falls ja, wie lange läuft der Mietvertrag noch?",
    "Teilungserklärung": "Liegt die Teilungserklärung vor und kann ich diese einsehen?",
    "Betriebskosten":    "Wie hoch waren die Betriebskosten der letzten zwei Jahre?",
}


def build_inquiry_email(inq: dict) -> str:
    contact   = inq.get("contact_name", "")
    url       = inq.get("url", "")
    missing   = inq.get("missing_fields", [])
    questions = inq.get("questions") or [
        MISSING_FIELD_QUESTIONS.get(f, f"Bitte ergänzen Sie: {f}")
        for f in missing
    ]
    greeting = (
        f"Sehr geehrte/r {contact},"
        if contact and contact.lower() not in ["", "unknown", "?", "n/a"]
        else "Sehr geehrte Damen und Herren,"
    )
    q_block = "\n".join(f"  - {q}" for q in questions)
    return f"""{greeting}

ich habe Ihr Inserat unter folgendem Link gefunden und bin ernsthaft an der Immobilie interessiert:
{url}

Für eine fundierte Investitionsentscheidung benötige ich noch folgende Informationen:

{q_block}

Ich würde mich auch über einen Besichtigungstermin freuen.
Mit freundlichen Grüßen"""


def write_inquiries(inquiries: list, city: str):
    if not inquiries:
        return
    lines = [
        "# RE Radar — Draft Inquiry Emails",
        f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
        f"City: {city.capitalize()}  |  {len(inquiries)} listing(s)\n",
        "---\n",
    ]
    for i, inq in enumerate(inquiries, 1):
        name  = inq.get("listing_name", f"Listing {i}")
        url   = inq.get("url", "")
        email = inq.get("contact_email", "")
        phone = inq.get("contact_phone", "")
        miss  = inq.get("missing_fields", [])
        lines.append(f"## {i}. {name[:80]}")
        lines.append(f"\n**URL:** {url}")
        if email: lines.append(f"  \n**Email:** `{email}`")
        if phone: lines.append(f"  \n**Phone:** {phone}")
        if miss:  lines.append(f"  \n**Missing:** {', '.join(miss)}")
        lines.append("\n```")
        lines.append(build_inquiry_email(inq))
        lines.append("```\n---\n")
    with open(INQUIRY_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    ok(f"Inquiry emails → {INQUIRY_FILE}  ({len(inquiries)} drafts)")

# ─────────────────────────────────────────────────────────────────
#  LISTING BUILDER  (same schema as v2 / index.html)
# ─────────────────────────────────────────────────────────────────
def build_listing(data: dict, city: str) -> dict:
    ts    = datetime.now().isoformat()
    state = data.get("state") or CITY_STATE.get(city.lower(), "")
    grest = GRUNDERWERBSTEUER.get(state, 6.0)
    mpb   = data.get("mietpreisbremse", city.lower() in MPB_CITIES)
    cold  = data.get("coldRent", 0) or 0
    warm  = data.get("warmRent", 0) or 0
    return {
        "id":               f"llm-v3-{int(datetime.now().timestamp())}-{abs(hash(data.get('sourceUrl','x')))%9999:04d}",
        "name":             (data.get("name") or "Untitled")[:100],
        "address":          data.get("address", ""),
        "city":             data.get("city") or city.capitalize(),
        "state":            state,
        "yearBuilt":        str(data.get("yearBuilt", "")),
        "source":           f"Browser Agent v3 — {data.get('portal','?')}",
        "imageUrl":         "",
        "price":            str(int(data["price"]))  if data.get("price") else "",
        "area":             str(int(data["area"]))   if data.get("area")  else "",
        "grunderwerbsteuer": str(grest),
        "notarkosten":      "1.5",
        "maklergebuehr":    str(data.get("maklergebuehr", 0)),
        "coldRent":         str(int(cold)) if cold else "",
        "warmRent":         str(int(warm)) if warm else "",
        "rentType":         "cold" if cold else ("warm" if warm else "unknown"),
        "tenanted":         data.get("tenanted", "unknown"),
        "mietpreisbremse":  mpb,
        "hausgeld":         str(int(data["hausgeld"])) if data.get("hausgeld") else "",
        "umlagefaehig":     "65",
        "ruecklage":        str(int(data["ruecklage"])) if data.get("ruecklage") else "",
        "energy":           data.get("energy", ""),
        "spekfrist":        "0",
        "maintenanceBacklog": False,
        "notes":            data.get("notes", ""),
        "createdAt":        ts,
        "updatedAt":        ts,
    }

# ─────────────────────────────────────────────────────────────────
#  INJECT INTO DASHBOARD
# ─────────────────────────────────────────────────────────────────
def inject(listings: list, dashboard: str = DASHBOARD_FILE) -> bool:
    if not os.path.exists(dashboard):
        err(f"{dashboard} not found")
        return False
    with open(dashboard, "r", encoding="utf-8") as f:
        content = f.read()
    if "// AGENT_LISTINGS_START" not in content:
        err("AGENT_LISTINGS markers not found in index.html")
        return False
    updated = re.sub(
        r"(// AGENT_LISTINGS_START\s*const AGENT_LISTINGS = ).*?(\s*// AGENT_LISTINGS_END)",
        lambda m: m.group(1) + json.dumps(listings, indent=2, ensure_ascii=False) + m.group(2),
        content,
        flags=re.DOTALL,
    )
    with open(dashboard, "w", encoding="utf-8") as f:
        f.write(updated)
    ok(f"Injected {len(listings)} listings into {dashboard}")
    return True

# ─────────────────────────────────────────────────────────────────
#  TOOLS — Claude's browser + analysis actions
# ─────────────────────────────────────────────────────────────────
TOOLS = [
    # ── Browser: navigate to a portal's search page ───────────────
    {
        "name": "navigate_to_portal",
        "description": (
            "Open the browser and navigate to a German real estate portal's "
            "search results page for apartments for sale in a city. "
            "The browser renders JavaScript so you see real listings. "
            "Cookie banners are dismissed automatically. "
            "Returns the visible page text and the current URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "portal": {
                    "type": "string",
                    "enum": ["immowelt", "immobilienscout24", "immonet", "ohne-makler", "kleinanzeigen"],
                },
                "city": {"type": "string", "description": "German city name"},
            },
            "required": ["portal", "city"],
        },
    },
    # ── Browser: get all listing URLs from current page ───────────
    {
        "name": "extract_listing_urls",
        "description": (
            "Extract all individual listing page URLs from the current "
            "search results page in the browser. "
            "Call this after navigate_to_portal to get the list of listings to open."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "portal": {
                    "type": "string",
                    "enum": ["immowelt", "immobilienscout24", "immonet", "ohne-makler", "kleinanzeigen"],
                    "description": "Which portal is currently open (needed to match URL patterns)",
                },
            },
            "required": ["portal"],
        },
    },
    # ── Browser: open a specific listing page ─────────────────────
    {
        "name": "open_listing",
        "description": (
            "Navigate the browser to a specific listing URL and return the "
            "full visible text of the listing page. "
            "Use this to read the exposé, find price, area, rent, energy class, "
            "Hausgeld, Rücklage, contact details, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url":    {"type": "string"},
                "reason": {"type": "string", "description": "Brief reason for opening this listing"},
            },
            "required": ["url"],
        },
    },
    # ── Browser: click something on the page ──────────────────────
    {
        "name": "click_on_page",
        "description": (
            "Click on an element on the current browser page by its visible text. "
            "Use this to click 'Mehr anzeigen', pagination buttons, 'Kontakt', etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Visible text of the element to click"},
            },
            "required": ["text"],
        },
    },
    # ── Browser: read current page ────────────────────────────────
    {
        "name": "read_current_page",
        "description": "Get the full visible text of whatever page is currently open in the browser.",
        "input_schema": {"type": "object", "properties": {}},
    },
    # ── Analysis: flag missing data + queue inquiry email ─────────
    {
        "name": "flag_missing_data",
        "description": (
            "Record which investment data fields are missing from a listing "
            "and queue a draft German inquiry email. "
            "Call this for every listing you open — even ones you save."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url":            {"type": "string"},
                "listing_name":   {"type": "string"},
                "contact_name":   {"type": "string"},
                "contact_email":  {"type": "string"},
                "contact_phone":  {"type": "string"},
                "missing_fields": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Use: Kaltmiete, Hausgeld, Rücklage, Protokolle, Wirtschaftsplan, Energieausweis, Baujahr, Mieter, Grundriss, Teilungserklärung, Betriebskosten",
                },
                "questions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["url", "listing_name", "missing_fields"],
        },
    },
    # ── Analysis: save a good listing ─────────────────────────────
    {
        "name": "save_listing",
        "description": (
            "Save a property to the RE Radar dashboard after reading its full page. "
            "Write complete investment reasoning in notes: gross yield, net yield, "
            "Rücklage risk, energy cost risk, Mietpreisbremse impact, verdict."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name":            {"type": "string"},
                "address":         {"type": "string"},
                "city":            {"type": "string"},
                "state":           {"type": "string"},
                "portal":          {"type": "string"},
                "price":           {"type": "number"},
                "area":            {"type": "number"},
                "rooms":           {"type": "number"},
                "yearBuilt":       {"type": "string"},
                "coldRent":        {"type": "number"},
                "warmRent":        {"type": "number"},
                "hausgeld":        {"type": "number"},
                "energy":          {"type": "string"},
                "tenanted":        {"type": "string", "enum": ["yes", "no", "unknown"]},
                "maklergebuehr":   {"type": "number"},
                "ruecklage":       {"type": "number"},
                "mietpreisbremse": {"type": "boolean"},
                "notes":           {"type": "string"},
                "sourceUrl":       {"type": "string"},
            },
            "required": ["name", "price", "area", "city"],
        },
    },
    # ── Wrap-up ───────────────────────────────────────────────────
    {
        "name": "done",
        "description": (
            "End the session. Call after searching ≥2 portals, "
            "opening ≥6 listing pages, saving the best properties, "
            "and flagging missing data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary":          {"type": "string"},
                "top_pick":         {"type": "string"},
                "listings_saved":   {"type": "integer"},
                "portals_searched": {"type": "array", "items": {"type": "string"}},
                "total_reviewed":   {"type": "integer"},
            },
            "required": ["summary", "listings_saved"],
        },
    },
]

# ─────────────────────────────────────────────────────────────────
#  AGENT LOOP
# ─────────────────────────────────────────────────────────────────
def run_agent(goal: str, city: str, max_save: int, budget: int, headless: bool):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        err("ANTHROPIC_API_KEY not set. Add it to a .env file.")
        sys.exit(1)

    client = anthropic.Anthropic(
        api_key=api_key,
        base_url="https://api.anthropic.com",
        default_headers={"anthropic-version": "2023-06-01"},
    )

    state   = CITY_STATE.get(city.lower(), "")
    grest   = GRUNDERWERBSTEUER.get(state, 6.0)
    mpb     = city.lower() in MPB_CITIES
    bclause = f"\nMaximum purchase budget: €{budget:,}." if budget else ""

    system = f"""You are an expert German real estate investment agent.
You control a REAL BROWSER — you can navigate to websites, see their rendered content,
click buttons, and interact with pages exactly as a human investor would.

YOUR GOAL: {goal}
{bclause}

══════════ BROWSER-FIRST WORKFLOW ══════════

Step 1 — SEARCH PORTALS (use navigate_to_portal)
  Open at least 2 portals. Start with immowelt, then immobilienscout24.
  After each portal loads, call extract_listing_urls to get the listings.
  Cookie banners are dismissed automatically — no need to handle them.

Step 2 — OPEN LISTINGS (use open_listing)
  Open each listing URL individually. Read the full page text.
  Look for: Kaufpreis, Wohnfläche, Zimmer, Baujahr, Energieeffizienzklasse,
  Hausgeld, Kaltmiete, Warmmiete, Rücklage, Mieterstatus, Kontaktdaten.
  Use click_on_page if you need to expand sections ("Mehr anzeigen", "Kontakt").

Step 3 — FLAG MISSING DATA (use flag_missing_data)
  For every listing with missing investment data, queue an inquiry email.
  Even for listings you save — investors always request WEG documents.

Step 4 — ANALYSE (read with full comprehension)
  "Provisionsfrei" = no agent fee. "Vermietet" = tenanted.
  "Kaltmiete" is the yield basis. Yield = (Kalt × 12) / Kaufpreis × 100.
  "WEG" = owners' association. "Rücklage" = maintenance reserve.

Step 5 — IDENTIFY GAPS
  Complete listing = price + area + rent + Hausgeld + Rücklage + energy + Baujahr + tenancy.
  Missing 3+ = "data-poor" listing.

Step 6 — DECIDE & SAVE (use save_listing)
  Bundesland: {state} | Grunderwerbsteuer: {grest}%
  Mietpreisbremse in {city.capitalize()}: {'YES' if mpb else 'NO'}
  Total acq. cost = price × (1 + ({grest} + 1.5 + Makler%) / 100)
  Gross yield target ≥ 4%. Energy F/G/H = EU renovation risk.
  Rücklage < €15/m² building area = Sonderumlage risk.

  Save up to {max_save} listings meeting ≥3 of:
    ✓ Gross yield ≥ 3.5%     ✓ Energy class A–D
    ✓ Rücklage present       ✓ Tenancy status known    ✓ Price clear
  Write full investment reasoning in notes.

════════════════════════════════════════════

Call done() when finished with full summary and top recommendation."""

    # Start browser
    session = BrowserSession(headless=headless)
    session.start()

    messages        = [{"role": "user", "content": goal}]
    saved_listings  = []
    inquiries       = []
    calls           = 0
    finished        = False

    hdr(f"RE RADAR  BROWSER AGENT v3  ·  {city.capitalize()}  ·  {MODEL}")
    info(f"Browser: {'headless' if headless else 'visible'}")
    agent_say(f"Starting: {goal}")

    try:
        while calls < MAX_TOOL_CALLS and not finished:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=system,
                tools=TOOLS,
                messages=messages,
            )

            for block in response.content:
                if hasattr(block, "text") and block.text.strip():
                    agent_say(block.text.strip()[:400])

            if response.stop_reason in ("end_turn", "stop_sequence"):
                break
            if response.stop_reason != "tool_use":
                warn(f"Unexpected stop_reason: {response.stop_reason}")
                break

            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue
                calls += 1
                name = block.name
                inp  = block.input

                # ── navigate_to_portal ─────────────────────────
                if name == "navigate_to_portal":
                    portal = inp["portal"]
                    c      = inp.get("city", city)
                    url    = PORTAL_URLS.get(portal, lambda x: "")(c)
                    tool_log(f"navigate_to_portal({portal}, {c})")
                    tool_log(f"  → {url}")
                    text = session.go(url)
                    snippet = text[:300].replace("\n", " ")
                    ok(f"  Page loaded — {len(text)} chars  |  url: {session.current_url()[-60:]}")
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": (
                            f"URL: {session.current_url()}\n\n"
                            f"PAGE TEXT (first 3000 chars):\n{text[:3000]}"
                        ),
                    })

                # ── extract_listing_urls ───────────────────────
                elif name == "extract_listing_urls":
                    portal   = inp.get("portal", "immowelt")
                    patterns = LISTING_PATTERNS.get(portal, ["/expose/"])
                    urls     = session.get_links(patterns)
                    tool_log(f"extract_listing_urls({portal}) → {len(urls)} URLs")
                    if urls:
                        ok(f"  Found {len(urls)} listing URLs")
                    else:
                        warn("  No listing URLs found — portal may have blocked or changed layout")
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": json.dumps({
                            "portal": portal,
                            "count":  len(urls),
                            "urls":   urls[:20],
                        }),
                    })

                # ── open_listing ───────────────────────────────
                elif name == "open_listing":
                    url    = inp["url"]
                    reason = inp.get("reason", "")
                    tool_log(f"open_listing  {url[-70:]}")
                    if reason:
                        info(f"  {reason}")
                    text = session.go(url)
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": (
                            f"URL: {session.current_url()}\n\n"
                            f"LISTING PAGE TEXT:\n{text[:9000]}"
                        ),
                    })

                # ── click_on_page ──────────────────────────────
                elif name == "click_on_page":
                    text_to_click = inp.get("text", "")
                    tool_log(f"click_on_page('{text_to_click}')")
                    success = session.click_text(text_to_click)
                    result  = "Clicked successfully." if success else "Element not found or not clickable."
                    if success:
                        result += f"\n\nPAGE AFTER CLICK:\n{session._text()[:4000]}"
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": result,
                    })

                # ── read_current_page ──────────────────────────
                elif name == "read_current_page":
                    tool_log("read_current_page()")
                    text = session._text()
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": f"URL: {session.current_url()}\n\n{text[:9000]}",
                    })

                # ── flag_missing_data ──────────────────────────
                elif name == "flag_missing_data":
                    lname   = inp.get("listing_name", "?")
                    missing = inp.get("missing_fields", [])
                    warn(f"Missing data: {lname[:55]}")
                    if missing:
                        warn(f"  Fields: {', '.join(missing)}")
                    inquiries.append(inp)
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": f"Inquiry queued for '{lname}'. Missing: {', '.join(missing)}.",
                    })

                # ── save_listing ───────────────────────────────
                elif name == "save_listing":
                    listing = build_listing(inp, city)
                    saved_listings.append(listing)
                    price = inp.get("price", 0) or 0
                    cold  = inp.get("coldRent", 0) or 0
                    gy    = (cold * 12 / price * 100) if price and cold else 0
                    line  = (
                        f"Saved [{len(saved_listings)}]: "
                        f"{inp.get('name','?')[:50]}  €{price:,.0f}"
                    )
                    if gy:
                        line += f"  GY {gy:.1f}%"
                    ok(line)
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": f"Saved. Total: {len(saved_listings)}.",
                    })

                # ── done ───────────────────────────────────────
                elif name == "done":
                    summary  = inp.get("summary", "")
                    top      = inp.get("top_pick", "")
                    portals  = inp.get("portals_searched", [])
                    reviewed = inp.get("total_reviewed", "?")
                    print()
                    hdr("AGENT SUMMARY")
                    if portals:
                        print(f"  Portals searched:  {', '.join(portals)}")
                    print(f"  Pages reviewed:    {reviewed}")
                    print(f"  Listings saved:    {len(saved_listings)}")
                    print(f"  Inquiry emails:    {len(inquiries)}")
                    print(f"\n  {summary}\n")
                    if top:
                        print(f"  \033[32mTop pick:\033[0m {top}\n")
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": "Session complete.",
                    })
                    finished = True

            messages.append({"role": "assistant", "content": response.content})
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

    finally:
        session.close()
        ok("Browser closed")

    if calls >= MAX_TOOL_CALLS:
        warn(f"Reached tool-call limit ({MAX_TOOL_CALLS}).")

    return saved_listings, inquiries

# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="RE Radar Browser Agent v3 — Claude controls a real browser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python radar_browser_agent_v3.py
  python radar_browser_agent_v3.py --city hamburg --max 3
  python radar_browser_agent_v3.py --city münchen --budget 400000
  python radar_browser_agent_v3.py --city berlin --headless
        """,
    )
    parser.add_argument("--city",      default="berlin",        help="City to search")
    parser.add_argument("--max",       type=int, default=4,     help="Max listings to save")
    parser.add_argument("--budget",    type=int, default=0,     help="Max price EUR")
    parser.add_argument("--goal",      default="",              help="Custom goal")
    parser.add_argument("--headless",  action="store_true",     help="Run browser in background (no window)")
    parser.add_argument("--dashboard", default=DASHBOARD_FILE,  help="Path to index.html")
    args = parser.parse_args()

    city   = args.city.lower().strip()
    budget = args.budget
    bstr   = f" under €{budget:,}" if budget else ""

    goal = args.goal or (
        f"Find {args.max} investment apartments in {city.capitalize()}{bstr}. "
        f"Search immowelt and immobilienscout24 using the real browser. "
        f"For each listing: open the full page, read the exposé, flag missing data, "
        f"and save the best properties with complete investment reasoning. "
        f"Prioritise: Kaltmiete data present, energy class B or better, "
        f"Rücklage disclosed, provisionsfrei preferred."
    )

    saved, inquiries = run_agent(goal, city, args.max, budget, args.headless)

    print()
    if saved:
        inject(saved, args.dashboard)
        info(f"Open {args.dashboard} — {len(saved)} new listings.")
    else:
        warn("No listings saved. Try a different city.")

    if inquiries:
        write_inquiries(inquiries, city)
        info(f"Open {INQUIRY_FILE} — {len(inquiries)} draft emails.")

    print()
    info(f"Run complete. Saved: {len(saved)}  |  Inquiries: {len(inquiries)}")


if __name__ == "__main__":
    main()
