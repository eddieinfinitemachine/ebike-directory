"""Dealer locator scraper — finds brand dealers via natural language queries."""
from __future__ import annotations

import os
import re
import json
import asyncio
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

# ── Configuration ─────────────────────────────────────────────────────────────
TIMEOUT = 8.0
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

BASE_DIR = Path(__file__).parent
BRAND_URLS_FILE = BASE_DIR / "brand_dealer_urls.json"

def _load_brand_urls() -> dict:
    if BRAND_URLS_FILE.exists():
        return json.loads(BRAND_URLS_FILE.read_text())
    return {}


# ── Brand extraction via Claude ───────────────────────────────────────────────
def extract_brand_from_query(query: str) -> str:
    """Use Claude Haiku to extract the brand name from a natural language query."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _extract_brand_fallback(query)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": (
                    "Extract ONLY the brand/company name from this dealer search query. "
                    "Return just the brand name, nothing else. No punctuation, no explanation.\n\n"
                    f"Query: \"{query}\""
                ),
            }],
        )
        brand = resp.content[0].text.strip().strip('"\'.')
        return brand if brand else _extract_brand_fallback(query)
    except Exception:
        return _extract_brand_fallback(query)


_STOP_WORDS = {
    "i", "want", "to", "find", "show", "me", "all", "the", "a", "an",
    "dealers", "dealer", "stores", "store", "shops", "shop", "locations",
    "retailers", "retailer", "near", "where", "can", "buy", "get",
    "sells", "sell", "carries", "carry", "that", "which", "for",
    "who", "what", "are", "is", "do", "does", "their", "list", "of",
    "please", "help", "look", "looking", "search", "ebike", "ebikes",
    "e-bike", "e-bikes", "electric", "bike", "bikes", "bicycle", "bicycles",
    "near", "me", "my", "area", "here", "around", "in", "from",
}

def _extract_brand_fallback(query: str) -> str:
    """Simple stop-word removal fallback when Claude is unavailable."""
    words = query.strip().split()
    brand_words = [w for w in words if w.lower().strip("'\".,!?") not in _STOP_WORDS]
    return " ".join(brand_words).strip("'\".,!?")


# ── Dealer locator URL discovery ──────────────────────────────────────────────
async def find_dealer_locator(brand: str) -> tuple[str | None, str]:
    """Find the dealer locator URL for a brand.
    Returns (url, type) where type is 'stockist', 'storerocket', 'storepoint', 'html', or 'auto'.
    """
    brand_urls = _load_brand_urls()

    # Check curated mapping (case-insensitive)
    for key, info in brand_urls.items():
        if key.lower() == brand.lower():
            return info["url"], info.get("type", "auto")

    # Try scraping the brand's homepage for dealer locator links
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', brand).strip()
    nospaces = clean.replace(' ', '').lower()
    dashed = clean.replace(' ', '-').lower()
    domains_to_try = [
        f"https://www.{nospaces}.com",
        f"https://{nospaces}.com",
        f"https://www.{dashed}.com",
        f"https://{dashed}.com",
        f"https://www.{nospaces}bikes.com",
        f"https://www.{nospaces}ebikes.com",
    ]

    async with httpx.AsyncClient(timeout=5.0, follow_redirects=True, headers=HEADERS, verify=False) as client:
        for domain in domains_to_try:
            try:
                resp = await client.get(domain)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "lxml")
                dealer_url = _find_dealer_link(soup, str(resp.url))
                if dealer_url:
                    return dealer_url, "auto"
            except Exception:
                continue

    return None, "unknown"


_DEALER_LINK_KEYWORDS = [
    "dealer", "store-locator", "find-a-dealer", "where-to-buy",
    "retailers", "find-a-store", "locations", "test-ride",
    "find-dealer", "dealer-locator", "store-finder", "find-us",
    "where-to-shop", "authorized-dealer",
]

def _find_dealer_link(soup: BeautifulSoup, base_url: str) -> str | None:
    """Find a dealer locator link on a brand's homepage."""
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        text = a.get_text(strip=True).lower()
        combined = href + " " + text
        if any(kw in combined for kw in _DEALER_LINK_KEYWORDS):
            full_url = urljoin(base_url, a["href"])
            # Only follow links on the same domain
            if urlparse(full_url).netloc == urlparse(base_url).netloc:
                return full_url
    return None


