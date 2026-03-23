"""Serverless function for prospect list management — backed by Airtable."""
import os
import json
from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")
TABLE_NAME = "Retailer Prospects"
AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(TABLE_NAME)}"


def _airtable_request(method, url, data=None):
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _fetch_all_with_lists():
    """Fetch all records that have Prospect Lists set."""
    records = []
    offset = None
    fields = "&".join(
        f"fields%5B%5D={urllib.parse.quote(f)}"
        for f in [
            "Store Name", "City", "State", "Rating", "Review Count",
            "Phone", "Email", "Website", "Store Type",
            "Outreach Status", "Prospect Lists", "Referral Source", "Notes",
        ]
    )
    while True:
        url = f"{AIRTABLE_URL}?{fields}&pageSize=100"
        if offset:
            url += f"&offset={offset}"
        try:
            result = _airtable_request("GET", url)
        except Exception:
            # Prospect Lists field may not exist yet — return empty
            return []
        for rec in result.get("records", []):
            f = rec.get("fields", {})
            if f.get("Prospect Lists"):
                records.append({"id": rec["id"], "fields": f})
        offset = result.get("offset")
        if not offset:
            break
    return records


def _get_lists_summary():
    """Return list names with counts and status breakdowns."""
    records = _fetch_all_with_lists()
    lists = {}
    for rec in records:
        f = rec["fields"]
        status = f.get("Outreach Status", "New")
        for list_name in f.get("Prospect Lists", []):
            if list_name not in lists:
                lists[list_name] = {"name": list_name, "count": 0, "statuses": {}}
            lists[list_name]["count"] += 1
            lists[list_name]["statuses"][status] = lists[list_name]["statuses"].get(status, 0) + 1
    return sorted(lists.values(), key=lambda x: x["name"])


def _get_prospects_for_list(list_name):
    """Fetch all records belonging to a specific list."""
    records = []
    offset = None
    fields = "&".join(
        f"fields%5B%5D={urllib.parse.quote(f)}"
        for f in [
            "Store Name", "City", "State", "Rating", "Review Count",
            "Phone", "Email", "Website", "Store Type",
            "Outreach Status", "Prospect Lists", "Referral Source", "Notes",
        ]
    )
    formula = urllib.parse.quote(f'FIND("{list_name}", ARRAYJOIN({{Prospect Lists}}, ","))')
    while True:
        url = f"{AIRTABLE_URL}?{fields}&filterByFormula={formula}&pageSize=100"
        if offset:
            url += f"&offset={offset}"
        result = _airtable_request("GET", url)
        for rec in result.get("records", []):
            records.append({"id": rec["id"], "fields": rec.get("fields", {})})
        offset = result.get("offset")
        if not offset:
            break
    return records


def _load_data():
    """Load data.json for index-to-name mapping."""
    data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.json")
    with open(data_path) as f:
        return json.load(f)


def _find_or_create_records(store_indices, list_name, referral_source=None):
    """Add stores to a list. Creates records if they don't exist in Airtable."""
    data = _load_data()

    # Build name->store mapping for requested indices
    requested = {}
    for idx in store_indices:
        if 0 <= idx < len(data):
            store = data[idx]
            requested[store["name"]] = store

    if not requested:
        return {"added": 0, "error": "No valid store indices"}

    # Fetch existing records to find matches
    existing = {}  # name -> {id, fields}
    offset = None
    while True:
        url = f"{AIRTABLE_URL}?fields%5B%5D=Store+Name&fields%5B%5D=Prospect+Lists&fields%5B%5D=Referral+Source&pageSize=100"
        if offset:
            url += f"&offset={offset}"
        result = _airtable_request("GET", url)
        for rec in result.get("records", []):
            name = rec.get("fields", {}).get("Store Name", "")
            if name:
                existing[name] = {"id": rec["id"], "fields": rec.get("fields", {})}
        offset = result.get("offset")
        if not offset:
            break

    updates = []
    creates = []

    for name, store in requested.items():
        if name in existing:
            rec = existing[name]
            current_lists = rec["fields"].get("Prospect Lists", [])
            if list_name not in current_lists:
                current_lists.append(list_name)
            fields = {"Prospect Lists": current_lists}
            if referral_source and not rec["fields"].get("Referral Source"):
                fields["Referral Source"] = referral_source
            updates.append({"id": rec["id"], "fields": fields})
        else:
            fields = {
                "Store Name": store.get("name", ""),
                "Address": store.get("address", ""),
                "City": store.get("city", ""),
                "State": store.get("state", ""),
                "Rating": float(store.get("rating", 0)),
                "Review Count": int(store.get("review_count", 0)),
                "Phone": store.get("phone", ""),
                "Website": store.get("website", ""),
                "Email": store.get("email", ""),
                "Store Type": store.get("store_type", ""),
                "Outreach Status": "New",
                "Prospect Lists": [list_name],
            }
            if referral_source:
                fields["Referral Source"] = referral_source
            # Remove empty values
            fields = {k: v for k, v in fields.items() if v != "" and v != 0}
            creates.append({"fields": fields})

    added = 0
    # Batch updates
    for i in range(0, len(updates), 10):
        batch = updates[i:i + 10]
        _airtable_request("PATCH", AIRTABLE_URL, {"records": batch, "typecast": True})
        added += len(batch)

    # Batch creates
    for i in range(0, len(creates), 10):
        batch = creates[i:i + 10]
        _airtable_request("POST", AIRTABLE_URL, {"records": batch, "typecast": True})
        added += len(batch)

    return {"added": added}


