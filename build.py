#!/usr/bin/env python3
"""Build the e-bike directory website with state grouping, chain detection,
selection checkboxes, enrichment modal, and Airtable export."""
import csv, json, re
from collections import defaultdict

# ── Chain detection ────────────────────────────────────────────────────────
CHAIN_PREFIXES = [
    "Trek Bicycle",
    "Pedego Electric Bikes",
    "Pedego Electric",
    "ERIK'S",
    "Conte's Bike Shop",
    "Fly E-Bike",
    "Rad Power Bikes",
    "Global Bikes & E-Bikes",
    "Global Bikes",
    "REI",
    "Cycle Gear",
    "Phat Tire Bike Shop",
    "Phat Tire",
    "Wheel & Sprocket",
    "Bike Mart",
    "Scheller's Fitness",
    "Mike's Bikes",
    "Whizz",
    "PRO BIKE+RUN",
    "Bicycle Garage Indy",
    "Bicycle Chain",
    "Tampa Bay eBikes",
    "Open Road Bicycles",
    "Freewheel Bike",
    "Kozy's Cyclery",
    "Scheels",
]

def get_chain(name):
    """Return chain name if store belongs to a chain, else None."""
    for prefix in sorted(CHAIN_PREFIXES, key=len, reverse=True):
        if name.startswith(prefix) or name.lower().startswith(prefix.lower()):
            return prefix
    return None

# ── Data loading ───────────────────────────────────────────────────────────
US_STATES_SET = {'AK','AL','AR','AZ','CA','CO','CT','DC','DE','FL','GA','HI',
    'IA','ID','IL','IN','KS','KY','LA','MA','MD','ME','MI','MN','MO','MS',
    'MT','NC','ND','NE','NH','NJ','NM','NV','NY','OH','OK','OR','PA','RI',
    'SC','SD','TN','TX','UT','VA','VT','WA','WI','WV','WY'}

US_STATES = {
    'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California',
    'CO':'Colorado','CT':'Connecticut','DE':'Delaware','DC':'District of Columbia',
    'FL':'Florida','GA':'Georgia','HI':'Hawaii','ID':'Idaho','IL':'Illinois',
    'IN':'Indiana','IA':'Iowa','KS':'Kansas','KY':'Kentucky','LA':'Louisiana',
    'MA':'Massachusetts','MD':'Maryland','ME':'Maine','MI':'Michigan',
    'MN':'Minnesota','MS':'Mississippi','MO':'Missouri','MT':'Montana',
    'NE':'Nebraska','NV':'Nevada','NH':'New Hampshire','NJ':'New Jersey',
    'NM':'New Mexico','NY':'New York','NC':'North Carolina','ND':'North Dakota',
    'OH':'Ohio','OK':'Oklahoma','OR':'Oregon','PA':'Pennsylvania',
    'RI':'Rhode Island','SC':'South Carolina','SD':'South Dakota',
    'TN':'Tennessee','TX':'Texas','UT':'Utah','VT':'Vermont','VA':'Virginia',
    'WA':'Washington','WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming'
}

with open('/Users/eddie/ebike_stores.csv') as f:
    rows = list(csv.DictReader(f))

rows = [r for r in rows if r['state'] in US_STATES_SET and not get_chain(r['name'])]
for i, r in enumerate(rows):
    r['rating'] = float(r['rating'])
    r['review_count'] = int(r['review_count'])
    r['score'] = round(r['rating'] * r['review_count'], 1)
    r['chain'] = None
    r['_idx'] = i  # stable index for selection

data_json = json.dumps(rows, separators=(',',':'))
print(f"Total stores: {len(rows)}")
print(f"In chains: {sum(1 for r in rows if r['chain'])}")
print(f"With email: {sum(1 for r in rows if r.get('email','').strip())}")

# Also write data.json separately for server mode
with open('/Users/eddie/ebike-directory/data.json', 'w') as f:
    f.write(data_json)
print("Written: data.json")

# ── Write HTML ─────────────────────────────────────────────────────────────
html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>US Electric Vehicle Retailer Directory</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --bg: #ffffff;
  --surface: #fafafa;
  --surface2: #f4f4f5;
  --border: #e5e5e5;
  --text: #171717;
  --text2: #737373;
  --accent: #6366f1;
  --accent2: #4f46e5;
  --green: #16a34a;
  --yellow: #ca8a04;
  --orange: #ea580c;
  --radius: 10px;
}}
body {{
  font-family: 'Geist', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.5; min-height: 100vh;
  padding-bottom: 80px;
  -webkit-font-smoothing: antialiased;
}}
.container {{ max-width: 1400px; margin: 0 auto; padding: 0 24px; }}

/* Header */
header {{ border-bottom: 1px solid var(--border); height: 56px; display: flex; align-items: center; }}
header .container {{ display: flex; align-items: center; justify-content: space-between; width: 100%; }}
.logo {{ display: flex; align-items: center; gap: 16px; }}
.logo svg {{ height: 18px; width: auto; }}
.logo .divider {{ width: 1px; height: 24px; background: var(--border); }}
.logo h1 {{ font-size: 15px; font-weight: 500; color: var(--text2); letter-spacing: -0.01em; }}
.header-meta {{ color: var(--text2); font-size: 12px; }}

/* Stats */
.stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; padding: 24px 0; }}
.stat-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; cursor: pointer; transition: all 0.15s; }}
.stat-card:hover {{ background: var(--surface2); border-color: rgba(0,0,0,0.08); }}
.stat-card.active {{ border-color: var(--accent); background: rgba(99,102,241,0.08); }}
.stat-card .label {{ font-size: 11px; color: var(--text2); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px; font-weight: 500; }}
.stat-card .value {{ font-size: 24px; font-weight: 700; letter-spacing: -0.02em; }}
.stat-card .value.accent {{ color: var(--text); }}
.stat-card .value.green {{ color: var(--green); }}
.stat-card .value.yellow {{ color: var(--yellow); }}

/* Controls */
.controls {{ display: flex; flex-wrap: wrap; gap: 10px; padding-bottom: 20px; align-items: stretch; }}
.search-box {{ flex: 1 1 280px; position: relative; }}
.search-box svg {{ position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--text2); width: 16px; height: 16px; }}
.search-box input {{
  width: 100%; padding: 9px 12px 9px 36px; background: transparent;
  border: 1px solid var(--border); border-radius: var(--radius); color: var(--text);
  font-size: 14px; outline: none; transition: border-color 0.15s;
}}
.search-box input:focus {{ border-color: rgba(0,0,0,0.15); }}
.search-box input::placeholder {{ color: var(--text2); }}
select {{
  padding: 9px 32px 9px 12px; background: transparent; border: 1px solid var(--border);
  border-radius: var(--radius); color: var(--text); font-size: 13px; outline: none;
  cursor: pointer; min-width: 140px; -webkit-appearance: none; appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23737373' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 10px center;
}}
select:focus {{ border-color: rgba(0,0,0,0.15); }}
.results-count {{ display: flex; align-items: center; padding: 0 4px; color: var(--text2); font-size: 13px; white-space: nowrap; }}

/* State section */
.state-section {{ margin-bottom: 24px; }}
.state-header {{
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius) var(--radius) 0 0; cursor: pointer; user-select: none;
  transition: background 0.15s;
}}
.state-header:hover {{ background: var(--surface2); }}
.state-header.collapsed {{ border-radius: var(--radius); }}
.state-header h2 {{ font-size: 15px; font-weight: 600; display: flex; align-items: center; gap: 8px; letter-spacing: -0.01em; }}
.state-header h2 .code {{ color: var(--accent2); font-size: 12px; font-weight: 600; background: rgba(99,102,241,0.12); padding: 2px 7px; border-radius: 5px; }}
.state-header .meta {{ display: flex; gap: 14px; align-items: center; color: var(--text2); font-size: 12px; }}
.state-header .arrow {{ font-size: 10px; color: var(--text2); transition: transform 0.15s; }}
.state-header.collapsed .arrow {{ transform: rotate(-90deg); }}
.state-body {{ border: 1px solid var(--border); border-top: none; border-radius: 0 0 var(--radius) var(--radius); overflow: hidden; }}
.state-body.hidden {{ display: none; }}

/* Chain group */
.chain-group {{ border-bottom: 1px solid var(--border); }}
.chain-group:last-child {{ border-bottom: none; }}
.chain-header {{
  display: flex; align-items: center; gap: 8px; padding: 10px 16px;
  background: rgba(99,102,241,0.04); cursor: pointer; user-select: none;
  font-size: 13px; font-weight: 600; color: var(--accent2);
  transition: background 0.15s;
}}
.chain-header:hover {{ background: rgba(99,102,241,0.08); }}
.chain-header .chain-arrow {{ font-size: 9px; color: var(--text2); transition: transform 0.15s; }}
.chain-header.collapsed .chain-arrow {{ transform: rotate(-90deg); }}
.chain-header .chain-count {{ font-weight: 400; color: var(--text2); font-size: 12px; }}
.chain-body.hidden {{ display: none; }}

