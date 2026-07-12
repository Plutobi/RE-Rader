#!/usr/bin/env python3
"""
RE Radar — Full LLM Investment Agent  v2
═══════════════════════════════════════════════════════════════════
Mirrors the 6-step manual process from the project brief:

  1. Search multiple portals     → search_portal tool
  2. Open individual listings    → fetch_listing tool
  3. Contact agents / inquiries  → flag_missing_data tool → inquiry_emails.md
  4. Read exposés                → Claude reads with LLM comprehension
  5. Identify missing info       → structured checklist per listing
  6. Decide financial quality    → score + reasoning → save_listing tool

Results  → injected into index.html  (same AGENT_LISTINGS markers)
Emails   → written to inquiry_emails.md (ready to copy-send)

Requirements:
    pip install anthropic python-dotenv

    API key — choose one approach (never hardcode it):
      Option A: .env file in the project folder (recommended)
                Copy .env.example to .env and fill in your key.
      Option B: Environment variable
                Windows CMD:  set ANTHROPIC_API_KEY=sk-ant-...
                Mac / Linux:  export ANTHROPIC_API_KEY=sk-ant-...

Usage:
    python radar_llm_agent_v2.py
    python radar_llm_agent_v2.py --city hamburg --max 3
    python radar_llm_agent_v2.py --city münchen --budget 450000
    python radar_llm_agent_v2.py --goal "Find 3 provisionsfrei apartments in Berlin under 400k with verified Kaltmiete"
"""

import os
import re
import sys
import json
import time
import argparse
import urllib.request
import urllib.parse
from datetime import datetime

# Load variables from a .env file if present.
# python-dotenv is optional — falls back to system environment variables.
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

# ─────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────
MODEL          = "claude-sonnet-4-6"
DASHBOARD_FILE = "index.html"
INQUIRY_FILE   = "inquiry_emails.md"
REQUEST_DELAY  = 1.2        # seconds between HTTP requests
MAX_TOOL_CALLS = 45         # safety ceiling for the agent loop
USER_AGENT     = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

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
    "stuttgart", "heidelberg", "freiburg", "freiburg im breisgau", "mainz",
    "darmstadt", "wiesbaden", "bonn", "münster", "regensburg", "augsburg",
    "ingolstadt", "würzburg", "erlangen", "potsdam", "rostock", "kiel",
    "mannheim", "karlsruhe", "tübingen", "konstanz", "ulm", "aachen",
    "bochum", "dortmund", "essen", "krefeld", "leipzig", "dresden", "erfurt",
}

# ─────────────────────────────────────────────────────────────────
#  CONSOLE HELPERS
# ─────────────────────────────────────────────────────────────────
def ok(msg):        print(f"  \033[32m✓\033[0m  {msg}")
def info(msg):      print(f"  \033[34m→\033[0m  {msg}")
def warn(msg):      print(f"  \033[33m⚠\033[0m  {msg}")
def err(msg):       print(f"  \033[31m✗\033[0m  {msg}")
def agent_say(msg): print(f"\n  \033[35m◆ Claude:\033[0m  {msg}")
def tool_log(msg):  print(f"  \033[36m⚙\033[0m  {msg}")
def hdr(msg):       print(f"\n\033[1m{'─'*64}\n  {msg}\n{'─'*64}\033[0m")

