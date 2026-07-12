# RE Radar — German Real Estate Investment Intelligence

A single-file web app for tracking, evaluating, and comparing German property listings. No build step, no dependencies, no backend — open `index.html` in any browser.

## Live Demo
Hosted on Netlify / GitHub Pages (see deployment link above)

## Features

- **Smart Paste** — paste raw listing text from ImmoScout24, Immowelt, Immonet etc.; AI parser auto-extracts Kaufpreis, Wohnfläche, Baujahr, Kaltmiete, Hausgeld, Energieklasse, Provision and pre-fills the form
- **Find Listings** — set criteria (city, price, area, rooms) and launch pre-filtered searches on 6 German portals in one click
- **Investment Scoring** — composite 0–100 score per property: gross yield, net yield, €/sqm vs market, Rücklage health, energy class, risk flags
- **Side-by-Side Compare** — select up to 4 properties; comparison table highlights best/worst value per metric
- **German RE Domain Model** — Kaltmiete vs Warmmiete (yield uses Kaltmiete only), Hausgeld split (umlagefähig / non-recoverable), Instandhaltungsrücklage risk detection, Grunderwerbsteuer by Bundesland, Spekulationsfrist (10-year CGT window), Mietpreisbremse auto-detection
- **Cards + Table views**, filters by city, state, energy class, risk; sort by score, yield, price, €/sqm
- **localStorage persistence** — data survives page reloads

## Project Files

| File | Purpose |
|------|---------|
| `index.html` | The full application (single file) |
| `PROVENANCE.md` | Model provenance & decision log |
| `DEV-PROCESS.md` | AI-assisted development process |
| `GIT-WORKFLOW.md` | Git branching & workflow guide |
| `PROJECT-OVERVIEW.md` | Architecture & domain model overview |
| `AUDIT-REPORT.md` | Cross-model audit report |
| `submission-summary.md` | Submission summary |

## Tech Stack

Vanilla HTML/CSS/JS · No frameworks · No build tools · Google Fonts (Inter) · localStorage

## Deployment

**GitHub Pages:** Enable in repo Settings → Pages → Deploy from branch `main`, root `/`

**Netlify:** Drag the repo folder onto [netlify.com/drop](https://app.netlify.com/drop)

## German RE Calculations

- **Bruttomietrendite** = (Kaltmiete × 12) / Kaufpreis × 100
- **Nettomietrendite** = (Kaltmiete × 12 − non-recoverable Hausgeld) / Kaufpreis × 100
- **Nebenkosten** = Grunderwerbsteuer (by Bundesland) + Notarkosten (1.5–2%) + Maklergebühr
- **Rücklage risk** = flags if Instandhaltungsrücklage < €15/sqm (Sonderumlage risk)
- **Mietpreisbremse** auto-detected for ~35 regulated cities