/* Store card */
.store-card {{
  display: grid !important;
  grid-template-columns: 1fr auto auto auto !important;
  gap: 16px;
  padding: 10px 16px;
  align-items: center;
  border-bottom: 1px solid var(--border);
  transition: background 0.15s;
  cursor: pointer;
}}
.store-card:hover {{ background: rgba(0,0,0,0.02); }}
.store-card.selected {{ background: rgba(99,102,241,0.08); }}
.store-card:last-child {{ border-bottom: none; }}
.store-check {{ width: 15px; height: 15px; accent-color: var(--accent); cursor: pointer; vertical-align: middle; margin-right: 6px; }}
.store-name {{ font-weight: 500; font-size: 14px; }}
.store-name a {{ color: var(--text); text-decoration: none; }}
.store-name a:hover {{ color: var(--accent2); }}
.store-address {{ font-size: 12px; color: var(--text2); margin-top: 1px; }}
.store-meta {{ display: flex; align-items: center; gap: 6px; white-space: nowrap; }}
.badge {{
  display: inline-block; padding: 2px 8px; border-radius: 6px;
  font-size: 11px; font-weight: 500; white-space: nowrap;
}}
.badge.ebike {{ background: rgba(99,102,241,0.12); color: var(--accent2); }}
.badge.general {{ background: rgba(34,197,94,0.12); color: var(--green); }}
.badge.motorcycle {{ background: rgba(249,115,22,0.12); color: var(--orange); }}
.badge.scooter {{ background: rgba(234,179,8,0.12); color: var(--yellow); }}
.badge.lastmile {{ background: rgba(6,182,212,0.12); color: #06b6d4; }}
.badge.powersports {{ background: rgba(239,68,68,0.12); color: #ef4444; }}
.badge.unknown {{ background: rgba(163,163,163,0.12); color: var(--text2); }}
.badge.enriched {{ background: rgba(34,197,94,0.1); color: var(--green); font-size: 10px; }}
.badge.has-email {{ background: rgba(234,179,8,0.1); color: var(--yellow); font-size: 10px; }}
.badge.starred {{ background: rgba(234,179,8,0.15); color: var(--yellow); font-size: 10px; }}
.badge.tag {{ background: rgba(6,182,212,0.12); color: #06b6d4; font-size: 10px; }}
.store-card.removed {{ opacity: 0.3; }}
.rating {{ display: flex; align-items: center; gap: 4px; white-space: nowrap; font-size: 13px; }}
.rating .stars {{ color: var(--yellow); font-size: 11px; }}
.rating .num {{ font-weight: 600; }}
.rating .reviews {{ color: var(--text2); font-size: 11px; }}
.contact {{ display: flex; flex-direction: column; gap: 1px; align-items: flex-end; min-width: 130px; }}
.contact a {{ color: var(--text2); text-decoration: none; font-size: 12px; }}
.contact a:hover {{ color: var(--text); }}
.contact .web {{ max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; }}
.contact .email {{ max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; }}

/* Independents section label */
.indep-label {{
  padding: 8px 16px; font-size: 11px; color: var(--text2);
  font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em;
  background: rgba(0,0,0,0.02); border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 8px; transition: background 0.15s;
}}
.indep-label:hover {{ background: rgba(0,0,0,0.03); }}
.indep-arrow {{ font-size: 10px; transition: transform 0.2s; }}
.indep-arrow.collapsed {{ transform: rotate(-90deg); }}

/* Empty */
.empty {{ text-align: center; padding: 60px 20px; color: var(--text2); }}
.empty h3 {{ font-size: 18px; color: var(--text); margin-bottom: 8px; }}

/* State nav */
.state-nav {{
  display: flex; flex-wrap: wrap; gap: 6px; padding-bottom: 24px;
}}
.state-nav a {{
  padding: 3px 10px; background: transparent; border: 1px solid var(--border);
  border-radius: 6px; color: var(--text2); text-decoration: none; font-size: 11px;
  font-weight: 500; transition: all 0.15s;
}}
.state-nav a:hover {{ border-color: rgba(0,0,0,0.12); color: var(--text); }}
.state-nav a.active-tag {{ border-color: var(--accent); color: var(--accent2); background: rgba(99,102,241,0.08); }}

/* ── Selection toolbar ── */
.toolbar {{
  position: fixed; bottom: 0; left: 0; right: 0; z-index: 100;
  background: var(--surface); border-top: 1px solid var(--border);
  padding: 10px 24px; display: none; align-items: center; gap: 12px;
  box-shadow: 0 -2px 12px rgba(0,0,0,0.3);
}}
.toolbar.visible {{ display: flex; }}
.toolbar .sel-count {{ font-weight: 600; font-size: 13px; color: var(--text); min-width: 90px; }}
.toolbar button {{
  padding: 7px 14px; border-radius: 8px; border: none; font-size: 12px;
  font-weight: 500; cursor: pointer; transition: all 0.15s;
}}
.toolbar .btn-secondary {{
  background: transparent; color: var(--text); border: 1px solid var(--border);
}}
.toolbar .btn-secondary:hover {{ border-color: rgba(0,0,0,0.12); background: var(--surface2); }}
.toolbar .btn-primary {{
  background: var(--accent); color: white;
}}
.toolbar .btn-primary:hover {{ background: var(--accent2); }}
.toolbar .btn-green {{
  background: var(--green); color: white;
}}
.toolbar .btn-green:hover {{ opacity: 0.85; }}
.toolbar .spacer {{ flex: 1; }}

/* ── Context menu ── */
.ctx-menu {{
  position: fixed; z-index: 500; background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.15); padding: 4px 0;
  min-width: 180px; display: none;
}}
.ctx-menu.visible {{ display: block; }}
.ctx-menu button {{
  display: block; width: 100%; text-align: left; padding: 8px 16px; border: none;
  background: none; font-size: 13px; cursor: pointer; color: var(--text);
  font-family: inherit;
}}
.ctx-menu button:hover {{ background: var(--surface2); }}

/* ── Modal ── */
.modal-overlay {{
  position: fixed; inset: 0; z-index: 200; background: rgba(0,0,0,0.4);
  display: none; align-items: center; justify-content: center;
}}
.modal-overlay.visible {{ display: flex; }}
.modal {{
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  width: 90%; max-width: 700px; max-height: 80vh; display: flex; flex-direction: column;
  box-shadow: 0 16px 48px rgba(0,0,0,0.4);
}}
.modal-header {{
  display: flex; align-items: center; justify-content: space-between;
  padding: 20px 24px; border-bottom: 1px solid var(--border);
}}
.modal-header h3 {{ font-size: 18px; font-weight: 700; }}
.modal-close {{
  background: none; border: none; color: var(--text2); font-size: 24px;
  cursor: pointer; padding: 4px 8px; border-radius: 6px;
}}
.modal-close:hover {{ background: var(--surface2); color: var(--text); }}
.modal-body {{ padding: 20px 24px; overflow-y: auto; flex: 1; }}
.modal-footer {{
  padding: 16px 24px; border-top: 1px solid var(--border);
  display: flex; align-items: center; gap: 12px;
}}

/* Progress bar */
.progress-bar {{ width: 100%; height: 8px; background: var(--surface2); border-radius: 4px; margin-bottom: 16px; overflow: hidden; }}
.progress-fill {{ height: 100%; background: linear-gradient(90deg, var(--accent), var(--green)); border-radius: 4px; transition: width 0.3s; width: 0%; }}

/* Log entries */
.log-entry {{ display: flex; align-items: center; gap: 10px; padding: 6px 0; font-size: 13px; border-bottom: 1px solid rgba(46,51,69,0.3); }}
.log-entry:last-child {{ border-bottom: none; }}
.log-status {{ font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600; white-space: nowrap; }}
.log-status.success {{ background: rgba(0,184,148,0.15); color: var(--green); }}
.log-status.cached {{ background: rgba(108,92,231,0.15); color: var(--accent2); }}
.log-status.partial {{ background: rgba(253,203,110,0.15); color: var(--yellow); }}
.log-status.error {{ background: rgba(225,112,85,0.15); color: var(--orange); }}
.log-status.timeout {{ background: rgba(225,112,85,0.15); color: var(--orange); }}
.log-status.scraping {{ background: rgba(108,92,231,0.15); color: var(--accent2); }}
.log-status.chain_skip {{ background: rgba(147,152,173,0.15); color: var(--text2); }}
.log-status.no_website {{ background: rgba(147,152,173,0.15); color: var(--text2); }}
.log-name {{ flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.log-detail {{ color: var(--text2); font-size: 12px; white-space: nowrap; }}

/* ── Detail modal ── */
.detail-overlay {{
  position: fixed; inset: 0; z-index: 300; background: rgba(0,0,0,0.4);
  display: none; align-items: center; justify-content: center;
  padding: 20px;
}}
.detail-overlay.visible {{ display: flex; }}
.detail-modal {{
  background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius);
  width: 95%; max-width: 960px; max-height: 90vh; display: flex; flex-direction: column;
  box-shadow: 0 16px 48px rgba(0,0,0,0.5);
}}
.detail-header {{
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 24px; border-bottom: 1px solid var(--border);
  background: var(--surface); border-radius: var(--radius) var(--radius) 0 0;
}}
.detail-header h2 {{ font-size: 17px; font-weight: 600; flex: 1; letter-spacing: -0.01em; }}
.detail-header .detail-badges {{ display: flex; gap: 6px; margin-left: 12px; }}
.detail-close {{
  background: none; border: none; color: var(--text2); font-size: 28px;
  cursor: pointer; padding: 4px 10px; border-radius: 8px; margin-left: 12px;
}}
.detail-close:hover {{ background: var(--surface2); color: var(--text); }}
.detail-body {{ display: flex; gap: 0; overflow: hidden; flex: 1; min-height: 0; }}
.detail-left {{
  flex: 0 0 380px; border-right: 1px solid var(--border);
  overflow-y: auto; background: var(--surface);
}}
.detail-right {{ flex: 1; overflow-y: auto; padding: 24px 28px; }}
.detail-images {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 2px;
}}
.detail-images img {{
  width: 100%; height: 140px; object-fit: cover; cursor: pointer;
  transition: opacity 0.2s; background: var(--surface2);
}}
.detail-images img:first-child {{
  grid-column: 1 / -1; height: 220px;
}}
.detail-images img:hover {{ opacity: 0.85; }}
.detail-images .img-placeholder {{
  grid-column: 1 / -1; padding: 60px 20px; text-align: center;
  color: var(--text2); font-size: 14px; background: var(--surface2);
}}
.detail-preview {{
  border-top: 1px solid var(--border);
}}
.detail-preview iframe {{
  width: 100%; height: 240px; border: none; background: white;
}}
.detail-preview-label {{
  padding: 10px 16px; font-size: 11px; color: var(--text2);
  text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600;
  display: flex; align-items: center; justify-content: space-between;
}}
.detail-preview-label a {{
  color: var(--accent2); text-decoration: none; font-size: 12px;
  text-transform: none; letter-spacing: 0; font-weight: 500;
}}
.detail-preview-label a:hover {{ color: var(--text); }}
.detail-section {{ margin-bottom: 24px; }}
.detail-section h4 {{
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
  color: var(--text2); margin-bottom: 10px; font-weight: 600;
}}
.detail-row {{
  display: flex; align-items: flex-start; gap: 10px;
  padding: 6px 0; font-size: 14px;
}}
.detail-row .label {{ color: var(--text2); min-width: 100px; font-size: 13px; flex-shrink: 0; }}
.detail-row .value {{ color: var(--text); word-break: break-word; }}
.detail-row .value a {{ color: var(--accent2); text-decoration: none; }}
.detail-row .value a:hover {{ text-decoration: underline; }}
.social-links {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.social-link {{
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 14px; background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; color: var(--accent2); text-decoration: none; font-size: 13px;
  font-weight: 500; transition: all 0.15s;
}}
.social-link:hover {{ border-color: var(--accent); background: var(--surface2); }}
.brand-tags {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.brand-tag {{
  padding: 3px 10px; background: rgba(99,102,241,0.08); border: 1px solid rgba(99,102,241,0.15);
  border-radius: 6px; font-size: 12px; font-weight: 500; color: var(--accent2);
}}
.detail-loading {{
  display: flex; align-items: center; justify-content: center;
  padding: 80px 20px; color: var(--text2); font-size: 15px; gap: 12px;
}}
.detail-loading .spinner {{
  width: 20px; height: 20px; border: 2px solid var(--border);
  border-top-color: var(--accent); border-radius: 50%;
  animation: spin 0.8s linear infinite;
}}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
.detail-actions {{
  display: flex; gap: 10px; flex-wrap: wrap; padding-top: 8px;
}}
.detail-actions button, .detail-actions a {{
  padding: 8px 18px; border-radius: 8px; border: none; font-size: 13px;
  font-weight: 600; cursor: pointer; text-decoration: none; display: inline-flex;
  align-items: center; gap: 6px; transition: all 0.15s;
}}

@media (max-width: 600px) {{
  .controls {{ flex-direction: column; }}
  .store-card {{ grid-template-columns: 1fr; gap: 8px; }}
  .contact {{ align-items: flex-start; }}
  .state-header .meta {{ display: none; }}
  .toolbar {{ flex-wrap: wrap; }}
  .detail-body {{ flex-direction: column; }}
  .detail-left {{ flex: none; max-height: 300px; border-right: none; border-bottom: 1px solid var(--border); }}
}}
</style>
</head>
<body>

<header>
  <div class="container">
    <div class="logo">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 831.97 45.21"><g><path fill="currentColor" d="M13.56.33V44.88H0V.33Z"/><path fill="currentColor" d="M44.93.33l27,33.86L71.58.33H84.4V44.88H62.63L36,11.35l.34,33.53h-13V.33Z"/><path fill="currentColor" d="M141.66.33V10.42H107.87V19.3h32.06V29.39H107.87V44.88H94.38V.33Z"/><path fill="currentColor" d="M163.09.33V44.88H149.54V.33Z"/><path fill="currentColor" d="M194.46.33l27,33.86L221.11.33h12.82V44.88H212.16L185.58,11.35l.33,33.53h-13V.33Z"/><path fill="currentColor" d="M257.44.33V44.88H243.89V.33Z"/><path fill="currentColor" d="M264.52,11.35V.33h53.23v11H297.91V44.88H284.35V11.35Z"/><path fill="currentColor" d="M374.26,10.42h-36V18.1h33.93v8.81H338.26V34.8h36.47V44.88H324.91V.33h49.35Z"/><path fill="currentColor" d="M423,.33l16.23,29.59L455.34.33h21.37V44.88H463.49l.67-34.39L444.39,44.88H433.57L414.13,10.49l.4,34.39H401.44V.33Z"/><path fill="currentColor" d="M526.62.33,551,44.88H536.17l-4.4-8H503.05l-4.28,8H483.41l25-44.55Zm-9.21,9.55-9.49,17.77H527Z"/><path fill="currentColor" d="M611.09,32.22c0,1.14-.11,2.11-.2,2.91a13.74,13.74,0,0,1-.36,2.07,11.1,11.1,0,0,1-.57,1.6,8.86,8.86,0,0,1-4.21,4.31,21.46,21.46,0,0,1-8.08,1.77q-2.07.19-6.18.27t-10.78.06c-3.21,0-5.91,0-8.12-.13a53.92,53.92,0,0,1-5.61-.47,20.34,20.34,0,0,1-3.9-.9,14.32,14.32,0,0,1-2.94-1.43,10.08,10.08,0,0,1-2.77-2.58,11.37,11.37,0,0,1-1.74-3.87,32.31,32.31,0,0,1-.9-5.84c-.18-2.32-.27-5.12-.27-8.42q0-4.41.27-7.48a23.36,23.36,0,0,1,1-5.24,10,10,0,0,1,1.87-3.54,10.88,10.88,0,0,1,2.9-2.37,16.6,16.6,0,0,1,3.17-1.44,23.22,23.22,0,0,1,4-.9Q570,.27,573.29.13c2.19-.09,4.83-.13,8-.13q6.21,0,10.22.07c2.67,0,4.88.15,6.61.33a27.49,27.49,0,0,1,4.21.7,18,18,0,0,1,3,1.1,8.12,8.12,0,0,1,4,4.35,20.63,20.63,0,0,1,1.27,7.94V16h-13a11.59,11.59,0,0,0-.5-2.87,2.69,2.69,0,0,0-1.7-1.6,12.6,12.6,0,0,0-3.87-.67c-1.7-.09-4-.13-6.95-.13q-4.14,0-6.74.06c-1.74.05-3.13.14-4.18.27a10.12,10.12,0,0,0-2.4.53,5.12,5.12,0,0,0-1.44.87,4.48,4.48,0,0,0-1,1.24,7.48,7.48,0,0,0-.6,1.87,20.61,20.61,0,0,0-.3,2.94c0,1.18-.07,2.66-.07,4.44a42.86,42.86,0,0,0,.37,6.31A5.34,5.34,0,0,0,570,32.66a8,8,0,0,0,4.21,1.43,75.75,75.75,0,0,0,7.68.31c2.54,0,4.57,0,6.11,0s2.77,0,3.71-.1a12.82,12.82,0,0,0,2.13-.23,7.73,7.73,0,0,0,1.47-.5,3.77,3.77,0,0,0,2.07-1.81,8.36,8.36,0,0,0,.6-3.6h13.16C611.16,29.72,611.14,31.09,611.09,32.22Z"/><path fill="currentColor" d="M633.44.33v16.5H664.3V.33h13.56V44.88H664.3v-17H633.44v17H619.88V.33Z"/><path fill="currentColor" d="M701.33.33V44.88H687.77V.33Z"/><path fill="currentColor" d="M732.7.33l27,33.86L759.35.33h12.82V44.88H750.4L723.82,11.35l.33,33.53h-13V.33Z"/><path fill="currentColor" d="M831.51,10.42h-36V18.1h33.93v8.81H795.51V34.8H832V44.88H782.15V.33h49.36Z"/></g></svg>
      <div class="divider"></div>
      <h1>Retailer Directory</h1>
    </div>
    <div class="header-meta">
      <a href="lists.html" style="color:var(--accent);text-decoration:none;font-weight:500;margin-right:16px;">Prospect Lists</a>
      3,573 EV retailers across 49 states
    </div>
  </div>
</header>

<main class="container">
  <div class="stats" id="stats"></div>

  <div class="controls">
    <div class="search-box">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input type="text" id="search" placeholder="Search stores, cities, chains...">
    </div>
    <select id="typeFilter">
      <option value="">All Types</option>
      <option value="dedicated_ebike">Dedicated E-Bike</option>
      <option value="general_bike_shop">General Bike Shop</option>
      <option value="electric_motorcycle">Electric Motorcycle</option>
      <option value="electric_scooter">Electric Scooter/Moped</option>
      <option value="electric_last_mile">Last Mile / Cargo</option>
      <option value="general_powersports">Powersports / Motorcycle</option>
    </select>
    <select id="sortSelect">
      <option value="score">Top Rated (Score)</option>
      <option value="rating">Highest Rating</option>
      <option value="reviews">Most Reviews</option>
      <option value="name">Name A-Z</option>
    </select>
    <span class="results-count" id="resultsCount"></span>
  </div>

  <div class="state-nav" id="stateNav"></div>
  <div class="state-nav" id="tagNav" style="padding-bottom:16px;"></div>
  <div id="content"></div>
  <div class="empty" id="empty" style="display:none;">
    <div style="font-size:48px;margin-bottom:16px;">&#128270;</div>
    <h3>No stores found</h3>
    <p>Try adjusting your search or filters</p>
  </div>
</main>

<!-- Context menu -->
<div class="ctx-menu" id="ctxMenu">
  <button onclick="ctxAddToList()">Add to List</button>
  <button onclick="ctxEnrich()">Enrich</button>
  <button onclick="ctxViewDetail()">View Details</button>
</div>

<!-- Selection toolbar -->
<div class="toolbar" id="toolbar">
  <span class="sel-count" id="selCount">0 selected</span>
  <button class="btn-secondary" onclick="selectAllVisible()">Select All Visible</button>
  <button class="btn-secondary" onclick="clearSelection()">Clear</button>
  <button class="btn-secondary" onclick="starSelected()" style="color:var(--yellow);">&#9733; Star</button>
  <button class="btn-secondary" onclick="tagSelected()" style="color:#00ced1;">Tag</button>
  <button class="btn-secondary" onclick="removeSelected()" style="color:var(--orange);">Remove</button>
  <span class="spacer"></span>
  <button class="btn-secondary" onclick="openAddToListModal()" style="color:var(--accent);">Add to List</button>
  <button class="btn-primary" onclick="enrichSelected()">Enrich Selected</button>
  <button class="btn-green" onclick="exportSelected()">Export to Airtable</button>
</div>

<!-- Add to List modal -->
<div class="modal-overlay" id="listModalOverlay" onclick="if(event.target===this)closeListModal()">
  <div class="modal" style="max-width:440px;">
    <div class="modal-header">
      <h3>Add to Prospect List</h3>
      <button class="modal-close" onclick="closeListModal()">&times;</button>
    </div>
    <div class="modal-body">
      <div style="margin-bottom:16px;">
        <label style="font-size:13px;font-weight:500;display:block;margin-bottom:6px;">List</label>
        <select id="listSelect" style="width:100%;margin-bottom:8px;" onchange="if(this.value==='__new__')document.getElementById('newListInput').style.display='block';">
          <option value="">Select a list...</option>
          <option value="__new__">+ Create new list</option>
        </select>
        <input type="text" id="newListInput" placeholder="New list name..." style="width:100%;display:none;padding:9px 12px;border:1px solid var(--border);border-radius:var(--radius);font-size:14px;background:transparent;color:var(--text);outline:none;">
      </div>
      <div>
        <label style="font-size:13px;font-weight:500;display:block;margin-bottom:6px;">Referral Source (optional)</label>
        <input type="text" id="listReferralInput" placeholder="e.g. Trade show, Cold outreach..." style="width:100%;padding:9px 12px;border:1px solid var(--border);border-radius:var(--radius);font-size:14px;background:transparent;color:var(--text);outline:none;">
      </div>
    </div>
    <div class="modal-footer">
      <span class="spacer" style="flex:1;"></span>
      <button class="btn-secondary" onclick="closeListModal()">Cancel</button>
      <button class="btn-primary" onclick="submitAddToList()">Add</button>
    </div>
  </div>
</div>

<!-- Enrichment modal -->
<div class="modal-overlay" id="modalOverlay">
  <div class="modal">
    <div class="modal-header">
      <h3 id="modalTitle">Enrichment Progress</h3>
      <button class="modal-close" onclick="closeModal()">&times;</button>
    </div>
    <div class="modal-body" id="modalBody">
      <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
      <div id="modalLog"></div>
    </div>
    <div class="modal-footer">
      <span id="modalStatus" style="color:var(--text2);font-size:13px;"></span>
      <span class="spacer" style="flex:1;"></span>
      <button class="btn-secondary" id="modalCloseBtn" onclick="closeModal()" style="display:none;">Close</button>
    </div>
  </div>
</div>

<!-- Store detail modal -->
<div class="detail-overlay" id="detailOverlay" onclick="if(event.target===this)closeDetail()">
  <div class="detail-modal">
    <div class="detail-header">
      <h2 id="detailName"></h2>
      <div class="detail-badges" id="detailBadges"></div>
      <button class="detail-close" onclick="closeDetail()">&times;</button>
    </div>
    <div class="detail-body">
      <div class="detail-left" id="detailLeft"></div>
      <div class="detail-right" id="detailRight"></div>
    </div>
  </div>
</div>

<script>
const DATA = {data_json};

const US_STATES = {json.dumps(US_STATES)};

// ── Selection state ──────────────────────────────────────────────────────
const selected = new Set();
const starred = new Set();
const removed = new Set();
const storeTags = {{}};  // idx -> Set of tags
let activeTag = '';  // current tag filter
const ENRICHMENT = {{}};  // idx -> enrichment data
const ENRICHMENT_STATUS = {{}};  // idx -> {{status, email_count, has_socials, brand_count}}
let lastVisibleIndices = [];

function init() {{
  renderStats();
  applyFilters();
  document.getElementById('search').addEventListener('input', debounce(applyFilters, 200));
  document.getElementById('typeFilter').addEventListener('change', () => {{ syncActiveCard(); applyFilters(); }});
  document.getElementById('sortSelect').addEventListener('change', applyFilters);
  loadEnrichmentStatus();
  loadTags();
  // Deep-link: ?detail=IDX opens store detail modal
  const params = new URLSearchParams(window.location.search);
  const detailIdx = params.get('detail');
  if (detailIdx !== null) openDetail(parseInt(detailIdx));
}}

async function loadTags() {{
  try {{
    const resp = await fetch('/api/tags');
    if (resp.ok) {{
      const data = await resp.json();
      Object.entries(data).forEach(([idx, tags]) => {{
        storeTags[parseInt(idx)] = new Set(tags);
      }});
      applyFilters();
    }}
  }} catch(e) {{}}
}}

async function saveTags() {{
  const out = {{}};
  Object.entries(storeTags).forEach(([idx, tags]) => {{
    if (tags.size > 0) out[idx] = Array.from(tags);
  }});
  try {{
    await fetch('/api/tags', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{tags: out}}),
    }});
  }} catch(e) {{}}
}}

async function loadEnrichmentStatus() {{
  try {{
    const resp = await fetch('/api/enrichment-status');
    if (resp.ok) {{
      const data = await resp.json();
      Object.entries(data).forEach(([idx, info]) => {{
        ENRICHMENT_STATUS[parseInt(idx)] = info;
      }});
      applyFilters();  // re-render with badges
    }}
  }} catch(e) {{
    // Not running via server.py, that's fine
  }}
}}

function renderStats() {{
  const total = DATA.length;
  const dedicated = DATA.filter(d => d.store_type === 'dedicated_ebike').length;
  const motorcycles = DATA.filter(d => d.store_type === 'electric_motorcycle').length;
  const scooters = DATA.filter(d => d.store_type === 'electric_scooter').length;
  const lastmile = DATA.filter(d => d.store_type === 'electric_last_mile').length;
  const powersports = DATA.filter(d => d.store_type === 'general_powersports').length;
  const general = DATA.filter(d => d.store_type === 'general_bike_shop').length;
  const states = new Set(DATA.map(d => d.state)).size;
  const chains = new Set(DATA.filter(d => d.chain).map(d => d.chain)).size;
  const withEmail = DATA.filter(d => d.email).length;
  document.getElementById('stats').innerHTML = `
    <div class="stat-card" data-type="" onclick="filterByType(this)"><div class="label">Total Stores</div><div class="value accent">${{total.toLocaleString()}}</div></div>
    <div class="stat-card" data-type="dedicated_ebike" onclick="filterByType(this)"><div class="label">E-Bike Specialists</div><div class="value green">${{dedicated}}</div></div>
    <div class="stat-card" data-type="electric_motorcycle" onclick="filterByType(this)"><div class="label">Electric Motorcycle</div><div class="value" style="color:var(--orange)">${{motorcycles}}</div></div>
    <div class="stat-card" data-type="general_powersports" onclick="filterByType(this)"><div class="label">Powersports</div><div class="value" style="color:#ff6b6b">${{powersports}}</div></div>
    <div class="stat-card" data-type="general_bike_shop" onclick="filterByType(this)"><div class="label">General Bike</div><div class="value green">${{general}}</div></div>
    <div class="stat-card" data-type="" onclick="filterByType(this)"><div class="label">States</div><div class="value">${{states}}</div></div>
    <div class="stat-card" data-type="" onclick="filterByType(this)"><div class="label">Have Email</div><div class="value yellow">${{withEmail}}</div></div>
  `;
}}

function applyFilters() {{
  const q = document.getElementById('search').value.toLowerCase().trim();
  const type = document.getElementById('typeFilter').value;
  const sort = document.getElementById('sortSelect').value;

  // Build tag nav from all tagged stores
  const allTags = {{}};
  Object.entries(storeTags).forEach(([idx, tags]) => {{
    tags.forEach(t => {{ allTags[t] = (allTags[t] || 0) + 1; }});
  }});
  const tagNav = document.getElementById('tagNav');
  if (Object.keys(allTags).length > 0) {{
    tagNav.innerHTML = Object.entries(allTags)
      .sort((a,b) => b[1] - a[1])
      .map(([tag, count]) => `<a href="#" class="${{activeTag === tag ? 'active-tag' : ''}}" onclick="filterByTag('${{tag}}');return false;">${{tag}} (${{count}})</a>`)
      .join('');
  }} else {{
    tagNav.innerHTML = '';
  }}

  let filtered = DATA.filter(d => {{
    if (type && d.store_type !== type) return false;
    if (activeTag) {{
      const tags = storeTags[d._idx];
      if (!tags || !tags.has(activeTag)) return false;
    }}
    if (q) {{
      const tagStr = storeTags[d._idx] ? Array.from(storeTags[d._idx]).join(' ') : '';
      const hay = `${{d.name}} ${{d.city}} ${{d.state}} ${{d.address}} ${{d.chain||''}} ${{d.email||''}} ${{US_STATES[d.state]||''}} ${{tagStr}}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }}
    return true;
  }});

  // Track visible indices for Select All Visible
  lastVisibleIndices = filtered.map(d => d._idx);

  // Sort within groups
  const sortFn = (a, b) => {{
    if (sort === 'score') return b.score - a.score;
    if (sort === 'rating') return b.rating - a.rating || b.review_count - a.review_count;
    if (sort === 'reviews') return b.review_count - a.review_count;
    if (sort === 'name') return a.name.localeCompare(b.name);
    return 0;
  }};

  // Group by state
  const byState = {{}};
  filtered.forEach(d => {{
    if (!byState[d.state]) byState[d.state] = [];
    byState[d.state].push(d);
  }});

  // Sort states by full name
  const stateKeys = Object.keys(byState).sort((a,b) => (US_STATES[a]||a).localeCompare(US_STATES[b]||b));

  // Build state nav
  const nav = document.getElementById('stateNav');
  nav.innerHTML = stateKeys.map(s => `<a href="#state-${{s}}">${{s}} (${{byState[s].length}})</a>`).join('');

  document.getElementById('resultsCount').textContent = `${{filtered.length}} stores in ${{stateKeys.length}} states`;

  const content = document.getElementById('content');
  const empty = document.getElementById('empty');

  if (filtered.length === 0) {{
    content.innerHTML = '';
    empty.style.display = 'block';
    return;
  }}
  empty.style.display = 'none';

  let html = '';
  stateKeys.forEach(st => {{
    const stores = byState[st].sort(sortFn);
    const dedicated = stores.filter(s => s.store_type === 'dedicated_ebike').length;

    // Separate chains and independents
    const chainGroups = {{}};
    const independents = [];
    stores.forEach(s => {{
      if (s.chain) {{
        if (!chainGroups[s.chain]) chainGroups[s.chain] = [];
        chainGroups[s.chain].push(s);
      }} else {{
        independents.push(s);
      }}
    }});

    const chainNames = Object.keys(chainGroups).sort((a,b) => chainGroups[b].length - chainGroups[a].length);

    html += `<div class="state-section" id="state-${{st}}">`;
    html += `<div class="state-header" onclick="toggleState('${{st}}')">
      <h2><span class="code">${{st}}</span> ${{US_STATES[st] || st}}</h2>
      <div class="meta">
        <span>${{stores.length}} stores</span>
        <span>${{dedicated}} e-bike specialists</span>
        ${{chainNames.length ? `<span>${{chainNames.length}} chains</span>` : ''}}
        <span class="arrow">&#9660;</span>
      </div>
    </div>`;
    html += `<div class="state-body" id="body-${{st}}">`;

    // Render chain groups
    chainNames.forEach(chain => {{
      const cStores = chainGroups[chain].sort(sortFn);
      const cid = `chain-${{st}}-${{chain.replace(/[^a-zA-Z0-9]/g,'_')}}`;
      html += `<div class="chain-group">`;
      html += `<div class="chain-header" onclick="toggleChain('${{cid}}')">
        <span class="chain-arrow">&#9660;</span>
        ${{esc(chain)}}
        <span class="chain-count">&mdash; ${{cStores.length}} location${{cStores.length>1?'s':''}}</span>
      </div>`;
      html += `<div class="chain-body" id="${{cid}}">`;
      cStores.forEach(s => {{ html += renderStore(s); }});
      html += `</div></div>`;
    }});

    // Render independents
    if (independents.length > 0) {{
      const iid = `indep-${{st}}`;
      if (chainNames.length > 0) {{
        html += `<div class="indep-label" onclick="toggleIndep('${{iid}}')" style="cursor:pointer;user-select:none;">
          <span class="indep-arrow" id="arrow-${{iid}}">&#9660;</span> Independent Stores (${{independents.length}})
        </div>`;
        html += `<div id="${{iid}}">`;
      }} else {{
        html += `<div>`;
      }}
      independents.forEach(s => {{ html += renderStore(s); }});
      html += `</div>`;
    }}

    html += `</div></div>`;
  }});

  content.innerHTML = html;
  updateToolbar();
}}

function renderStore(d) {{
  const badgeMap = {{
    'dedicated_ebike': ['ebike', 'E-Bike Specialist'],
    'general_bike_shop': ['general', 'General Bike'],
    'electric_motorcycle': ['motorcycle', 'Electric Motorcycle'],
    'electric_scooter': ['scooter', 'Scooter / Moped'],
    'electric_last_mile': ['lastmile', 'Last Mile / Cargo'],
    'general_powersports': ['powersports', 'Powersports'],
  }};
  const [bc, bl] = badgeMap[d.store_type] || ['unknown', 'Other'];
  const badge = `<span class="badge ${{bc}}">${{bl}}</span>`;

  const stars = '&#9733;'.repeat(Math.floor(d.rating));
  const webClean = d.website ? d.website.replace(/^https?:\\/\\//, '').replace(/\\/+$/, '').split('?')[0].split('#')[0] : '';
  const webHref = d.website && !d.website.startsWith('http') ? 'https://' + d.website : d.website;

  const isChecked = selected.has(d._idx) ? 'checked' : '';
  const selClass = selected.has(d._idx) ? ' selected' : '';

  // Enrichment/email badges
  let extraBadges = '';
  if (d.email) extraBadges += ' <span class="badge has-email">email</span>';
  const es = ENRICHMENT_STATUS[d._idx];
  if (es) {{
    extraBadges += ' <span class="badge enriched">enriched</span>';
  }}

  const isStarred = starred.has(d._idx);
  const isRemoved = removed.has(d._idx);
  const removedClass = isRemoved ? ' removed' : '';
  if (isStarred) extraBadges += ' <span class="badge starred">&#9733;</span>';
  const tags = storeTags[d._idx];
  if (tags && tags.size > 0) {{
    tags.forEach(t => {{ extraBadges += ` <span class="badge tag">${{esc(t)}}</span>`; }});
  }}

  return `<div class="store-card${{selClass}}${{removedClass}}" data-idx="${{d._idx}}" onclick="onCardClick(event, ${{d._idx}})" ondblclick="onCardDblClick(event, ${{d._idx}})" oncontextmenu="onCardContext(event, ${{d._idx}})">
    <div>
      <div class="store-name">${{esc(d.name)}}${{extraBadges}}</div>
      <div class="store-address">${{esc(d.address)}}</div>
    </div>
    <div>${{badge}}</div>
    <div class="rating">
      <span class="num">${{d.rating}}</span>
      <span class="stars">${{stars}}</span>
      <span class="reviews">(${{d.review_count.toLocaleString()}})</span>
    </div>
    <div class="contact">
      ${{d.phone ? `<a href="tel:${{d.phone}}">${{esc(d.phone)}}</a>` : ''}}
      ${{d.email ? `<a class="email" href="mailto:${{d.email.split(';')[0].trim()}}">${{esc(d.email.split(';')[0].trim())}}</a>` : ''}}
      ${{webClean ? `<a class="web" href="${{esc(webHref)}}" target="_blank" rel="noopener">${{esc(webClean)}}</a>` : ''}}
    </div>
  </div>`;
}}

// ── Selection functions ──────────────────────────────────────────────────
function toggleSelect(idx, checked) {{
  if (checked) {{
    selected.add(idx);
  }} else {{
    selected.delete(idx);
  }}
  // Update card visual
  const card = document.querySelector(`.store-card[data-idx="${{idx}}"]`);
  if (card) card.classList.toggle('selected', checked);
  updateToolbar();
}}

function selectAllVisible() {{
  lastVisibleIndices.forEach(idx => selected.add(idx));
  document.querySelectorAll('.store-card').forEach(card => card.classList.add('selected'));
  updateToolbar();
}}

function clearSelection() {{
  selected.clear();
  document.querySelectorAll('.store-card').forEach(card => card.classList.remove('selected'));
  updateToolbar();
}}

function updateToolbar() {{
  const tb = document.getElementById('toolbar');
  const count = selected.size;
  if (count > 0) {{
    tb.classList.add('visible');
    document.getElementById('selCount').textContent = `${{count}} selected`;
  }} else {{
    tb.classList.remove('visible');
  }}
}}

// ── Enrichment ──────────────────────────────────────────────────────────
async function enrichSelected() {{
  const indices = Array.from(selected);
  if (indices.length === 0) return;

  if (indices.length > 100) {{
    if (!confirm(`You're about to enrich ${{indices.length}} stores. This may take a while. Continue?`)) return;
  }}

  openModal('Enrichment Progress');
  const log = document.getElementById('modalLog');
  const fill = document.getElementById('progressFill');
  const status = document.getElementById('modalStatus');
  log.innerHTML = '';
  fill.style.width = '0%';
  status.textContent = 'Starting...';
  document.getElementById('modalCloseBtn').style.display = 'none';

  try {{
    const resp = await fetch('/api/enrich', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{store_indices: indices}}),
    }});

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {{
      const {{done, value}} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {{stream: true}});

      // Parse SSE lines
      const lines = buffer.split('\\n');
      buffer = lines.pop();  // keep incomplete line

      for (const line of lines) {{
        if (line.startsWith('data: ')) {{
          try {{
            const data = JSON.parse(line.slice(6));
            if (data.total) {{
              const pct = Math.round((data.progress / data.total) * 100);
              fill.style.width = pct + '%';
              status.textContent = `${{data.progress}} / ${{data.total}}`;
            }}
            if (data.name && data.status !== 'scraping') {{
              // Store enrichment data
              if (data.data) {{
                ENRICHMENT[data.index] = data.data;
                ENRICHMENT_STATUS[data.index] = {{
                  status: data.data.status,
                  email_count: (data.data.emails || []).length,
                  has_socials: !!(data.data.instagram || data.data.facebook || data.data.twitter),
                  brand_count: (data.data.brands_carried || []).length,
                }};
              }}
              // Add log entry
              const detail = data.data ?
                `${{(data.data.emails||[]).length}} emails, ${{(data.data.brands_carried||[]).length}} brands, ${{data.data.pages_scraped||0}} pages` :
                (data.message || '');
              log.innerHTML += `<div class="log-entry">
                <span class="log-status ${{data.status}}">${{data.status}}</span>
                <span class="log-name">${{esc(data.name)}}</span>
                <span class="log-detail">${{detail}}</span>
              </div>`;
              log.scrollTop = log.scrollHeight;
            }}
          }} catch(e) {{}}
        }}
      }}
    }}

    status.textContent = 'Enrichment complete!';
  }} catch(e) {{
    status.textContent = 'Error: ' + e.message;
  }}

  document.getElementById('modalCloseBtn').style.display = 'block';
  applyFilters();  // re-render with enrichment badges
}}

// ── Airtable export ──────────────────────────────────────────────────────
async function exportSelected() {{
  const indices = Array.from(selected);
  if (indices.length === 0) return;

  if (!confirm(`Export ${{indices.length}} stores to Airtable?`)) return;

  openModal('Airtable Export');
  const log = document.getElementById('modalLog');
  const fill = document.getElementById('progressFill');
  const status = document.getElementById('modalStatus');
  log.innerHTML = '<div class="log-entry"><span class="log-status scraping">pushing</span><span class="log-name">Sending to Airtable...</span></div>';
  fill.style.width = '50%';
  status.textContent = 'Exporting...';
  document.getElementById('modalCloseBtn').style.display = 'none';

  try {{
    const resp = await fetch('/api/export-airtable', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{store_indices: indices}}),
    }});
    const data = await resp.json();
    fill.style.width = '100%';

    if (data.success) {{
      status.textContent = 'Export complete!';
      log.innerHTML = `<div class="log-entry">
        <span class="log-status success">done</span>
        <span class="log-name">Created: ${{data.created}}, Updated: ${{data.updated}}, Errors: ${{data.errors}}</span>
      </div>`;
    }} else {{
      status.textContent = 'Export failed';
      log.innerHTML = `<div class="log-entry">
        <span class="log-status error">error</span>
        <span class="log-name">${{esc(data.error || 'Unknown error')}}</span>
      </div>`;
    }}
  }} catch(e) {{
    fill.style.width = '100%';
    status.textContent = 'Error: ' + e.message;
    log.innerHTML = `<div class="log-entry"><span class="log-status error">error</span><span class="log-name">${{esc(e.message)}}</span></div>`;
  }}

  document.getElementById('modalCloseBtn').style.display = 'block';
}}