# ─────────────────────────────────────────────────────────────────
#  HTTP — fetch + parse
# ─────────────────────────────────────────────────────────────────
def _fetch_raw(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent":      USER_AGENT,
        "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Cache-Control":   "no-cache",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return f"__ERROR__ {e}"


def _html_to_text(html: str) -> str:
    """Strip HTML to readable plain text."""
    for tag in ["script", "style", "nav", "footer", "header", "aside", "noscript"]:
        html = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", " ", html,
                      flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    for entity, char in [
        ("&nbsp;", " "), ("&amp;", "&"), ("&euro;", "€"), ("&#8364;", "€"),
        ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"),
    ]:
        text = text.replace(entity, char)
    return re.sub(r"\s+", " ", text).strip()


def _extract_listing_links(html: str, base: str, patterns: list) -> list:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
    seen, result = set(), []
    for h in hrefs:
        full = h if h.startswith("http") else urllib.parse.urljoin(base, h)
        if any(p in full for p in patterns) and full not in seen:
            seen.add(full)
            result.append(full)
    return result


def _extract_contact(html: str) -> dict:
    contact = {}
    email_m = re.search(r'[\w.+\-]+@[\w.\-]+\.[a-zA-Z]{2,6}', html)
    phone_m = re.search(r'(\+49[\s\-]?|0)[\d][\d\s\-/]{7,}', html)
    name_m  = re.search(
        r'(?:Ansprechpartner|Makler|Kontakt|Anbieter)[:\s]*([A-ZÄÖÜ][a-zäöüß]+'
        r'(?:\s[A-ZÄÖÜ][a-zäöüß]+)+)',
        html
    )
    if email_m: contact["email"] = email_m.group(0)
    if phone_m: contact["phone"] = phone_m.group(0).strip()
    if name_m:  contact["name"]  = name_m.group(1).strip()
    return contact

# ─────────────────────────────────────────────────────────────────
#  STEP 1 — PORTAL SEARCH
#  Each portal config defines how to build the search URL and
#  which URL substrings identify a listing (not a generic page).
# ─────────────────────────────────────────────────────────────────
def _city_slug(city: str) -> str:
    return (city.lower()
            .replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")
            .replace("ß", "ss").replace(" ", "-"))

PORTAL_CONFIGS = {
    "ohne-makler": {
        "url": lambda c, p: (
            f"https://www.ohne-makler.net/immobilien/wohnung-kaufen/{_city_slug(c)}/"
            + (f"?seite={p}" if p > 1 else "")
        ),
        "base":     "https://www.ohne-makler.net",
        "patterns": ["/immobilie/"],
    },
    "immowelt": {
        "url": lambda c, p: (
            f"https://www.immowelt.de/suche/{_city_slug(c)}/wohnungen/kaufen"
            + (f"?cp={p}" if p > 1 else "")
        ),
        "base":     "https://www.immowelt.de",
        "patterns": ["/expose/"],
    },
    "immonet": {
        "url": lambda c, p: (
            f"https://www.immonet.de/immobiliensuche/sel.do"
            f"?objecttype=1&listsize=20&parentcat=1&suchart=1"
            f"&city={urllib.parse.quote(c)}&page={p}"
        ),
        "base":     "https://www.immonet.de",
        "patterns": ["/angebot/"],
    },
    "ebay-kleinanzeigen": {
        "url": lambda c, p: (
            f"https://www.kleinanzeigen.de/s-wohnung-kaufen/{_city_slug(c)}/k0c196"
        ),
        "base":     "https://www.kleinanzeigen.de",
        "patterns": ["/s-anzeige/"],
    },
}


def portal_search(portal: str, city: str, page: int = 1) -> dict:
    """Fetch a portal search page and return all listing URLs found."""
    cfg = PORTAL_CONFIGS.get(portal)
    if not cfg:
        return {"error": f"Unknown portal '{portal}'", "urls": []}

    url = cfg["url"](city, page)
    time.sleep(REQUEST_DELAY)
    html = _fetch_raw(url)

    if html.startswith("__ERROR__"):
        return {"portal": portal, "error": html, "urls": [], "search_url": url}

    urls = _extract_listing_links(html, cfg["base"], cfg["patterns"])
    return {
        "portal":       portal,
        "city":         city,
        "search_url":   url,
        "listing_count": len(urls),
        "urls":         urls[:25],          # cap at 25 per page
    }

# ─────────────────────────────────────────────────────────────────
#  STEP 2 — OPEN INDIVIDUAL LISTINGS
# ─────────────────────────────────────────────────────────────────
def fetch_listing(url: str) -> str:
    """Fetch a listing page and return plain text + any contact info found."""
    time.sleep(REQUEST_DELAY)
    html = _fetch_raw(url)

    if html.startswith("__ERROR__"):
        return f"ERROR fetching {url}: {html}"

    contact = _extract_contact(html)
    text    = _html_to_text(html)

    result = f"URL: {url}\n\n"
    if contact:
        result += "CONTACT DETAILS FOUND ON PAGE:\n"
        for k, v in contact.items():
            result += f"  {k}: {v}\n"
        result += "\n"
    result += f"FULL LISTING TEXT:\n{text[:10000]}"
    return result

# ─────────────────────────────────────────────────────────────────
#  STEP 3 — INQUIRY EMAIL GENERATOR
#  Called when Claude flags missing data. Generates a professional
#  German email the user can copy and send to the agent/owner.
# ─────────────────────────────────────────────────────────────────
MISSING_FIELD_QUESTIONS = {
    "Kaltmiete":      "Was ist die aktuelle monatliche Kaltmiete (netto, ohne Nebenkosten)?",
    "Warmmiete":      "Wie hoch ist die monatliche Warmmiete inkl. Nebenkosten?",
    "Hausgeld":       "Wie hoch ist das monatliche Hausgeld? Welcher Anteil ist umlagefähig?",
    "Rücklage":       "Wie hoch ist die aktuelle Instandhaltungsrücklage (Gesamtbetrag der WEG)?",
    "Protokolle":     "Könnten Sie mir bitte die Protokolle der letzten drei Eigentümerversammlungen zusenden?",
    "Wirtschaftsplan":"Liegt ein aktueller Wirtschaftsplan der WEG vor?",
    "Energieausweis": "Welche Energieeffizienzklasse weist der Energieausweis aus?",
    "Baujahr":        "In welchem Jahr wurde das Gebäude errichtet?",
    "Mieter":         "Ist die Wohnung aktuell vermietet? Falls ja, wie lange läuft der Mietvertrag noch?",
    "Grundriss":      "Könnten Sie mir bitte den Grundriss zusenden?",
    "Teilungserklärung": "Liegt die Teilungserklärung vor und kann ich diese einsehen?",
    "Betriebskosten": "Wie hoch waren die Betriebskosten-Nebenkostenabrechnungen der letzten zwei Jahre?",
}


def build_inquiry_email(inq: dict) -> str:
    contact   = inq.get("contact_name", "")
    url       = inq.get("url", "")
    missing   = inq.get("missing_fields", [])
    questions = inq.get("questions") or []

    greeting = (
        f"Sehr geehrte/r {contact},"
        if contact and contact.lower() not in ["", "unknown", "?", "n/a"]
        else "Sehr geehrte Damen und Herren,"
    )

    if not questions:
        questions = [
            MISSING_FIELD_QUESTIONS.get(f, f"Bitte ergänzen Sie die Angabe zu: {f}")
            for f in missing
        ]

    q_block = "\n".join(f"  - {q}" for q in questions)

    return f"""{greeting}

ich habe Ihr Inserat unter folgendem Link gefunden und bin ernsthaft an der Immobilie interessiert:
{url}

Für eine fundierte Investitionsentscheidung benötige ich noch folgende Informationen:

{q_block}

Ich würde mich auch über einen Besichtigungstermin freuen, sobald die obigen Punkte geklärt sind.
Für Rückfragen stehe ich jederzeit zur Verfügung.

Mit freundlichen Grüßen"""


def write_inquiries(inquiries: list, city: str):
    """Write all inquiry emails to inquiry_emails.md."""
    if not inquiries:
        return

    lines = [
        "# RE Radar — Draft Inquiry Emails",
        f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
        f"City: {city.capitalize()}  |  {len(inquiries)} listing(s)\n",
        "> Copy each email block, paste into your email client, "
        "add your name, and send.\n",
        "---\n",
    ]

    for i, inq in enumerate(inquiries, 1):
        name  = inq.get("listing_name", f"Listing {i}")
        url   = inq.get("url", "")
        email = inq.get("contact_email", "")
        phone = inq.get("contact_phone", "")
        miss  = inq.get("missing_fields", [])

        lines.append(f"## {i}. {name[:80]}")
        lines.append(f"\n**Listing URL:** {url}")
        if email: lines.append(f"  \n**Agent email:** `{email}`")
        if phone: lines.append(f"  \n**Phone:** {phone}")
        if miss:  lines.append(f"  \n**Missing data:** {', '.join(miss)}")
        lines.append("\n**Draft email:**\n")
        lines.append("```")
        lines.append(build_inquiry_email(inq))
        lines.append("```\n")
        lines.append("---\n")

    with open(INQUIRY_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    ok(f"Inquiry emails → {INQUIRY_FILE}  ({len(inquiries)} drafts)")

# ─────────────────────────────────────────────────────────────────
#  STEPS 4–6 — Claude handles via the agent loop
#  build_listing() converts Claude's save_listing call to the
#  exact schema RE Radar's index.html expects.
# ─────────────────────────────────────────────────────────────────
def build_listing(data: dict, city: str) -> dict:
    ts    = datetime.now().isoformat()
    state = data.get("state") or CITY_STATE.get(city.lower(), "")
    grest = GRUNDERWERBSTEUER.get(state, 6.0)
    mpb   = data.get("mietpreisbremse", city.lower() in MPB_CITIES)
    cold  = data.get("coldRent", 0) or 0
    warm  = data.get("warmRent", 0) or 0
    rent_type = "cold" if cold > 0 else ("warm" if warm > 0 else "unknown")

    return {
        "id":               (
            f"llm-v2-{int(datetime.now().timestamp())}"
            f"-{abs(hash(data.get('sourceUrl', 'x'))) % 9999:04d}"
        ),
        "name":             (data.get("name") or "Untitled")[:100],
        "address":          data.get("address", ""),
        "city":             data.get("city") or city.capitalize(),
        "state":            state,
        "yearBuilt":        str(data.get("yearBuilt", "")) if data.get("yearBuilt") else "",
        "source":           f"LLM Agent — {data.get('portal') or 'unknown portal'}",
        "imageUrl":         "",
        "price":            str(int(data["price"]))   if data.get("price") else "",
        "area":             str(int(data["area"]))    if data.get("area")  else "",
        "grunderwerbsteuer": str(grest),
        "notarkosten":      "1.5",
        "maklergebuehr":    str(data.get("maklergebuehr", 0)),
        "coldRent":         str(int(cold)) if cold > 0 else "",
        "warmRent":         str(int(warm)) if warm > 0 else "",
        "rentType":         rent_type,
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
        err(f"{dashboard} not found — run from the same folder as index.html")
        return False
    with open(dashboard, "r", encoding="utf-8") as f:
        content = f.read()
    if "// AGENT_LISTINGS_START" not in content:
        err("AGENT_LISTINGS markers not found in index.html")
        return False
    pattern = (
        r"(// AGENT_LISTINGS_START\s*const AGENT_LISTINGS = )"
        r".*?"
        r"(\s*// AGENT_LISTINGS_END)"
    )
    updated = re.sub(
        pattern,
        lambda m: m.group(1) + json.dumps(listings, indent=2, ensure_ascii=False) + m.group(2),
        content,
        flags=re.DOTALL,
    )
    with open(dashboard, "w", encoding="utf-8") as f:
        f.write(updated)
    ok(f"Injected {len(listings)} listings into {dashboard}")
    return True

# ─────────────────────────────────────────────────────────────────
#  TOOL DEFINITIONS
#  These are exactly the 6-step actions a human investor takes.
# ─────────────────────────────────────────────────────────────────
TOOLS = [
    # ── Step 1: search multiple portals ───────────────────────────
    {
        "name": "search_portal",
        "description": (
            "Search a German real estate portal for apartments for sale in a city. "
            "Returns a list of listing URLs from the search results page. "
            "Always search at least 2 different portals before analysing individual listings. "
            "Prefer 'ohne-makler' (commission-free) and 'immowelt'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "portal": {
                    "type": "string",
                    "enum": ["ohne-makler", "immowelt", "immonet", "ebay-kleinanzeigen"],
                    "description": "Which portal to search",
                },
                "city": {
                    "type": "string",
                    "description": "German city name, e.g. 'Berlin' or 'Hamburg'",
                },
                "page": {
                    "type": "integer",
                    "description": "Results page number, default 1",
                },
            },
            "required": ["portal", "city"],
        },
    },
    # ── Step 2: open a listing page ───────────────────────────────
    {
        "name": "fetch_listing",
        "description": (
            "Open a single listing URL and return its full readable text plus any "
            "contact details found on the page. "
            "Read the result carefully to extract all property data and "
            "identify what information is missing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url":    {"type": "string", "description": "Full listing URL"},
                "reason": {"type": "string", "description": "Brief reason for fetching"},
            },
            "required": ["url"],
        },
    },
    # ── Step 3: flag missing info + queue inquiry email ────────────
    {
        "name": "flag_missing_data",
        "description": (
            "Record which data fields are absent or unclear in a listing, and "
            "store the contact details so an inquiry email can be drafted. "
            "Call this for EVERY listing you read — even listings you save — "
            "whenever key investment data is missing. "
            "A draft German email will be generated automatically and saved "
            "to inquiry_emails.md for the user to send."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url":           {"type": "string"},
                "listing_name":  {"type": "string", "description": "Title of the listing"},
                "contact_name":  {"type": "string", "description": "Agent or owner name if found"},
                "contact_email": {"type": "string", "description": "Email address if found"},
                "contact_phone": {"type": "string", "description": "Phone number if found"},
                "missing_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of missing data fields. Use these exact names where possible: "
                        "Kaltmiete, Warmmiete, Hausgeld, Rücklage, Protokolle, "
                        "Wirtschaftsplan, Energieausweis, Baujahr, Mieter, Grundriss, "
                        "Teilungserklärung, Betriebskosten"
                    ),
                },
                "questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional: custom German-language questions to ask. "
                        "If omitted, standard questions are generated from missing_fields."
                    ),
                },
            },
            "required": ["url", "listing_name", "missing_fields"],
        },
    },
    # ── Steps 4–6: analyse and save ───────────────────────────────
    {
        "name": "save_listing",
        "description": (
            "Save a property to the RE Radar dashboard after reading and analysing "
            "the full exposé. "
            "Only call this when you have: confirmed the price, area, and at least "
            "attempted to find rent/yield data. "
            "Write your complete investment reasoning (yield calc, risk flags, "
            "Rücklage assessment, energy risk, Mietpreisbremse impact) in notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name":            {"type": "string", "description": "Property title"},
                "address":         {"type": "string"},
                "city":            {"type": "string"},
                "state":           {"type": "string", "description": "Bundesland code, e.g. BE, BY, HH"},
                "portal":          {"type": "string", "description": "Source portal name"},
                "price":           {"type": "number", "description": "Purchase price EUR"},
                "area":            {"type": "number", "description": "Living area m²"},
                "rooms":           {"type": "number"},
                "yearBuilt":       {"type": "string"},
                "coldRent":        {"type": "number", "description": "Monthly Kaltmiete EUR"},
                "warmRent":        {"type": "number", "description": "Monthly Warmmiete EUR"},
                "hausgeld":        {"type": "number", "description": "Monthly Hausgeld EUR"},
                "energy":          {"type": "string", "description": "Energy class A+–H"},
                "tenanted":        {
                    "type": "string",
                    "enum": ["yes", "no", "unknown"],
                    "description": "Is the apartment currently rented out?",
                },
                "maklergebuehr":   {"type": "number", "description": "Agent fee % (0 = provisionsfrei)"},
                "ruecklage":       {"type": "number", "description": "Total Instandhaltungsrücklage EUR"},
                "mietpreisbremse": {"type": "boolean"},
                "notes":           {
                    "type": "string",
                    "description": (
                        "Your full investment reasoning: gross yield, net yield estimate, "
                        "risk flags spotted, Rücklage sufficiency, energy cost risk, "
                        "Mietpreisbremse impact, overall verdict."
                    ),
                },
                "sourceUrl": {"type": "string"},
            },
            "required": ["name", "price", "area", "city"],
        },
    },
    # ── Wrap up ───────────────────────────────────────────────────
    {
        "name": "done",
        "description": (
            "End the search session. Call this after you have searched at least "
            "2 portals, read at least 6 listings, saved the best ones, and "
            "flagged missing data for all shortlisted properties."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary":          {"type": "string", "description": "What you found overall"},
                "top_pick":         {"type": "string", "description": "Your top recommendation and why"},
                "listings_saved":   {"type": "integer"},
                "portals_searched": {"type": "array", "items": {"type": "string"}},
                "total_reviewed":   {"type": "integer", "description": "Total listing pages you read"},
            },
            "required": ["summary", "listings_saved"],
        },
    },
]