def _remove_from_list(record_ids, list_name):
    """Remove list_name from records' Prospect Lists field."""
    # Fetch current lists for these records
    updates = []
    for rec_id in record_ids:
        url = f"{AIRTABLE_URL}/{rec_id}?fields%5B%5D=Prospect+Lists"
        try:
            result = _airtable_request("GET", url)
            current = result.get("fields", {}).get("Prospect Lists", [])
            new_lists = [l for l in current if l != list_name]
            updates.append({"id": rec_id, "fields": {"Prospect Lists": new_lists}})
        except Exception:
            continue

    removed = 0
    for i in range(0, len(updates), 10):
        batch = updates[i:i + 10]
        _airtable_request("PATCH", AIRTABLE_URL, {"records": batch, "typecast": True})
        removed += len(batch)

    return {"removed": removed}


def _update_prospect(record_id, status=None, notes=None, referral_source=None):
    """Update a single prospect's fields."""
    fields = {}
    if status is not None:
        fields["Outreach Status"] = status
    if notes is not None:
        fields["Notes"] = notes
    if referral_source is not None:
        fields["Referral Source"] = referral_source
    if not fields:
        return {"updated": False, "error": "No fields to update"}

    _airtable_request("PATCH", AIRTABLE_URL, {
        "records": [{"id": record_id, "fields": fields}],
        "typecast": True,
    })
    return {"updated": True}


def _bulk_status(record_ids, status):
    """Batch update outreach status for multiple records."""
    updates = [{"id": rid, "fields": {"Outreach Status": status}} for rid in record_ids]
    updated = 0
    for i in range(0, len(updates), 10):
        batch = updates[i:i + 10]
        _airtable_request("PATCH", AIRTABLE_URL, {"records": batch, "typecast": True})
        updated += len(batch)
    return {"updated": updated}


class handler(BaseHTTPRequestHandler):
    def _send_json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            action = params.get("action", [""])[0]

            if action == "get_lists":
                self._send_json(200, {"lists": _get_lists_summary()})
            elif action == "get_prospects":
                list_name = params.get("list", [""])[0]
                if not list_name:
                    self._send_json(400, {"error": "Missing list parameter"})
                    return
                prospects = _get_prospects_for_list(list_name)
                self._send_json(200, {"prospects": prospects})
            elif action == "search_stores":
                q = params.get("q", [""])[0].lower().strip()
                limit = int(params.get("limit", ["30"])[0])
                if len(q) < 2:
                    self._send_json(400, {"error": "Query must be at least 2 characters"})
                    return
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
                self._send_json(200, {"stores": results})
            else:
                self._send_json(400, {"error": f"Unknown action: {action}"})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))
            action = body.get("action", "")

            if action == "add_to_list":
                result = _find_or_create_records(
                    body.get("store_indices", []),
                    body.get("list_name", ""),
                    body.get("referral_source"),
                )
                self._send_json(200, {"success": True, **result})

            elif action == "create_list":
                list_name = body.get("list_name", "").strip()
                if not list_name:
                    self._send_json(400, {"error": "List name required"})
                    return
                self._send_json(200, {"success": True, "list_name": list_name})

            elif action == "update_prospect":
                result = _update_prospect(
                    body.get("record_id", ""),
                    status=body.get("status"),
                    notes=body.get("notes"),
                    referral_source=body.get("referral_source"),
                )
                self._send_json(200, {"success": True, **result})

            elif action == "remove_from_list":
                result = _remove_from_list(
                    body.get("record_ids", []),
                    body.get("list_name", ""),
                )
                self._send_json(200, {"success": True, **result})

            elif action == "bulk_status":
                result = _bulk_status(
                    body.get("record_ids", []),
                    body.get("status", ""),
                )
                self._send_json(200, {"success": True, **result})

            elif action == "ai_populate":
                list_name = body.get("list_name", "").strip()
                description = body.get("description", "").strip()
                if not list_name or not description:
                    self._send_json(400, {"error": "list_name and description required"})
                    return
                anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
                if not anthropic_key:
                    self._send_json(500, {"error": "ANTHROPIC_API_KEY not configured"})
                    return

                data = _load_data()
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

                req = urllib.request.Request(
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
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        result = json.loads(resp.read())
                    text = result["content"][0]["text"].strip()
                    if "```" in text:
                        text = text.split("```")[1]
                        if text.startswith("json"):
                            text = text[4:]
                        text = text.strip()
                    indices = json.loads(text)
                    indices = [i for i in indices if isinstance(i, int) and 0 <= i < len(data)]
                except Exception as e:
                    self._send_json(500, {"error": f"AI matching failed: {str(e)}"})
                    return

                if not indices:
                    self._send_json(200, {"success": True, "added": 0, "matched": 0})
                    return

                result = _find_or_create_records(indices, list_name)
                self._send_json(200, {"success": True, **result, "matched": len(indices)})

            else:
                self._send_json(400, {"error": f"Unknown action: {action}"})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
