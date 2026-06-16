"""
Company website enrichment module (requests + BeautifulSoup4 + Claude haiku).

Fetching: requests + bs4 scrape of homepage + up to 8 subpages.
Extraction: Claude haiku-4-5 interprets all scraped text and returns structured JSON.
Phone/email: extracted directly from HTML (more reliable than Claude for raw strings).

Returns a dict matching the OpenClaw schema.
"""

import json
import logging
import os
import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse, unquote

import requests
from anthropic import Anthropic
from bs4 import BeautifulSoup

log = logging.getLogger("enrichment")
if not log.handlers:
    import sys
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s [enrich] %(levelname)s %(message)s",
                                     datefmt="%H:%M:%S"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_PHONE_RE = re.compile(
    r'\b(?:\+46[\s\-]?|0)'
    r'(?:\d{2,3}[\s\-]?\d{3,4}[\s\-]?\d{2,4}'
    r'|\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})\b'
)
_EMAIL_RE = re.compile(
    r'\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b'
)

_SUBPATHS_TO_TRY = [
    '/om-oss', '/om-foretaget', '/om', '/about', '/about-us',
    '/team', '/our-team', '/personal', '/medarbetare', '/staff',
    '/kontakt', '/contact', '/contact-us',
]

_CLAUDE_SYSTEM = (
    "You extract structured business intelligence from raw Swedish company website text. "
    "Return ONLY valid JSON, never guess missing data, never hallucinate. "
    "If a field is unknown, return null.\n"
    "Fields:\n"
    '{"industry": "cleaning|automotive|construction|transport|food|consulting|'
    'electrical|real_estate|accounting|rental|other or null", '
    '"estimated_size": "solo|2-10|11-50|50+ or null", '
    '"phone": "phone number string or null", '
    '"email": "email address string or null", '
    '"contact_form": true or false, '
    '"booking_system": true or false, '
    '"live_chat": true or false, '
    '"decision_maker_name": "first name only or null", '
    '"decision_maker_role": "role/title or null", '
    '"automation_opportunities": ["opportunity 1", "opportunity 2", "..."], '
    '"summary": "2 sentences max describing business and automation potential"}'
)

_anthropic: Optional[Anthropic] = None


def _client() -> Anthropic:
    global _anthropic
    if _anthropic is None:
        _anthropic = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _anthropic


def _fetch(url: str, timeout: int = 8) -> tuple[Optional[BeautifulSoup], str]:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        ct = resp.headers.get('Content-Type', '')
        if 'text/html' not in ct:
            return None, 'not_html'
        soup = BeautifulSoup(resp.text, 'html.parser')
        body_text = soup.get_text(' ', strip=True)
        if len(body_text) < 150 and soup.find('div', id='root'):
            return soup, 'js_only'
        return soup, 'ok'
    except requests.Timeout:
        return None, 'timeout'
    except requests.ConnectionError:
        return None, 'connection_error'
    except requests.HTTPError as e:
        return None, f'http_{e.response.status_code}'
    except Exception as e:
        log.debug("Fetch %s: %s", url, e)
        return None, 'error'


def _phones(soup: BeautifulSoup) -> list[str]:
    phones = []
    for a in soup.find_all('a', href=re.compile(r'^tel:', re.I)):
        raw = unquote(a['href'].replace('tel:', '')).strip()
        clean = re.sub(r'\s', '', raw)
        if clean:
            phones.append(raw)
    text = soup.get_text(' ', strip=True)
    for m in _PHONE_RE.findall(text):
        clean = re.sub(r'\s', '', m)
        if clean not in {re.sub(r'\s', '', p) for p in phones}:
            phones.append(m.strip())
    return phones[:3]