// ── Add to List ─────────────────────────────────────────────────────────
async function openAddToListModal() {{
  const sel = document.getElementById('listSelect');
  // Keep first two options, remove the rest
  while (sel.options.length > 2) sel.remove(2);
  document.getElementById('newListInput').style.display = 'none';
  document.getElementById('newListInput').value = '';
  document.getElementById('listReferralInput').value = '';
  sel.value = '';
  // Fetch existing lists
  try {{
    const resp = await fetch('/api/lists?action=get_lists');
    if (resp.ok) {{
      const data = await resp.json();
      (data.lists || []).forEach(l => {{
        const opt = document.createElement('option');
        opt.value = l.name;
        opt.textContent = `${{l.name}} (${{l.count}})`;
        sel.appendChild(opt);
      }});
    }}
  }} catch(e) {{}}
  document.getElementById('listModalOverlay').classList.add('visible');
}}

function closeListModal() {{
  document.getElementById('listModalOverlay').classList.remove('visible');
}}

async function submitAddToList() {{
  const sel = document.getElementById('listSelect');
  let listName = sel.value;
  if (listName === '__new__') {{
    listName = document.getElementById('newListInput').value.trim();
  }}
  if (!listName) {{ alert('Please select or create a list.'); return; }}

  const referral = document.getElementById('listReferralInput').value.trim() || undefined;
  const indices = Array.from(selected);
  if (indices.length === 0) return;

  closeListModal();
  openModal('Adding to List');
  const log = document.getElementById('modalLog');
  const fill = document.getElementById('progressFill');
  const status = document.getElementById('modalStatus');
  log.innerHTML = '<div class="log-entry"><span class="log-status scraping">adding</span><span class="log-name">Adding stores to list...</span></div>';
  fill.style.width = '50%';
  status.textContent = `Adding ${{indices.length}} stores to "${{listName}}"...`;
  document.getElementById('modalCloseBtn').style.display = 'none';

  try {{
    const resp = await fetch('/api/lists', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{action: 'add_to_list', store_indices: indices, list_name: listName, referral_source: referral}}),
    }});
    const data = await resp.json();
    fill.style.width = '100%';
    if (data.success) {{
      status.textContent = 'Done!';
      log.innerHTML = `<div class="log-entry"><span class="log-status success">done</span><span class="log-name">Added ${{data.added}} stores to "${{esc(listName)}}"</span></div>`;
    }} else {{
      status.textContent = 'Failed';
      log.innerHTML = `<div class="log-entry"><span class="log-status error">error</span><span class="log-name">${{esc(data.error || 'Unknown error')}}</span></div>`;
    }}
  }} catch(e) {{
    fill.style.width = '100%';
    status.textContent = 'Error: ' + e.message;
    log.innerHTML = `<div class="log-entry"><span class="log-status error">error</span><span class="log-name">${{esc(e.message)}}</span></div>`;
  }}
  document.getElementById('modalCloseBtn').style.display = 'block';
}}

