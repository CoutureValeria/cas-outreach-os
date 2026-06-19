"""
Web crawler for company enrichment.
Crawls homepage + up to 8 subpages using requests + BeautifulSoup4.
"""

import logging
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("openclaw_client")

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


def _fetch_url(url: str, timeout: int = 8):
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
        log.debug("fetch %s: %s", url, e)
        return None, "error"


def get_page_text(url: str) -> Optional[str]:
    """
    Fetch all visible text from a company website.
    Crawls homepage + up to 8 common subpages (about, team, contact).
    Returns None if the site cannot be reached.
    """
    if not url:
        return None

    url = url.strip()
    if not url.startswith("http"):
        url = f"https://{url}"

    log.info("Fetching page text: %s", url)

    soup, status = _fetch_url(url)
    if not soup:
        log.warning("  homepage fetch failed (%s) for %s", status, url)
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
        sub_soup, _ = _fetch_url(sub_url, timeout=6)
        if sub_soup:
            all_text += " " + sub_soup.get_text(" ", strip=True)

    result = all_text.strip() or None
    if result:
        log.info("  fetched: %d chars", len(result))
    else:
        log.warning("  no content extracted for %s", url)
    return result
