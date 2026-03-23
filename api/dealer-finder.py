"""Serverless function — find brand dealers via natural language."""
import os
import sys
import json
import asyncio
from http.server import BaseHTTPRequestHandler

# Add parent dir to path so we can import dealer_scraper
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dealer_scraper import find_brand_dealers


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))

            query = body.get("query", "")
            brand = body.get("brand", "")
            url = body.get("url", "")

            result = asyncio.run(find_brand_dealers(query=query, brand=brand, url=url))

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "brand": "", "dealers": [], "source_url": "",
                "strategy": "none", "count": 0, "error": str(e),
            }).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
