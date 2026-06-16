"""
Company website enrichment module (requests + BeautifulSoup4).

OpenClaw is not installed in this environment. This module replicates the
key enrichment capabilities using plain HTTP + HTML parsing:

  - Homepage scrape: title, description, phone, email, contact form
  - Subpage crawl: /kontakt, /om-oss, /team — finds decision maker
  - Signal detection: booking widgets, live chat, automation opportunities
  - Size estimation: from language clues on team/about pages

Returns a dict matching the OpenClaw schema so the calling code is
swap-ready if OpenClaw becomes available later.

LIMITATION: JavaScript-rendered pages (React SPAs) return minimal content.
The scraper handles this gracefully — it returns what it finds and notes
the limitation in scrape_status.
"""

import logging
import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse, unquote

import requests
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

_BOOKING_SIGNALS = [
    "bokadirekt.se", "timma.se", "calendly.com", "acuityscheduling.com",
    "booksy.com", "fresha.com", "onlinebokning", "easybooking",
    "bokningssystem", "boka tid online", "boka online", "book a time",
    "schedule online",
]

_CHAT_SIGNALS = [
    "intercom", "zendesk.com/chat", "tawk.to", "livechat.com",
    "drift.com", "crisp.chat", "tidio", "freshchat",
]

_DM_TITLE_PATTERNS = [
    r'\bVD\b', r'[Vv]erkst[äa]llande\s+[Dd]irekt[öo]r',
    r'\b[Ää]gare\b', r'\b[Gg]rundare\b', r'\b[Ff]ounder\b', r'\bCEO\b',
    r'\b[Mm]anaging\s+[Dd]irector\b', r'\b[Vv]erksamhetsansvarig\b',
    r'\bChef\s+och\s+[äa]gare\b', r'\b[äÄ]gare\s+och\b',
]
_DM_TITLE_RE = re.compile('|'.join(_DM_TITLE_PATTERNS))

_NAME_RE = re.compile(
    r'\b([A-ZÅÄÖ][a-zåäö]{1,15}(?:\s+[A-ZÅÄÖ][a-zåäö]{1,15}){1,2})\b'
)

_SUBPATHS_TO_TRY = [
    '/om-oss', '/om-foretaget', '/om', '/about', '/about-us',
    '/team', '/our-team', '/personal', '/medarbetare', '/staff',
    '/kontakt', '/contact', '/contact-us',
]

_INDUSTRY_HINTS = {
    'städ': 'cleaning', 'rengöring': 'cleaning', 'städning': 'cleaning',
    'rör': 'plumbing', 'vvs': 'plumbing',
    'bil': 'automotive', 'fordon': 'automotive', 'däck': 'automotive', 'verkstad': 'automotive',
    'bygg': 'construction', 'byggnation': 'construction',
    'uthyrning': 'rental', 'hyra': 'rental', 'hyr ': 'rental',
    'transport': 'transport', 'frakt': 'transport', 'logistik': 'logistics',
    'restaurang': 'food', 'café': 'food', 'catering': 'food',
    'konsult': 'consulting', 'rådgivning': 'consulting',
    'el ': 'electrical', 'elektrisk': 'electrical', 'el-': 'electrical',
    'fastighe': 'real_estate', 'bostäder': 'real_estate',
    'städning': 'cleaning',
    'redovisning': 'accounting', 'bokföring': 'accounting',
}

_NAME_BLOCKLIST = {
    'kontakta', 'kontakt', 'välkommen', 'läs', 'mer', 'information',
    'om', 'oss', 'vårt', 'vår', 'din', 'ditt', 'här', 'detta',
    'click', 'read', 'more', 'learn',
}