// ── Modal helpers ────────────────────────────────────────────────────────
function openModal(title) {{
  document.getElementById('modalTitle').textContent = title;
  document.getElementById('modalOverlay').classList.add('visible');
}}

function closeModal() {{
  document.getElementById('modalOverlay').classList.remove('visible');
}}

// ── Context menu ─────────────────────────────────────────────────────────
let ctxIdx = null;
function onCardContext(event, idx) {{
  event.preventDefault();
  ctxIdx = idx;
  // If this card isn't selected, select it
  if (!selected.has(idx)) {{
    toggleSelect(idx, true);
    const card = document.querySelector(`.store-card[data-idx="${{idx}}"]`);
    if (card) card.classList.add('selected');
    const cb = card?.querySelector('input[type="checkbox"]');
    if (cb) cb.checked = true;
    updateSelectionToolbar();
  }}
  const menu = document.getElementById('ctxMenu');
  menu.style.left = Math.min(event.clientX, window.innerWidth - 200) + 'px';
  menu.style.top = Math.min(event.clientY, window.innerHeight - 120) + 'px';
  menu.classList.add('visible');
}}
document.addEventListener('click', () => document.getElementById('ctxMenu').classList.remove('visible'));
document.addEventListener('contextmenu', (e) => {{
  if (!e.target.closest('.store-card')) document.getElementById('ctxMenu').classList.remove('visible');
}});