# ─────────────────────────────────────────────────────────────────
#  AGENT LOOP
# ─────────────────────────────────────────────────────────────────
def run_agent(goal: str, city: str, max_save: int, budget: int):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        err("ANTHROPIC_API_KEY not found.")
        err("Add it to a .env file in this folder:")
        err("  ANTHROPIC_API_KEY=sk-ant-api03-...")
        err("(Copy .env.example to .env and fill in your key.)")
        sys.exit(1)

    client = anthropic.Anthropic(
        api_key=api_key,
        base_url="https://api.anthropic.com",
        default_headers={"anthropic-version": "2023-06-01"},
    )

    state  = CITY_STATE.get(city.lower(), "")
    grest  = GRUNDERWERBSTEUER.get(state, 6.0)
    mpb    = city.lower() in MPB_CITIES
    bclause = f"\nMaximum purchase budget: €{budget:,}." if budget else ""

    system = f"""You are an expert German real estate investment agent.
You conduct property searches on behalf of a buyer, following exactly the same
steps a professional investor would take manually.

YOUR GOAL: {goal}
{bclause}

══════════ THE 6-STEP WORKFLOW YOU MUST FOLLOW ══════════

Step 1 — SEARCH MULTIPLE PORTALS
  Call search_portal for at least 2 portals (start with ohne-makler, then immowelt).
  Collect all listing URLs before opening any individual listings.

Step 2 — OPEN EACH LISTING
  Call fetch_listing on each URL. Read the returned text carefully.
  Look for: Kaufpreis, Wohnfläche, Zimmer, Baujahr, Energieeffizienzklasse,
  Hausgeld, Kaltmiete, Warmmiete, Rücklage, tenancy status, contact details,
  Makler/Provision info.

Step 3 — FLAG MISSING DATA
  For every listing where key investment data is absent, call flag_missing_data.
  This creates a draft German inquiry email the user can send to the agent/owner.
  Flag missing: Kaltmiete, Warmmiete, Hausgeld, Rücklage, Energieausweis,
  Baujahr, Mieter status, Protokolle, Wirtschaftsplan, Grundriss.
  Call flag_missing_data even for listings you SAVE — investors always request
  documents even after deciding to proceed.

Step 4 — READ EXPOSÉS WITH FULL COMPREHENSION
  You are reading German text. Understand context, not just patterns.
  "Provisionsfrei" means no Makler fee. "Vermietet" means tenanted.
  "Kaltmiete" is the rent basis for yield. "Warmmiete" includes ancillaries.
  "WEG" = Wohnungseigentümergemeinschaft (owners' association).

Step 5 — IDENTIFY MISSING INFORMATION
  After reading each listing, summarise what is present and what is absent.
  A complete listing has: price, area, rent (Kalt or Warm), Hausgeld, Rücklage,
  energy class, Baujahr, tenancy status.
  A listing missing 3+ of these fields is a "data-poor" listing.

Step 6 — DECIDE FINANCIAL ATTRACTIVENESS
  Apply German RE investment criteria:
  - Bundesland: {state}  |  Grunderwerbsteuer: {grest}%
  - Mietpreisbremse applies in {city.capitalize()}: {'YES' if mpb else 'NO'}
  - Yield basis: ALWAYS Kaltmiete. If only Warmmiete: estimate Kalt ≈ Warm × 0.82
  - Gross yield = (Kaltmiete × 12) / Kaufpreis × 100  →  target ≥ 4%
  - Net yield = (annual Kalt − non-recoverable Hausgeld × 12) / total acq. cost × 100
  - Total acquisition cost = price × (1 + ({grest}% + 1.5% Notar + Makler%) / 100)
  - Rücklage < €15/m² of building area → Sonderumlage risk
  - Energy class F/G/H → EU renovation directive risk (flag it)
  - Non-recoverable Hausgeld ≈ 35% of total Hausgeld
  - Spekulationsfrist: if seller bought < 10 years ago → CGT exposure on their side

  Save up to {max_save} listings that meet ≥ 3 of these:
    ✓ Gross yield ≥ 3.5%
    ✓ Energy class A–D
    ✓ Rücklage data present and adequate
    ✓ Tenancy status known
    ✓ Price clearly stated
  Write full investment reasoning in the notes field.

═════════════════════════════════════════════════════════

After completing all 6 steps, call done() with a summary and top recommendation."""

    messages = [{"role": "user", "content": goal}]
    saved_listings: list = []
    inquiries:      list = []
    calls = 0
    finished = False

    hdr(f"RE RADAR  LLM AGENT v2  ·  {city.capitalize()}  ·  {MODEL}")
    agent_say(f"Starting: {goal}")

    while calls < MAX_TOOL_CALLS and not finished:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        # Print any reasoning text Claude produces
        for block in response.content:
            if hasattr(block, "text") and block.text.strip():
                agent_say(block.text.strip()[:500])

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

            # ── search_portal ──────────────────────────────────
            if name == "search_portal":
                portal = inp.get("portal", "")
                c      = inp.get("city", city)
                page   = inp.get("page", 1)
                tool_log(f"search_portal({portal}, {c}, page={page})")
                result = portal_search(portal, c, page)
                n = len(result.get("urls", []))
                if n:
                    ok(f"  {portal}: {n} listing URLs")
                else:
                    warn(f"  {portal}: no listings found (may be blocked or no results)")
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     json.dumps(result),
                })

            # ── fetch_listing ──────────────────────────────────
            elif name == "fetch_listing":
                url    = inp.get("url", "")
                reason = inp.get("reason", "")
                tool_log(f"fetch_listing  {url[-60:]}")
                if reason:
                    info(f"  {reason}")
                text = fetch_listing(url)
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     text[:8000],
                })

            # ── flag_missing_data ──────────────────────────────
            elif name == "flag_missing_data":
                lname   = inp.get("listing_name", "?")
                missing = inp.get("missing_fields", [])
                warn(f"Missing data: {lname[:55]}")
                if missing:
                    warn(f"  Fields: {', '.join(missing)}")
                inquiries.append(inp)
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     (
                        f"Inquiry queued for '{lname}'. "
                        f"Missing: {', '.join(missing)}. "
                        f"Email draft will be generated at end of run."
                    ),
                })

            # ── save_listing ───────────────────────────────────
            elif name == "save_listing":
                listing = build_listing(inp, city)
                saved_listings.append(listing)
                price = inp.get("price", 0) or 0
                area  = inp.get("area",  0) or 0
                cold  = inp.get("coldRent", 0) or 0
                gy    = (cold * 12 / price * 100) if price and cold else 0
                line  = (
                    f"Saved [{len(saved_listings)}]: "
                    f"{inp.get('name','?')[:50]}  "
                    f"€{price:,.0f}  {area}m²"
                )
                if gy:
                    line += f"  GY: {gy:.1f}%"
                ok(line)
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     f"Saved. Total saved: {len(saved_listings)}.",
                })

            # ── done ───────────────────────────────────────────
            elif name == "done":
                summary  = inp.get("summary", "")
                top      = inp.get("top_pick", "")
                portals  = inp.get("portals_searched", [])
                reviewed = inp.get("total_reviewed", "?")
                print()
                hdr("AGENT SUMMARY")
                if portals:
                    print(f"  Portals searched: {', '.join(portals)}")
                print(f"  Listings reviewed: {reviewed}")
                print(f"  Listings saved:    {len(saved_listings)}")
                print(f"  Inquiry emails:    {len(inquiries)}")
                print(f"\n  {summary}\n")
                if top:
                    print(f"  \033[32mTop pick:\033[0m {top}\n")
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     "Session complete.",
                })
                finished = True

        messages.append({"role": "assistant", "content": response.content})
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    if calls >= MAX_TOOL_CALLS:
        warn(f"Reached tool call limit ({MAX_TOOL_CALLS}). Wrapping up.")

    return saved_listings, inquiries