def _fetch(url: str, timeout: int = 8) -> tuple[Optional[BeautifulSoup], str]:
    """Returns (soup, status_hint). status_hint: 'ok', 'failed', 'js_only'."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        ct = resp.headers.get('Content-Type', '')
        if 'text/html' not in ct:
            return None, 'not_html'
        soup = BeautifulSoup(resp.text, 'html.parser')
        # Heuristic: if body text is very short, it's probably a React SPA
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
    # tel: links first (most reliable)
    for a in soup.find_all('a', href=re.compile(r'^tel:', re.I)):
        raw = unquote(a['href'].replace('tel:', '')).strip()
        clean = re.sub(r'\s', '', raw)
        if clean: phones.append(raw)
    # regex over text
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
        if '@' in addr: found.add(addr)
    text = soup.get_text(' ', strip=True)
    for m in _EMAIL_RE.findall(text):
        ml = m.lower()
        if any(ml.endswith(x) for x in ('.png', '.jpg', '.gif', '.svg')): continue
        if any(x in ml for x in ('@example', '@noreply', '@sentry', '@pixel', '@w3')): continue
        found.add(ml)
    return list(found)[:2]


def _has_contact_form(soup: BeautifulSoup) -> bool:
    for form in soup.find_all('form'):
        has_text_input = any(
            i.get('type', 'text') in ('text', 'email', 'tel', '')
            for i in form.find_all('input')
        )
        has_textarea = bool(form.find('textarea'))
        if has_text_input or has_textarea:
            return True
    return False


def _has_booking(soup: BeautifulSoup, raw_html: str) -> bool:
    low = raw_html.lower()
    return any(sig in low for sig in _BOOKING_SIGNALS)


def _has_live_chat(raw_html: str) -> bool:
    low = raw_html.lower()
    return any(sig in low for sig in _CHAT_SIGNALS)


def _estimate_size(text: str) -> str:
    low = text.lower()
    # Explicit count mentions
    m = re.search(r'(\d+)\s+(?:anst[äa]llda|medarbetare|kollegor|anst[äa]llning)', low)
    if m:
        n = int(m.group(1))
        if n == 1: return 'solo'
        if n <= 10: return '2-10'
        if n <= 50: return '11-50'
        return '50+'
    # Language clues
    if any(w in low for w in ['enmansfirma', 'ensam', 'solo', 'jag driver']):
        return 'solo'
    if any(w in low for w in ['litet team', 'liten verksamhet', 'familjeföretag', 'vi är ett litet']):
        return '2-10'
    if any(w in low for w in ['snabbväxande', 'expanding', 'growing team', 'vi är nu']):
        return '11-50'
    return 'unknown'


def _guess_industry(text: str) -> str:
    low = text.lower()
    for kw, industry in _INDUSTRY_HINTS.items():
        if kw in low:
            return industry
    return ''


def _find_decision_maker(soup: BeautifulSoup, text: str) -> tuple[str, str]:
    """Returns (first_name_only, role_string). Empty strings if not found."""

    # Strategy 1: "Name, Title" or "Name — Title" in running text
    inline_pattern = re.compile(
        r'([A-ZÅÄÖ][a-zåäö]+(?:\s+[A-ZÅÄÖ][a-zåäö]+){0,2})'
        r'\s*[,\-–]\s*'
        r'(VD|[Ää]gare|[Gg]rundare|CEO|[Vv]erkst[äa]llande direktör'
        r'|[Vv]erksamhetsansvarig|[Ff]ounder|Managing Director)',
        re.IGNORECASE
    )
    m = inline_pattern.search(text)
    if m:
        full_name = m.group(1).strip()
        role      = m.group(2).strip()
        first     = full_name.split()[0]
        if first.lower() not in _NAME_BLOCKLIST and len(first) > 1:
            return first, role

    # Strategy 2: "Title: Name" or "Title — Name"
    prefix_pattern = re.compile(
        r'(?:VD|[Ää]gare|[Gg]rundare|CEO|Grundare|Founder)\s*[:–\-]\s*'
        r'([A-ZÅÄÖ][a-zåäö]+(?:\s+[A-ZÅÄÖ][a-zåäö]+){0,2})',
        re.IGNORECASE
    )
    m = prefix_pattern.search(text)
    if m:
        full_name = m.group(1).strip()
        first     = full_name.split()[0]
        if first.lower() not in _NAME_BLOCKLIST and len(first) > 1:
            return first, 'owner/founder'

    # Strategy 3: element proximity — find title keyword, look for adjacent name
    for elem in soup.find_all(['h3', 'h4', 'p', 'span', 'div']):
        elem_text = elem.get_text(' ', strip=True)
        if not _DM_TITLE_RE.search(elem_text):
            continue
        # Try the element itself (e.g. "<h4>Anna Larsson, VD</h4>")
        names = _NAME_RE.findall(elem_text)
        for name in names:
            first = name.split()[0]
            if first.lower() not in _NAME_BLOCKLIST and len(first) > 2:
                role_m = _DM_TITLE_RE.search(elem_text)
                role   = role_m.group(0) if role_m else 'owner/founder'
                return first, role
        # Try previous sibling (name above, title below)
        prev = elem.find_previous_sibling(['h3', 'h4', 'p', 'span'])
        if prev:
            prev_text = prev.get_text(' ', strip=True)
            names = _NAME_RE.findall(prev_text)
            for name in names:
                first = name.split()[0]
                if first.lower() not in _NAME_BLOCKLIST and len(first) > 2:
                    role_m = _DM_TITLE_RE.search(elem_text)
                    role   = role_m.group(0) if role_m else 'owner/founder'
                    return first, role

    return '', ''


def _automation_opportunities(soup: BeautifulSoup, all_text: str) -> list[str]:
    low = all_text.lower()
    opps = []
    if 'bokning' in low or 'boka' in low or 'book' in low:
        opps.append('Booking/scheduling language on site')
    if _has_contact_form(soup):
        opps.append('Contact form present — intake/response automation possible')
    elif 'kontaktformulär' in low or 'skriv till oss' in low:
        opps.append('Contact form mentioned — intake automation possible')
    if 'faktura' in low or 'betalning' in low or 'betala' in low:
        opps.append('Invoicing/payment workflow visible')
    if 'offert' in low or 'quote' in low or 'anbud' in low or 'prisförfrågan' in low:
        opps.append('Quote/offer request workflow visible')
    if 'uppföljning' in low or 'återkoppling' in low or 'follow-up' in low:
        opps.append('Follow-up communication mentioned')
    if 'ring oss' in low or 'telefon' in low and 'kontakta' in low:
        opps.append('Phone-first contact model — digital triage opportunity')
    return opps[:5]


def enrich_company(company_name: str, website: Optional[str]) -> dict:
    """
    Scrapes a company website and returns an enrichment dict.

    Compatible with the OpenClaw schema — swap out this function for the
    real OpenClaw client once it's installed.
    """
    result = {
        "company_name":             company_name,
        "website":                  website,
        "industry":                 "",
        "estimated_size":           "unknown",
        "phone":                    "",
        "email":                    "",
        "contact_form":             False,
        "booking_system":           False,
        "live_chat":                False,
        "decision_maker":           "",
        "decision_maker_role":      "",
        "automation_opportunities": [],
        "summary":                  "",
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
        # Continue — partial data is better than nothing

    raw_html  = str(soup)
    page_text = soup.get_text(' ', strip=True)
    all_text  = page_text

    # ── Basic extractions from homepage ──────────────────────────────────────
    phones = _phones(soup)
    emails = _emails(soup)
    result["phone"]          = phones[0] if phones else ""
    result["email"]          = emails[0] if emails else ""
    result["contact_form"]   = _has_contact_form(soup)
    result["booking_system"] = _has_booking(soup, raw_html)
    result["live_chat"]      = _has_live_chat(raw_html)
    result["industry"]       = _guess_industry(page_text)
    result["estimated_size"] = _estimate_size(page_text)

    # ── Crawl subpages ────────────────────────────────────────────────────────
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    visited = {url.rstrip('/'), base.rstrip('/')}

    for subpath in _SUBPATHS_TO_TRY[:8]:
        sub_url = urljoin(base, subpath)
        if sub_url.rstrip('/') in visited:
            continue
        visited.add(sub_url.rstrip('/'))

        time.sleep(0.25)
        sub_soup, sub_status = _fetch(sub_url, timeout=6)
        if not sub_soup:
            continue

        sub_text = sub_soup.get_text(' ', strip=True)
        all_text += ' ' + sub_text
        sub_html = str(sub_soup)

        if not result["phone"]:
            ps = _phones(sub_soup)
            if ps: result["phone"] = ps[0]
        if not result["email"]:
            es = _emails(sub_soup)
            if es: result["email"] = es[0]
        if not result["contact_form"]:
            result["contact_form"] = _has_contact_form(sub_soup)
        if not result["booking_system"]:
            result["booking_system"] = _has_booking(sub_soup, sub_html)
        if not result["live_chat"]:
            result["live_chat"] = _has_live_chat(sub_html)
        if result["estimated_size"] == 'unknown':
            result["estimated_size"] = _estimate_size(sub_text)

        if not result["decision_maker"]:
            dm, role = _find_decision_maker(sub_soup, sub_text)
            if dm:
                result["decision_maker"]      = dm
                result["decision_maker_role"] = role

    # ── Decision maker fallback: try homepage ─────────────────────────────────
    if not result["decision_maker"]:
        dm, role = _find_decision_maker(soup, page_text)
        if dm:
            result["decision_maker"]      = dm
            result["decision_maker_role"] = role

    # ── Automation opportunities ──────────────────────────────────────────────
    result["automation_opportunities"] = _automation_opportunities(soup, all_text)

    # ── Summary ───────────────────────────────────────────────────────────────
    parts = []
    if result["decision_maker"]:
        parts.append(f"Decision maker: {result['decision_maker']} ({result['decision_maker_role']})")
    else:
        parts.append("No decision maker found on site")
    signals = [s for s, v in [
        ("booking system", result["booking_system"]),
        ("contact form",   result["contact_form"]),
        ("live chat",      result["live_chat"]),
    ] if v]
    if signals:
        parts.append(f"Found: {', '.join(signals)}")
    parts.append(f"Estimated size: {result['estimated_size']}")
    result["summary"] = ". ".join(parts) + "."

    if status != 'js_only':
        result["scrape_status"] = "ok"

    return result
