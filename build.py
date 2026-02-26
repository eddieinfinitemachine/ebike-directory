#!/usr/bin/env python3
"""Build the e-bike directory website with state grouping and chain detection."""
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

rows = [r for r in rows if r['state'] in US_STATES_SET]
for r in rows:
    r['rating'] = float(r['rating'])
    r['review_count'] = int(r['review_count'])
    r['score'] = round(r['rating'] * r['review_count'], 1)
    r['chain'] = get_chain(r['name'])

data_json = json.dumps(rows, separators=(',',':'))
print(f"Total stores: {len(rows)}")
print(f"In chains: {sum(1 for r in rows if r['chain'])}")

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
  --bg: #0f1117;
  --surface: #1a1d27;
  --surface2: #232733;
  --border: #2e3345;
  --text: #e4e6ef;
  --text2: #9398ad;
  --accent: #6c5ce7;
  --accent2: #a29bfe;
  --green: #00b894;
  --yellow: #fdcb6e;
  --orange: #e17055;
  --radius: 12px;
}}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.6; min-height: 100vh;
}}
.container {{ max-width: 1400px; margin: 0 auto; padding: 0 24px; }}

/* Header */
header {{ border-bottom: 1px solid var(--border); padding: 24px 0; }}
header .container {{ display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; }}
.logo {{ display: flex; align-items: center; gap: 12px; }}
.logo-icon {{ width: 40px; height: 40px; background: linear-gradient(135deg, var(--accent), var(--accent2)); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; }}
.logo h1 {{ font-size: 22px; font-weight: 700; }}
.logo h1 span {{ color: var(--accent2); }}
.header-meta {{ color: var(--text2); font-size: 14px; }}

/* Stats */
.stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 16px; padding: 32px 0; }}
.stat-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; cursor: pointer; transition: border-color 0.2s, background 0.2s; }}
.stat-card:hover {{ background: var(--surface2); }}
.stat-card.active {{ border-color: var(--accent); background: var(--surface2); }}
.stat-card .label {{ font-size: 12px; color: var(--text2); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }}
.stat-card .value {{ font-size: 28px; font-weight: 700; }}
.stat-card .value.accent {{ color: var(--accent2); }}
.stat-card .value.green {{ color: var(--green); }}
.stat-card .value.yellow {{ color: var(--yellow); }}

/* Controls */
.controls {{ display: flex; flex-wrap: wrap; gap: 12px; padding-bottom: 24px; align-items: stretch; }}
.search-box {{ flex: 1 1 300px; position: relative; }}
.search-box svg {{ position: absolute; left: 14px; top: 50%; transform: translateY(-50%); color: var(--text2); width: 18px; height: 18px; }}
.search-box input {{
  width: 100%; padding: 12px 12px 12px 42px; background: var(--surface);
  border: 1px solid var(--border); border-radius: var(--radius); color: var(--text);
  font-size: 15px; outline: none; transition: border-color 0.2s;
}}
.search-box input:focus {{ border-color: var(--accent); }}
.search-box input::placeholder {{ color: var(--text2); }}
select {{
  padding: 12px 16px; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); color: var(--text); font-size: 14px; outline: none;
  cursor: pointer; min-width: 160px; -webkit-appearance: none; appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%239398ad' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 12px center; padding-right: 36px;
}}
select:focus {{ border-color: var(--accent); }}
.results-count {{ display: flex; align-items: center; padding: 0 4px; color: var(--text2); font-size: 14px; white-space: nowrap; }}

