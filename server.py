"""FastAPI server for e-bike directory enrichment and export."""
import json
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

# ── Setup ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CACHE_FILE = BASE_DIR / "enrichment_cache.json"
TAGS_FILE = BASE_DIR / "tags.json"
DATA_FILE = BASE_DIR / "data.json"
INDEX_FILE = BASE_DIR / "index.html"
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

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