function ctxAddToList() {{
  document.getElementById('ctxMenu').classList.remove('visible');
  openAddToListModal();
}}
function ctxEnrich() {{
  document.getElementById('ctxMenu').classList.remove('visible');
  enrichSelected();
}}
function ctxViewDetail() {{
  document.getElementById('ctxMenu').classList.remove('visible');
  if (ctxIdx !== null) openDetail(ctxIdx);
}}

// ── Row click handler ────────────────────────────────────────────────────
function onCardClick(event, idx) {{
  const tag = event.target.tagName.toLowerCase();
  if (tag === 'input' || tag === 'a' || tag === 'button') return;
  // Single click = toggle select
  const isNowSelected = !selected.has(idx);
  toggleSelect(idx, isNowSelected);
  const card = document.querySelector(`.store-card[data-idx="${{idx}}"]`);
  if (card) card.classList.toggle('selected', isNowSelected);
}}

function onCardDblClick(event, idx) {{
  const tag = event.target.tagName.toLowerCase();
  if (tag === 'input' || tag === 'a' || tag === 'button') return;
  openDetail(idx);
}}

function toggleStar(idx) {{
  if (starred.has(idx)) starred.delete(idx);
  else starred.add(idx);
  applyFilters();
}}

function toggleRemove(idx) {{
  if (removed.has(idx)) removed.delete(idx);
  else removed.add(idx);
  applyFilters();
}}

