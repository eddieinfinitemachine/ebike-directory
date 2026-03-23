"""FastAPI server for e-bike directory enrichment and export."""
import os
import json

from dotenv import load_dotenv
load_dotenv()
import hashlib
import time
import asyncio
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse
import uvicorn

from scraper import scrape_store
from airtable_export import export_to_airtable
from dealer_scraper import find_brand_dealers

# ── Setup ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CACHE_FILE = BASE_DIR / "enrichment_cache.json"
TAGS_FILE = BASE_DIR / "tags.json"
DATA_FILE = BASE_DIR / "data.json"
INDEX_FILE = BASE_DIR / "index.html"
LISTS_FILE = BASE_DIR / "lists.html"
CACHE_TTL = 30 * 24 * 3600  # 30 days

app = FastAPI(title="E-Bike Directory Server")

# ── Cache management ──────────────────────────────────────────────────────────
def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

def _save_cache(cache: dict):
    CACHE_FILE.write_text(json.dumps(cache, indent=2))

def _cache_key(name: str, website: str) -> str:
    raw = f"{name}|{website}".lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()

def _is_cache_valid(entry: dict) -> bool:
    return time.time() - entry.get("timestamp", 0) < CACHE_TTL

def _load_data() -> list[dict]:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return []

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/")
async def serve_index():
    return FileResponse(INDEX_FILE, media_type="text/html")

@app.get("/lists.html")
async def serve_lists():
    return FileResponse(LISTS_FILE, media_type="text/html")

@app.get("/data.json")
async def serve_data():
    return FileResponse(DATA_FILE, media_type="application/json")

@app.get("/api/enrichment-status")
async def enrichment_status():
    """Return which store indices have cached enrichment data."""
    cache = _load_cache()
    data = _load_data()
    enriched = {}
    for i, store in enumerate(data):
        key = _cache_key(store.get("name", ""), store.get("website", ""))
        if key in cache and _is_cache_valid(cache[key]):
            entry = cache[key]
            enriched[str(i)] = {
                "status": entry.get("data", {}).get("status", "unknown"),
                "email_count": len(entry.get("data", {}).get("emails", [])),
                "has_socials": any(
                    entry.get("data", {}).get(p)
                    for p in ("instagram", "facebook", "twitter", "youtube", "tiktok", "linkedin")
                ),
                "brand_count": len(entry.get("data", {}).get("brands_carried", [])),
            }
    return JSONResponse(enriched)

@app.post("/api/enrich")
async def enrich_stores(request: Request):
    """Enrich selected stores via SSE stream."""
    body = await request.json()
    indices = body.get("store_indices", [])
    data = _load_data()
    cache = _load_cache()

    async def event_generator():
        total = len(indices)
        yield {"event": "start", "data": json.dumps({"total": total})}

        for progress_idx, store_idx in enumerate(indices):
            if store_idx < 0 or store_idx >= len(data):
                yield {"event": "progress", "data": json.dumps({
                    "index": store_idx, "progress": progress_idx + 1, "total": total,
                    "name": "Unknown", "status": "error", "message": "Invalid index",
                })}
                continue

            store = data[store_idx]
            name = store.get("name", "Unknown")
            website = store.get("website", "")
            key = _cache_key(name, website)

            # Check cache
            if key in cache and _is_cache_valid(cache[key]):
                result = cache[key]["data"]
                yield {"event": "progress", "data": json.dumps({
                    "index": store_idx, "progress": progress_idx + 1, "total": total,
                    "name": name, "status": "cached",
                    "data": result,
                })}
                continue

            # Scrape
            yield {"event": "progress", "data": json.dumps({
                "index": store_idx, "progress": progress_idx + 1, "total": total,
                "name": name, "status": "scraping",
            })}

            try:
                result = await scrape_store(website, store.get("email", ""))
                # Cache result
                cache[key] = {"timestamp": time.time(), "data": result}
                _save_cache(cache)

                yield {"event": "progress", "data": json.dumps({
                    "index": store_idx, "progress": progress_idx + 1, "total": total,
                    "name": name, "status": result["status"],
                    "data": result,
                })}
            except Exception as e:
                yield {"event": "progress", "data": json.dumps({
                    "index": store_idx, "progress": progress_idx + 1, "total": total,
                    "name": name, "status": "error", "message": str(e),
                })}

        yield {"event": "done", "data": json.dumps({"message": "Enrichment complete"})}

    return EventSourceResponse(event_generator())