/* State section */
.state-section {{ margin-bottom: 32px; }}
.state-header {{
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius) var(--radius) 0 0; cursor: pointer; user-select: none;
  transition: background 0.2s;
}}
.state-header:hover {{ background: var(--surface2); }}
.state-header.collapsed {{ border-radius: var(--radius); }}
.state-header h2 {{ font-size: 18px; font-weight: 700; display: flex; align-items: center; gap: 10px; }}
.state-header h2 .code {{ color: var(--accent2); font-size: 14px; font-weight: 600; background: rgba(108,92,231,0.15); padding: 2px 8px; border-radius: 6px; }}
.state-header .meta {{ display: flex; gap: 16px; align-items: center; color: var(--text2); font-size: 13px; }}
.state-header .arrow {{ font-size: 12px; color: var(--text2); transition: transform 0.2s; }}
.state-header.collapsed .arrow {{ transform: rotate(-90deg); }}
.state-body {{ border: 1px solid var(--border); border-top: none; border-radius: 0 0 var(--radius) var(--radius); overflow: hidden; }}
.state-body.hidden {{ display: none; }}

/* Chain group */
.chain-group {{ border-bottom: 1px solid var(--border); }}
.chain-group:last-child {{ border-bottom: none; }}
.chain-header {{
  display: flex; align-items: center; gap: 10px; padding: 12px 20px;
  background: rgba(108,92,231,0.05); cursor: pointer; user-select: none;
  font-size: 14px; font-weight: 600; color: var(--accent2);
  transition: background 0.15s;
}}
.chain-header:hover {{ background: rgba(108,92,231,0.1); }}
.chain-header .chain-arrow {{ font-size: 10px; color: var(--text2); transition: transform 0.2s; }}
.chain-header.collapsed .chain-arrow {{ transform: rotate(-90deg); }}
.chain-header .chain-count {{ font-weight: 400; color: var(--text2); font-size: 13px; }}
.chain-body.hidden {{ display: none; }}

