"""
LLM extraction — calls Claude haiku to extract structured enrichment JSON from website text.
Input: raw_text (str)
Output: raw JSON string or None on failure
"""

import logging
import os
from typing import Optional

from anthropic import Anthropic

from .prompt import SYSTEM_PROMPT

log = logging.getLogger("enrichment.extractor")
_client: Optional[Anthropic] = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def extract(raw_text: str) -> Optional[str]:
    """
    Call Claude haiku to extract structured JSON from raw website text.
    Returns raw JSON string or None on failure.
    """
    if not raw_text or not raw_text.strip():
        return None

    snippet = raw_text[:6000]
    try:
        resp = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Website text:\n{snippet}"}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        return raw.strip()
    except Exception as e:
        log.warning("Claude haiku extraction failed: %s", e)
        return None
