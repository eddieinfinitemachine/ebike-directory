"""Async website scraper for e-bike retailer enrichment."""
from __future__ import annotations

import re
import asyncio
from typing import Optional, List, Dict
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

# ── Configuration ─────────────────────────────────────────────────────────────
TIMEOUT = 5.0
MAX_CONCURRENT = 5
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Chains/SPAs that won't scrape usefully
CHAIN_DOMAINS = {
    "trekbikes.com", "rei.com", "specialized.com", "giant-bicycles.com",
    "cannondale.com", "scheels.com", "dickssportinggoods.com", "walmart.com",
    "target.com", "costco.com", "amazon.com",
}

# ── Brand list ────────────────────────────────────────────────────────────────
KNOWN_BRANDS = [
    "Specialized", "Trek", "Giant", "Cannondale", "Santa Cruz", "Yeti",
    "Bianchi", "Scott", "Merida", "Cervelo", "BMC", "Pinarello",
    "Rad Power", "RadPower", "Aventon", "Lectric", "Juiced", "Ride1Up",
    "Pedego", "Blix", "Velotric", "Magicycle", "Himiway", "Ariel Rider",
    "Sur Ron", "SurRon", "Onyx", "CAKE", "Zero Motorcycles", "Zero FX",
    "Energica", "LiveWire", "Damon", "NIU", "Segway", "SUPER73", "Super 73",
    "Tern", "Benno", "Yuba", "Xtracycle", "Urban Arrow", "Riese & Müller",
    "Gazelle", "Moustache", "Haibike", "Bulls", "Pivot", "Kona",
    "Salsa", "Surly", "All City", "Brompton", "Dahon", "Tern",
    "Shimano", "Bosch", "Bafang", "Yamaha", "Brose",
]
_brand_patterns = [(b, re.compile(re.escape(b), re.IGNORECASE)) for b in KNOWN_BRANDS]

# ── Email extraction ──────────────────────────────────────────────────────────
EMAIL_RE = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
)
EMAIL_BLACKLIST = {
    "noreply", "no-reply", "example.com", "sentry.io", "wixpress.com",
    "squarespace.com", "shopify.com", "wordpress.com", "google.com",
    "facebook.com", "instagram.com", "twitter.com", "schema.org",
    "w3.org", "googleapis.com", "cloudflare.com", "gstatic.com",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"}

def _valid_email(email: str) -> bool:
    email = email.lower().strip()
    if any(bl in email for bl in EMAIL_BLACKLIST):
        return False
    if any(email.endswith(ext) for ext in IMAGE_EXTS):
        return False
    if email.startswith("_") or ".." in email:
        return False
    return True

# ── Social media extraction ───────────────────────────────────────────────────
SOCIAL_PATTERNS = {
    "instagram": re.compile(r'https?://(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)/?', re.I),
    "facebook": re.compile(r'https?://(?:www\.)?facebook\.com/([a-zA-Z0-9.\-]+)/?', re.I),
    "twitter": re.compile(r'https?://(?:www\.)?(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)/?', re.I),
    "youtube": re.compile(r'https?://(?:www\.)?youtube\.com/(?:@|channel/|c/|user/)?([a-zA-Z0-9_\-]+)/?', re.I),
    "tiktok": re.compile(r'https?://(?:www\.)?tiktok\.com/@([a-zA-Z0-9_.]+)/?', re.I),
    "linkedin": re.compile(r'https?://(?:www\.)?linkedin\.com/(?:company|in)/([a-zA-Z0-9_\-]+)/?', re.I),
}
SOCIAL_NOISE = {"share", "sharer", "intent", "dialog", "hashtag", "explore", "login", "signup", "help"}

def _valid_social(platform: str, handle: str) -> bool:
    return handle.lower() not in SOCIAL_NOISE and len(handle) > 1

# ── Hours extraction ──────────────────────────────────────────────────────────
def _extract_hours(soup: BeautifulSoup) -> str | None:
    # Try JSON-LD first
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = data[0]
            hours = data.get("openingHoursSpecification") or data.get("openingHours")
            if hours:
                if isinstance(hours, list):
                    parts = []
                    for h in hours:
                        if isinstance(h, dict):
                            day = h.get("dayOfWeek", "")
                            if isinstance(day, list):
                                day = ", ".join(d.split("/")[-1] for d in day)
                            elif "/" in str(day):
                                day = day.split("/")[-1]
                            opens = h.get("opens", "")
                            closes = h.get("closes", "")
                            if opens and closes:
                                parts.append(f"{day}: {opens}-{closes}")
                        elif isinstance(h, str):
                            parts.append(h)
                    if parts:
                        return "; ".join(parts[:7])
                elif isinstance(hours, str):
                    return hours
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue

    # Try <time> elements
    times = soup.find_all("time")
    if times:
        parts = [t.get_text(strip=True) for t in times if t.get_text(strip=True)]
        if parts:
            return "; ".join(parts[:7])

    return None

# ── Contact/owner extraction ──────────────────────────────────────────────────
OWNER_PATTERNS = [
    re.compile(r'(?:owner|founded by|proprietor)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)', re.I),
    re.compile(r'(?:meet|about)\s+(?:the\s+)?(?:owner|team)[:\s]*([A-Z][a-z]+ [A-Z][a-z]+)', re.I),
]

def _extract_contacts(text: str) -> str | None:
    for pattern in OWNER_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1).strip()
    return None

