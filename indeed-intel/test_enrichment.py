"""
Tests the enrichment module on 3 indeed-intel leads.

Mix chosen to cover all scenarios from the task:
  1. BRP Systems AB   — company website available, no Platsbanken contact name
  2. Lindalens Städ   — small SMB cleaning company
  3. R Gruppen Hyr AB — vehicle rental, borderline 48% score

For each lead: shows enrichment JSON + final email greeting comparison
(Platsbanken contact_name vs OpenClaw decision_maker).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from enrichment.openclaw_enrich import enrich_company
from scoring.task_scorer import generate_email, AUTOMATION_TYPES

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "results_20260615_174405.json")

with open(DATA_FILE, encoding="utf-8") as f:
    all_postings = json.load(f)

# ── Pick the 3 targets ────────────────────────────────────────────────────────
TARGETS = {
    "BRP Systems AB":       "BRP SYSTEMS",
    "Lindalens Städ":       "Lindalens",
    "R Gruppen Hyr AB":     "R Gruppen Hyr",
}

found = {}
for posting in all_postings:
    name = posting.get("employer_name", "")
    for label, needle in TARGETS.items():
        if needle.lower() in name.lower() and label not in found:
            found[label] = posting

missing = set(TARGETS) - set(found)
if missing:
    print(f"WARNING: could not find: {', '.join(missing)}")
    print("Available names:", [p.get('employer_name') for p in all_postings[:20]])
    sys.exit(1)

# ── Run enrichment on each target ────────────────────────────────────────────
print("\n" + "=" * 70)
print("  ENRICHMENT TEST — 3 indeed-intel leads")
print("=" * 70)

for label, posting in found.items():
    company_name = posting.get("employer_name", "")
    website      = posting.get("employer_url") or ""
    # Strip job-specific paths — use root domain where possible
    if website and '/lediga' in website:
        from urllib.parse import urlparse
        p = urlparse(website)
        website = f"{p.scheme}://{p.netloc}"

    plats_contact = posting.get("_contact_name") or ""
    score         = posting.get("automation_fit_score", 0)
    score_data    = posting.get("score_data") or {}
    atype         = score_data.get("automation_type", "general_admin")

    print(f"\n{'-' * 70}")
    print(f"  {label}  ({score}%)  |  url: {website or '(none)'}")
    print(f"  Platsbanken contact: {plats_contact or '(none)'}")
    print(f"  Automation type: {atype}")

    # ── Enrich ───────────────────────────────────────────────────────────────
    enrichment = enrich_company(company_name, website or None)

    print(f"\n  ENRICHMENT JSON:")
    print("  " + json.dumps(enrichment, ensure_ascii=False, indent=4).replace("\n", "\n  "))

    # ── Determine greeting contact name ──────────────────────────────────────
    # Priority: Platsbanken contact_name > OpenClaw decision_maker > generic
    if plats_contact:
        greeting_name = plats_contact
        greeting_src  = "Platsbanken"
    elif enrichment.get("decision_maker"):
        greeting_name = enrichment["decision_maker"]
        greeting_src  = "OpenClaw/website"
    else:
        greeting_name = None
        greeting_src  = "generic"

    print(f"\n  GREETING RESOLUTION:")
    print(f"    Platsbanken contact: {plats_contact or '(none)'}")
    print(f"    Website DM found:    {enrichment.get('decision_maker') or '(none)'} ({enrichment.get('decision_maker_role') or '-'})")
    print(f"    => Using '{greeting_name or 'Hej,'}' (source: {greeting_src})")

    # ── Generate email with the resolved contact name ─────────────────────────
    posting_copy = dict(posting)
    posting_copy["_contact_name"] = greeting_name or ""
    # Inject any enrichment-found email if the original had none
    if enrichment.get("email") and not posting_copy.get("employer_email"):
        posting_copy["employer_email"] = enrichment["email"]

    print(f"\n  GENERATED EMAIL:")
    if score_data:
        email_text = generate_email(posting_copy, score_data)
        for line in email_text.split("\n"):
            print(f"    {line}")
        dash_ok = "—" not in email_text and "–" not in email_text
        print(f"\n  Dash check: {'PASS' if dash_ok else 'FAIL — dashes found!'}")
    else:
        print("  (score_data missing — cannot generate email)")

print(f"\n{'=' * 70}")
print("  Done.")
print("=" * 70)
