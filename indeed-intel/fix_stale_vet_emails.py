"""
fix_stale_vet_emails.py — Regenerates vet lead emails stored before the 2026-06-18 prompt fixes.

Targets: approved/generated veterinary leads with old body format
('Drivverk AB', 'Vill du inte bli kontaktad', 'Svara bara').

Rebuilds the same prompt as emailService.js buildEmailPrompt(), calls claude-opus-4-7,
and patches Supabase with new subject + body.
"""

import json
import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(__file__))
from scoring.task_scorer import sanitize_email

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = ""
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.startswith("ANTHROPIC_API_KEY="):
                ANTHROPIC_API_KEY = line.split("=", 1)[1].strip()
                break
if not ANTHROPIC_API_KEY:
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SUPABASE_URL     = "https://tjpkmonazlqmbaazcker.supabase.co"
SUPABASE_SVC_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRqcGttb25hemxxbWJhYXpja2VyIiwicm9sZSI6"
    "InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3ODE2MDM5MiwiZXhwIjoyMDkzNzM2MzkyfQ."
    "mjtJWBbzozd6PVojq_j0bNHQwWpwTabRT2tmkAo3Qi4"
)

_SB_HEADERS = {
    "apikey":        SUPABASE_SVC_KEY,
    "Authorization": f"Bearer {SUPABASE_SVC_KEY}",
    "Content-Type":  "application/json",
}

OLD_MARKERS = ["Vill du inte bli kontaktad", "Drivverk AB", "Svara bara"]


def is_stale(body: str) -> bool:
    return any(m in (body or "") for m in OLD_MARKERS)


def extract_first_name(full_name: str | None) -> str | None:
    if not full_name:
        return None
    name = full_name.strip()
    first = name.split()[0] if name.split() else None
    if not first or len(first) < 2:
        return None
    BLOCKLIST = ["högst", "ansvarig", "verksamhets", "klinik", "bitr", "vice", "övrig", "null"]
    if any(first.lower().startswith(b) for b in BLOCKLIST):
        return None
    if not re.match(r'^[A-ZÅÄÖ]', first):
        return None
    return first


def build_vet_email_prompt(lead: dict, research: dict | None) -> str:
    """Mirrors emailService.js buildEmailPrompt() exactly."""
    has_automation = research and research.get("automatable_problem") is True
    problem_type   = (research or {}).get("problem_type") or lead.get("primary_pain") or ""
    evidence       = (research or {}).get("evidence") or lead.get("pain_evidence") or ""
    pain_source    = (research or {}).get("pain_source") or lead.get("pain_source") or "review"
    is_structural  = pain_source in ("structural",) or (pain_source or "").find("structural") >= 0

    first_name = extract_first_name(
        lead.get("contact_name")
        or (research or {}).get("contactName")
        or (research or {}).get("decision_maker_name")
    )

    fn = f" {first_name}" if first_name else ""

    structural_block = f"""
The pain is STRUCTURAL: observable from the clinic's website, not reviews.
Open with a direct, casual observation. Start with "Hej{fn}, jag märkte att..." or "Hej{fn}, jag noterade att..."
Examples:
  no booking system → "Hej{fn}, jag märkte att ni inte verkar ha ett bokningssystem online, är det telefon som gäller för att boka tid?"
  phone-only contact → "Hej{fn}, jag noterade att telefon verkar vara det enda sättet att nå er, hur hanterar ni förfrågningar som kommer in när ni är mitt i ett besök?"
Pain fact to reference: {evidence or problem_type}
DO NOT reference reviews. This signal came from their website or Places data.
"""

    review_block = f"""
Reference the real signal you found, paraphrased casually. Never quote word for word.
Start with "Hej{fn}, jag såg att..." or "Hej{fn}, jag märkte att..."
Examples:
  missed calls → "Hej{fn}, jag såg att några kunder nämnt att det ibland varit svårt att nå er på telefon."
  slow follow-up → "Hej{fn}, jag märkte att ett par kunder tagit upp att återkopplingen ibland dröjt."
Match the tone to the actual signal: {problem_type}
"""

    fallback_block = f"""
Use this fallback opener. Do NOT invent a problem:
"Hej{fn}, jag är nyfiken på hur ni hanterar inkommande bokningsförfrågningar när ni är mitt i ett besök."
"""

    if is_structural:
        line1_block = structural_block
    elif has_automation:
        line1_block = review_block
    else:
        line1_block = fallback_block

    return f"""
Write a short cold outreach email in Swedish for a veterinary clinic.
This is a DISCOVERY email. The goal is to get them talking about their problem. Do NOT pitch a solution.

Clinic: {lead.get("name", "")}
Area: {lead.get("area", "")}
{f'Contact name: {first_name} (use as greeting: "Hej {first_name}," not generic "Hej,")' if first_name else ""}
{f'''
Identified signal from their reviews/website: {problem_type}
Evidence (paraphrase this, never quote verbatim): "{evidence}"
''' if has_automation else "No specific pain signal found."}

FORMAT: 3 lines + sign-off. Short. Sounds like a curious human, not a sales pitch.

LINE 1: The opener (same personalisation logic as always):
{line1_block}

LINES 2-3: Discovery question (NOT a solution pitch):
Ask one or two short, genuine questions about which operational area feels heaviest right now.
The question should flow naturally from the opener. No product. No "we" or "our solution".
Make it feel like a curious person asking, not a sales sequence.

These are example angles (generate naturally, not copy verbatim):
  - "Vad tar mest tid av det administrativa just nu, samtal, bokningar, eller uppföljning?"
  - "Är det mest inkommande samtal eller mer journalhantering och uppföljning som äter tid?"
  - "Märker ni av många missade samtal, eller är det mer uppföljning och administration som känns tyngst?"
  - "Hur hanterar ni förfrågningar som trillar in utanför öppettiderna, är det ett problem ni stöter på ofta?"

The question IS the closing. No separate CTA line.

Blank line.
Line (exact): Hör inte av dig om det inte känns relevant, ingen stress.
Blank line.
Sign-off (exact): Kasper

RULES:
- This is a discovery email: no solution, no pitch, no "Vi löser det"
- No "AI" anywhere in the email
- No bullet points, no bold, no headers, no dashes, no em dashes
- Maximum 3 lines before the "Hör inte av dig" line
- Problem in line 1 must be real and from this clinic's signal, never invent
- Paraphrase only, never quote verbatim
- If no signal exists, use the fallback opener
- Never use "vi" (we): ALWAYS use "jag" (I). Not "vi hjälper", not "vi ser", not "vi erbjuder"
- Never mention Drivverk AB, CAS Automations, or any company name
- Sound like a curious individual who stumbled on this clinic, NOT a company doing outreach

Also write a short subject line in Swedish (max 7 words, no spam words).

Respond in this exact format:
SUBJECT: [subject here]
BODY:
[full email body here]
""".strip()


