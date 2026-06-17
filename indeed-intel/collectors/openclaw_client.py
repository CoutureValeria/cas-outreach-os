"""
OpenClaw bridge client.

Primary:  POST to OpenClaw browser agent (localhost:8888) for JS-rendered page text.
Fallback: requests + BeautifulSoup4 crawl (homepage + up to 8 subpages).

Timeout: 30s. Retries once on failure.
"""

import logging
import os
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("openclaw_client")

_OPENCLAW_URL = os.environ.get("OPENCLAW_URL", "").strip() or None
_TIMEOUT = 30

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_SUBPATHS_TO_TRY = [
    "/om-oss", "/om-foretaget", "/om", "/about", "/about-us",
    "/team", "/our-team", "/personal", "/medarbetare", "/staff",
    "/kontakt", "/contact", "/contact-us",
]


_OPENCLAW_CAS_PROMPT = """You are a lead research agent for CAS Automations (Drivverk AB), \
a Swedish AI automation agency that helps SMBs automate repetitive manual work — specifically: \
phone/booking intake, customer follow-up, order processing, scheduling, and administrative workflows.

Your job is to research this company website and identify:
1. What manual, repetitive work they likely do every day
2. Whether they handle customer bookings or appointments manually
3. Whether they have live chat, contact forms, or phone as their main contact method
4. Any visible team members who appear to be owners, founders, or decision-makers \
(NOT HR, NOT marketing, NOT receptionists)
5. Company size signals (solo, 2-10, 11-50, 50+)

Visit the homepage, about page, contact page, and team page.
Ignore cookie banners and popups.
Focus on: what does this company actually DO day to day, \
and where does manual human work slow them down?

Return ONLY this JSON:
{
  "industry": "",
  "estimated_size": "",
  "phone": "",
  "email": "",
  "contact_form": false,
  "booking_system": false,
  "live_chat": false,
  "decision_maker_name": "",
  "decision_maker_role": "",
  "automation_opportunities": [],
  "summary": ""
}

If a field cannot be verified from the website, return null. \
Never guess. Never hallucinate names or contact details."""


def _openclaw_fetch(url: str) -> Optional[str]:
    if not _OPENCLAW_URL:
        return None
    payload = {
        "message": (
            "Visit this URL and extract all visible text content from the page including: "
            "company description, services, team/staff names and roles, contact details "
            "(phone/email), and any booking or scheduling information. "
            "Return the raw extracted text only, no formatting."
        ),
        "url": url,
        "expectJsonReply": False,
    }
    for attempt in range(1, 3):
        try:
            resp = requests.post(_OPENCLAW_URL, json=payload, timeout=_TIMEOUT)
            if resp.status_code == 200:
                text = resp.text.strip()
                if text:
                    return text
            log.debug("OpenClaw attempt %d: status=%s empty=%s", attempt, resp.status_code, not resp.text.strip())
        except Exception as e:
            log.debug("OpenClaw attempt %d failed: %s", attempt, e)
        if attempt < 2:
            time.sleep(2)
    return None


def _openclaw_enrich(url: str) -> Optional[dict]:
    """
    Uses the CAS-specific research prompt to extract structured company data via OpenClaw.
    Returns a parsed dict on success, None on failure or when OpenClaw is not configured.
    """
    if not _OPENCLAW_URL:
        return None
    payload = {
        "message": _OPENCLAW_CAS_PROMPT,
        "url": url,
        "expectJsonReply": True,
    }
    import json as _json
    for attempt in range(1, 3):
        try:
            resp = requests.post(_OPENCLAW_URL, json=payload, timeout=_TIMEOUT)
            if resp.status_code == 200:
                raw = resp.text.strip()
                if raw:
                    try:
                        return _json.loads(raw)
                    except _json.JSONDecodeError:
                        log.debug("OpenClaw enrich: JSON parse failed, raw=%s", raw[:200])
            log.debug("OpenClaw enrich attempt %d: status=%s", attempt, resp.status_code)
        except Exception as e:
            log.debug("OpenClaw enrich attempt %d failed: %s", attempt, e)
        if attempt < 2:
            time.sleep(2)
    return None


def _bs4_fetch_url(url: str, timeout: int = 8):
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        if "text/html" not in resp.headers.get("Content-Type", ""):
            return None, "not_html"
        soup = BeautifulSoup(resp.text, "html.parser")
        body_text = soup.get_text(" ", strip=True)
        if len(body_text) < 150 and soup.find("div", id="root"):
            return soup, "js_only"
        return soup, "ok"
    except requests.Timeout:
        return None, "timeout"
    except requests.ConnectionError:
        return None, "connection_error"
    except Exception as e:
        log.debug("bs4 fetch %s: %s", url, e)
        return None, "error"


def _bs4_crawl(url: str) -> Optional[str]:
    soup, status = _bs4_fetch_url(url)
    if not soup:
        log.warning("bs4 fallback: homepage fetch failed (%s) for %s", status, url)
        return None

    all_text = soup.get_text(" ", strip=True)
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    visited = {url.rstrip("/"), base.rstrip("/")}

    for subpath in _SUBPATHS_TO_TRY[:8]:
        sub_url = urljoin(base, subpath)
        if sub_url.rstrip("/") in visited:
            continue
        visited.add(sub_url.rstrip("/"))
        time.sleep(0.25)
        sub_soup, _ = _bs4_fetch_url(sub_url, timeout=6)
        if sub_soup:
            all_text += " " + sub_soup.get_text(" ", strip=True)

    return all_text.strip() or None


def get_page_text(url: str) -> Optional[str]:
    """
    Fetch all visible text from a company website.
    Tries OpenClaw first, falls back to BeautifulSoup crawl.
    Returns None if both methods fail.
    """
    if not url:
        return None

    url = url.strip()
    if not url.startswith("http"):
        url = f"https://{url}"

    log.info("Fetching page text: %s", url)

    text = _openclaw_fetch(url)
    if text:
        log.info("  OpenClaw: %d chars", len(text))
        return text

    log.info("  OpenClaw unavailable, using bs4 fallback")
    text = _bs4_crawl(url)
    if text:
        log.info("  bs4 fallback: %d chars", len(text))
        return text

    log.warning("  Both fetch methods failed for %s", url)
    return None


def get_company_json(url: str) -> Optional[dict]:
    """
    Fetch structured company intelligence using the CAS research prompt via OpenClaw.
    Returns a dict with the CAS JSON schema on success, None if OpenClaw is not configured
    or the request fails. Falls back to None — callers should use get_page_text() + Claude
    Haiku extraction as the fallback path.
    """
    if not url:
        return None

    url = url.strip()
    if not url.startswith("http"):
        url = f"https://{url}"

    log.info("OpenClaw enrichment (CAS prompt): %s", url)
    result = _openclaw_enrich(url)
    if result:
        log.info("  OpenClaw enrich: success")
    else:
        log.info("  OpenClaw enrich: failed or not configured")
    return result