function starSelected() {{
  selected.forEach(idx => starred.add(idx));
  applyFilters();
}}

function removeSelected() {{
  selected.forEach(idx => removed.add(idx));
  clearSelection();
}}

function addTag(idx, tag) {{
  tag = tag.trim();
  if (!tag) return;
  if (!storeTags[idx]) storeTags[idx] = new Set();
  storeTags[idx].add(tag);
  saveTags();
}}

function removeTag(idx, tag) {{
  if (storeTags[idx]) storeTags[idx].delete(tag);
  saveTags();
}}

function tagSelected() {{
  const tag = prompt('Enter tag for selected stores:');
  if (!tag || !tag.trim()) return;
  selected.forEach(idx => addTag(idx, tag.trim()));
  applyFilters();
}}

// ── Toggle functions ─────────────────────────────────────────────────────
function toggleState(st) {{
  const body = document.getElementById('body-' + st);
  const header = body.previousElementSibling;
  body.classList.toggle('hidden');
  header.classList.toggle('collapsed');
}}

function toggleChain(id) {{
  const body = document.getElementById(id);
  const header = body.previousElementSibling;
  body.classList.toggle('hidden');
  header.classList.toggle('collapsed');
}}

function esc(s) {{
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}}

function toggleIndep(id) {{
  const body = document.getElementById(id);
  const arrow = document.getElementById('arrow-' + id);
  body.classList.toggle('hidden');
  arrow.classList.toggle('collapsed');
}}