def call_claude(prompt: str) -> str:
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key":         ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        json={
            "model":      "claude-opus-4-7",
            "max_tokens": 512,
            "messages":   [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def parse_response(text: str, lead_name: str) -> tuple[str, str]:
    subject_m = re.search(r"SUBJECT:\s*(.+)", text)
    body_m    = re.search(r"BODY:\s*([\s\S]+)", text)
    subject = subject_m.group(1).strip() if subject_m else f"Fråga till {lead_name}"
    body    = body_m.group(1).strip()    if body_m    else text.strip()
    return sanitize_email(subject), sanitize_email(body)


def patch_lead(lead_id: str, subject: str, body: str) -> bool:
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/leads?id=eq.{lead_id}",
        headers={**_SB_HEADERS, "Prefer": "return=minimal"},
        json={"subject": subject, "body": body},
        timeout=10,
    )
    return resp.status_code in (200, 204)


def main(dry_run: bool = False):
    print("Fetching stale approved/generated vet leads...")
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/leads",
        headers=_SB_HEADERS,
        params={"select": "*", "status": "in.(approved,generated)", "type": "eq.veterinary"},
        timeout=15,
    )
    leads = resp.json()
    stale = [l for l in leads if is_stale(l.get("body") or "")]
    print(f"Found {len(stale)} stale vet leads\n")

    if not stale:
        print("Nothing to fix.")
        return

    if dry_run:
        print("[DRY RUN — no changes written]\n")

    fixed = failed = 0

    for lead in stale:
        name    = lead.get("name", "?")
        lead_id = lead.get("id", "")

        print(f"── {name} (id={lead_id})")

        research = None
        rn_raw = lead.get("research_notes")
        if rn_raw:
            try:
                research = json.loads(rn_raw)
            except Exception:
                pass

        prompt = build_vet_email_prompt(lead, research)

        try:
            raw = call_claude(prompt)
            subject, body = parse_response(raw, name)
        except Exception as e:
            print(f"  ✗ Generation failed: {e}")
            failed += 1
            continue

        print(f"  NEW SUBJECT: {subject}")
        print(f"  NEW BODY:\n{body}\n")

        # Sanity check
        remaining_issues = [m for m in OLD_MARKERS if m in body]
        if remaining_issues:
            print(f"  ✗ Still has old markers: {remaining_issues} — NOT patching")
            failed += 1
            continue

        if dry_run:
            print("  [DRY RUN] Would PATCH Supabase")
            fixed += 1
            continue

        ok = patch_lead(lead_id, subject, body)
        if ok:
            print(f"  ✓ Patched in Supabase")
            fixed += 1
        else:
            print(f"  ✗ Supabase PATCH failed")
            failed += 1

        time.sleep(0.5)

    print(f"\n══ DONE — fixed: {fixed}  failed: {failed} ══")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    main(dry_run=args.dry_run)
