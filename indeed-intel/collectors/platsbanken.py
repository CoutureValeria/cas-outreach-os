"""
Platsbanken (Arbetsförmedlingen) API collector.

Fetches job postings for Stockholm using multiple search queries.
Applies three pre-filters before returning — in this order, cheapest first:
  1. Agency filter     — staffing/recruitment firms posting on behalf of clients
  2. Government filter — Swedish public-sector entities (org number prefix 20-23)
  3. Enterprise filter — large private corporations (name blocklist)

All three run BEFORE task scoring to avoid burning Claude API calls on
postings that will be rejected regardless of their task content.
"""

import re
import time
import requests

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import (
    PLATSBANKEN_BASE,
    MUNICIPALITY_STOCKHOLM,
    SEARCH_QUERIES,
    RESULTS_PER_QUERY,
    AGENCY_BLOCKLIST,
    GOV_ORG_PREFIXES,
    ENTERPRISE_BLOCKLIST,
)

_SESSION = requests.Session()
_SESSION.headers.update({"Accept": "application/json"})


_AGENCY_SUFFIX_PATTERNS = re.compile(
    r'\b(staffing|bemanning|rekrytering|rekryt|bemanningsf[öo]retag)\b',
    re.IGNORECASE,
)

# Trade unions, associations, and non-profits — not realistic cold-email targets
# Uses substring matching (no word boundaries) because terms like "förbund"
# often appear embedded in compound names like "Personskadeforbundet".
_NONPROFIT_KEYWORDS = [
    "förbund", "forbund",          # e.g. Personskadeforbundet, Byggnadsförbund
    "fackförbund", "fackforbund",  # trade union (compound)
    "facket",                      # "the union"
    "förening", "forening",        # association
    "stiftelse",                   # foundation
    "samfund",                     # society/association
    "sällskap", "sallskap",        # society
    "intresseorganisation",        # interest org
    "byggnads ",                   # "BYGGNADS NORRBOTTEN/STOCKHOLM/VÄST" — construction workers union chapters
    "kommunal ",                   # "KOMMUNAL STOCKHOLM" — municipal workers union chapters
]

def _is_agency(employer_name: str) -> bool:
    n = employer_name.lower()
    if any(a in n for a in AGENCY_BLOCKLIST):
        return True
    # Catch any name that contains staffing/bemanning keywords
    if _AGENCY_SUFFIX_PATTERNS.search(employer_name):
        return True
    return False


def _is_government(org_number: str) -> bool:
    """
    Returns True if the org number indicates a Swedish government/public-sector entity.
    Swedish org numbers: 20x = state agencies, 21x = municipalities,
    22x = county councils, 23x = regions.
    """
    if not org_number or len(org_number) < 2:
        return False
    return org_number[:2] in GOV_ORG_PREFIXES


def _is_large_enterprise(employer_name: str) -> bool:
    n = employer_name.lower()
    return any(corp in n for corp in ENTERPRISE_BLOCKLIST)


def _is_nonprofit(employer_name: str) -> bool:
    n = employer_name.lower()
    return any(kw in n for kw in _NONPROFIT_KEYWORDS)


def _filter_reason(employer_name: str, org_number: str) -> str | None:
    """Returns the filter reason string, or None if posting passes all filters."""
    if _is_agency(employer_name):
        return "agency"
    if _is_government(org_number):
        return "government"
    if _is_large_enterprise(employer_name):
        return "large enterprise"
    if _is_nonprofit(employer_name):
        return "non-profit/union"
    return None


def _posting_from_hit(hit: dict) -> dict | None:
    employer    = hit.get("employer", {}) or {}
    address     = hit.get("workplace_address", {}) or {}
    description = hit.get("description", {}) or {}

    employer_name = employer.get("name", "")
    org_number    = employer.get("organization_number", "") or ""

    if not employer_name:
        return None

    reason = _filter_reason(employer_name, org_number)
    if reason:
        return None

    desc_text = description.get("text", "") or ""
    if len(desc_text) < 200:
        return None

    text_lower = desc_text.lower()
    if "vår kund" in text_lower and "konsultuppdrag" in text_lower:
        return None

    return {
        "id":              hit.get("id", ""),
        "headline":        hit.get("headline", ""),
        "webpage_url":     hit.get("webpage_url", ""),
        "employer_name":   employer_name,
        "org_number":      org_number,
        "employer_url":    employer.get("url") or None,
        "employer_email":  employer.get("email") or None,
        "employer_phone":  employer.get("phone_number") or None,
        "city":            address.get("city", "Stockholm"),
        "street_address":  address.get("street_address", ""),
        "postcode":        address.get("postcode", ""),
        "description_text": desc_text,
    }


def fetch_postings(max_per_query: int = RESULTS_PER_QUERY) -> list[dict]:
    """
    Fetches postings from Platsbanken using all configured search queries.
    Deduplicates by posting ID.
    Applies agency + government + enterprise filters before returning.
    """
    seen_ids: set[str] = set()
    results: list[dict] = []
    filter_counts = {"agency": 0, "government": 0, "large enterprise": 0, "non-profit/union": 0, "short text": 0}

    for query in SEARCH_QUERIES:
        print(f"  [Platsbanken] Fetching: '{query}' (max {max_per_query})...")
        try:
            resp = _SESSION.get(
                PLATSBANKEN_BASE,
                params={
                    "q":                       query,
                    "municipality-concept-id": MUNICIPALITY_STOCKHOLM,
                    "limit":                   max_per_query,
                    "offset":                  0,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", [])

            accepted = 0
            for hit in hits:
                posting_id = hit.get("id", "")
                if posting_id in seen_ids:
                    continue
                seen_ids.add(posting_id)

                employer  = hit.get("employer", {}) or {}
                org_num   = employer.get("organization_number", "") or ""
                emp_name  = employer.get("name", "")

                reason = _filter_reason(emp_name, org_num)
                if reason:
                    filter_counts[reason] = filter_counts.get(reason, 0) + 1
                    continue

                posting = _posting_from_hit(hit)
                if posting:
                    results.append(posting)
                    accepted += 1
                else:
                    filter_counts["short text"] += 1

            total_available = data.get("total", {}).get("value", 0)
            print(f"    -> {accepted} accepted / {len(hits)} fetched  (total available: {total_available})")
            time.sleep(0.3)

        except Exception as e:
            print(f"    [ERROR] Query failed: {e}")
            continue

    print(f"\n  [Platsbanken] Accepted: {len(results)} | Filtered out:")
    for reason, count in filter_counts.items():
        if count:
            print(f"    {reason}: {count}")
    return results