@app.get("/api/store/{idx}")
async def store_detail(idx: int):
    """Return full store data + cached enrichment. Triggers scrape if not cached."""
    data = _load_data()
    if idx < 0 or idx >= len(data):
        return JSONResponse({"error": "Invalid index"}, status_code=404)

    store = data[idx]
    cache = _load_cache()
    key = _cache_key(store.get("name", ""), store.get("website", ""))

    enrichment = None
    if key in cache and _is_cache_valid(cache[key]):
        enrichment = cache[key]["data"]
    else:
        # Auto-enrich on detail open
        try:
            enrichment = await scrape_store(
                store.get("website", ""),
                store.get("email", ""),
            )
            cache[key] = {"timestamp": time.time(), "data": enrichment}
            _save_cache(cache)
        except Exception as e:
            enrichment = {"status": "error", "message": str(e)}

    return JSONResponse({"store": store, "enrichment": enrichment})

## ── Tags persistence ─────────────────────────────────────────────────────────
def _load_tags() -> dict:
    if TAGS_FILE.exists():
        try:
            return json.loads(TAGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

def _save_tags(tags: dict):
    TAGS_FILE.write_text(json.dumps(tags, indent=2))

@app.get("/api/tags")
async def get_tags():
    """Return all store tags."""
    return JSONResponse(_load_tags())

@app.post("/api/tags")
async def save_tags(request: Request):
    """Save store tags. Body: {tags: {idx: [tag1, tag2], ...}}"""
    body = await request.json()
    tags = body.get("tags", {})
    _save_tags(tags)
    return JSONResponse({"success": True})

@app.post("/api/export-airtable")
async def export_airtable(request: Request):
    """Export selected stores to Airtable."""
    body = await request.json()
    indices = body.get("store_indices", [])
    data = _load_data()
    cache = _load_cache()

    # Build stores list with enrichment data
    stores = []
    enrichments = {}
    for idx in indices:
        if 0 <= idx < len(data):
            store = {**data[idx], "_idx": idx}
            stores.append(store)
            # Attach enrichment if cached
            key = _cache_key(store.get("name", ""), store.get("website", ""))
            if key in cache and _is_cache_valid(cache[key]):
                enrichments[idx] = cache[key]["data"]

    try:
        stats = await export_to_airtable(stores, enrichments)
        return JSONResponse({"success": True, **stats})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

## ── Dealer Finder API ────────────────────────────────────────────────────────
@app.post("/api/dealer-finder")
async def dealer_finder(request: Request):
    """Find dealers for a brand via natural language query or direct URL."""
    body = await request.json()
    query = body.get("query", "")
    brand = body.get("brand", "")
    url = body.get("url", "")

    try:
        result = await find_brand_dealers(query=query, brand=brand, url=url)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse(
            {"brand": brand, "dealers": [], "source_url": "", "strategy": "none",
             "count": 0, "error": str(e)},
            status_code=500,
        )


## ── Lists API (proxies to api/lists.py logic for local dev) ─────────────────
import urllib.parse as _urlparse
import urllib.request as _urlreq

_AT_URL = f"https://api.airtable.com/v0/{os.environ.get('AIRTABLE_BASE_ID', '')}/{_urlparse.quote('Retailer Prospects')}"
_AT_KEY = os.environ.get("AIRTABLE_API_KEY", "")

def _at_request(method, url, data=None):
    headers = {"Authorization": f"Bearer {_AT_KEY}", "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    req = _urlreq.Request(url, data=body, headers=headers, method=method)
    with _urlreq.urlopen(req) as resp:
        return json.loads(resp.read())

def _at_fetch_all_with_lists():
    records = []
    offset = None
    fields = "&".join(
        f"fields%5B%5D={_urlparse.quote(f)}"
        for f in ["Store Name","City","State","Rating","Review Count","Phone","Email",
                   "Website","Store Type","Outreach Status","Prospect Lists","Referral Source","Notes"]
    )
    while True:
        url = f"{_AT_URL}?{fields}&pageSize=100"
        if offset: url += f"&offset={offset}"
        try:
            result = _at_request("GET", url)
        except Exception:
            # Prospect Lists field may not exist yet — return empty
            return []
        for rec in result.get("records", []):
            f = rec.get("fields", {})
            if f.get("Prospect Lists"):
                records.append({"id": rec["id"], "fields": f})
        offset = result.get("offset")
        if not offset: break
    return records

@app.get("/api/lists")
async def lists_get(request: Request):
    params = dict(request.query_params)
    action = params.get("action", "")

    if action == "get_lists":
        records = _at_fetch_all_with_lists()
        lists = {}
        for rec in records:
            f = rec["fields"]
            status = f.get("Outreach Status", "New")
            for ln in f.get("Prospect Lists", []):
                if ln not in lists:
                    lists[ln] = {"name": ln, "count": 0, "statuses": {}}
                lists[ln]["count"] += 1
                lists[ln]["statuses"][status] = lists[ln]["statuses"].get(status, 0) + 1
        return JSONResponse({"lists": sorted(lists.values(), key=lambda x: x["name"])})

    elif action == "get_prospects":
        list_name = params.get("list", "")
        if not list_name:
            return JSONResponse({"error": "Missing list"}, status_code=400)
        records = []
        offset = None
        fields = "&".join(
            f"fields%5B%5D={_urlparse.quote(f)}"
            for f in ["Store Name","City","State","Rating","Review Count","Phone","Email",
                       "Website","Store Type","Outreach Status","Prospect Lists","Referral Source","Notes"]
        )
        formula = _urlparse.quote(f'FIND("{list_name}", ARRAYJOIN({{Prospect Lists}}, ","))')
        while True:
            url = f"{_AT_URL}?{fields}&filterByFormula={formula}&pageSize=100"
            if offset: url += f"&offset={offset}"
            try:
                result = _at_request("GET", url)
            except Exception:
                break
            for rec in result.get("records", []):
                records.append({"id": rec["id"], "fields": rec.get("fields", {})})
            offset = result.get("offset")
            if not offset: break
        return JSONResponse({"prospects": records})

    elif action == "search_stores":
        q = params.get("q", "").lower().strip()
        limit = int(params.get("limit", "30"))
        if len(q) < 2:
            return JSONResponse({"error": "Query must be at least 2 characters"}, status_code=400)
        data = _load_data()
        results = []
        for i, store in enumerate(data):
            if len(results) >= limit:
                break
            name = (store.get("name") or "").lower()
            city = (store.get("city") or "").lower()
            state = (store.get("state") or "").lower()
            if q in name or q in city or q in state:
                results.append({
                    "idx": i,
                    "name": store.get("name", ""),
                    "city": store.get("city", ""),
                    "state": store.get("state", ""),
                    "rating": store.get("rating"),
                    "store_type": store.get("store_type", ""),
                })
        return JSONResponse({"stores": results})

    return JSONResponse({"error": "Unknown action"}, status_code=400)

@app.post("/api/lists")
async def lists_post(request: Request):
    body = await request.json()
    action = body.get("action", "")

    if action == "add_to_list":
        data = _load_data()
        store_indices = body.get("store_indices", [])
        list_name = body.get("list_name", "")
        referral_source = body.get("referral_source")
        requested = {}
        for idx in store_indices:
            if 0 <= idx < len(data):
                requested[data[idx]["name"]] = data[idx]
        # Fetch existing
        existing = {}
        offset = None
        while True:
            url = f"{_AT_URL}?fields%5B%5D=Store+Name&fields%5B%5D=Prospect+Lists&fields%5B%5D=Referral+Source&pageSize=100"
            if offset: url += f"&offset={offset}"
            result = _at_request("GET", url)
            for rec in result.get("records", []):
                name = rec.get("fields", {}).get("Store Name", "")
                if name: existing[name] = {"id": rec["id"], "fields": rec.get("fields", {})}
            offset = result.get("offset")
            if not offset: break
        updates, creates = [], []
        for name, store in requested.items():
            if name in existing:
                rec = existing[name]
                cur = rec["fields"].get("Prospect Lists", [])
                if list_name not in cur: cur.append(list_name)
                flds = {"Prospect Lists": cur}
                if referral_source and not rec["fields"].get("Referral Source"):
                    flds["Referral Source"] = referral_source
                updates.append({"id": rec["id"], "fields": flds})
            else:
                flds = {"Store Name": store.get("name",""), "City": store.get("city",""),
                         "State": store.get("state",""), "Outreach Status": "New",
                         "Prospect Lists": [list_name]}
                if referral_source: flds["Referral Source"] = referral_source
                creates.append({"fields": flds})
        added = 0
        for i in range(0, len(updates), 10):
            _at_request("PATCH", _AT_URL, {"records": updates[i:i+10], "typecast": True})
            added += len(updates[i:i+10])
        for i in range(0, len(creates), 10):
            _at_request("POST", _AT_URL, {"records": creates[i:i+10], "typecast": True})
            added += len(creates[i:i+10])
        return JSONResponse({"success": True, "added": added})

    elif action == "update_prospect":
        flds = {}
        if body.get("status") is not None: flds["Outreach Status"] = body["status"]
        if body.get("notes") is not None: flds["Notes"] = body["notes"]
        if body.get("referral_source") is not None: flds["Referral Source"] = body["referral_source"]
        _at_request("PATCH", _AT_URL, {"records": [{"id": body["record_id"], "fields": flds}], "typecast": True})
        return JSONResponse({"success": True, "updated": True})

    elif action == "remove_from_list":
        record_ids = body.get("record_ids", [])
        list_name = body.get("list_name", "")
        updates = []
        for rid in record_ids:
            try:
                r = _at_request("GET", f"{_AT_URL}/{rid}?fields%5B%5D=Prospect+Lists")
                cur = r.get("fields", {}).get("Prospect Lists", [])
                updates.append({"id": rid, "fields": {"Prospect Lists": [l for l in cur if l != list_name]}})
            except Exception: pass
        for i in range(0, len(updates), 10):
            _at_request("PATCH", _AT_URL, {"records": updates[i:i+10], "typecast": True})
        return JSONResponse({"success": True, "removed": len(updates)})

    elif action == "bulk_status":
        record_ids = body.get("record_ids", [])
        status = body.get("status", "")
        updates = [{"id": rid, "fields": {"Outreach Status": status}} for rid in record_ids]
        for i in range(0, len(updates), 10):
            _at_request("PATCH", _AT_URL, {"records": updates[i:i+10], "typecast": True})
        return JSONResponse({"success": True, "updated": len(updates)})

    elif action == "ai_populate":
        list_name = body.get("list_name", "").strip()
        description = body.get("description", "").strip()
        if not list_name or not description:
            return JSONResponse({"error": "list_name and description required"}, status_code=400)
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not anthropic_key:
            return JSONResponse({"error": "ANTHROPIC_API_KEY not configured"}, status_code=500)

        data = _load_data()
        # Build compact store list
        lines = []
        for i, s in enumerate(data):
            lines.append(f"{i}|{s.get('name','')}|{s.get('city','')}|{s.get('state','')}|{s.get('store_type','')}|{s.get('rating','')}")
        stores_compact = "\n".join(lines)

        payload = json.dumps({
            "model": "claude-opus-4-6",
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": f"""You are a store matching assistant for an e-bike retailer directory. Given the list of stores below and the user's description, return ONLY a JSON array of store index numbers that match the criteria.

Consider store name, city, state, store type, and rating when matching. Be thorough — include all stores that reasonably fit the description.

Store types: dedicated_ebike (e-bike specialist), bike_shop (general bicycle shop), outdoor_rec (outdoor/recreation), motorcycle (motorcycle dealer), sporting_goods (sporting goods store), other

Description: {description}

Stores (format: index|name|city|state|type|rating):
{stores_compact}

Return ONLY a valid JSON array of matching store indices, e.g. [0, 5, 12]. No explanation or other text."""}]
        }).encode()

        req = _urlreq.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with _urlreq.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read())
        except Exception as e:
            err_msg = str(e)
            if hasattr(e, 'read'):
                try:
                    err_body = e.read().decode()
                    err_json = json.loads(err_body)
                    err_msg = err_json.get("error", {}).get("message", err_body)
                except Exception:
                    pass
            return JSONResponse({"error": f"AI API error: {err_msg}"}, status_code=500)

        try:
            text = result["content"][0]["text"].strip()
            # Handle markdown code blocks
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            indices = json.loads(text)
            indices = [i for i in indices if isinstance(i, int) and 0 <= i < len(data)]
        except Exception as e:
            return JSONResponse({"error": f"Failed to parse AI response: {str(e)}"}, status_code=500)

        if not indices:
            return JSONResponse({"success": True, "added": 0, "matched": 0})

        # Use existing add_to_list logic
        requested = {}
        for idx in indices:
            requested[data[idx]["name"]] = data[idx]
        try:
            existing = {}
            offset = None
            while True:
                url = f"{_AT_URL}?fields%5B%5D=Store+Name&fields%5B%5D=Prospect+Lists&pageSize=100"
                if offset: url += f"&offset={offset}"
                r = _at_request("GET", url)
                for rec in r.get("records", []):
                    nm = rec.get("fields", {}).get("Store Name", "")
                    if nm: existing[nm] = {"id": rec["id"], "fields": rec.get("fields", {})}
                offset = r.get("offset")
                if not offset: break
            updates, creates = [], []
            for nm, store in requested.items():
                if nm in existing:
                    rec = existing[nm]
                    cur = rec["fields"].get("Prospect Lists", [])
                    if list_name not in cur: cur.append(list_name)
                    updates.append({"id": rec["id"], "fields": {"Prospect Lists": cur}})
                else:
                    creates.append({"fields": {
                        "Store Name": store.get("name",""), "City": store.get("city",""),
                        "State": store.get("state",""), "Outreach Status": "New",
                        "Prospect Lists": [list_name],
                    }})
            added = 0
            for i in range(0, len(updates), 10):
                _at_request("PATCH", _AT_URL, {"records": updates[i:i+10], "typecast": True})
                added += len(updates[i:i+10])
            for i in range(0, len(creates), 10):
                _at_request("POST", _AT_URL, {"records": creates[i:i+10], "typecast": True})
                added += len(creates[i:i+10])
            return JSONResponse({"success": True, "added": added, "matched": len(indices)})
        except Exception as e:
            return JSONResponse({"error": f"Airtable error: {str(e)}"}, status_code=500)

    return JSONResponse({"error": "Unknown action"}, status_code=400)

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
