"""Serverless function for tag management — backed by Airtable."""
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


def _fetch_all_tags():
    """Fetch Tags field from all Airtable records, return {store_name: [tags]}."""
    tags = {}
    offset = None
    while True:
        url = f"{AIRTABLE_URL}?fields%5B%5D=Store+Name&fields%5B%5D=Tags&pageSize=100"
        if offset:
            url += f"&offset={offset}"
        result = _airtable_request("GET", url)
        for rec in result.get("records", []):
            f = rec.get("fields", {})
            name = f.get("Store Name", "")
            tag_str = f.get("Tags", "")
            if name and tag_str:
                tags[name] = [t.strip() for t in tag_str.split(",") if t.strip()]
        offset = result.get("offset")
        if not offset:
            break
    return tags


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Return tags keyed by store index."""
        try:
            # Load data.json to map names to indices
            data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.json")
            with open(data_path) as f:
                data = json.load(f)

            name_to_idx = {s["name"]: s["_idx"] for s in data}
            airtable_tags = _fetch_all_tags()

            # Convert name-keyed tags to idx-keyed
            idx_tags = {}
            for name, tag_list in airtable_tags.items():
                if name in name_to_idx:
                    idx_tags[str(name_to_idx[name])] = tag_list

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(idx_tags).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_POST(self):
        """Save tags to Airtable."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))
            new_tags = body.get("tags", {})

            # Load data.json to map indices to names
            data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.json")
            with open(data_path) as f:
                data = json.load(f)

            idx_to_name = {str(s["_idx"]): s["name"] for s in data}

            # Fetch existing Airtable records to find record IDs
            existing = {}
            offset = None
            while True:
                url = f"{AIRTABLE_URL}?fields%5B%5D=Store+Name&pageSize=100"
                if offset:
                    url += f"&offset={offset}"
                result = _airtable_request("GET", url)
                for rec in result.get("records", []):
                    name = rec.get("fields", {}).get("Store Name", "")
                    if name:
                        existing[name] = rec["id"]
                offset = result.get("offset")
                if not offset:
                    break

            # Update records with tags
            updates = []
            for idx_str, tag_list in new_tags.items():
                name = idx_to_name.get(idx_str, "")
                if name and name in existing:
                    updates.append({
                        "id": existing[name],
                        "fields": {"Tags": ", ".join(tag_list) if tag_list else ""},
                    })

            # Batch update (10 at a time)
            for i in range(0, len(updates), 10):
                batch = updates[i : i + 10]
                _airtable_request("PATCH", AIRTABLE_URL, {"records": batch, "typecast": True})

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "updated": len(updates)}).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
