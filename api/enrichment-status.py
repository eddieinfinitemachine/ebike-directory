"""Serverless function — returns enrichment status from Airtable."""
import os
import json
from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")
TABLE_NAME = "Retailer Prospects"
AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(TABLE_NAME)}"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Load data.json to map names to indices
            data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.json")
            with open(data_path) as f:
                data = json.load(f)
            name_to_idx = {s["name"]: s["_idx"] for s in data}

            # Fetch enrichment status from Airtable
            enriched = {}
            offset = None
            fields = "fields%5B%5D=Store+Name&fields%5B%5D=Enrichment+Status&fields%5B%5D=Email&fields%5B%5D=Instagram&fields%5B%5D=Facebook"
            while True:
                url = f"{AIRTABLE_URL}?{fields}&pageSize=100"
                if offset:
                    url += f"&offset={offset}"
                headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req) as resp:
                    result = json.loads(resp.read())

                for rec in result.get("records", []):
                    f_data = rec.get("fields", {})
                    name = f_data.get("Store Name", "")
                    status = f_data.get("Enrichment Status", "")
                    if name in name_to_idx and status and status != "not_enriched":
                        enriched[str(name_to_idx[name])] = {
                            "status": status,
                            "email_count": 1 if f_data.get("Email") else 0,
                            "has_socials": bool(f_data.get("Instagram") or f_data.get("Facebook")),
                        }
                offset = result.get("offset")
                if not offset:
                    break

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(enriched).encode())
        except Exception as e:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")