# ─────────────────────────────────────────────────────────────────
#  CLOUD-FRIENDLY AGENT  (used by app.py / FastAPI)
#  Same logic as run_agent but:
#    • uses progress_cb instead of printing to stdout
#    • does NOT write to index.html or inquiry_emails.md
#    • returns (saved_listings, inquiries) for the API to handle
# ─────────────────────────────────────────────────────────────────
def run_agent_cloud(
    goal: str,
    city: str,
    max_save: int,
    budget: int,
    progress_cb=None,
) -> tuple:
    """Cloud entry-point.  progress_cb(str) is called for each log line."""
    cb = progress_cb or (lambda _: None)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set.")

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
You conduct property searches on behalf of a buyer, following exactly the same
steps a professional investor would take manually.

YOUR GOAL: {goal}
{bclause}

══════════ THE 6-STEP WORKFLOW YOU MUST FOLLOW ══════════

Step 1 — SEARCH MULTIPLE PORTALS
  Call search_portal for at least 2 portals (start with ohne-makler, then immowelt).
  Collect all listing URLs before opening any individual listings.

Step 2 — OPEN EACH LISTING
  Call fetch_listing on each URL. Read the returned text carefully.
  Look for: Kaufpreis, Wohnfläche, Zimmer, Baujahr, Energieeffizienzklasse,
  Hausgeld, Kaltmiete, Warmmiete, Rücklage, tenancy status, contact details,
  Makler/Provision info.