/* Store card */
.store-card {{
  display: grid;
  grid-template-columns: 1fr auto auto auto;
  gap: 16px;
  padding: 14px 20px;
  align-items: center;
  border-bottom: 1px solid rgba(46,51,69,0.5);
  transition: background 0.15s;
}}
.store-card:hover {{ background: rgba(108,92,231,0.04); }}
.store-card:last-child {{ border-bottom: none; }}
.store-name {{ font-weight: 600; font-size: 14px; }}
.store-name a {{ color: var(--text); text-decoration: none; }}
.store-name a:hover {{ color: var(--accent2); }}
.store-address {{ font-size: 13px; color: var(--text2); margin-top: 2px; }}
.store-meta {{ display: flex; align-items: center; gap: 6px; white-space: nowrap; }}
.badge {{
  display: inline-block; padding: 3px 10px; border-radius: 20px;
  font-size: 11px; font-weight: 600; white-space: nowrap;
}}
.badge.ebike {{ background: rgba(108,92,231,0.15); color: var(--accent2); }}
.badge.general {{ background: rgba(0,184,148,0.15); color: var(--green); }}
.badge.motorcycle {{ background: rgba(225,112,85,0.15); color: var(--orange); }}
.badge.scooter {{ background: rgba(253,203,110,0.2); color: var(--yellow); }}
.badge.lastmile {{ background: rgba(0,206,209,0.15); color: #00ced1; }}
.badge.powersports {{ background: rgba(255,107,107,0.15); color: #ff6b6b; }}
.badge.unknown {{ background: rgba(147,152,173,0.15); color: var(--text2); }}
.rating {{ display: flex; align-items: center; gap: 4px; white-space: nowrap; font-size: 14px; }}
.rating .stars {{ color: var(--yellow); font-size: 12px; }}
.rating .num {{ font-weight: 700; }}
.rating .reviews {{ color: var(--text2); font-size: 12px; }}
.contact {{ display: flex; flex-direction: column; gap: 2px; align-items: flex-end; min-width: 140px; }}
.contact a {{ color: var(--accent2); text-decoration: none; font-size: 13px; }}
.contact a:hover {{ color: var(--text); }}
.contact .web {{ max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; }}
.contact .email {{ max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; }}

/* Independents section label */
.indep-label {{
  padding: 10px 20px; font-size: 13px; color: var(--text2);
  font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
  background: rgba(0,0,0,0.15); border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 8px; transition: background 0.15s;
}}
.indep-label:hover {{ background: rgba(0,0,0,0.25); }}
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
  padding: 4px 10px; background: var(--surface); border: 1px solid var(--border);
  border-radius: 6px; color: var(--text2); text-decoration: none; font-size: 12px;
  font-weight: 600; transition: all 0.15s;
}}
.state-nav a:hover {{ border-color: var(--accent); color: var(--accent2); }}

@media (max-width: 900px) {{
  .controls {{ flex-direction: column; }}
  .store-card {{ grid-template-columns: 1fr; gap: 8px; }}
  .contact {{ align-items: flex-start; }}
  .state-header .meta {{ display: none; }}
}}
</style>
</head>
<body>

<header>
  <div class="container">
    <div class="logo">
      <div class="logo-icon">&#9889;</div>
      <h1>US Electric Vehicle <span>Retailer Directory</span></h1>
    </div>
    <div class="header-meta">E-Bikes, Electric Motorcycles, Scooters &amp; Last-Mile Vehicles</div>
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
  <div id="content"></div>
  <div class="empty" id="empty" style="display:none;">
    <div style="font-size:48px;margin-bottom:16px;">&#128270;</div>
    <h3>No stores found</h3>
    <p>Try adjusting your search or filters</p>
  </div>
</main>

<script>
const DATA = {data_json};

const US_STATES = {json.dumps(US_STATES)};

function init() {{
  renderStats();
  applyFilters();
  document.getElementById('search').addEventListener('input', debounce(applyFilters, 200));
  document.getElementById('typeFilter').addEventListener('change', () => {{ syncActiveCard(); applyFilters(); }});
  document.getElementById('sortSelect').addEventListener('change', applyFilters);
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
  document.getElementById('stats').innerHTML = `
    <div class="stat-card" data-type="" onclick="filterByType(this)"><div class="label">Total Stores</div><div class="value accent">${{total.toLocaleString()}}</div></div>
    <div class="stat-card" data-type="dedicated_ebike" onclick="filterByType(this)"><div class="label">E-Bike Specialists</div><div class="value green">${{dedicated}}</div></div>
    <div class="stat-card" data-type="electric_motorcycle" onclick="filterByType(this)"><div class="label">Electric Motorcycle</div><div class="value" style="color:var(--orange)">${{motorcycles}}</div></div>
    <div class="stat-card" data-type="general_powersports" onclick="filterByType(this)"><div class="label">Powersports</div><div class="value" style="color:#ff6b6b">${{powersports}}</div></div>
    <div class="stat-card" data-type="general_bike_shop" onclick="filterByType(this)"><div class="label">General Bike</div><div class="value green">${{general}}</div></div>
    <div class="stat-card" data-type="" onclick="filterByType(this)"><div class="label">States</div><div class="value">${{states}}</div></div>
  `;
}}

function applyFilters() {{
  const q = document.getElementById('search').value.toLowerCase().trim();
  const type = document.getElementById('typeFilter').value;
  const sort = document.getElementById('sortSelect').value;

  let filtered = DATA.filter(d => {{
    if (type && d.store_type !== type) return false;
    if (q) {{
      const hay = `${{d.name}} ${{d.city}} ${{d.state}} ${{d.address}} ${{d.chain||''}} ${{d.email||''}} ${{US_STATES[d.state]||''}}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }}
    return true;
  }});

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

  return `<div class="store-card">
    <div>
      <div class="store-name">${{d.website ? `<a href="${{esc(webHref)}}" target="_blank" rel="noopener">${{esc(d.name)}}</a>` : esc(d.name)}}</div>
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

function filterByType(el) {{
  const type = el.dataset.type;
  const sel = document.getElementById('typeFilter');
  // Toggle: if already active, clear filter
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

init();
</script>
</body>
</html>'''

with open('/Users/eddie/ebike-directory/index.html', 'w') as f:
    f.write(html)

print(f"Written: {len(html)} bytes")