def _emails(soup: BeautifulSoup) -> list[str]:
    found = set()
    for a in soup.find_all('a', href=re.compile(r'^mailto:', re.I)):
        addr = a['href'].replace('mailto:', '').split('?')[0].strip().lower()
        if '@' in addr:
            found.add(addr)
    text = soup.get_text(' ', strip=True)
    for m in _EMAIL_RE.findall(text):
        ml = m.lower()
        if any(ml.endswith(x) for x in ('.png', '.jpg', '.gif', '.svg')):
            continue
        if any(x in ml for x in ('@example', '@noreply', '@sentry', '@pixel', '@w3')):
            continue
        found.add(ml)
    return list(found)[:2]


def _extract_with_claude(all_text: str, company_name: str) -> dict:
    snippet = all_text[:6000]
    user_msg = f"Company: {company_name}\n\nWebsite text:\n{snippet}"
    try:
        resp = _client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            temperature=0,
            system=_CLAUDE_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = resp.content[0].text.strip()
        # Strip markdown fences
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        log.warning("Claude haiku extraction failed for %s: %s", company_name, e)
        return {}


def enrich_company(company_name: str, website: Optional[str]) -> dict:
    result = {
        "company_name":             company_name,
        "website":                  website,
        "industry":                 None,
        "estimated_size":           None,
        "phone":                    None,
        "email":                    None,
        "contact_form":             False,
        "booking_system":           False,
        "live_chat":                False,
        "decision_maker":           None,
        "decision_maker_role":      None,
        "automation_opportunities": [],
        "summary":                  None,
        "scrape_status":            "no_website",
    }

    if not website:
        result["summary"] = "No website — enrichment skipped."
        return result

    url = website if website.startswith('http') else f"https://{website}"
    log.info("Enriching: %s  (%s)", company_name, url)

    soup, status = _fetch(url)
    if not soup:
        result["scrape_status"] = status
        result["summary"] = f"Homepage fetch failed ({status})."
        return result
    if status == 'js_only':
        result["scrape_status"] = "js_only"

    # ── Direct HTML extraction for phone/email (more reliable than Claude) ──
    phones = _phones(soup)
    emails = _emails(soup)
    result["phone"] = phones[0] if phones else None
    result["email"] = emails[0] if emails else None

    all_text = soup.get_text(' ', strip=True)

    # ── Crawl subpages ─────────────────────────────────────────────────────
    base    = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    visited = {url.rstrip('/'), base.rstrip('/')}

    for subpath in _SUBPATHS_TO_TRY[:8]:
        sub_url = urljoin(base, subpath)
        if sub_url.rstrip('/') in visited:
            continue
        visited.add(sub_url.rstrip('/'))

        time.sleep(0.25)
        sub_soup, _ = _fetch(sub_url, timeout=6)
        if not sub_soup:
            continue

        sub_text = sub_soup.get_text(' ', strip=True)
        all_text += ' ' + sub_text

        if not result["phone"]:
            ps = _phones(sub_soup)
            if ps:
                result["phone"] = ps[0]
        if not result["email"]:
            es = _emails(sub_soup)
            if es:
                result["email"] = es[0]

    # ── Claude haiku extraction ────────────────────────────────────────────
    log.info("  -> calling Claude haiku for structured extraction")
    extracted = _extract_with_claude(all_text, company_name)

    if extracted:
        result["industry"]                 = extracted.get("industry")
        result["estimated_size"]           = extracted.get("estimated_size")
        result["contact_form"]             = bool(extracted.get("contact_form", False))
        result["booking_system"]           = bool(extracted.get("booking_system", False))
        result["live_chat"]                = bool(extracted.get("live_chat", False))
        result["decision_maker"]           = extracted.get("decision_maker_name")
        result["decision_maker_role"]      = extracted.get("decision_maker_role")
        result["automation_opportunities"] = extracted.get("automation_opportunities") or []
        result["summary"]                  = extracted.get("summary")
        # Use Claude's phone/email only as fallback
        if not result["phone"] and extracted.get("phone"):
            result["phone"] = extracted["phone"]
        if not result["email"] and extracted.get("email"):
            result["email"] = extracted["email"]

    if status != 'js_only':
        result["scrape_status"] = "ok" if extracted else status

    return result
