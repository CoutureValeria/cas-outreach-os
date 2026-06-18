"""
Task-based scoring engine for job postings.

Uses Claude claude-haiku-4-5-20251001 to:
  1. Read the full posting description
  2. Extract every listed task/responsibility + classify automatable vs not
  3. Calculate automation_fit_score = (automatable / total) * 100
  4. Identify automation_type (category) for concrete example mapping
  5. Generate email using general category framing, not mirrored task list

Score tiers:
  HIGH   (75-100): direct — "funderat pa automatisering?"
  MODERATE (50-74): discovery — general category + concrete example
  IGNORE (<50):    discard
"""

import json
import re
import requests
import anthropic

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import ANTHROPIC_API_KEY, SCORE_THRESHOLD

_CLIENT = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
_MODEL  = "claude-haiku-4-5-20251001"


# ── Dash sanitizer (shared) ────────────────────────────────────────────────────

def sanitize_email(text: str) -> str:
    """
    Strips em dashes and en dashes from any Claude-generated text before it
    reaches Supabase or Resend. Prompt rules alone are not reliable (Claude
    ignores them ~20% of the time). Applied to all outbound email text.
    """
    if not text:
        return text
    text = text.replace("—", ",")
    text = text.replace("–", ",")
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\s+,\s+", ", ", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()

# Alias for backwards compatibility with any callers using the old name
sanitize_dashes = sanitize_email


# ── Automation type → concrete example + Swedish label ────────────────────────

AUTOMATION_TYPES = {
    "booking_scheduling": {
        "label": "bokning och schemaläggning",
        "example": "T.ex. kan kunder boka tid via SMS, och systemet bekräftar och påminner automatiskt.",
    },
    "order_invoicing": {
        "label": "uppföljning av leveranser och fakturor",
        "example": "T.ex. skickar systemet automatiskt påminnelser om obetalda fakturor och uppdaterar status när betalning kommer in.",
    },
    "customer_intake": {
        "label": "inkommande förfrågningar och kundkontakt",
        "example": "T.ex. svarar ett system automatiskt på vanliga frågor via chatt eller SMS, dygnet runt.",
    },
    "coordination_routing": {
        "label": "koordinering och resursstyrning",
        "example": "T.ex. kan systemet ta emot förfrågningar, sortera dem och skicka vidare till rätt person utan manuell hantering.",
    },
    "admin_documentation": {
        "label": "administrativ hantering och dokumentation",
        "example": "T.ex. kan ett system automatiskt generera och skicka bekräftelser, avtal och dokumentation.",
    },
    "general_admin": {
        "label": "administrativt arbete och uppföljning",
        "example": "T.ex. kan rutinmässig kommunikation och uppföljning skötas automatiskt utan att någon behöver göra det manuellt.",
    },
}


# ── Contact extraction from description text ──────────────────────────────────

_CONTACT_PATTERNS = [
    r'[Kk]ontakta(?:person)?:?\s+([A-ZÅÄÖ][a-zåäö]+(?:\s+[A-ZÅÄÖ][a-zåäö]+){1,2})',
    r'[Hh]ar du fr[åa]gor\??\.?\s*[Kk]ontakta\s+([A-ZÅÄÖ][a-zåäö]+(?:\s+[A-ZÅÄÖ][a-zåäö]+){1,2})',
    r'[Ff]r[åa]gor.*?kontakta\s+([A-ZÅÄÖ][a-zåäö]+(?:\s+[A-ZÅÄÖ][a-zåäö]+){1,2})',
    r'[Vv]älkommen att kontakta\s+([A-ZÅÄÖ][a-zåäö]+(?:\s+[A-ZÅÄÖ][a-zåäö]+){1,2})',
    r'[Mm]er information.*?kontakta\s+([A-ZÅÄÖ][a-zåäö]+(?:\s+[A-ZÅÄÖ][a-zåäö]+){1,2})',
    r'[Rr]ekryterande.*?chef:?\s+([A-ZÅÄÖ][a-zåäö]+(?:\s+[A-ZÅÄÖ][a-zåäö]+){1,2})',
    r'[Ff]r[åa]gor om tj[äa]nsten.*?([A-ZÅÄÖ][a-zåäö]+(?:\s+[A-ZÅÄÖ][a-zåäö]+){1,2})',
]

