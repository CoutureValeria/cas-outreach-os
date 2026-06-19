"""
fix_stale_indeed_emails.py — One-shot repair for approved indeed leads with old email format.

Identifies leads where body still has:
  - "Drivverk AB" (old sign-off)
  - "Vill du inte bli kontaktad" (old formal opt-out)
  - raw em dash characters (—  or –)

Regenerates the email using the current prompt and sanitization, then PATCHes Supabase.
"""

import json
import os
import re
import sys
import time

import requests
sys.path.insert(0, os.path.dirname(__file__))

from pipeline_enrich_approve import generate_indeed_email, sanitize_email

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SUPABASE_URL      = "https://tjpkmonazlqmbaazcker.supabase.co"
SUPABASE_SVC_KEY  = os.environ.get(
    "SUPABASE_SERVICE_ROLE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRqcGttb25hemxxbWJhYXpja2VyIiwicm9sZSI6"
    "InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3ODE2MDM5MiwiZXhwIjoyMDkzNzM2MzkyfQ."
    "mjtJWBbzozd6PVojq_j0bNHQwWpwTabRT2tmkAo3Qi4"
)

if not ANTHROPIC_API_KEY:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("ANTHROPIC_API_KEY="):
                    ANTHROPIC_API_KEY = line.split("=", 1)[1].strip()
                    break
os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY

_HEADERS = {
    "apikey":        SUPABASE_SVC_KEY,
    "Authorization": f"Bearer {SUPABASE_SVC_KEY}",
    "Content-Type":  "application/json",
}

OLD_MARKERS = [
    "Drivverk AB",
    "Vill du inte bli kontaktad",
    "Svara bara på det här mejlet",
    "Svara bara pa det har mejlet",
    "—",  # raw em dash
    "–",  # raw en dash
]


def is_stale(body: str) -> bool:
    if not body:
        return False
    return any(marker in body for marker in OLD_MARKERS)


def fetch_approved_indeed_leads() -> list[dict]:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/leads",
        headers=_HEADERS,
        params={
            "select": "*",
            "status": "eq.approved",
            "type":   "eq.job-posting",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json() or []


def patch_lead(lead_id: str, subject: str, body: str) -> bool:
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/leads?id=eq.{lead_id}",
        headers={**_HEADERS, "Prefer": "return=minimal"},
        json={"subject": subject, "body": body},
        timeout=10,
    )
    return resp.status_code in (200, 204)


def rebuild_enrichment(research_notes_raw: str, contact_name: str | None) -> dict:
    """Reconstruct enrichment dict from what was stored in research_notes."""
    rn = {}
    if research_notes_raw:
        try:
            rn = json.loads(research_notes_raw)
        except Exception:
            pass

    return {
        "decision_maker": rn.get("decision_maker_name") or contact_name,
        "summary":        rn.get("summary"),
        "automation_opportunities": rn.get("automation_opportunities") or [],
    }


def main(dry_run: bool = False):
    print("Fetching approved indeed leads from Supabase...")
    leads = fetch_approved_indeed_leads()
    print(f"Found {len(leads)} approved indeed leads total")

    stale = [l for l in leads if is_stale(l.get("body", "") or "")]
    print(f"Stale (old format): {len(stale)}")

    if not stale:
        print("Nothing to fix.")
        return

    if dry_run:
        print("\n[DRY RUN — no changes written]\n")

    fixed = 0
    failed = 0

    for lead in stale:
        name    = lead.get("name", "?")
        lead_id = lead.get("id", "")
        old_body = lead.get("body", "")

        print(f"\n── {name} (id: {lead_id})")
        print(f"   OLD body tail: {repr(old_body[-120:])}")

        enrichment = rebuild_enrichment(lead.get("research_notes"), lead.get("contact_name"))

        try:
            new_subject, new_body = generate_indeed_email(lead, enrichment)
        except Exception as e:
            print(f"   ✗ Generation failed: {e}")
            failed += 1
            continue

        print(f"   NEW subject: {new_subject}")
        print(f"   NEW body:\n{new_body}\n")

        # Verify new body is clean
        if is_stale(new_body):
            # sanitize_email already ran inside generate_indeed_email, but double-check
            new_subject = sanitize_email(new_subject)
            new_body    = sanitize_email(new_body)

        if dry_run:
            print("   [DRY RUN] Would PATCH Supabase")
            fixed += 1
            continue

        ok = patch_lead(lead_id, new_subject, new_body)
        if ok:
            print(f"   ✓ Patched in Supabase")
            fixed += 1
        else:
            print(f"   ✗ Supabase PATCH failed")
            failed += 1

        time.sleep(0.5)

    print(f"\n══ DONE — fixed: {fixed}  failed: {failed} ══")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = p.parse_args()
    main(dry_run=args.dry_run)