# ── Multi-strategy dealer scraper ─────────────────────────────────────────────
async def scrape_dealers(url: str, brand: str = "") -> dict:
    """Scrape dealers from a dealer locator page.
    Returns {dealers: [...], strategy: str, source_url: str, error: str|None}.
    """
    result = {"dealers": [], "strategy": "none", "source_url": url, "error": None}

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=HEADERS, verify=False) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            result["error"] = f"Failed to fetch {url}: {str(e)}"
            return result

    # Strategy 1: Detect Stockist embed
    stockist_match = re.search(r'stockist\.co/api/v1/(\w+)', html)
    if stockist_match:
        account_id = stockist_match.group(1)
        dealers = await _scrape_stockist(account_id)
        if dealers:
            result["dealers"] = dealers
            result["strategy"] = "stockist"
            return result

    # Strategy 2: Detect StoreRocket embed
    storerocket_match = re.search(r'storerocket\.io/api/user/([a-zA-Z0-9]+)', html)
    if storerocket_match:
        user_id = storerocket_match.group(1)
        dealers = await _scrape_storerocket(user_id)
        if dealers:
            result["dealers"] = dealers
            result["strategy"] = "storerocket"
            return result

    # Strategy 3: Detect Storepoint embed
    storepoint_match = (
        re.search(r'storepoint\.co/api/v1/([a-zA-Z0-9]+)', html) or
        re.search(r'StorepointWidget\(["\']([a-fA-F0-9]+)', html)
    )
    if storepoint_match:
        sp_id = storepoint_match.group(1)
        dealers = await _scrape_storepoint(sp_id)
        if dealers:
            result["dealers"] = dealers
            result["strategy"] = "storepoint"
            return result

    # Strategy 4: Look for inline JSON data
    dealers = _extract_inline_json(html)
    if dealers:
        result["dealers"] = dealers
        result["strategy"] = "inline_json"
        return result

    # Strategy 5: Use Claude to extract from HTML
    dealers = _extract_with_claude(html, brand)
    if dealers:
        result["dealers"] = dealers
        result["strategy"] = "claude_extraction"
        return result

    # Strategy 6: Basic HTML structure parsing
    dealers = _extract_html_structure(html, url)
    if dealers:
        result["dealers"] = dealers
        result["strategy"] = "html_parse"
        return result

    result["error"] = "Could not extract dealers. The page may use JavaScript rendering."
    return result


# ── Stockist scraper ──────────────────────────────────────────────────────────
async def _scrape_stockist(account_id: str) -> list[dict]:
    """Scrape all dealers from a Stockist account."""
    dealers = []
    # Query with US center, large radius to get all
    url = f"https://stockist.co/api/v1/{account_id}/locations/search"
    params = {"latitude": 39.8, "longitude": -98.5, "distance": 10000}

    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as client:
        try:
            resp = await client.get(url, params=params)
            data = resp.json()
            for loc in data.get("locations", []):
                dealers.append(_normalize_stockist(loc))
        except Exception:
            pass

    return dealers


def _normalize_stockist(loc: dict) -> dict:
    return {
        "name": loc.get("name", "").strip(),
        "address": loc.get("address_line_1", "").strip(),
        "city": loc.get("city", "").strip(),
        "state": loc.get("state", "").strip(),
        "zip": loc.get("postal_code", "").strip(),
        "phone": loc.get("phone", "").strip(),
        "website": loc.get("website", "").strip(),
        "lat": loc.get("latitude"),
        "lng": loc.get("longitude"),
    }


# ── StoreRocket scraper ──────────────────────────────────────────────────────
async def _scrape_storerocket(user_id: str) -> list[dict]:
    dealers = []
    url = f"https://storerocket.io/api/user/{user_id}/locations"

    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as client:
        try:
            resp = await client.get(url)
            data = resp.json()
            for loc in data.get("results", {}).get("locations", []):
                dealers.append({
                    "name": loc.get("name", "").strip(),
                    "address": loc.get("address", "").strip(),
                    "city": loc.get("city", "").strip(),
                    "state": loc.get("state", "").strip(),
                    "zip": loc.get("postcode", "").strip(),
                    "phone": loc.get("phone", "").strip(),
                    "website": loc.get("url", "").strip(),
                    "lat": loc.get("lat"),
                    "lng": loc.get("lng"),
                })
        except Exception:
            pass

    return dealers


