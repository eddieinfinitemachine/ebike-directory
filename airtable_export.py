"""Export enriched retailer data to Airtable."""
from __future__ import annotations

import os
import asyncio
import time
from typing import Dict, List, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "").strip('"')
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "").strip('"')
TABLE_NAME = "Retailer Prospects"
AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_NAME}"
META_URL = f"https://api.airtable.com/v0/meta/bases/{AIRTABLE_BASE_ID}/tables"
BATCH_SIZE = 10
RATE_DELAY = 0.25  # seconds between batches

def _headers():
    return {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }

# ── Table creation via Metadata API ───────────────────────────────────────────
TABLE_SCHEMA = {
    "name": TABLE_NAME,
    "fields": [
        {"name": "Store Name", "type": "singleLineText"},
        {"name": "Address", "type": "singleLineText"},
        {"name": "City", "type": "singleLineText"},
        {"name": "State", "type": "singleLineText"},
        {"name": "Rating", "type": "number", "options": {"precision": 1}},
        {"name": "Review Count", "type": "number", "options": {"precision": 0}},
        {"name": "Score", "type": "number", "options": {"precision": 1}},
        {"name": "Phone", "type": "phoneNumber"},
        {"name": "Website", "type": "url"},
        {"name": "Store Type", "type": "singleSelect", "options": {"choices": [
            {"name": "dedicated_ebike", "color": "purpleBright"},
            {"name": "general_bike_shop", "color": "greenBright"},
            {"name": "electric_motorcycle", "color": "orangeBright"},
            {"name": "electric_scooter", "color": "yellowBright"},
            {"name": "electric_last_mile", "color": "cyanBright"},
            {"name": "general_powersports", "color": "redBright"},
        ]}},
        {"name": "Chain", "type": "singleLineText"},
        {"name": "Email", "type": "email"},
        {"name": "Instagram", "type": "url"},
        {"name": "Facebook", "type": "url"},
        {"name": "Twitter/X", "type": "url"},
        {"name": "YouTube", "type": "url"},
        {"name": "TikTok", "type": "url"},
        {"name": "LinkedIn", "type": "url"},
        {"name": "Owner/Contact", "type": "singleLineText"},
        {"name": "Store Hours", "type": "multilineText"},
        {"name": "Brands Carried", "type": "multilineText"},
        {"name": "Enrichment Status", "type": "singleSelect", "options": {"choices": [
            {"name": "success", "color": "greenBright"},
            {"name": "partial", "color": "yellowBright"},
            {"name": "cached", "color": "purpleBright"},
            {"name": "timeout", "color": "orangeBright"},
            {"name": "error", "color": "redBright"},
            {"name": "chain_skip", "color": "grayBright"},
            {"name": "no_website", "color": "grayBright"},
            {"name": "not_enriched", "color": "grayBright"},
        ]}},
        {"name": "Outreach Status", "type": "singleSelect", "options": {"choices": [
            {"name": "New", "color": "blueBright"},
            {"name": "Contacted", "color": "yellowBright"},
            {"name": "Responded", "color": "greenBright"},
            {"name": "Not Interested", "color": "redBright"},
            {"name": "Partner", "color": "purpleBright"},
        ]}},
        {"name": "Tags", "type": "multilineText"},
        {"name": "Notes", "type": "multilineText"},
    ],
}

async def _ensure_table_exists(client: httpx.AsyncClient) -> bool:
    """Check if table exists, create if not. Returns True if ready."""
    # Try listing tables to see if ours exists
    resp = await client.get(META_URL, headers=_headers())
    if resp.status_code != 200:
        # Try creating anyway
        pass
    else:
        tables = resp.json().get("tables", [])
        for t in tables:
            if t.get("name") == TABLE_NAME:
                return True  # Already exists

    # Create the table
    resp = await client.post(META_URL, headers=_headers(), json=TABLE_SCHEMA)
    if resp.status_code in (200, 201):
        return True
    # If 422, table might already exist (race condition)
    if resp.status_code == 422 and "already exists" in resp.text.lower():
        return True
    print(f"Table creation failed: {resp.status_code} {resp.text}")
    return False

