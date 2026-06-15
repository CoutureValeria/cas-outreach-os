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

RESULTS_PER_QUERY = 20

# ── Scoring ───────────────────────────────────────────────────────────────────
# Lowered from 50 to 40 — after government + large-corp filtering the 40-49%
# range is almost entirely genuine SMBs with real automation potential.
SCORE_THRESHOLD = 40

# ── Safety ────────────────────────────────────────────────────────────────────
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# ── Government org number prefixes ────────────────────────────────────────────
# Swedish organization numbers starting with these 2-digit prefixes are always
# government / public-sector entities (statliga myndigheter, kommuner, regioner,
# landsting). This catches ALL of them without any name matching.
#   20x = statliga myndigheter (Luftfartsverket, Arbetsförmedlingen, KTH...)
#   21x = kommuner (Stockholms Stad, Malmö Stad, Smedjebacken Kommun...)
#   22x = landsting
#   23x = regioner (Region Stockholm, Region Skåne...)
GOV_ORG_PREFIXES = {"20", "21", "22", "23"}

# ── Large enterprise name blocklist ───────────────────────────────────────────
# Private companies (5xx org numbers) too large to be realistic outreach targets.
# Will never act on a cold email from a solo founder.
# Checked against employer_name (lowercase, partial match).
ENTERPRISE_BLOCKLIST = [
    # Swedish industrial / manufacturing
    "volvo", "scania", "saab aktiebolag", "sandvik", "atlas copco", "skf",
    "alfa laval", "husqvarna", "epiroc", "autoliv", "trelleborg", "assa abloy",
    "electrolux", "nibe industrier", "hexagon", "ssab", "lkab", "boliden",
    "outokumpu", "billerud", "sca ", "stora enso", "essity", "getinge",

    # Swedish telecom / tech
    "ericsson", "telia", "tele2", "telefonaktiebolaget",

    # Swedish retail / consumer
    "ica gruppen", "ica Sverige", "axfood", "coop", "h & m ", "hennes & mauritz",
    "ikea", "åhléns", "kappahl", "lindex", "mekonomen",

    # Swedish energy / utilities
    "vattenfall", "fortum", "statkraft", "eon sverige",

    # Swedish construction
    "skanska", "ncc ", "peab", "arcona",

    # Swedish paper / packaging
    "sofidel", "mondi",

    # Swedish logistics / transport
    "postnord", "sj ab", "dsv", "db schenker", "fedex sverige",
    "dhl ", "ups sverige", "transdev", "mtr nordic",

    # Swedish banking / insurance / finance
    "nordea", "skandinaviska enskilda", "svenska handelsbanken",
    "swedbank", "länsförsäkringar", "folksam", "alecta", "amf pension",
    "skandia", "söderberg & partners",

    # Swedish security / facilities
    "securitas", "g4s", "iss facility", "sodexo", "compass group",

    # Swedish healthcare
    "capio", "aleris", "humana",

    # Swedish agriculture / food
    "arla", "lantmännen", "orkla",

    # Global tech with large Swedish presence
    "microsoft", "google", "amazon", "meta ", "apple ", "ibm",
    "accenture", "capgemini", "infosys", "tata consultancy", "wipro",
    "oracle", "sap ", "cisco",

    # Global consulting / audit
    "deloitte", "kpmg", "pricewaterhousecoopers", "pwc", "ernst & young",
    "mckinsey", "boston consulting", "bain & company",

    # Global staffing (not caught by agency blocklist due to naming variants)
    "adecco", "manpower group", "gi group", "hays plc",

    # Other large Swedish employers
    "swerock", "nobia", "bravida", "assemblin", "coor service",
    "stena ", "kinnevik", "investor ab", "industrivärden",

    # Global industrials with large Swedish presence
    "hitachi energy", "hitachi",
    "siemens", "ABB ",
    "honeywell", "johnson controls",
    "tyco", "thales",
]

# ── Known Swedish staffing / recruitment agencies to filter out ───────────────
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
    # Additional agencies caught in second run
    "aura personal", "framtiden i sverige", "framtiden ab",
    "posti logistics staffing", "posti staffing",
    "studentconsulting", "student consulting",
    "hirely", "sway sourcing",
    "experis", "bemano",
    "a-talent tech", "a-talent",
    "responda group", "responda ab",
    "ework group", "ework",
    "compass education", "barona",
    "primo jobb", "qa group", "qa Sverige",
]

# ── Output ────────────────────────────────────────────────────────────────────
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