# ── Main scrape function ──────────────────────────────────────────────────────
def _is_chain_domain(website: str) -> bool:
    try:
        domain = urlparse(website).netloc.lower()
        return any(cd in domain for cd in CHAIN_DOMAINS)
    except Exception:
        return False

def _find_subpages(soup: BeautifulSoup, base_url: str) -> List[str]:
    """Find about/contact page links."""
    targets = []
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        text = a.get_text(strip=True).lower()
        if any(kw in href or kw in text for kw in ("about", "contact", "team", "our-story")):
            full = urljoin(base_url, a["href"])
            if urlparse(full).netloc == urlparse(base_url).netloc:
                targets.append(full)
    # Deduplicate, max 2
    seen = set()
    unique = []
    for t in targets:
        normalized = t.split("?")[0].split("#")[0].rstrip("/")
        if normalized not in seen:
            seen.add(normalized)
            unique.append(t)
    return unique[:2]

def _extract_images(soup: BeautifulSoup, base_url: str) -> List[str]:
    """Extract meaningful images: og:image, twitter:image, logo, hero images."""
    images = []
    seen = set()

    def _add(url):
        if not url or url in seen:
            return
        # Skip tiny icons, tracking pixels, svgs
        low = url.lower()
        if any(x in low for x in ('.svg', '1x1', 'pixel', 'tracking', 'spacer', 'blank', 'data:image')):
            return
        # Make absolute
        abs_url = urljoin(base_url, url)
        if abs_url not in seen:
            seen.add(abs_url)
            images.append(abs_url)

    # og:image — highest priority
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        _add(og["content"])

    # twitter:image
    tw = soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        _add(tw["content"])

    # JSON-LD image
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json as _json
            ld = _json.loads(script.string or "")
            if isinstance(ld, list):
                ld = ld[0]
            for key in ("image", "logo", "photo"):
                val = ld.get(key)
                if isinstance(val, str):
                    _add(val)
                elif isinstance(val, dict):
                    _add(val.get("url", ""))
                elif isinstance(val, list):
                    for v in val[:2]:
                        _add(v if isinstance(v, str) else (v.get("url", "") if isinstance(v, dict) else ""))
        except Exception:
            pass

    # Large <img> tags (likely hero/product images)
    for img in soup.find_all("img", src=True):
        src = img["src"]
        # Skip if obviously small
        w = img.get("width", "")
        h = img.get("height", "")
        try:
            if w and int(w) < 80:
                continue
            if h and int(h) < 80:
                continue
        except ValueError:
            pass
        low = src.lower()
        if any(x in low for x in ('logo', 'hero', 'banner', 'slide', 'feature', 'shop', 'store', 'bike', 'ebike')):
            _add(src)
        # Also grab srcset best image
        srcset = img.get("srcset", "")
        if srcset:
            parts = [s.strip().split()[0] for s in srcset.split(",") if s.strip()]
            if parts:
                _add(parts[-1])  # last = largest

    # Fallback: first few meaningful images
    if len(images) < 3:
        for img in soup.find_all("img", src=True)[:20]:
            src = img["src"]
            low = src.lower()
            if any(x in low for x in ('.svg', 'icon', 'pixel', '1x1', 'data:image', 'gravatar')):
                continue
            _add(src)
            if len(images) >= 6:
                break

    return images[:6]

