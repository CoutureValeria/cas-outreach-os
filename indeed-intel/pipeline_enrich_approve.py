"""
pipeline_enrich_approve.py — Full indeed leads pipeline
Runs for all indeed leads (type=job-posting) that have no email address yet.

Steps per lead:
  1. Normalize website URL (strip recruiter subdomains → real company domain)
  2. Run openclaw enrichment to find email, phone, decision_maker, summary
  3. Generate a Swedish cold email (job-posting pitch, not vet-specific)
  4. PATCH lead in Supabase via service_role REST API
     Fields: email, phone, contact_name, research_notes, subject, body,
             status='approved', generated_at, personalization_level

Run: python pipeline_enrich_approve.py
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from anthropic import Anthropic

# Add parent for enrichment import
sys.path.insert(0, os.path.dirname(__file__))
from collectors.openclaw_client import get_page_text
from enrichment.pipeline import run_pipeline as _run_enrichment_pipeline
from scoring.task_scorer import sanitize_email


def enrich_company(company_name: str, website: str | None) -> dict:
    """Adapter: run new enrichment pipeline and return flat dict matching old interface."""
    blank = {
        "company_name": company_name, "website": website,
        "industry": None, "estimated_size": None,
        "phone": None, "email": None,
        "contact_form": False, "booking_system": False, "live_chat": False,
        "decision_maker": None, "decision_maker_role": None,
        "automation_opportunities": [], "summary": None,
        "scrape_status": "no_website",
    }
    if not website:
        blank["summary"] = "No website — enrichment skipped."
        return blank

    raw_text = get_page_text(website)
    if not raw_text:
        blank["scrape_status"] = "fetch_failed"
        blank["summary"] = "Website fetch failed."
        return blank

    result = _run_enrichment_pipeline(raw_text, website)
    if not result.get("extraction_success"):
        blank["scrape_status"] = "extraction_failed"
        return blank

    data = result["data"] or {}
    contact = data.get("contact") or {}
    dm = data.get("decision_maker") or {}

    return {
        "company_name":             company_name,
        "website":                  website,
        "industry":                 data.get("industry"),
        "estimated_size":           data.get("estimated_size"),
        "phone":                    contact.get("phone"),
        "email":                    contact.get("email"),
        "contact_form":             bool(contact.get("contact_form", False)),
        "booking_system":           bool(contact.get("booking_system", False)),
        "live_chat":                bool(contact.get("live_chat", False)),
        "decision_maker":           dm.get("name"),
        "decision_maker_role":      dm.get("role"),
        "automation_opportunities": data.get("automation_opportunities") or [],
        "summary":                  data.get("summary"),
        "scrape_status":            "ok",
    }

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [pipeline] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
SUPABASE_URL        = "https://tjpkmonazlqmbaazcker.supabase.co"
SUPABASE_SVC_KEY    = os.environ.get(
    "SUPABASE_SERVICE_ROLE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRqcGttb25hemxxbWJhYXpja2VyIiwicm9sZSI6"
    "InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3ODE2MDM5MiwiZXhwIjoyMDkzNzM2MzkyfQ."
    "mjtJWBbzozd6PVojq_j0bNHQwWpwTabRT2tmkAo3Qi4"
)
ENGINE_URL          = "https://cas-email-engine-backend-production-3b02.up.railway.app"
ENGINE_KEY          = "1790f2bc89c3b684ae79d51d73d2e0a550797e34c243dd23383d0df70fda6a58"

# Load ANTHROPIC_API_KEY from .env file if not in env
if not ANTHROPIC_API_KEY:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("ANTHROPIC_API_KEY="):
                    ANTHROPIC_API_KEY = line.split("=", 1)[1].strip()
                    break

os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY

_client = Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Recruiter subdomain normalization ────────────────────────────────────────
# URLs like company.teamtailor.com, career.company.com → company.com / company.se
_RECRUITER_DOMAINS = {"teamtailor.com", "teamtailor.se", "career.svea.com"}
_RECRUITER_SUBPATHS = {"/lediga-tjanster", "/jobs", "/careers", "/career", "/jobb"}

def normalize_website(url: str | None, company_name: str) -> str | None:
    """Return the best URL to scrape for the company's real contact info."""
    if not url:
        return None
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url

    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    # Strip recruiter subdomains: company.teamtailor.com → try company.se
    if any(rd in host for rd in ["teamtailor.com", "teamtailor.se"]):
        subdomain = host.split(".")[0]
        # Try .se first, then .com
        return f"https://{subdomain}.se"

    # Strip career subdomains: career.svea.com → svea.com
    if host.startswith("career.") or host.startswith("careers."):
        root = ".".join(host.split(".")[1:])
        return f"{parsed.scheme}://{root}"

    # Strip jobs subdomain: jobs.avaron.se → avaron.se
    if host.startswith("jobs.") or host.startswith("jobb.") or host.startswith("team."):
        root = ".".join(host.split(".")[1:])
        return f"{parsed.scheme}://{root}"

    # Strip job posting paths
    path = parsed.path.lower()
    for subpath in _RECRUITER_SUBPATHS:
        if path.startswith(subpath):
            return f"{parsed.scheme}://{parsed.netloc}"

    return url


