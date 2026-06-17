"""
Enrichment pipeline orchestration.

Input:  raw_text (str), source_url (str)
Output: {"data": dict|None, "automation_score": int, "source_url": str, "extraction_success": bool}
"""

import json
import logging

from .extractor import extract
from .scoring import compute_score

log = logging.getLogger("enrichment.pipeline")


def run_pipeline(raw_text: str, source_url: str) -> dict:
    result = {
        "data": None,
        "automation_score": 0,
        "source_url": source_url,
        "extraction_success": False,
    }

    raw_json = extract(raw_text)
    if not raw_json:
        return result

    try:
        data = json.loads(raw_json)
        result["data"] = data
        result["automation_score"] = compute_score(data)
        result["extraction_success"] = True
    except (json.JSONDecodeError, Exception) as e:
        log.warning("Enrichment JSON parse failed for %s: %s", source_url, e)

    return result