def _extract_description(soup: BeautifulSoup) -> Optional[str]:
    """Extract site description from meta tags."""
    for attr in [{"property": "og:description"}, {"name": "description"}, {"name": "twitter:description"}]:
        tag = soup.find("meta", attrs=attr)
        if tag and tag.get("content", "").strip():
            return tag["content"].strip()[:300]
    return None

async def scrape_store(website: str, existing_email: str = "") -> dict:
    """Scrape a single store website. Returns enrichment data dict."""
    result = {
        "emails": [],
        "instagram": None,
        "facebook": None,
        "twitter": None,
        "youtube": None,
        "tiktok": None,
        "linkedin": None,
        "owner_contact": None,
        "store_hours": None,
        "brands_carried": [],
        "images": [],
        "description": None,
        "status": "success",
        "pages_scraped": 0,
    }

    if not website:
        result["status"] = "no_website"
        return result

    if _is_chain_domain(website):
        result["status"] = "chain_skip"
        return result

    # Normalize URL
    if not website.startswith("http"):
        website = "https://" + website

    all_text = ""
    all_html = ""
    pages_to_scrape = [website]

    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers=HEADERS,
        verify=False,
    ) as client:
        for i, url in enumerate(pages_to_scrape):
            for attempt in range(2):  # retry once
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    html = resp.text
                    soup = BeautifulSoup(html, "lxml")
                    result["pages_scraped"] += 1

                    page_text = soup.get_text(separator=" ", strip=True)
                    all_text += " " + page_text
                    all_html += " " + html

                    # Find subpages from homepage only
                    if i == 0:
                        subpages = _find_subpages(soup, url)
                        pages_to_scrape.extend(subpages)
                        # Extract images and description from homepage
                        result["images"] = _extract_images(soup, url)
                        result["description"] = _extract_description(soup)

                    # Extract hours from every page
                    if not result["store_hours"]:
                        result["store_hours"] = _extract_hours(soup)

                    break  # success, no retry
                except httpx.TimeoutException:
                    if attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                    result["status"] = "timeout"
                except httpx.HTTPStatusError:
                    result["status"] = "error"
                    break
                except Exception:
                    result["status"] = "error"
                    break

    # Extract emails from all pages combined
    found_emails = set()
    for email in EMAIL_RE.findall(all_html):
        if _valid_email(email):
            found_emails.add(email.lower())
    if existing_email:
        found_emails.discard(existing_email.lower().split(";")[0].strip())
    result["emails"] = sorted(found_emails)

    # Extract socials from all HTML
    for platform, pattern in SOCIAL_PATTERNS.items():
        matches = pattern.findall(all_html)
        for handle in matches:
            if _valid_social(platform, handle):
                result[platform] = f"https://{platform}.com/{handle}" if platform != "twitter" else f"https://x.com/{handle}"
                break

    # Extract brands
    found_brands = set()
    for brand_name, pattern in _brand_patterns:
        if pattern.search(all_text):
            found_brands.add(brand_name)
    result["brands_carried"] = sorted(found_brands)

    # Extract contacts
    result["owner_contact"] = _extract_contacts(all_text)

    # Determine final status
    if result["pages_scraped"] == 0:
        if result["status"] == "success":
            result["status"] = "error"
    elif result["status"] == "success" and result["pages_scraped"] < len(pages_to_scrape):
        result["status"] = "partial"

    return result

# ── Batch scraping with concurrency control ───────────────────────────────────
_semaphore = asyncio.Semaphore(MAX_CONCURRENT)

async def _scrape_with_semaphore(website: str, existing_email: str = "") -> dict:
    async with _semaphore:
        return await scrape_store(website, existing_email)

async def scrape_batch(stores: List[Dict], callback=None) -> List[Dict]:
    """Scrape a batch of stores. callback(index, store, result) called per completion."""
    tasks = []
    for store in stores:
        tasks.append(_scrape_with_semaphore(
            store.get("website", ""),
            store.get("email", ""),
        ))

    results = []
    for i, coro in enumerate(asyncio.as_completed(tasks)):
        # as_completed doesn't preserve order, so we use gather instead
        pass

    # Use gather to preserve order
    results = await asyncio.gather(*tasks)

    if callback:
        for i, (store, result) in enumerate(zip(stores, results)):
            await callback(i, store, result)

    return results