Step 3 — FLAG MISSING DATA
  For every listing where key investment data is absent, call flag_missing_data.
  This creates a draft German inquiry email the user can send to the agent/owner.

Step 4 — READ EXPOSÉS WITH FULL COMPREHENSION
  Understand context. "Provisionsfrei" means no Makler fee. "Vermietet" = tenanted.
  "Kaltmiete" is the rent basis for yield. "WEG" = owners' association.

Step 5 — IDENTIFY MISSING INFORMATION
  A complete listing has: price, area, rent (Kalt or Warm), Hausgeld, Rücklage,
  energy class, Baujahr, tenancy status.

Step 6 — DECIDE FINANCIAL ATTRACTIVENESS
  - Bundesland: {state}  |  Grunderwerbsteuer: {grest}%
  - Mietpreisbremse applies in {city.capitalize()}: {'YES' if mpb else 'NO'}
  - Gross yield = (Kaltmiete × 12) / Kaufpreis × 100  →  target ≥ 4%
  - Net yield = (annual Kalt − non-recoverable Hausgeld × 12) / total acq. cost × 100
  - Total acquisition cost = price × (1 + ({grest}% + 1.5% Notar + Makler%) / 100)
  - Rücklage < €15/m² → Sonderumlage risk. Energy class F/G/H → EU renovation risk.
  - Non-recoverable Hausgeld ≈ 35% of total Hausgeld.

  Save up to {max_save} listings that meet ≥ 3 of these:
    ✓ Gross yield ≥ 3.5%
    ✓ Energy class A–D
    ✓ Rücklage data present and adequate
    ✓ Tenancy status known
    ✓ Price clearly stated
  Write full investment reasoning in the notes field.