# Titles/words that would falsely match as names
_NAME_BLOCKLIST = {
    "mer", "information", "om", "oss", "dig", "den", "det", "har", "kan",
    "gärna", "direkt", "kontakt", "ansökan", "rekrytering", "chef",
}


def extract_contact_from_text(text: str) -> str | None:
    """Extract recruiter/contact first name from posting description text."""
    if not text:
        return None
    for pattern in _CONTACT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            full_name = m.group(1).strip()
            parts = full_name.split()
            if not parts:
                continue
            first = parts[0].lower()
            if first in _NAME_BLOCKLIST or len(parts[0]) < 2:
                continue
            # Return just first name for greeting
            return parts[0]
    return None


def _company_context(posting: dict) -> str:
    """
    Extracts a brief company context line from the posting description.
    Takes the first non-empty sentence from the description (usually company intro).
    """
    text = posting.get("description_text", "")
    if not text:
        return ""
    # Try to get first real sentence (up to 200 chars)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    for s in sentences:
        s = s.strip()
        if 30 < len(s) < 250 and not s.startswith("Du ") and not s.startswith("Vi "):
            return s
    return text[:180].strip()


# ── Scoring prompt ─────────────────────────────────────────────────────────────

_SCORE_PROMPT_TEMPLATE = """\
You are analyzing a Swedish job posting to determine what fraction of the listed tasks could be automated.

AUTOMATABLE (counts toward score):
- Booking/scheduling/routing: boka, planera, schemalägga resor, tider, möten, kalendrar
- Intake/triage: hantera inkommande samtal, mail, bokningsförfrågningar, ärenden
- Coordination/routing: koordinera, vidarebefordra, samordna resurser, personal, leveranser
- Repetitive admin: fakturering, registrering, arkivering, kontraktshantering, orderhantering
- Routine communication: skicka påminnelser, bekräfta tider, svara på standardfrågor, kontakt med leverantör/bank/kund för rutinärenden

NOT AUTOMATABLE:
- Physical presence at a location for the core work (städning, inspektion, hantverkare, körning)
- Specialized expert judgment (teknisk diagnos, juridisk rådgivning, medicinsk bedömning, veterinär)
- Face-to-face client interaction as the PRIMARY value (personlig assistent, hemtjänst, mötesfacilitering)
- Strategic/creative decisions (produktutveckling, marknadsföringsstrategi, management)

AUTOMATION TYPE — pick the single best match for the dominant automatable pattern:
  "booking_scheduling"    — primary work is booking/scheduling/calendar
  "order_invoicing"       — primary work is orders, invoicing, delivery follow-up
  "customer_intake"       — primary work is inbound customer contact, FAQ, triage
  "coordination_routing"  — primary work is routing tasks/people/resources
  "admin_documentation"   — primary work is paperwork, contracts, archiving
  "general_admin"         — mixed or none of the above fit well

RULES:
- Only count tasks EXPLICITLY listed in the posting as responsibilities/arbetsuppgifter
- Ignore qualifications, requirements, company descriptions
- A task is automatable if MOST of what is needed is information routing, not physical action or expert judgment
- Mixed tasks (e.g. "planera och genomföra event"): count as NOT automatable (physical execution required)
- Return ONLY valid JSON, no markdown, no explanation

Return this exact JSON structure:
{
  "total_tasks": <integer>,
  "automatable_tasks": [
    {"task": "<short description>", "reason": "<why automatable>"}
  ],
  "non_automatable_tasks": [
    {"task": "<short description>", "reason": "<why not>"}
  ],
  "automation_fit_score": <integer 0-100>,
  "automation_type": "<one of the six types above>",
  "automation_angle": "<1 sentence in Swedish: what specifically could be automated>",
  "confidence": "<high or medium or low>"
}

Job posting:
---
TEXT_PLACEHOLDER
---
"""

# ── Email prompt ───────────────────────────────────────────────────────────────