function filterByTag(tag) {{
  activeTag = (activeTag === tag) ? '' : tag;
  applyFilters();
}}

function filterByType(el) {{
  const type = el.dataset.type;
  const sel = document.getElementById('typeFilter');
  if (sel.value === type && type !== '') {{
    sel.value = '';
  }} else {{
    sel.value = type;
  }}
  syncActiveCard();
  applyFilters();
}}

function syncActiveCard() {{
  const type = document.getElementById('typeFilter').value;
  document.querySelectorAll('.stat-card').forEach(c => {{
    c.classList.toggle('active', c.dataset.type === type);
  }});
}}

function debounce(fn, ms) {{
  let t;
  return (...a) => {{ clearTimeout(t); t = setTimeout(() => fn(...a), ms); }};
}}

// ── Store detail modal ──────────────────────────────────────────────────
let detailCurrentIdx = null;

async function openDetail(idx) {{
  detailCurrentIdx = idx;
  const d = DATA[idx];
  if (!d) return;

  const overlay = document.getElementById('detailOverlay');
  const left = document.getElementById('detailLeft');
  const right = document.getElementById('detailRight');
  const nameEl = document.getElementById('detailName');
  const badgesEl = document.getElementById('detailBadges');

  // Set header
  nameEl.textContent = d.name;
  const badgeMap = {{
    'dedicated_ebike': ['ebike', 'E-Bike Specialist'],
    'general_bike_shop': ['general', 'General Bike'],
    'electric_motorcycle': ['motorcycle', 'Electric Motorcycle'],
    'electric_scooter': ['scooter', 'Scooter / Moped'],
    'electric_last_mile': ['lastmile', 'Last Mile / Cargo'],
    'general_powersports': ['powersports', 'Powersports'],
  }};
  const [bc, bl] = badgeMap[d.store_type] || ['unknown', 'Other'];
  badgesEl.innerHTML = `<span class="badge ${{bc}}">${{bl}}</span>`;

  // Loading state
  left.innerHTML = '<div class="detail-loading"><div class="spinner"></div>Loading...</div>';
  right.innerHTML = '<div class="detail-loading"><div class="spinner"></div>Enriching store data...</div>';
  overlay.classList.add('visible');

  // Fetch detail (auto-enriches if needed)
  try {{
    const resp = await fetch(`/api/store/${{idx}}`);
    if (!resp.ok) throw new Error('Failed to load');
    const data = await resp.json();
    const store = data.store;
    const enrich = data.enrichment || {{}};

    // Store in global cache
    if (enrich.status) {{
      ENRICHMENT[idx] = enrich;
      ENRICHMENT_STATUS[idx] = {{
        status: enrich.status,
        email_count: (enrich.emails || []).length,
        has_socials: !!(enrich.instagram || enrich.facebook || enrich.twitter),
        brand_count: (enrich.brands_carried || []).length,
      }};
    }}

    renderDetailLeft(store, enrich);
    renderDetailRight(store, enrich);
  }} catch(e) {{
    right.innerHTML = `<div class="detail-loading" style="color:var(--orange)">Could not load store details. Make sure server.py is running.</div>`;
    // Still render basic info on left
    renderDetailLeftBasic(d);
  }}
}}

function renderDetailLeft(store, enrich) {{
  const left = document.getElementById('detailLeft');
  const images = enrich.images || [];
  const webHref = store.website && !store.website.startsWith('http') ? 'https://' + store.website : store.website;
  let html = '';

  // Images gallery
  if (images.length > 0) {{
    html += '<div class="detail-images">';
    images.forEach((img, i) => {{
      html += `<img src="${{esc(img)}}" alt="Store photo" loading="lazy" onerror="this.style.display='none'" onclick="window.open(this.src,'_blank')">`;
    }});
    html += '</div>';
  }} else {{
    html += '<div class="detail-images"><div class="img-placeholder">No images found on website</div></div>';
  }}

  // Website preview iframe
  if (webHref) {{
    html += `<div class="detail-preview">
      <div class="detail-preview-label">
        Website Preview
        <a href="${{esc(webHref)}}" target="_blank" rel="noopener">Open in new tab &#8599;</a>
      </div>
      <iframe src="${{esc(webHref)}}" sandbox="allow-scripts allow-same-origin" loading="lazy"></iframe>
    </div>`;
  }}

  left.innerHTML = html;
}}

