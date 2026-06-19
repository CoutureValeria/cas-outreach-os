"""
gen_test_emails.py — Generate 3 sample indeed-intel emails to verify current format.
Uses realistic mock postings to test the current prompt + sanitization pipeline.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from pipeline_enrich_approve import generate_indeed_email

MOCK_LEADS = [
    {
        "id": "test-1",
        "name": "Committo AB",
        "area": "Stockholm",
        "research_notes": '{"job_headline": "Koordinator till konsultbolag"}',
        "contact_name": "Rebecca",
    },
    {
        "id": "test-2",
        "name": "Drivverk AB",
        "area": "Göteborg",
        "research_notes": '{"job_headline": "Administratör med ansvar för bokningar"}',
        "contact_name": None,
    },
    {
        "id": "test-3",
        "name": "Logistik & Transport Sverige",
        "area": "Stockholm",
        "research_notes": '{"job_headline": "Orderhanterare för inkommande leveranser"}',
        "contact_name": "Johan",
    },
]

MOCK_ENRICHMENTS = [
    {
        "decision_maker": "Rebecca",
        "summary": "Konsultbolag som matchar specialister till industriprojekt, hanterar mycket koordinering och uppföljning manuellt.",
        "automation_opportunities": ["konsultmatchning och koordinering", "uppföljning av projekt"],
    },
    {
        "decision_maker": None,
        "summary": "Transportbolag som hanterar allt från små skåpbilar till tunga lastbilar.",
        "automation_opportunities": ["bokning och schemaläggning av fordon", "uppföljning av leveranser"],
    },
    {
        "decision_maker": "Johan",
        "summary": "Grossist med hög volym inkommande ordrar och manuell orderbehandling.",
        "automation_opportunities": ["orderregistrering", "leveransuppföljning och fakturastatus"],
    },
]

for i, (lead, enrich) in enumerate(zip(MOCK_LEADS, MOCK_ENRICHMENTS), 1):
    print(f"\n{'='*60}")
    print(f"TEST EMAIL {i} — {lead['name']} ({lead['area']})")
    print(f"{'='*60}")
    try:
        subject, body = generate_indeed_email(lead, enrich)
        print(f"SUBJECT: {subject}")
        print(f"\nBODY:\n{body}")

        # Verify format
        issues = []
        if "Drivverk AB" in body:       issues.append("FAIL: 'Drivverk AB' in body")
        if "CAS Automations" in body:    issues.append("FAIL: 'CAS Automations' in body")
        if "Vill du inte bli kontaktad" in body: issues.append("FAIL: old opt-out line present")
        if "—" in body or "–" in body:  issues.append("FAIL: em/en dash in body")
        if " , " in body:               issues.append("WARN: orphaned space-comma-space")
        if body.strip().endswith("Kasper"):
            issues.append("OK: signs as 'Kasper' only")
        if "Hör inte av dig" in body:
            issues.append("OK: opt-out line present")
        for issue in issues:
            print(f"\n[{issue}]")
    except Exception as e:
        print(f"ERROR: {e}")
