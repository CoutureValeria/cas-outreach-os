"""
Webhook client — pushes SEND leads to the email engine.

Endpoint: POST /api/leads/import
Idempotency: stable key per posting ID (Platsbanken ID is unique per posting)
Retry: up to 3 attempts with backoff

NOTE: Only enable after the email engine has been updated to handle
job-posting-sourced leads with appropriate research + email prompts.
This client pushes the lead; the engine handles research + email generation.
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone

import requests
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import EMAIL_ENGINE_URL, EMAIL_ENGINE_API_KEY, DATA_DIR, DRY_RUN

_ENDPOINT      = f"{EMAIL_ENGINE_URL}/api/leads/import"
_SENT_IDS_FILE = os.path.join(DATA_DIR, ".sent_ids.json")
_MAX_RETRIES   = 3
_RETRY_DELAYS  = [1, 3, 7]

log = logging.getLogger("indeed_webhook")
if not log.handlers:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s [webhook] %(levelname)s %(message)s",
                                     datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(h)
    log.setLevel(logging.INFO)


def _idem_key(posting_id: str, employer_name: str) -> str:
    raw = f"{posting_id}|{employer_name.lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _load_sent() -> set:
    if not os.path.exists(_SENT_IDS_FILE):
        return set()
    try:
        with open(_SENT_IDS_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _record_sent(key: str) -> None:
    ids = _load_sent()
    ids.add(key)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_SENT_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, indent=2)


def _build_import_payload(posting: dict, score_data: dict) -> dict:
    auto_tasks = score_data.get("automatable_tasks", [])
    pain_snippet = auto_tasks[0]["task"] if auto_tasks else ""
    auto_task_names = [t["task"] for t in auto_tasks]

    enrich = posting.get("_enrichment") or {}
    enrich_data = enrich.get("data") or {}
    enrich_contact = enrich_data.get("contact") or {}
    enrich_dm = enrich_data.get("decision_maker") or {}

    # Prefer enrichment contact info over raw posting data
    phone   = enrich_contact.get("phone")   or posting.get("employer_phone")
    email   = enrich_contact.get("email")   or posting.get("employer_email")
    contact_name = posting.get("_contact_name") or enrich_dm.get("name")

    return {
        "name":            posting.get("employer_name", ""),
        "area":            posting.get("city", "Stockholm"),
        "address":         posting.get("street_address", ""),
        "phone":           phone,
        "website":         posting.get("employer_url"),
        "email":           email,
        "contact_name":    contact_name,
        "email_priority":  "generic",
        "lead_score":      score_data.get("automation_fit_score", 0),
        "pain_score":      score_data.get("automation_fit_score", 0),
        "primary_pain":    score_data.get("automation_angle", ""),
        "pain_evidence":   "; ".join(auto_task_names[:3]),
        "pain_source":     "job-posting",
        "signal_categories": ["booking_scheduling"] if auto_tasks else [],
        "pain_snippet":    pain_snippet,
        "source":          "indeed-intel-v1",
        "research_notes":  json.dumps({
            "job_headline":              posting.get("headline", ""),
            "posting_url":               posting.get("webpage_url", ""),
            "automatable_tasks":         auto_task_names,
            "automation_angle":          score_data.get("automation_angle", ""),
            "automation_score":          score_data.get("automation_fit_score", 0),
            "website_enrichment":        enrich_data,
            "website_automation_score":  enrich.get("automation_score", 0),
        }, ensure_ascii=False),
    }


def _post_with_retry(payload: dict, idem_key: str) -> tuple[bool, str]:
    headers = {
        "X-API-Key":         EMAIL_ENGINE_API_KEY,
        "Content-Type":      "application/json",
        "X-Idempotency-Key": idem_key,
    }
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.post(_ENDPOINT, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                body = resp.json()
                return True, "duplicate" if body.get("skipped") else "ok"
            if resp.status_code == 409:
                return True, "duplicate (409)"
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAYS[attempt - 1])
                    continue
                return False, f"HTTP {resp.status_code} after {attempt} attempts"
            return False, f"HTTP {resp.status_code}: {resp.text[:120]}"
        except requests.Timeout:
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAYS[attempt - 1])
            else:
                return False, "Timeout"
        except requests.RequestException as exc:
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAYS[attempt - 1])
            else:
                return False, f"Network error: {exc}"
    return False, "Max retries exceeded"


def send_all(send_leads: list[dict]) -> dict:
    """
    Pushes all SEND leads to the email engine.
    send_leads: list of enriched posting dicts (with score_data attached).
    """
    if not send_leads:
        log.info("No SEND leads to push.")
        return {"sent": 0, "skipped": 0, "errors": 0, "dry_run": DRY_RUN}

    if DRY_RUN:
        log.info("DRY RUN — no webhook calls.")
        for lead in send_leads:
            score_data = lead.get("score_data", {}) or {}
            payload = _build_import_payload(lead, score_data)
            log.info("DRY RUN | WOULD SEND: %s | score=%s",
                     payload["name"], payload["lead_score"])
        return {"sent": 0, "skipped": len(send_leads), "errors": 0, "dry_run": True}

    sent_ids = _load_sent()
    sent = skipped = errors = 0

    for lead in send_leads:
        name  = lead.get("employer_name", "unknown")
        pid   = lead.get("id", "")
        score = lead.get("automation_fit_score", 0)
        idem  = _idem_key(pid, name)

        if idem in sent_ids:
            log.info("SKIP | already sent | %s", name)
            skipped += 1
            continue

        score_data = lead.get("score_data", {}) or {}
        payload    = _build_import_payload(lead, score_data)
        success, reason = _post_with_retry(payload, idem)

        if success:
            if "duplicate" in reason:
                log.info("SKIP | %s | %s", reason, name)
                skipped += 1
            else:
                log.info("SENT | %s | score=%s | key=%s", name, score, idem)
                _record_sent(idem)
                sent += 1
        else:
            log.error("ERROR | %s | %s", reason, name)
            errors += 1

    log.info("DONE | sent=%d | skipped=%d | errors=%d", sent, skipped, errors)
    return {"sent": sent, "skipped": skipped, "errors": errors, "dry_run": False}
