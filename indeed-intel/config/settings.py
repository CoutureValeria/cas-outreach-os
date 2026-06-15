import os
from dotenv import load_dotenv

load_dotenv()

# ── Anthropic ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY not set")

# ── Email engine webhook ──────────────────────────────────────────────────────
EMAIL_ENGINE_URL     = os.getenv("EMAIL_ENGINE_URL", "https://cas-email-engine-backend-production-3b02.up.railway.app")
EMAIL_ENGINE_API_KEY = os.getenv("EMAIL_ENGINE_API_KEY")
if not EMAIL_ENGINE_API_KEY:
    raise RuntimeError("EMAIL_ENGINE_API_KEY not set")

# ── Platsbanken API ───────────────────────────────────────────────────────────
PLATSBANKEN_BASE = "https://jobsearch.api.jobtechdev.se/search"

# Stockholm municipality concept ID
MUNICIPALITY_STOCKHOLM = "0180"

# Broad queries that surface admin/scheduling/coordination roles.
# No role-title filter — the scorer decides what's automatable.
# These are starting points to get a representative cross-section.
SEARCH_QUERIES = [
    "koordinator planering administration",
    "receptionist kundtjanst",
    "administratör kontor",
    "backoffice support administration",
    "kontorsassistent",
    "sekreterare administration",
    "kundservice inkommande",
    "schemaläggning personal",
]

# How many postings to fetch per query
RESULTS_PER_QUERY = 20

# ── Scoring ───────────────────────────────────────────────────────────────────
SCORE_THRESHOLD = 50   # >= SEND, < IGNORE

# ── Safety ────────────────────────────────────────────────────────────────────
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# ── Known Swedish staffing / recruitment agencies to filter out ───────────────
# We want the company POSTING the job — not agencies brokering on their behalf.
AGENCY_BLOCKLIST = [
    "adecco", "manpower", "randstad", "academic work", "tng group",
    "poolia", "perido", "uniflex", "bemannia", "speed group",
    "wise professionals", "wise group", "dfind", "recruitive", "talent & partner",
    "jobbunster", "bravura", "inhouse", "novare", "eterni",
    "clevry", "jurek", "axenn", "professionals nord", "jeffs",
    "careerbuilder", "michael page", "robert half", "hays", "pagegroup",
    "jobbusters", "the woerk", "bemanning", "rekryt", "bemanningsföretag",
    "2complete", "standby", "studentwork", "lernia", "performiq",
    "hero ab", "jobs europe",
]

# ── Output ────────────────────────────────────────────────────────────────────
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
