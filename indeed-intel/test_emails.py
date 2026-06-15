"""
Re-scores 3 postings with the new prompt, then shows before/after email comparison.
"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from scoring.task_scorer import score_posting, generate_email, extract_contact_from_text, sanitize_dashes, AUTOMATION_TYPES

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "results_20260615_170831.json")
with open(DATA_FILE, encoding="utf-8") as f:
    all_postings = json.load(f)

targets = {}
for p in all_postings:
    name = p.get("employer_name", "")
    if "Danda" in name and "Danda AB" not in targets:
        targets["Danda AB"] = p
    if "LUFTFART" in name and "LUFTFARTSVERKET" not in targets:
        targets["LUFTFARTSVERKET"] = p
    if "Cyklande" in name and "Cyklande" not in targets:
        targets["Cyklande Rormokaren"] = p

OLD_EMAILS = {
    "Danda AB": (
        "Jag sag att ni soker Support Services Specialist for att hantera "
        "orderbehandling och fakturering, har ni funderat pa om den biten gar att "
        "automatisera innan ni anstaller? Vi hjalper foretag att satta upp order- och "
        "ekonomisystem som hanterar leveransovervakning och compliance-kontroll utan manuell hantering.\n\n"
        "Kasper, Drivverk AB\n\n"
        "Vill du inte bli kontaktad igen? Svara bara pa det har mejlet."
    ),
    "LUFTFARTSVERKET": (
        "Jag sag er annons for Watch Supervisor Support, schemaläggning och hantering av "
        "personalforandringar sticker ut som nagot som ofta gar att losa med regelbaserad "
        "automatisering. Ar det den biten som tar mest tid, eller ar det annat i rollen?\n\n"
        "Kasper, Drivverk AB\n\n"
        "Vill du inte bli kontaktad igen? Svara bara pa det har mejlet."
    ),
    "Cyklande Rormokaren": (
        "(No email generated in previous run - was borderline SEND)"
    ),
}

print("=" * 65)
print("  BEFORE / AFTER -- FRESH SCORE + NEW EMAIL PROMPT")
print("=" * 65)

for label, posting in targets.items():
    old_score = posting.get("automation_fit_score", 0)
    print(f"\n\nRe-scoring {label} (was {old_score}%)...")

    contact = extract_contact_from_text(posting.get("description_text", ""))
    posting["_contact_name"] = contact

    new_score_data = score_posting(posting)
    if not new_score_data:
        print(f"  Scoring failed for {label}")
        continue

    new_score  = new_score_data.get("automation_fit_score", 0)
    atype      = new_score_data.get("automation_type", "general_admin")
    type_info  = AUTOMATION_TYPES.get(atype, AUTOMATION_TYPES["general_admin"])
    auto_tasks = new_score_data.get("automatable_tasks", [])
    non_auto   = new_score_data.get("non_automatable_tasks", [])
    total      = new_score_data.get("total_tasks", 0)

    print(f"\n{'=' * 65}")
    print(f"  {label}")
    print(f"  Score: {old_score}% -> {new_score}%  |  Type: {atype}")
    if contact:
        print(f"  Contact found in description: {contact}")
    else:
        print(f"  Contact: not found in description text")
    print(f"  Tasks: {len(auto_tasks)} automatable / {total} total")
    if auto_tasks:
        print(f"  AUTOMATABLE:")
        for t in auto_tasks:
            print(f"    + {t['task']}")
    if non_auto:
        print(f"  NOT AUTOMATABLE:")
        for t in non_auto:
            print(f"    - {t['task']}")
    print(f"  Concrete example: {type_info['example']}")

    print(f"\n  --- BEFORE (old prompt) ---")
    for line in OLD_EMAILS.get(label, "").split("\n"):
        print(f"  {line}")

    print(f"\n  --- AFTER (new prompt) ---")
    posting["score_data"] = new_score_data
    new_email = generate_email(posting, new_score_data)
    for line in new_email.split("\n"):
        print(f"  {line}")

    em_ok = "—" not in new_email and "–" not in new_email
    print(f"\n  Dash check: {'PASS - no em/en dashes' if em_ok else 'FAIL'}")
    print(f"{'=' * 65}")

print("\nDone.")