function renderDetailLeftBasic(store) {{
  const left = document.getElementById('detailLeft');
  const webHref = store.website && !store.website.startsWith('http') ? 'https://' + store.website : store.website;
  let html = '<div class="detail-images"><div class="img-placeholder">Enrich this store to see images</div></div>';
  if (webHref) {{
    html += `<div class="detail-preview">
      <div class="detail-preview-label">
        Website Preview
        <a href="${{esc(webHref)}}" target="_blank" rel="noopener">Open in new tab &#8599;</a>
      </div>
      <iframe src="${{esc(webHref)}}" sandbox="allow-scripts allow-same-origin" loading="lazy"></iframe>
    </div>`;
  }}
  left.innerHTML = html;
}}

function renderDetailRight(store, enrich) {{
  const right = document.getElementById('detailRight');
  const webHref = store.website && !store.website.startsWith('http') ? 'https://' + store.website : store.website;
  let html = '';

  // Description
  if (enrich.description) {{
    html += `<div class="detail-section">
      <h4>About</h4>
      <p style="font-size:14px;color:var(--text2);line-height:1.6;">${{esc(enrich.description)}}</p>
    </div>`;
  }}

  // Basic info
  html += '<div class="detail-section"><h4>Store Info</h4>';
  html += `<div class="detail-row"><span class="label">Address</span><span class="value">${{esc(store.address)}}</span></div>`;
  html += `<div class="detail-row"><span class="label">City / State</span><span class="value">${{esc(store.city)}}, ${{store.state}}</span></div>`;
  if (store.phone) html += `<div class="detail-row"><span class="label">Phone</span><span class="value"><a href="tel:${{store.phone}}">${{esc(store.phone)}}</a></span></div>`;
  if (webHref) html += `<div class="detail-row"><span class="label">Website</span><span class="value"><a href="${{esc(webHref)}}" target="_blank" rel="noopener">${{esc(webHref.replace(/^https?:\\/\\//, '').split('?')[0])}}</a></span></div>`;
  html += `<div class="detail-row"><span class="label">Rating</span><span class="value">${{store.rating}} &#9733; (${{store.review_count.toLocaleString()}} reviews) &mdash; Score: ${{store.score}}</span></div>`;
  if (store.chain) html += `<div class="detail-row"><span class="label">Chain</span><span class="value">${{esc(store.chain)}}</span></div>`;
  html += '</div>';

  // Contact / Emails
  const allEmails = [];
  if (store.email) allEmails.push(store.email.split(';')[0].trim());
  (enrich.emails || []).forEach(e => {{ if (!allEmails.includes(e)) allEmails.push(e); }});
  if (allEmails.length > 0 || enrich.owner_contact) {{
    html += '<div class="detail-section"><h4>Contact</h4>';
    allEmails.forEach(email => {{
      html += `<div class="detail-row"><span class="label">Email</span><span class="value"><a href="mailto:${{email}}">${{esc(email)}}</a></span></div>`;
    }});
    if (enrich.owner_contact) html += `<div class="detail-row"><span class="label">Owner</span><span class="value">${{esc(enrich.owner_contact)}}</span></div>`;
    html += '</div>';
  }}

  // Social media
  const socials = [];
  if (enrich.instagram) socials.push(['Instagram', enrich.instagram, 'IG']);
  if (enrich.facebook) socials.push(['Facebook', enrich.facebook, 'FB']);
  if (enrich.twitter) socials.push(['Twitter/X', enrich.twitter, 'X']);
  if (enrich.youtube) socials.push(['YouTube', enrich.youtube, 'YT']);
  if (enrich.tiktok) socials.push(['TikTok', enrich.tiktok, 'TT']);
  if (enrich.linkedin) socials.push(['LinkedIn', enrich.linkedin, 'LI']);
  if (socials.length > 0) {{
    html += '<div class="detail-section"><h4>Social Media</h4><div class="social-links">';
    socials.forEach(([name, url, abbr]) => {{
      html += `<a class="social-link" href="${{esc(url)}}" target="_blank" rel="noopener">${{abbr}} ${{name}}</a>`;
    }});
    html += '</div></div>';
  }}

  // Brands
  if ((enrich.brands_carried || []).length > 0) {{
    html += '<div class="detail-section"><h4>Brands Carried</h4><div class="brand-tags">';
    enrich.brands_carried.forEach(b => {{
      html += `<span class="brand-tag">${{esc(b)}}</span>`;
    }});
    html += '</div></div>';
  }}

  // Hours
  if (enrich.store_hours) {{
    html += `<div class="detail-section"><h4>Store Hours</h4>
      <p style="font-size:13px;color:var(--text);white-space:pre-line;">${{esc(enrich.store_hours.replace(/; /g, '\\n'))}}</p>
    </div>`;
  }}

  // Enrichment status
  html += `<div class="detail-section"><h4>Enrichment</h4>
    <div class="detail-row"><span class="label">Status</span><span class="value"><span class="log-status ${{enrich.status || 'unknown'}}">${{enrich.status || 'not enriched'}}</span></span></div>
    <div class="detail-row"><span class="label">Pages scraped</span><span class="value">${{enrich.pages_scraped || 0}}</span></div>
  </div>`;

  // Tags section
  const currentTags = storeTags[detailCurrentIdx] || new Set();
  html += `<div class="detail-section"><h4>Tags</h4>`;
  if (currentTags.size > 0) {{
    html += '<div class="brand-tags" style="margin-bottom:10px;">';
    currentTags.forEach(t => {{
      html += `<span class="brand-tag" style="background:rgba(0,206,209,0.1);border-color:rgba(0,206,209,0.2);color:#00ced1;cursor:pointer;" onclick="removeTag(${{detailCurrentIdx}},'${{t}}');renderDetailRight(DATA[${{detailCurrentIdx}}],ENRICHMENT[${{detailCurrentIdx}}]||{{}});">${{esc(t)}} &times;</span>`;
    }});
    html += '</div>';
  }}
  html += `<div style="display:flex;gap:8px;">
    <input type="text" id="tagInput" placeholder="Add tag..." style="flex:1;padding:6px 12px;background:var(--surface2);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;outline:none;" onkeydown="if(event.key==='Enter'){{addTag(${{detailCurrentIdx}},this.value);this.value='';renderDetailRight(DATA[${{detailCurrentIdx}}],ENRICHMENT[${{detailCurrentIdx}}]||{{}});}}">
    <button class="btn-secondary" style="background:var(--surface);color:#00ced1;border:1px solid var(--border);padding:6px 14px;font-size:13px;border-radius:6px;cursor:pointer;" onclick="const inp=document.getElementById('tagInput');addTag(${{detailCurrentIdx}},inp.value);inp.value='';renderDetailRight(DATA[${{detailCurrentIdx}}],ENRICHMENT[${{detailCurrentIdx}}]||{{}});">Add</button>
  </div></div>`;

  // Actions
  const starLabel = starred.has(detailCurrentIdx) ? 'Unstar' : 'Star';
  const starIcon = starred.has(detailCurrentIdx) ? '&#9733;' : '&#9734;';
  const removeLabel = removed.has(detailCurrentIdx) ? 'Restore' : 'Remove';
  html += `<div class="detail-actions">
    ${{webHref ? `<a href="${{esc(webHref)}}" target="_blank" rel="noopener" class="btn-primary" style="background:var(--accent);color:white;">Visit Website &#8599;</a>` : ''}}
    <button class="btn-secondary" style="background:var(--surface);color:var(--text);border:1px solid var(--border);" onclick="toggleSelect(${{detailCurrentIdx}},true);closeDetail();">Select for Export</button>
    <button class="btn-secondary" style="background:var(--surface);color:var(--yellow);border:1px solid var(--border);" onclick="toggleStar(${{detailCurrentIdx}});renderDetailRight(DATA[${{detailCurrentIdx}}],ENRICHMENT[${{detailCurrentIdx}}]||{{}});">${{starIcon}} ${{starLabel}}</button>
    <button class="btn-secondary" style="background:var(--surface);color:var(--orange);border:1px solid var(--border);" onclick="toggleRemove(${{detailCurrentIdx}});closeDetail();">${{removeLabel}}</button>
  </div>`;

  right.innerHTML = html;
}}

function closeDetail() {{
  document.getElementById('detailOverlay').classList.remove('visible');
  // Clean up iframe to stop loading
  const left = document.getElementById('detailLeft');
  left.querySelectorAll('iframe').forEach(f => f.src = 'about:blank');
  detailCurrentIdx = null;
  applyFilters();  // refresh badges
}}

// Close detail on Escape
document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') {{
    if (document.getElementById('detailOverlay').classList.contains('visible')) closeDetail();
    else if (document.getElementById('modalOverlay').classList.contains('visible')) closeModal();
  }}
}});

init();
</script>
</body>
</html>'''

with open('/Users/eddie/ebike-directory/index.html', 'w') as f:
    f.write(html)

print(f"Written: index.html ({len(html)} bytes)")