# ── Storepoint scraper ────────────────────────────────────────────────────────
async def _scrape_storepoint(sp_id: str) -> list[dict]:
    dealers = []
    url = f"https://api.storepoint.co/v1/{sp_id}/locations"

    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as client:
        try:
            resp = await client.get(url)
            data = resp.json()
            for loc in data.get("results", {}).get("locations", []):
                # Storepoint puts full address in streetaddress as comma-separated
                addr_parts = [p.strip() for p in loc.get("streetaddress", "").split(",")]
                address = addr_parts[0] if addr_parts else ""
                city = addr_parts[1] if len(addr_parts) > 1 else ""
                state = addr_parts[2] if len(addr_parts) > 2 else ""
                zip_code = addr_parts[3] if len(addr_parts) > 3 else ""

                dealers.append({
                    "name": loc.get("name", "").strip(),
                    "address": address,
                    "city": city,
                    "state": state,
                    "zip": zip_code,
                    "phone": loc.get("phone", "").strip(),
                    "website": loc.get("website", "").strip(),
                    "lat": loc.get("loc_lat"),
                    "lng": loc.get("loc_long"),
                })
        except Exception:
            pass

    return dealers


# ── Inline JSON extraction ────────────────────────────────────────────────────
def _extract_inline_json(html: str) -> list[dict]:
    """Look for inline JSON location data in the HTML source."""
    # Common patterns: var locations = [...], window.stores = [...], etc.
    patterns = [
        r'(?:locations|stores|dealers|markers|points)\s*[=:]\s*(\[[\s\S]*?\]);',
        r'JSON\.parse\([\'"](\[.*?\])[\'"]\)',
        r'"locations"\s*:\s*(\[[\s\S]*?\])\s*[,}]',
        r'"stores"\s*:\s*(\[[\s\S]*?\])\s*[,}]',
        r'"dealers"\s*:\s*(\[[\s\S]*?\])\s*[,}]',
        r'"results"\s*:\s*(\[[\s\S]*?\])\s*[,}]',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, html)
        for match in matches:
            try:
                data = json.loads(match)
                if isinstance(data, list) and len(data) > 2:
                    dealers = _normalize_json_locations(data)
                    if dealers:
                        return dealers
            except (json.JSONDecodeError, ValueError):
                continue

    return []


def _normalize_json_locations(locations: list) -> list[dict]:
    """Normalize a list of JSON location objects into our standard format."""
    dealers = []
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        dealer = {
            "name": "",
            "address": "",
            "city": "",
            "state": "",
            "zip": "",
            "phone": "",
            "website": "",
            "lat": None,
            "lng": None,
        }
        # Try common field names
        for name_key in ["name", "title", "store_name", "storeName", "dealer_name", "dealerName"]:
            if loc.get(name_key):
                dealer["name"] = str(loc[name_key]).strip()
                break
        for addr_key in ["address", "address_line_1", "street", "address1", "streetAddress"]:
            if loc.get(addr_key):
                dealer["address"] = str(loc[addr_key]).strip()
                break
        for city_key in ["city", "town", "locality"]:
            if loc.get(city_key):
                dealer["city"] = str(loc[city_key]).strip()
                break
        for state_key in ["state", "region", "province", "state_code"]:
            if loc.get(state_key):
                dealer["state"] = str(loc[state_key]).strip()
                break
        for phone_key in ["phone", "telephone", "phone_number", "tel"]:
            if loc.get(phone_key):
                dealer["phone"] = str(loc[phone_key]).strip()
                break
        for web_key in ["website", "url", "web", "site_url", "link"]:
            if loc.get(web_key):
                dealer["website"] = str(loc[web_key]).strip()
                break
        for lat_key in ["lat", "latitude", "loc_lat"]:
            if loc.get(lat_key):
                try:
                    dealer["lat"] = float(loc[lat_key])
                except (ValueError, TypeError):
                    pass
                break
        for lng_key in ["lng", "longitude", "lon", "loc_long", "loc_lng"]:
            if loc.get(lng_key):
                try:
                    dealer["lng"] = float(loc[lng_key])
                except (ValueError, TypeError):
                    pass
                break

        if dealer["name"] or dealer["address"]:
            dealers.append(dealer)

    return dealers


