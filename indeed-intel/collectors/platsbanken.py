"""
Platsbanken (Arbetsförmedlingen) API collector.

Fetches job postings for Stockholm using multiple search queries.
Deduplicates by posting ID and filters out staffing/recruitment agencies.
Returns postings with their full description text for task-based scoring.

API docs: https://jobtechdev.se/docs/apis/jobsearch/
No authentication required — free public API.
"""

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
)

_SESSION = requests.Session()
_SESSION.headers.update({"Accept": "application/json"})


def _is_agency(employer_name: str) -> bool:
    name_lower = employer_name.lower()
    return any(agency in name_lower for agency in AGENCY_BLOCKLIST)


def _posting_from_hit(hit: dict) -> dict | None:
    employer    = hit.get("employer", {}) or {}
    address     = hit.get("workplace_address", {}) or {}
    description = hit.get("description", {}) or {}

    employer_name = employer.get("name", "")
    if not employer_name or _is_agency(employer_name):
        return None

    desc_text = description.get("text", "") or ""
    if len(desc_text) < 200:
        return None

    # Check the posting isn't from a "vår kund"-style agency text
    text_lower = desc_text.lower()
    if "vår kund" in text_lower and "konsultuppdrag" in text_lower:
        return None

    return {
        "id":              hit.get("id", ""),
        "headline":        hit.get("headline", ""),
        "webpage_url":     hit.get("webpage_url", ""),
        "employer_name":   employer_name,
        "org_number":      employer.get("organization_number", ""),
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
    Returns list of posting dicts ready for scoring.
    """
    seen_ids: set[str] = set()
    results: list[dict] = []

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
                posting = _posting_from_hit(hit)
                if posting:
                    results.append(posting)
                    accepted += 1

            total_available = data.get("total", {}).get("value", 0)
            print(f"    -> {accepted} accepted / {len(hits)} fetched  (total available: {total_available})")
            time.sleep(0.3)  # be polite to the API

        except Exception as e:
            print(f"    [ERROR] Query failed: {e}")
            continue

    print(f"\n  [Platsbanken] Total unique postings after dedup + agency filter: {len(results)}")
    return results