══════════════════════════════════════════════════════════

After completing all 6 steps, call done() with a summary and top recommendation."""

    messages       = [{"role": "user", "content": goal}]
    saved_listings: list = []
    inquiries:      list = []
    calls = 0
    finished = False

    cb(f"Agent starting — city: {city.capitalize()}, goal: {goal[:120]}")

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
                cb(f"Claude: {block.text.strip()[:300]}")

        if response.stop_reason in ("end_turn", "stop_sequence"):
            break
        if response.stop_reason != "tool_use":
            cb(f"Unexpected stop_reason: {response.stop_reason}")
            break

        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue
            calls += 1
            name = block.name
            inp  = block.input

            if name == "search_portal":
                portal = inp.get("portal", "")
                c      = inp.get("city", city)
                page   = inp.get("page", 1)
                cb(f"Searching {portal} in {c} (page {page})")
                result = portal_search(portal, c, page)
                n = len(result.get("urls", []))
                cb(f"{portal}: {n} listing URLs found")
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": json.dumps(result),
                })

            elif name == "fetch_listing":
                url = inp.get("url", "")
                cb(f"Reading listing: {url[-70:]}")
                text = fetch_listing(url)
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": text[:8000],
                })

            elif name == "flag_missing_data":
                lname   = inp.get("listing_name", "?")
                missing = inp.get("missing_fields", [])
                cb(f"Missing data: {lname[:55]} → {', '.join(missing)}")
                inquiries.append(inp)
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": f"Inquiry queued for '{lname}'.",
                })

            elif name == "save_listing":
                listing = build_listing(inp, city)
                saved_listings.append(listing)
                price = inp.get("price", 0) or 0
                cold  = inp.get("coldRent", 0) or 0
                gy    = (cold * 12 / price * 100) if price and cold else 0
                cb(
                    f"SAVED [{len(saved_listings)}]: {inp.get('name','?')[:50]}  "
                    f"€{price:,.0f}" + (f"  GY {gy:.1f}%" if gy else "")
                )
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": f"Saved. Total saved: {len(saved_listings)}.",
                })

            elif name == "done":
                summary = inp.get("summary", "")
                top     = inp.get("top_pick", "")
                cb(f"DONE — {summary[:250]}")
                if top:
                    cb(f"Top pick: {top[:250]}")
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": "Session complete.",
                })
                finished = True

        messages.append({"role": "assistant", "content": response.content})
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    if calls >= MAX_TOOL_CALLS:
        cb(f"Reached tool-call limit ({MAX_TOOL_CALLS}).")

    return saved_listings, inquiries


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="RE Radar LLM Agent v2 — full 6-step investment brief",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python radar_llm_agent_v2.py
  python radar_llm_agent_v2.py --city hamburg --max 3
  python radar_llm_agent_v2.py --city münchen --budget 450000
  python radar_llm_agent_v2.py --goal "Find 2 provisionsfrei flats in Berlin under 400k"
        """,
    )
    parser.add_argument("--city",      default="berlin",         help="City to search")
    parser.add_argument("--max",       type=int, default=4,      help="Max listings to save")
    parser.add_argument("--budget",    type=int, default=0,      help="Max price EUR (0 = no limit)")
    parser.add_argument("--goal",      default="",               help="Custom goal for the agent")
    parser.add_argument("--dashboard", default=DASHBOARD_FILE,   help="Path to index.html")
    args = parser.parse_args()

    city   = args.city.lower().strip()
    budget = args.budget
    bstr   = f" under €{budget:,}" if budget else ""

    goal = args.goal or (
        f"Find {args.max} investment apartments in {city.capitalize()}{bstr}. "
        f"Search ohne-makler and immowelt portals. "
        f"For each listing: read the full exposé, flag missing data with a "
        f"draft inquiry email, and save the best properties with complete "
        f"investment reasoning. Prioritise: Kaltmiete data present, energy "
        f"class B or better, Rücklage disclosed, provisionsfrei preferred."
    )

    # Run the agent
    saved, inquiries = run_agent(goal, city, args.max, budget)

    # Write outputs
    print()
    if saved:
        inject(saved, args.dashboard)
        info(f"Open {args.dashboard} in your browser — {len(saved)} new listings.")
    else:
        warn("No listings were saved. Try a different city or broader goal.")

    if inquiries:
        write_inquiries(inquiries, city)
        info(f"Open {INQUIRY_FILE} — {len(inquiries)} draft inquiry emails ready to send.")
    else:
        info("No inquiry emails generated (all listings had complete data).")

    print()
    info(f"Run complete. Saved: {len(saved)}  |  Inquiries: {len(inquiries)}")


if __name__ == "__main__":
    main()