_EMAIL_PROMPT_TEMPLATE = """\
Write a cold outreach email in Swedish from Kasper. This must sound like a curious individual, NOT a company doing outreach.

CONTEXT (use to understand the company, do NOT repeat back to them):
  Company: EMPLOYER_NAME
  Job posted: HEADLINE
  Company intro (1 sentence from their posting): COMPANY_CONTEXT
  Automation category found: AUTOMATION_TYPE_LABEL
  Concrete example for this category: CONCRETE_EXAMPLE
  Contact name (if available): CONTACT_NAME

STRUCTURE — exactly 3 lines/sentences before sign-off:
  LINE 1: Greeting. If contact_name is set use "Hej CONTACT_NAME," else "Hej,". Then one short sentence: "jag såg er annons för [role type]," referencing the job headline.
  LINE 2: A genuine question: "Den typen av roll involverar ofta mycket [AUTOMATION_TYPE_LABEL], är det något ni känner igen?"
  LINE 3: "Eller har ni redan koll på det?"

Blank line.
Hör inte av dig om det inte känns relevant — ingen stress.
Blank line.
Sign-off (exact): Kasper

STRICT RULES — violating these means the email fails:
- NEVER use "vi" (we) — always "jag" (I). Not "vi hjälper", not "vi jobbar", not "vi erbjuder"
- NEVER mention Drivverk AB, CAS Automations, or any company name
- Do NOT use em dashes or en dashes anywhere. Use comma or period instead.
- Do NOT mention AI, bots, or technology brands
- Do NOT pitch a solution — only ask a question
- Write natural Swedish with proper Swedish characters (å, ä, ö)
- Output ONLY the email text, nothing else
"""


def _truncate_text(text: str, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[...truncated]"


# ── Score a posting ────────────────────────────────────────────────────────────

def score_posting(posting: dict) -> dict | None:
    """
    Scores a single posting for automation fit.
    Returns score dict or None if scoring fails.
    """
    text = posting.get("description_text", "")
    if not text:
        return None

    prompt = _SCORE_PROMPT_TEMPLATE.replace("TEXT_PLACEHOLDER", _truncate_text(text))

    try:
        resp = _CLIENT.messages.create(
            model=_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)

    except (json.JSONDecodeError, Exception) as e:
        print(f"    [Scorer] Failed for '{posting.get('headline', '?')}': {e}")
        return None


# ── Generate email ─────────────────────────────────────────────────────────────

def generate_email(posting: dict, score_data: dict) -> str:
    """
    Generates a Swedish cold email.
    Uses general category framing (not mirrored task list).
    Sanitizes dashes from output.
    """
    atype        = score_data.get("automation_type", "general_admin")
    type_info    = AUTOMATION_TYPES.get(atype, AUTOMATION_TYPES["general_admin"])
    type_label   = type_info["label"]
    example      = type_info["example"]

    contact_name = posting.get("_contact_name") or ""
    company_ctx  = _company_context(posting)

    prompt = (
        _EMAIL_PROMPT_TEMPLATE
        .replace("EMPLOYER_NAME",        posting.get("employer_name", ""))
        .replace("HEADLINE",             posting.get("headline", ""))
        .replace("COMPANY_CONTEXT",      company_ctx)
        .replace("AUTOMATION_TYPE_LABEL", type_label)
        .replace("CONCRETE_EXAMPLE",     example)
        .replace("CONTACT_NAME",         contact_name or "(none)")
    )

    try:
        resp = _CLIENT.messages.create(
            model=_MODEL,
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        return sanitize_email(raw)
    except Exception as e:
        return f"[Email generation failed: {e}]"


# ── Score all postings ─────────────────────────────────────────────────────────

def score_all(postings: list[dict]) -> list[dict]:
    """
    Scores all postings. Extracts contact name from description before scoring.
    Returns list of enriched posting dicts.
    """
    results = []

    for i, posting in enumerate(postings, 1):
        headline = posting.get("headline", "?")
        employer = posting.get("employer_name", "?")
        print(f"  [{i}/{len(postings)}] Scoring: {headline[:50]} -- {employer[:40]}...")

        # Extract contact name from description text
        contact = extract_contact_from_text(posting.get("description_text", ""))
        posting["_contact_name"] = contact

        score_data = score_posting(posting)

        if score_data is None:
            posting["score_data"]          = None
            posting["automation_fit_score"] = 0
            posting["bucket"]               = "error"
            results.append(posting)
            continue

        score = score_data.get("automation_fit_score", 0)
        posting["score_data"]          = score_data
        posting["automation_fit_score"] = score
        posting["bucket"]               = "SEND" if score >= SCORE_THRESHOLD else "IGNORE"

        results.append(posting)

    return results