# ── Fetch indeed leads from backend ──────────────────────────────────────────
def get_indeed_leads() -> list[dict]:
    resp = requests.get(
        f"{ENGINE_URL}/api/leads?limit=200",
        headers={"X-API-Key": ENGINE_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()
    leads = body.get("leads") if isinstance(body, dict) else body
    return [l for l in (leads or []) if l.get("type") == "job-posting" and not l.get("email")]


# ── Supabase PATCH ────────────────────────────────────────────────────────────
def patch_lead(lead_id: str, updates: dict) -> bool:
    headers = {
        "apikey":        SUPABASE_SVC_KEY,
        "Authorization": f"Bearer {SUPABASE_SVC_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/leads?id=eq.{lead_id}",
        headers=headers,
        json=updates,
        timeout=10,
    )
    if resp.status_code not in (200, 204):
        log.error("Supabase PATCH failed %s: %s %s", lead_id, resp.status_code, resp.text[:200])
        return False
    return True


# ── Email generation (job-posting specific) ──────────────────────────────────
_EMAIL_SYSTEM = (
    "Du skriver svenska cold emails som Kasper, en enskild person, inte ett bolag. "
    "Tonfall: genuint nyfiken, inte säljigt. Aldrig 'vi', alltid 'jag'. "
    "Nämn aldrig Drivverk AB, CAS Automations, eller vad Kasper säljer. "
    "Max 3 rader + signatur. Ingen AI-nämning. Inga tankstreck (— eller –)."
)

def generate_indeed_email(lead: dict, enrichment: dict) -> tuple[str, str]:
    """Generate Swedish cold email for a general business lead. Returns (subject, body)."""
    name            = lead.get("name", "")
    area            = lead.get("area", "Stockholm")
    decision_maker  = enrichment.get("decision_maker") or ""
    summary         = enrichment.get("summary") or ""
    opportunities   = enrichment.get("automation_opportunities") or []

    # Parse job_headline from research_notes if present
    job_headline = ""
    research_raw = lead.get("research_notes")
    if research_raw:
        try:
            rn = json.loads(research_raw)
            job_headline = rn.get("job_headline", "")
        except Exception:
            pass

    greeting = f"Hej {decision_maker}," if decision_maker else "Hej,"
    opp_context = f"\nManuella arbetsuppgifter identifierade i annonsen: {', '.join(opportunities[:2])}" if opportunities else ""

    prompt = f"""Skriv ett kort cold email på svenska. Det ska låta som att en enskild person (Kasper) skickar det av nyfikenhet, INTE som ett bolag som gör outreach.

Mottagare: {name}, {area}
{f'Jobbtitel de söker: {job_headline}' if job_headline else ''}
{f'Sammanfattning av företaget: {summary}' if summary else ''}
{opp_context}

FORMAT — 3 rader + signatur:

RAD 1 (opener): Referera till deras jobannons om möjligt.
{f'Börja med: "{greeting} jag såg er annons för {job_headline}," och lägg sedan till en kort observation om att den typen av roll ofta innebär mycket manuellt arbete.'
 if job_headline else
 f'Börja med: "{greeting} jag märkte att..." eller "{greeting} jag snubblade på er sida och noterade att..." och gör en konkret observation.'}

RADER 2-3 (discovery-fråga): En kort, genuin fråga om det är något de känner igen, eller om de redan har koll på det.
Ingen pitch. Ingen lösning. Ingen teknik. Bara nyfiken.

ABSOLUTA REGLER:
- Aldrig "vi", alltid "jag"
- Nämn INTE Drivverk AB, CAS Automations, eller något eget företagsnamn
- Nämn inte AI, automatisering, teknik, eller vad Kasper säljer
- Det ska låta som en person som råkade se deras annons och blev nyfiken
- Inga bullet points, inga fetstil, inga bindestreck

Avsluta med en blank rad, sedan exakt:
Kasper

Sen en sista rad exakt:
Vill du inte bli kontaktad igen? Svara bara på det här mejlet.

Skriv också ett kort ämnesrad (max 7 ord, inga spam-ord).

Svara i exakt detta format:
SUBJECT: [ämnesrad]
BODY:
[brödtext]
"""

    resp = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=_EMAIL_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()

    subject_m = re.search(r"SUBJECT:\s*(.+)", text)
    body_m    = re.search(r"BODY:\s*([\s\S]+)", text)

    subject = subject_m.group(1).strip() if subject_m else f"Fråga till {name}"
    body    = body_m.group(1).strip() if body_m else text

    return sanitize_email(subject), sanitize_email(body)


# ── Main pipeline ─────────────────────────────────────────────────────────────
def main():
    log.info("Fetching indeed leads without email...")
    leads = get_indeed_leads()
    log.info("Found %d leads to process", len(leads))

    results = {"enriched": 0, "emailed": 0, "approved": 0, "skipped": 0, "errors": 0}

    for lead in leads:
        name    = lead.get("name", "?")
        lead_id = lead.get("id", "")
        raw_url = lead.get("website")

        log.info("── %s ──", name)

        # 1. Normalize URL
        website = normalize_website(raw_url, name)
        if raw_url and website != raw_url:
            log.info("  URL normalized: %s → %s", raw_url, website)

        # 2. Enrich
        enrich = {}
        if website:
            try:
                enrich = enrich_company(name, website)
                log.info("  Enriched: email=%s phone=%s dm=%s",
                         enrich.get("email"), enrich.get("phone"), enrich.get("decision_maker"))
                results["enriched"] += 1
            except Exception as e:
                log.warning("  Enrichment failed: %s", e)
        else:
            log.info("  No website — skipping enrichment")

        email = enrich.get("email")
        if not email:
            log.warning("  No email found — cannot approve for sending, skipping")
            results["skipped"] += 1
            continue

        # 3. Generate email
        try:
            subject, body = generate_indeed_email(lead, enrich)
            log.info("  Generated email: %s", subject)
            results["emailed"] += 1
        except Exception as e:
            log.error("  Email generation failed: %s", e)
            results["errors"] += 1
            continue

        # 4. Build research_notes from enrichment
        research_notes = json.dumps({
            "industry":              enrich.get("industry"),
            "estimated_size":        enrich.get("estimated_size"),
            "contact_form":          enrich.get("contact_form"),
            "booking_system":        enrich.get("booking_system"),
            "automation_opportunities": enrich.get("automation_opportunities") or [],
            "summary":               enrich.get("summary"),
            "decision_maker_name":   enrich.get("decision_maker"),
            "scrape_status":         enrich.get("scrape_status"),
        }, ensure_ascii=False)

        # 5. PATCH lead in Supabase
        updates = {
            "email":                email,
            "phone":                enrich.get("phone") or lead.get("phone"),
            "website":              website or raw_url,
            "contact_name":         enrich.get("decision_maker"),
            "research_notes":       research_notes,
            "subject":              subject,
            "body":                 body,
            "status":               "approved",
            "approved_at":          datetime.now(timezone.utc).isoformat(),
            "generated_at":         datetime.now(timezone.utc).isoformat(),
            "personalization_level": "researched" if enrich.get("summary") else "low",
            "researched":           True,
        }

        ok = patch_lead(lead_id, updates)
        if ok:
            log.info("  ✓ Approved: %s → %s", name, email)
            results["approved"] += 1
        else:
            results["errors"] += 1

        time.sleep(1)  # be nice to APIs

    log.info("\n═══ PIPELINE COMPLETE ═══")
    log.info("Enriched:  %d", results["enriched"])
    log.info("Emailed:   %d", results["emailed"])
    log.info("Approved:  %d", results["approved"])
    log.info("Skipped (no email found): %d", results["skipped"])
    log.info("Errors:    %d", results["errors"])
    return results


if __name__ == "__main__":
    main()