# ── Record building ───────────────────────────────────────────────────────────
def _build_record(store: dict, enrichment: Optional[dict] = None) -> dict:
    """Build an Airtable record from store data + optional enrichment."""
    fields = {
        "Store Name": store.get("name", ""),
        "Address": store.get("address", ""),
        "City": store.get("city", ""),
        "State": store.get("state", ""),
        "Rating": float(store.get("rating", 0)),
        "Review Count": int(store.get("review_count", 0)),
        "Score": float(store.get("score", 0)),
        "Phone": store.get("phone", ""),
        "Website": store.get("website", ""),
        "Store Type": store.get("store_type", ""),
        "Chain": store.get("chain") or "",
    }

    # Email: prefer CSV email, supplement with scraped
    emails = []
    if store.get("email"):
        emails.append(store["email"].split(";")[0].strip())
    if enrichment:
        for e in enrichment.get("emails", []):
            if e not in emails:
                emails.append(e)
        fields["Email"] = "; ".join(emails[:3])  # max 3 emails
        fields["Instagram"] = enrichment.get("instagram") or ""
        fields["Facebook"] = enrichment.get("facebook") or ""
        fields["Twitter/X"] = enrichment.get("twitter") or ""
        fields["YouTube"] = enrichment.get("youtube") or ""
        fields["TikTok"] = enrichment.get("tiktok") or ""
        fields["LinkedIn"] = enrichment.get("linkedin") or ""
        fields["Owner/Contact"] = enrichment.get("owner_contact") or ""
        fields["Store Hours"] = enrichment.get("store_hours") or ""
        fields["Brands Carried"] = ", ".join(enrichment.get("brands_carried", []))
        fields["Enrichment Status"] = enrichment.get("status", "")
    else:
        fields["Email"] = "; ".join(emails) if emails else ""
        fields["Enrichment Status"] = "not_enriched"

    fields["Outreach Status"] = "New"

    # Tags
    if store.get("_tags"):
        fields["Tags"] = ", ".join(store["_tags"])

    # Remove empty string values to keep records clean
    return {"fields": {k: v for k, v in fields.items() if v != "" and v != 0}}

def _dedup_key(store: dict) -> str:
    return f"{store.get('name', '').strip()}|{store.get('state', '').strip()}"

async def _fetch_existing(client: httpx.AsyncClient) -> Dict[str, str]:
    """Fetch all existing records, return {dedup_key: record_id}."""
    existing = {}
    offset = None
    while True:
        params = {"pageSize": "100"}
        if offset:
            params["offset"] = offset
        resp = await client.get(AIRTABLE_URL, headers=_headers(), params=params)
        if resp.status_code in (404, 403, 422):
            return {}
        resp.raise_for_status()
        data = resp.json()
        for rec in data.get("records", []):
            f = rec.get("fields", {})
            key = f"{f.get('Store Name', '').strip()}|{f.get('State', '').strip()}"
            existing[key] = rec["id"]
        offset = data.get("offset")
        if not offset:
            break
        await asyncio.sleep(RATE_DELAY)
    return existing

async def export_to_airtable(
    stores: List[dict],
    enrichments: Optional[Dict[int, dict]] = None,
    callback=None,
) -> dict:
    """Push stores to Airtable. Returns summary stats."""
    stats = {"created": 0, "updated": 0, "errors": 0, "total": len(stores)}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Ensure table exists
        if not await _ensure_table_exists(client):
            raise RuntimeError("Could not create or find Airtable table")

        await asyncio.sleep(RATE_DELAY)

        # Get existing records for dedup
        existing = await _fetch_existing(client)

        # Build records, separating creates vs updates
        creates = []
        updates = []
        for store in stores:
            idx = store.get("_idx")
            enrichment = enrichments.get(idx) if enrichments and idx is not None else None
            record = _build_record(store, enrichment)
            key = _dedup_key(store)

            if key in existing:
                record["id"] = existing[key]
                updates.append(record)
            else:
                creates.append(record)

        # Batch creates
        for i in range(0, len(creates), BATCH_SIZE):
            batch = creates[i:i + BATCH_SIZE]
            try:
                resp = await client.post(
                    AIRTABLE_URL,
                    headers=_headers(),
                    json={"records": batch, "typecast": True},
                )
                resp.raise_for_status()
                stats["created"] += len(batch)
            except Exception as e:
                stats["errors"] += len(batch)
                if callback:
                    await callback("error", f"Create batch failed: {e}")
            await asyncio.sleep(RATE_DELAY)

        # Batch updates
        for i in range(0, len(updates), BATCH_SIZE):
            batch = updates[i:i + BATCH_SIZE]
            try:
                resp = await client.patch(
                    AIRTABLE_URL,
                    headers=_headers(),
                    json={"records": batch, "typecast": True},
                )
                resp.raise_for_status()
                stats["updated"] += len(batch)
            except Exception as e:
                stats["errors"] += len(batch)
                if callback:
                    await callback("error", f"Update batch failed: {e}")
            await asyncio.sleep(RATE_DELAY)

    if callback:
        await callback("done", stats)

    return stats
