"""
Test the full enrichment pipeline on 3 SEND leads with websites.
"""
import json
import os
import sys

# Load env
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

sys.path.insert(0, os.path.dirname(__file__))

from collectors.openclaw_client import get_page_text
from enrichment.pipeline import run_pipeline

TEST_LEADS = [
    {"name": "Smartchain Logistics Nordics AB", "website": "https://www.smartchain.se"},
    {"name": "Lindalens Stad och Tillaggstjanster AB", "website": "https://www.lindalensstad.se"},
    {"name": "Nord Armering AB", "website": "https://nordarmering.se"},
]

print("=" * 70)
print("  ENRICHMENT PIPELINE TEST")
print("=" * 70)

for lead in TEST_LEADS:
    name = lead["name"]
    url = lead["website"]
    print("\n" + "-" * 60)
    print(f"  Company: {name}")
    print(f"  URL:     {url}")

    raw_text = get_page_text(url)
    if not raw_text:
        print("  RESULT: page text fetch FAILED (both OpenClaw and bs4)")
        continue

    print(f"  Page text: {len(raw_text)} chars")
    preview = raw_text[:200].encode("ascii", errors="replace").decode("ascii")
    print(f"  Preview:   {repr(preview)}")

    result = run_pipeline(raw_text, url)

    print(f"\n  Extraction success: {result['extraction_success']}")
    print(f"  Automation score:  {result['automation_score']}")

    if result["extraction_success"]:
        data = result["data"]
        dm = data.get("decision_maker") or {}
        contact = data.get("contact") or {}
        signals = data.get("signals") or {}
        print(f"  Decision maker:    {dm.get('name')} ({dm.get('role')})")
        print(f"  Industry:          {data.get('industry')}")
        print(f"  Size:              {data.get('estimated_size')}")
        print(f"  Phone:             {contact.get('phone')}")
        print(f"  Email:             {contact.get('email')}")
        print(f"  Booking system:    {contact.get('booking_system')}")
        print(f"  Manual workflows:  {signals.get('manual_workflows')}")
        print(f"  Appointment heavy: {signals.get('appointment_heavy')}")
        print(f"  Recruitment:       {signals.get('recruitment_active')}")
        opps = data.get("automation_opportunities") or []
        for opp in opps:
            opp_safe = opp.encode("ascii", errors="replace").decode("ascii")
            print(f"  Opportunity:       {opp_safe}")
        summary = (data.get("summary") or "").encode("ascii", errors="replace").decode("ascii")
        print(f"  Summary:           {summary}")
    else:
        print("  RESULT: extraction FAILED (JSON parse or Claude error)")

print("\n" + "=" * 70)
print("  TEST COMPLETE")
print("=" * 70)
