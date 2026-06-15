"""
Task-based scoring engine for job postings.

Uses Claude claude-haiku-4-5-20251001 to:
  1. Read the full posting description
  2. Extract every listed task/responsibility
  3. Classify each as AUTOMATABLE or NOT_AUTOMATABLE
  4. Calculate automation_fit_score = (automatable / total) * 100

AUTOMATABLE tasks — booking/scheduling/routing/admin:
  - Boka/planera resor, tider, möten
  - Hantera inkommande samtal/bokningar/mail
  - Koordinera leveranser, resurser, personal
  - Enklare bokföring, fakturering, administration
  - Kontakt med bank/leverantör/kund för rutinärenden
  - Besvara repetitiva frågor, bekräfta avtalade tider, skicka påminnelser
  - Orderhantering, ärendeloggning, dataregistrering

NOT AUTOMATABLE tasks:
  - Physical presence required (hantverkare, städning, inspektion)
  - Specialized judgment (teknisk diagnos, juridik, medicin)
  - Face-to-face interaction is the CORE of the role (mötesbaserad rådgivning)
  - Creative/strategic decisions (marknadsföring, produktutveckling)

Score tiers:
  HIGH   (75-100): direct pitch — "har ni funderat på automatisering?"
  MODERATE (50-74): discovery — reference specific automatable tasks
  IGNORE (<50):   discard
"""

import json
import re
import anthropic

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import ANTHROPIC_API_KEY, SCORE_THRESHOLD

_CLIENT = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
_MODEL  = "claude-haiku-4-5-20251001"

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

RULES:
- Only count tasks EXPLICITLY listed in the posting as responsibilities/arbetsuppgifter
- Ignore qualifications, requirements, company descriptions — only score TASKS
- A task is automatable if MOST of what's needed is information routing, not physical action or expert judgment
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
  "automation_angle": "<1 sentence in Swedish: what specifically could be automated>",
  "confidence": "<high or medium or low>"
}

Job posting:
---
TEXT_PLACEHOLDER
---
"""

_EMAIL_PROMPT = """\
Write a short, direct cold email in Swedish from Kasper at Drivverk AB to the company "{employer_name}"
that just posted a job ad for "{headline}".

Context:
- Automation fit score: {score}%
- Automatable tasks found: {automatable_list}
- Automation angle: {automation_angle}

Email style based on score:
{style_instruction}

Rules:
- 2-3 sentences max before sign-off
- No generic filler like "Hoppas allt är bra" or "Mitt namn är"
- Start directly with the observation about their posting or their specific task
- Reference SPECIFIC tasks from the posting — not generic "administration"
- End with sign-off: "Kasper, Drivverk AB"
- Footer (last line): "Vill du inte bli kontaktad igen? Svara bara på det här mejlet."
- Tone: direct, confident, curious — not salesy
- Output ONLY the email text, nothing else

HIGH score style: Direct — "Jag såg att ni söker [role] för att hantera [specific task] — har ni funderat på om det går att automatisera innan ni anställer?"
MODERATE score style: Discovery — "Jag såg er annons för [role] — [specific automatable task] sticker ut som något som ofta går att lösa med automatisering. Är det den biten som tar mest tid, eller är det annat i rollen?"
"""


def _truncate_text(text: str, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    # Keep beginning and relevant section
    return text[:max_chars] + "\n[...truncated]"


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

        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        data = json.loads(raw)
        return data

    except (json.JSONDecodeError, Exception) as e:
        print(f"    [Scorer] Failed for '{posting.get('headline', '?')}': {e}")
        return None


def generate_email(posting: dict, score_data: dict) -> str:
    """
    Generates a Swedish cold email based on the score tier and automatable tasks.
    """
    score = score_data.get("automation_fit_score", 0)
    auto_tasks = score_data.get("automatable_tasks", [])
    automation_angle = score_data.get("automation_angle", "")

    automatable_list = "; ".join(t["task"] for t in auto_tasks[:4]) or "generell administration"

    if score >= 75:
        style_instruction = (
            "HIGH score: Direct pitch. Ask if they've considered automating before hiring. "
            "Reference the specific automatable task most prominently listed."
        )
    else:
        style_instruction = (
            "MODERATE score: Discovery angle. Reference the specific automatable task. "
            "Ask if that's the most time-consuming part, or if there's something else."
        )

    prompt = _EMAIL_PROMPT.format(
        employer_name=posting.get("employer_name", ""),
        headline=posting.get("headline", ""),
        score=score,
        automatable_list=automatable_list,
        automation_angle=automation_angle,
        style_instruction=style_instruction,
    )

    try:
        resp = _CLIENT.messages.create(
            model=_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        return f"[Email generation failed: {e}]"


def score_all(postings: list[dict]) -> list[dict]:
    """
    Scores all postings. Returns list of enriched posting dicts with score data.
    Includes ALL postings (scored + unscored), so caller can compute full distribution.
    """
    results = []

    for i, posting in enumerate(postings, 1):
        headline = posting.get("headline", "?")
        employer = posting.get("employer_name", "?")
        print(f"  [{i}/{len(postings)}] Scoring: {headline[:50]} — {employer[:40]}...")

        score_data = score_posting(posting)

        if score_data is None:
            posting["score_data"] = None
            posting["automation_fit_score"] = 0
            posting["bucket"] = "error"
            results.append(posting)
            continue

        score = score_data.get("automation_fit_score", 0)
        posting["score_data"] = score_data
        posting["automation_fit_score"] = score

        if score >= SCORE_THRESHOLD:
            posting["bucket"] = "SEND"
        else:
            posting["bucket"] = "IGNORE"

        results.append(posting)

    return results
