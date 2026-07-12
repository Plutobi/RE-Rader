"""
RE Radar — Cloud API  (app.py)
═══════════════════════════════════════════════════════════════════
FastAPI backend that exposes the LLM agent over HTTP so the
dashboard can trigger city searches without running Python locally.

Deploy to Railway / Render / any Python host:
  1.  Set  ANTHROPIC_API_KEY  as an environment variable on the host.
  2.  Railway auto-detects the Procfile and runs uvicorn.

Local dev:
  pip install -r requirements.txt
  uvicorn app:app --reload

Endpoints:
  POST /search          { city, max_listings, budget, goal }  → { job_id }
  GET  /jobs/{job_id}   → { status, log, listings, ... }
  GET  /listings        → [ listing, ... ]
  DELETE /listings/{id} → { deleted }
  GET  /inquiries       → [ inquiry, ... ]
  GET  /health          → { status, listings }
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load .env if present (local dev)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import cloud entry-point from the agent module
from radar_llm_agent_v2 import run_agent_cloud  # noqa: E402

# ─────────────────────────────────────────────────────────────────
#  App
# ─────────────────────────────────────────────────────────────────
app = FastAPI(title="RE Radar API", version="2.0")

# Allow any origin so the frontend (served from a different domain) can call us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────
#  Persistent storage  (flat JSON files — simple, portable)
# ─────────────────────────────────────────────────────────────────
LISTINGS_FILE  = Path("listings.json")
INQUIRIES_FILE = Path("inquiry_emails.json")


def _read_json(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _write_json(path: Path, data: list) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────
#  In-memory job store   { job_id: { ...state } }
# ─────────────────────────────────────────────────────────────────
jobs: dict[str, dict] = {}


# ─────────────────────────────────────────────────────────────────
#  Request model
# ─────────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    city: str
    max_listings: int = 5
    budget: int = 0       # 0 = no price ceiling
    goal: str = ""        # custom goal; auto-generated when empty


# ─────────────────────────────────────────────────────────────────
#  Background job
# ─────────────────────────────────────────────────────────────────
def _run_job(job_id: str, req: SearchRequest) -> None:
    job = jobs[job_id]

    def log(msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        job["log"].append(f"[{ts}] {msg}")

    try:
        city   = req.city.lower().strip()
        budget = req.budget
        bstr   = f" under €{budget:,}" if budget else ""

        goal = req.goal or (
            f"Find {req.max_listings} investment apartments in {city.capitalize()}{bstr}. "
            f"Search ohne-makler and immowelt portals. "
            f"For each listing: read the full exposé, flag missing data with a "
            f"draft inquiry email, and save the best properties with complete "
            f"investment reasoning. Prioritise: Kaltmiete data present, energy "
            f"class B or better, Rücklage disclosed, provisionsfrei preferred."
        )

        saved, inquiries = run_agent_cloud(
            goal=goal,
            city=city,
            max_save=req.max_listings,
            budget=budget,
            progress_cb=log,
        )

        # ── Persist listings ────────────────────────────────────
        existing = _read_json(LISTINGS_FILE)
        for lst in saved:
            lst.setdefault("id", str(uuid.uuid4())[:8])
        existing.extend(saved)
        _write_json(LISTINGS_FILE, existing)

        # ── Persist inquiry emails ──────────────────────────────
        inq_all = _read_json(INQUIRIES_FILE)
        for inq in inquiries:
            inq["job_id"] = job_id
            inq["city"]   = city
        inq_all.extend(inquiries)
        _write_json(INQUIRIES_FILE, inq_all)

        job["status"]          = "completed"
        job["listings"]        = saved
        job["inquiries_count"] = len(inquiries)
        log(f"Completed — saved {len(saved)} listings, {len(inquiries)} inquiry emails.")

    except Exception as exc:  # noqa: BLE001
        job["status"] = "failed"
        job["error"]  = str(exc)
        log(f"ERROR: {exc}")


# ─────────────────────────────────────────────────────────────────
#  Routes
# ─────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status":   "ok",
        "listings": len(_read_json(LISTINGS_FILE)),
        "api_key":  bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


@app.post("/search")
def start_search(req: SearchRequest, background_tasks: BackgroundTasks):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(500, "ANTHROPIC_API_KEY is not configured on this server.")

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id":              job_id,
        "city":            req.city,
        "status":          "running",
        "started_at":      datetime.now().isoformat(),
        "log":             [],
        "listings":        [],
        "inquiries_count": 0,
        "error":           None,
    }
    background_tasks.add_task(_run_job, job_id, req)
    return {"job_id": job_id, "status": "running"}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, f"Job '{job_id}' not found.")
    return jobs[job_id]


@app.get("/jobs")
def list_jobs():
    return sorted(jobs.values(), key=lambda j: j["started_at"], reverse=True)


@app.get("/listings")
def get_listings():
    return _read_json(LISTINGS_FILE)


@app.delete("/listings/{listing_id}")
def delete_listing(listing_id: str):
    listings = [l for l in _read_json(LISTINGS_FILE) if l.get("id") != listing_id]
    _write_json(LISTINGS_FILE, listings)
    return {"deleted": listing_id, "remaining": len(listings)}


@app.delete("/listings")
def clear_all_listings():
    _write_json(LISTINGS_FILE, [])
    return {"cleared": True}


@app.get("/inquiries")
def get_inquiries():
    return _read_json(INQUIRIES_FILE)