# ── Claude-based HTML extraction ──────────────────────────────────────────────
def _extract_with_claude(html: str, brand: str) -> list[dict]:
    """Use Claude to extract dealer info from HTML when other strategies fail."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return []

    # Trim HTML to avoid token limits — keep text content only
    soup = BeautifulSoup(html, "lxml")
    # Remove script/style tags
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Limit to ~8000 chars to keep within Haiku token limits
    if len(text) > 8000:
        text = text[:8000]

    if len(text.strip()) < 50:
        return []

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": (
                    f"Extract all dealer/store locations from this {brand} dealer locator page text. "
                    "Return ONLY a JSON array of objects with these fields: "
                    "name, address, city, state, zip, phone, website. "
                    "If a field is not available, use empty string. "
                    "Return [] if no dealers found. No explanation, just the JSON array.\n\n"
                    f"Page text:\n{text}"
                ),
            }],
        )
        raw = resp.content[0].text.strip()
        # Extract JSON array from response
        json_match = re.search(r'\[[\s\S]*\]', raw)
        if json_match:
            dealers = json.loads(json_match.group())
            # Validate structure
            valid = []
            for d in dealers:
                if isinstance(d, dict) and (d.get("name") or d.get("address")):
                    valid.append({
                        "name": str(d.get("name", "")).strip(),
                        "address": str(d.get("address", "")).strip(),
                        "city": str(d.get("city", "")).strip(),
                        "state": str(d.get("state", "")).strip(),
                        "zip": str(d.get("zip", "")).strip(),
                        "phone": str(d.get("phone", "")).strip(),
                        "website": str(d.get("website", "")).strip(),
                    })
            return valid
    except Exception:
        pass

    return []


# ── HTML structure parsing ────────────────────────────────────────────────────
_US_STATE_ABBREVS = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA',
    'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY',
    'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX',
    'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
}

_PHONE_RE = re.compile(r'\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}')
_ZIP_RE = re.compile(r'\b\d{5}(?:-\d{4})?\b')
_STATE_RE = re.compile(r'\b(' + '|'.join(_US_STATE_ABBREVS) + r')\b')

def _extract_html_structure(html: str, base_url: str) -> list[dict]:
    """Try to extract dealers from HTML structure (tables, lists, divs)."""
    soup = BeautifulSoup(html, "lxml")
    # Remove nav/header/footer noise
    for tag in soup(["nav", "header", "footer", "script", "style"]):
        tag.decompose()

    dealers = []

    # Try tables first
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows[1:]:  # skip header
            cells = row.find_all(["td", "th"])
            text = " ".join(c.get_text(strip=True) for c in cells)
            dealer = _parse_address_text(text)
            if dealer:
                dealers.append(dealer)
        if len(dealers) >= 3:
            return dealers
    dealers = []

    # Try repeated div/li/article with address-like content
    # Must find at least 3 with BOTH phone AND state to count
    for container_tag in ["li", "article", "div"]:
        elements = soup.find_all(container_tag)
        candidates = []
        for el in elements:
            # Skip if element has too many children (likely a wrapper)
            if len(el.find_all(container_tag)) > 3:
                continue
            text = el.get_text(separator=" ", strip=True)
            if 40 < len(text) < 400:
                has_phone = _PHONE_RE.search(text)
                has_state = _STATE_RE.search(text)
                has_zip = _ZIP_RE.search(text)
                if has_phone and (has_state or has_zip):
                    dealer = _parse_address_text(text)
                    if dealer:
                        candidates.append(dealer)
        if len(candidates) >= 3:
            return candidates

    return []


def _parse_address_text(text: str) -> dict | None:
    """Parse a block of text into a dealer record."""
    phone_match = _PHONE_RE.search(text)
    zip_match = _ZIP_RE.search(text)
    state_match = _STATE_RE.search(text)

    if not (phone_match or (zip_match and state_match)):
        return None

    # Split text into lines/segments
    lines = [l.strip() for l in re.split(r'[|\n\r]+', text) if l.strip()]
    name = lines[0] if lines else ""

    return {
        "name": name[:100],
        "address": "",
        "city": "",
        "state": state_match.group(1) if state_match else "",
        "zip": zip_match.group() if zip_match else "",
        "phone": phone_match.group() if phone_match else "",
        "website": "",
    }


# ── Main orchestrator ─────────────────────────────────────────────────────────
async def find_brand_dealers(query: str = "", brand: str = "", url: str = "") -> dict:
    """Main entry point. Accepts natural language query, brand name, or direct URL.
    Returns {brand, dealers, source_url, strategy, count, error}.
    """
    # Extract brand if only query provided
    if not brand and query:
        brand = extract_brand_from_query(query)

    if not brand and not url:
        return {"brand": "", "dealers": [], "source_url": "", "strategy": "none",
                "count": 0, "error": "Could not determine brand name from query."}

    # Find dealer locator URL if not provided
    if not url:
        url, loc_type = await find_dealer_locator(brand)

    if not url:
        return {"brand": brand, "dealers": [], "source_url": "", "strategy": "none",
                "count": 0, "error": f"Could not find a dealer locator for '{brand}'. "
                "Try pasting the dealer locator URL directly."}

    # Scrape dealers
    result = await scrape_dealers(url, brand)
    return {
        "brand": brand,
        "dealers": result["dealers"],
        "source_url": result["source_url"],
        "strategy": result["strategy"],
        "count": len(result["dealers"]),
        "error": result["error"],
    }
