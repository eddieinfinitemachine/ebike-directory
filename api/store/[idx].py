"""Serverless function — returns store data + any Airtable enrichment."""
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
            # Parse idx from URL path: /api/store/123
            path = self.path.split("?")[0]
            idx = int(path.strip("/").split("/")[-1])

            # Load data.json
            data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data.json")
            with open(data_path) as f:
                data = json.load(f)

            if idx < 0 or idx >= len(data):
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid index"}).encode())
                return

            store = data[idx]

            # Try to fetch enrichment data from Airtable
            enrichment = {"status": "not_enriched", "emails": [], "images": [], "brands_carried": []}
            try:
                formula = urllib.parse.quote(f"{{Store Name}}='{store['name']}'")
                url = f"{AIRTABLE_URL}?filterByFormula={formula}&maxRecords=1"
                headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req) as resp:
                    result = json.loads(resp.read())
                    records = result.get("records", [])
                    if records:
                        f = records[0].get("fields", {})
                        enrichment = {
                            "status": f.get("Enrichment Status", "not_enriched"),
                            "emails": [e.strip() for e in (f.get("Email", "") or "").split(";") if e.strip()],
                            "instagram": f.get("Instagram"),
                            "facebook": f.get("Facebook"),
                            "twitter": f.get("Twitter/X"),
                            "youtube": f.get("YouTube"),
                            "tiktok": f.get("TikTok"),
                            "linkedin": f.get("LinkedIn"),
                            "owner_contact": f.get("Owner/Contact"),
                            "store_hours": f.get("Store Hours"),
                            "brands_carried": [b.strip() for b in (f.get("Brands Carried", "") or "").split(",") if b.strip()],
                            "images": [],
                            "description": None,
                            "pages_scraped": 0,
                        }
            except Exception:
                pass

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"store": store, "enrichment": enrichment}).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
