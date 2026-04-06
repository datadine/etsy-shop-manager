#!/usr/bin/env python3
"""
report.py
=========
Daily Etsy shop audit — runs at 9am EST via cron.
Fetches all listings, scores SEO, flags performance issues,
sends HTML email to configured EMAIL_TO recipients.

SKU data comes from rug_inventory.csv (built by build_inventory.py).
If the CSV is missing, run build_inventory.py first to rebuild it from Etsy.

Setup:
  crontab -e
  0 9 * * * /usr/bin/env python3 /path/to/your/app/report.py

Requires:
  - etsy_token.json (saved by server.py after OAuth)
  - rug_inventory.csv (built by build_inventory.py)
  - pip install requests
"""

import os, json, csv, re, requests, smtplib, datetime, sys, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import config

ALRUG      = 'https://www.alrug.com'
ALRUG_DELAY = 0.4   # seconds between requests

# ── alrug.com availability checker ───────────────────────────────────────────
def check_alrug_product(handle, csv_sku=""):
    """
    Check a product on alrug.com using the suggest API which correctly
    returns available: True/False unlike the products.json endpoint.

    Matching strategy (in order):
      1. Search by csv_sku — match any result where SKU appears in title
         (handles cases where handle has a different number than the title SKU)
      2. Search by SKU extracted from handle — same title match
      3. Fall back to exact handle match in results

    Falls back to products.json for price.
    Returns: status ('ok'|'sold_out'|'not_found'|'error'), price, available
    """
    if not handle:
        return {'status': 'no_handle', 'price': None, 'available': False}
    try:
        sku_from_handle = handle.split('-no-')[-1].upper() if '-no-' in handle else ''
        search_terms = list(dict.fromkeys(
            t for t in [csv_sku, sku_from_handle] if t
        ))

        available = None
        real_handle = handle  # may be updated if we find the real product

        for search_term in search_terms:
            r = requests.get(
                f'{ALRUG}/search/suggest.json',
                params={'q': search_term, 'resources[type]': 'product', 'resources[limit]': 5},
                timeout=12,
                headers={'User-Agent': 'Mozilla/5.0'},
            )
            if not r.ok:
                continue
            products = r.json().get('resources', {}).get('results', {}).get('products', [])
            if not products:
                continue

            # Match: SKU appears anywhere in the product title (case-insensitive)
            # This handles alrug.com mismatches where handle != title SKU
            match = next(
                (p for p in products
                 if search_term.lower() in p.get('title', '').lower()),
                None
            )
            # Fallback: SKU in handle
            if not match:
                match = next(
                    (p for p in products
                     if search_term.lower() in p.get('handle', '').lower()),
                    None
                )
            if match:
                available = match.get('available')
                real_handle = match.get('handle', handle)
                break

        # Get price from products.json using the real handle we found
        price = None
        pr = requests.get(f'{ALRUG}/products/{real_handle}.json',
                          timeout=12, headers={'User-Agent': 'Mozilla/5.0'})
        if pr.status_code == 404 and real_handle == handle:
            # Only treat as not_found if both the stored and real handle 404
            return {'status': 'not_found', 'price': None, 'available': False}
        if pr.ok:
            variants = pr.json().get('product', {}).get('variants', [])
            if variants:
                try:
                    price = float(variants[0].get('price', 0))
                except (ValueError, TypeError):
                    price = None

        if available is None:
            return {'status': 'not_found', 'price': None, 'available': False}

        return {'status': 'ok' if available else 'sold_out', 'price': price, 'available': available}

    except Exception:
        return {'status': 'error', 'price': None, 'available': False}

def run_alrug_check(inventory):
    """
    Check every row in inventory against alrug.com.
    Returns a dict with keys: removed, sold_out, price_up, price_down, ok, error
    Also prints results to terminal.
    """
    PRICE_THR = 1.0
    results   = {'removed': [], 'sold_out': [], 'price_up': [],
                 'price_down': [], 'ok': [], 'error': []}
    rows      = list(inventory.values())
    total     = len(rows)

    print(f'\n  Checking {total} listings against alrug.com…')
    for i, row in enumerate(rows, 1):
        handle    = row.get('alrug_handle', '').strip()
        sku       = row.get('sku', '?')
        eid       = row.get('etsy_listing_id', '')
        try:
            etsy_price = float(row.get('etsy_price_usd', '') or 0)
        except ValueError:
            etsy_price = 0.0

        result      = check_alrug_product(handle, csv_sku=sku)
        alrug_price = result['price']
        status      = result['status']
        time.sleep(ALRUG_DELAY)

        # price change logic
        price_flag   = None
        price_change = ''
        if alrug_price and etsy_price:
            diff = alrug_price - etsy_price
            if diff > PRICE_THR:
                price_flag   = 'price_up'
                price_change = f'alrug ${alrug_price:.0f} vs Etsy ${etsy_price:.0f} (+${diff:.0f})'
            elif diff < -PRICE_THR:
                price_flag   = 'price_down'
                price_change = f'alrug ${alrug_price:.0f} vs Etsy ${etsy_price:.0f} (-${abs(diff):.0f})'

        row['_alrug_status'] = status
        row['_alrug_price']  = alrug_price
        row['_price_change'] = price_change
        row['_price_flag']   = price_flag

        if status == 'not_found':
            results['removed'].append(row)
            print(f'  [{i:>3}/{total}] 🔴 REMOVED    SKU {sku:12} Etsy {eid}')
        elif status == 'sold_out':
            results['sold_out'].append(row)
            print(f'  [{i:>3}/{total}] 🟠 SOLD OUT   SKU {sku:12} Etsy {eid}')
        elif status == 'error':
            results['error'].append(row)
            print(f'  [{i:>3}/{total}] ⚠️  ERROR      SKU {sku:12} Etsy {eid}')
        elif price_flag == 'price_up':
            results['price_up'].append(row)
            print(f'  [{i:>3}/{total}] 💰 PRICE UP   SKU {sku:12} Etsy {eid}  {price_change}')
        elif price_flag == 'price_down':
            results['price_down'].append(row)
            print(f'  [{i:>3}/{total}] 💸 PRICE DOWN SKU {sku:12} Etsy {eid}  {price_change}')
        else:
            results['ok'].append(row)
            p = f'${alrug_price:.0f}' if alrug_price else '?'
            print(f'  [{i:>3}/{total}] ✅ OK         SKU {sku:12} Etsy {eid}  alrug {p}')

    total_issues = (len(results['removed']) + len(results['sold_out']) +
                    len(results['price_up']) + len(results['price_down']))
    print(f'\n  Alrug check: 🔴 {len(results["removed"])} removed  '
          f'🟠 {len(results["sold_out"])} sold out  '
          f'💰 {len(results["price_up"])} price up  '
          f'💸 {len(results["price_down"])} price down  '
          f'✅ {len(results["ok"])} ok')
    return results

def build_alrug_html(alrug_results):
    """Build the alrug sync section to inject into the HTML report."""
    removed    = alrug_results.get('removed', [])
    sold_out   = alrug_results.get('sold_out', [])
    price_up   = alrug_results.get('price_up', [])
    price_down = alrug_results.get('price_down', [])
    ok_count   = len(alrug_results.get('ok', []))
    total_issues = len(removed) + len(sold_out) + len(price_up) + len(price_down)

    if total_issues == 0:
        return f'''<div class="section">
  <h2>🛒 Alrug Sync — All Clear</h2>
  <div style="background:#f2f8f4;border:1.5px solid #b2d8c0;border-radius:9px;padding:13px 15px;font-size:13px;color:#2d5a3d">
    ✅ All {ok_count} rugs are available on alrug.com with no price changes.
  </div>
</div>'''

    def row_html(row, border, badge_bg, badge_label, note=''):
        eid   = row.get('etsy_listing_id', '')
        sku   = row.get('sku', '')
        title = (row.get('etsy_title') or '')[:65]
        state = row.get('etsy_state', '')
        state_color = '#b2d8c0' if state == 'active' else '#f0d080'
        state_text  = '#1a4a2a' if state == 'active' else '#7a5500'
        state_label = 'ACTIVE' if state == 'active' else 'DRAFT'
        note_html   = f'<div style="font-size:11px;color:#8a7560;margin-top:3px">{note}</div>' if note else ''
        alrug_url   = f'https://www.alrug.com/products/{row.get("alrug_handle","")}' if row.get('alrug_handle') else '#'
        return f'''<div style="border:1.5px solid {border};border-radius:9px;padding:11px 14px;margin-bottom:8px;background:#fffdf9">
  <div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:4px">
    <span style="font-size:12px;font-weight:700">{title}</span>
    <span style="background:#e8f0ea;color:#2d5a3d;padding:1px 7px;border-radius:10px;font-size:10px;font-weight:700">SKU: {sku}</span>
    <span style="background:{badge_bg};color:#fff;padding:1px 8px;border-radius:10px;font-size:10px;font-weight:700">{badge_label}</span>
  </div>
  <div style="font-size:11px;color:#8a7560">
    Etsy ID: {eid} ·
    <span style="background:{state_color};color:{state_text};padding:1px 6px;border-radius:8px;font-size:10px;font-weight:700">{state_label}</span>
  </div>
  {note_html}
  <div style="margin-top:7px">
    <a style="display:inline-block;padding:4px 11px;background:#f5f0e8;color:#4a3a28;border-radius:6px;font-size:11px;font-weight:700;text-decoration:none;border:1.5px solid #d4c8b4" href="https://www.etsy.com/your/shops/{SHOP_NAME}/tools/listings/{eid}/edit" target="_blank">Edit on Etsy ↗</a>
    <a style="display:inline-block;padding:4px 11px;background:#f5f0e8;color:#4a3a28;border-radius:6px;font-size:11px;font-weight:700;text-decoration:none;border:1.5px solid #d4c8b4;margin-left:6px" href="{alrug_url}" target="_blank">View on Alrug ↗</a>
  </div>
</div>'''

    html = f'<div class="section"><h2>🛒 Alrug Sync — {total_issues} item(s) need attention</h2>'

    if removed:
        html += f'<div style="font-size:13px;font-weight:700;color:#b02020;margin-bottom:8px">🔴 Removed from alrug.com — consider deleting these Etsy listings ({len(removed)})</div>'
        for r in removed:
            html += row_html(r, '#f5aaaa', '#b02020', 'REMOVED', 'This product no longer exists on alrug.com')

    if sold_out:
        html += f'<div style="font-size:13px;font-weight:700;color:#c8860a;margin:12px 0 8px">🟠 Sold out on alrug.com — consider deactivating on Etsy ({len(sold_out)})</div>'
        for r in sold_out:
            html += row_html(r, '#f0d080', '#c8860a', 'SOLD OUT', 'All variants are unavailable on alrug.com')

    if price_up:
        html += f'<div style="font-size:13px;font-weight:700;color:#c8860a;margin:12px 0 8px">💰 Alrug raised the price — you may want to update Etsy ({len(price_up)})</div>'
        for r in price_up:
            html += row_html(r, '#f5d080', '#8a6000', 'PRICE UP', r.get('_price_change', ''))

    if price_down:
        html += f'<div style="font-size:13px;font-weight:700;color:#2d5a3d;margin:12px 0 8px">💸 Alrug lowered the price — you could match it to stay competitive ({len(price_down)})</div>'
        for r in price_down:
            html += row_html(r, '#b2d8c0', '#2d5a3d', 'PRICE DOWN', r.get('_price_change', ''))

    if ok_count:
        html += f'<div style="font-size:12px;color:#8a7560;margin-top:12px">✅ {ok_count} other listings are available on alrug.com with no price changes.</div>'

    html += '</div>'
    return html

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, 'etsy_token.json')
CSV_FILE   = os.path.join(BASE_DIR, 'rug_inventory.csv')
ETSY_KEY   = config.ETSY_KEY
SHOP_ID    = config.SHOP_ID
SHOP_NAME  = config.SHOP_NAME
ETSY_BASE  = 'https://openapi.etsy.com/v3/application'

SMTP_HOST  = config.SMTP_HOST
SMTP_PORT  = config.SMTP_PORT
SMTP_USER  = config.SMTP_USER
SMTP_PASS  = config.SMTP_PASS
EMAIL_FROM = config.EMAIL_FROM
EMAIL_TO   = config.EMAIL_TO

# ── Banned words (Etsy policy) ────────────────────────────────────────────────
BANNED = ['persian', 'iran', 'iranian', 'isfahan', 'tabriz', 'qom', 'tehran', 'persia']

# ── SEO term lists ────────────────────────────────────────────────────────────
STYLE_TERMS   = ['kazak','baluchi','gabbeh','kilim','bokhara','oushak','ziegler',
                 'kashan','kohistani','jaldar','mashwani','moroccan','turkmen',
                 'tribal','afghan','balisht','barjasta','abstract']
COLOR_TERMS   = ['red','blue','green','grey','gray','beige','ivory','navy','teal',
                 'black','white','brown','gold','pink','orange','purple','cream',
                 'tan','rust','terracotta','multicolor']
ROOM_TERMS    = ['living room','bedroom','entryway','hallway','dining room',
                 'kitchen','office','bathroom']
QUALITY_TERMS = ['vegetable dyed','natural dyes','chemical free','hand knotted',
                 'hand woven','wool','organic']
ORIGIN_TERMS  = ['afghan','turkish','moroccan','pakistan','turkmen']

# ── Load CSV inventory ────────────────────────────────────────────────────────
def load_inventory():
    """
    Load rug_inventory.csv into a dict keyed by etsy_listing_id (string).
    Returns empty dict if file doesn't exist — report still runs, just without SKUs.
    """
    inv = {}
    if not os.path.exists(CSV_FILE):
        print(f'  WARNING: {CSV_FILE} not found.')
        print(f'  Run build_inventory.py first to create it.')
        print(f'  Report will continue without SKU data.')
        return inv
    with open(CSV_FILE, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            inv[row['etsy_listing_id']] = row
    print(f'  Loaded {len(inv)} SKU records from CSV inventory.')
    return inv

# ── Token management ──────────────────────────────────────────────────────────
def load_token():
    if not os.path.exists(TOKEN_FILE):
        sys.exit(f'ERROR: {TOKEN_FILE} not found. Connect via the importer first.')
    with open(TOKEN_FILE) as f:
        return json.load(f)

def refresh_access_token(token_data):
    r = requests.post(
        'https://openapi.etsy.com/v3/public/oauth/token',
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data={
            'grant_type':    'refresh_token',
            'client_id':     token_data.get('client_id', ETSY_KEY),
            'refresh_token': token_data['refresh_token'],
        },
        timeout=15,
    )
    if not r.ok:
        sys.exit(f'ERROR refreshing token: {r.text}')
    new_data = r.json()
    token_data['access_token']  = new_data['access_token']
    token_data['refresh_token'] = new_data.get('refresh_token', token_data['refresh_token'])
    token_data['saved_at']      = datetime.datetime.now().isoformat()
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token_data, f, indent=2)
    print('  Token refreshed.')
    return new_data['access_token']

def get_headers(access_token):
    return {
        'Authorization': f'Bearer {access_token}',
        'x-api-key':     f'{ETSY_KEY}:{config.ETSY_SECRET}',
    }

# ── Etsy API calls ────────────────────────────────────────────────────────────
def get_shop_stats(headers):
    r = requests.get(f'{ETSY_BASE}/shops/{SHOP_ID}', headers=headers, timeout=15)
    return r.json() if r.ok else {}

def get_all_listings(headers):
    listings = []
    for state in ['active', 'draft']:
        offset = 0
        while True:
            r = requests.get(
                f'{ETSY_BASE}/shops/{SHOP_ID}/listings',
                headers=headers,
                params={'limit': 100, 'offset': offset, 'state': state},
                timeout=20,
            )
            if not r.ok:
                print(f'  {state}: HTTP {r.status_code} — {r.text[:100]}')
                break
            data  = r.json()
            batch = data.get('results', [])
            listings.extend(batch)
            if len(batch) < 100:
                break
            offset += 100
    active_n = sum(1 for l in listings if l.get('state') == 'active')
    draft_n  = sum(1 for l in listings if l.get('state') == 'draft')
    print(f'  Found {active_n} active, {draft_n} drafts')
    return listings

def get_listing_stats(headers, listing_id):
    r = requests.get(
        f'{ETSY_BASE}/shops/{SHOP_ID}/listings/{listing_id}',
        headers=headers,
        params={'includes': ['Stats']},
        timeout=10,
    )
    if r.ok:
        d = r.json()
        return {'views': d.get('views', 0), 'favorites': d.get('num_favorers', 0)}
    return {'views': 0, 'favorites': 0}

def get_recent_orders(headers):
    r = requests.get(
        f'{ETSY_BASE}/shops/{SHOP_ID}/receipts',
        headers=headers,
        params={'limit': 25, 'was_paid': 'true'},
        timeout=15,
    )
    return r.json().get('results', []) if r.ok else []

# ── SEO Scorer ────────────────────────────────────────────────────────────────
def score_listing(listing):
    title  = (listing.get('title') or '').lower()
    tags   = [t.lower() for t in (listing.get('tags') or [])]
    desc   = (listing.get('description') or '').lower()
    issues = []
    score  = 100

    tlen = len(listing.get('title', ''))
    if tlen < 80:
        issues.append(('🔴', 'Title too short', f'Only {tlen} chars — aim for 120-140'))
        score -= 20
    elif tlen < 100:
        issues.append(('🟡', 'Title could be longer', f'{tlen} chars — aim for 120-140'))
        score -= 10

    for word in BANNED:
        if word in title or word in desc:
            issues.append(('🔴', f'BANNED WORD: "{word}"', 'Remove immediately — account risk'))
            score -= 30

    tag_count = len(tags)
    if tag_count < 13:
        issues.append(('🔴', 'Missing tags', f'Only {tag_count}/13 tags used'))
        score -= 15

    if not any(s in title for s in STYLE_TERMS):
        issues.append(('🟡', 'No style term in title', 'Add: Kazak, Baluchi, Gabbeh, Kilim etc.'))
        score -= 10

    if not any(c in title for c in COLOR_TERMS):
        issues.append(('🟡', 'No color in title', 'Add the primary color'))
        score -= 8

    if not re.search(r'\d+x\d+|\d+[\'"]\s*\d+', title):
        issues.append(('🟡', 'No size in title', "Add size e.g. 4x6 or 4'2\" x 6'3\""))
        score -= 8

    if not (any(r in title for r in ROOM_TERMS) or any(r in ' '.join(tags) for r in ROOM_TERMS)):
        issues.append(('🟡', 'No room use case', 'Add: living room rug, bedroom rug etc.'))
        score -= 7

    if not any(o in title for o in ORIGIN_TERMS):
        issues.append(('🟡', 'No origin term', 'Add: Afghan, Turkmen, Turkish etc.'))
        score -= 7

    if not any(q in ' '.join(tags) for q in QUALITY_TERMS):
        issues.append(('🟡', 'No quality terms in tags', 'Add: hand knotted, wool, vegetable dyed'))
        score -= 5

    if len(listing.get('description', '')) < 200:
        desc_len = len(listing.get('description', ''))
        issues.append(('🟡', 'Short description', f'Only {desc_len} chars — add care instructions, story'))
        score -= 5

    return max(0, score), issues

def get_score_color(score):
    if score >= 80: return '#2D5A3D'
    if score >= 60: return '#C8860A'
    return '#B02020'

def get_score_label(score):
    if score >= 80: return 'Good'
    if score >= 60: return 'Needs Work'
    return 'Poor'

# ── Performance analysis ──────────────────────────────────────────────────────
def analyze_performance(listing, stats, days_listed):
    issues = []
    views, favorites = stats.get('views', 0), stats.get('favorites', 0)
    if days_listed >= 14 and views == 0:
        issues.append(('🔴', 'No views in 14+ days', 'Consider deleting and relisting fresh'))
    elif days_listed >= 7 and views < 5:
        issues.append(('🟡', f'Only {views} views in {days_listed} days', 'Title may not match buyer searches'))
    if views >= 20 and favorites == 0:
        issues.append(('🟡', f'{views} views but 0 favorites', 'Photo quality may be the issue'))
    if views >= 50 and favorites >= 5:
        issues.append(('🟢', f'Strong interest: {views} views, {favorites} favs', 'Consider Etsy Ads'))
    if favorites >= 3 and views > 0 and (favorites/views)*100 > 10:
        issues.append(('🟢', f'High favorite rate {(favorites/views)*100:.0f}%', 'Check price competitiveness'))
    return issues

# ── SKU badge helper ──────────────────────────────────────────────────────────
def sku_badge(inventory, listing_id):
    row = inventory.get(str(listing_id), {})
    sku = row.get('sku', '')
    if not sku:
        return ''
    return (f'<span style="background:#e8f0ea;color:#2d5a3d;padding:1px 8px;'
            f'border-radius:10px;font-size:10px;font-weight:700;margin-left:6px">'
            f'SKU: {sku}</span>')

# ── HTML report builder ───────────────────────────────────────────────────────
def build_html_report(shop, listings_data, orders, today, inventory, alrug_results=None):
    total   = len(listings_data)
    crit_n  = sum(1 for _, d in listings_data if d['seo_score'] < 60)
    avg_seo = int(sum(d['seo_score'] for _, d in listings_data) / max(total, 1))
    tot_v   = sum(d['stats'].get('views', 0)     for _, d in listings_data)
    tot_f   = sum(d['stats'].get('favorites', 0) for _, d in listings_data)
    n_active = sum(1 for l, _ in listings_data if l.get('state') == 'active')
    n_draft  = sum(1 for l, _ in listings_data if l.get('state') == 'draft')

    sorted_data = sorted(listings_data, key=lambda x: x[1]['seo_score'])

    missing_sku = [str(l['listing_id']) for l, _ in listings_data
                   if not inventory.get(str(l['listing_id']), {}).get('sku')]
    missing_banner = ''
    if missing_sku:
        missing_banner = f'''<div style="background:#fff8ec;border:1.5px solid #f0d080;border-radius:10px;
padding:12px 16px;margin-bottom:16px;font-size:12px;color:#7a5500;line-height:1.7">
  ⚠️ <strong>{len(missing_sku)} listing(s) have no SKU in the CSV.</strong>
  Run <code>python3 build_inventory.py</code> to update the inventory file.
</div>'''

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body{{font-family:'Helvetica Neue',Arial,sans-serif;background:#f5f0e8;margin:0;padding:20px;color:#1c1410}}
  .wrap{{max-width:700px;margin:0 auto}}
  .hdr{{background:#1a3d28;border-radius:12px;padding:24px 28px;margin-bottom:20px;color:#fff}}
  .hdr h1{{font-size:22px;margin:0 0 4px;font-weight:700}}
  .hdr p{{margin:0;font-size:13px;opacity:.7}}
  .stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px}}
  .stat{{background:#fff;border-radius:10px;padding:14px;text-align:center;border:1.5px solid #e8dfd0}}
  .stat-n{{font-size:26px;font-weight:700;line-height:1}}
  .stat-l{{font-size:11px;color:#8a7560;margin-top:4px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}}
  .section{{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;border:1.5px solid #e8dfd0}}
  .section h2{{font-size:15px;font-weight:700;margin:0 0 14px;padding-bottom:10px;border-bottom:1.5px solid #f0ebe1}}
  .listing{{border:1.5px solid #e8dfd0;border-radius:9px;padding:13px 15px;margin-bottom:10px;background:#fffdf9}}
  .listing.critical{{border-color:#f5aaaa;background:#fef8f8}}
  .listing.good{{border-color:#b2d8c0;background:#f2f8f4}}
  .l-title{{font-size:13px;font-weight:700;margin-bottom:4px;line-height:1.4}}
  .l-meta{{font-size:11px;color:#8a7560;margin-bottom:8px}}
  .score-badge{{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;color:#fff}}
  .issue{{font-size:12px;padding:4px 0;border-bottom:1px solid #f5f0e8;line-height:1.5}}
  .issue:last-child{{border:none}}
  .issue-icon{{font-size:13px;margin-right:4px}}
  .fix-btn{{display:inline-block;margin-top:8px;padding:6px 14px;background:#f5a623;color:#1c1410;border-radius:6px;font-size:11px;font-weight:700;text-decoration:none}}
  .view-btn{{display:inline-block;margin-top:8px;margin-left:6px;padding:6px 14px;background:#f5f0e8;color:#4a3a28;border-radius:6px;font-size:11px;font-weight:700;text-decoration:none;border:1.5px solid #d4c8b4}}
  .green{{color:#2d5a3d}}.red{{color:#b02020}}.amber{{color:#c8860a}}
  .top-badge{{background:#2d5a3d}}.warn-badge{{background:#c8860a}}.crit-badge{{background:#b02020}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <h1>📊 Etsy Rugs Daily Report</h1>
    <p>{today.strftime('%A, %B %d, %Y')} · {n_active} active · {n_draft} drafts</p>
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-n {'red' if crit_n > 0 else 'green'}">{crit_n}</div><div class="stat-l">Critical Issues</div></div>
    <div class="stat"><div class="stat-n" style="color:{get_score_color(avg_seo)}">{avg_seo}</div><div class="stat-l">Avg SEO Score</div></div>
    <div class="stat"><div class="stat-n">{tot_v}</div><div class="stat-l">Total Views</div></div>
    <div class="stat"><div class="stat-n">{tot_f}</div><div class="stat-l">Total Favorites</div></div>
  </div>
{missing_banner}"""

    # Alrug sync section — appears at the top, right after the stats
    if alrug_results is not None:
        html += build_alrug_html(alrug_results)

    def state_badge(state):
        if state == 'active':
            return '<span style="background:#b2d8c0;color:#1a4a2a;padding:1px 7px;border-radius:10px;font-weight:700;font-size:10px">ACTIVE</span>'
        return '<span style="background:#f0d080;color:#7a5500;padding:1px 7px;border-radius:10px;font-weight:700;font-size:10px">DRAFT</span>'

    # Critical
    critical = [(l, d) for l, d in sorted_data if d['seo_score'] < 60]
    if critical:
        html += f'<div class="section"><h2>🔴 Critical — {len(critical)} listings</h2>'
        for listing, data in critical[:10]:
            lid   = listing['listing_id']
            title = listing.get('title', '')[:80]
            score = data['seo_score']
            html += f'''<div class="listing critical">
  <div class="l-title">{title}{'…' if len(listing.get('title',''))>80 else ''}{sku_badge(inventory, lid)}</div>
  <div class="l-meta">ID: {lid} · {state_badge(listing.get('state',''))} · Views: {data['stats'].get('views',0)} · Favs: {data['stats'].get('favorites',0)} · {data['days_listed']}d listed</div>
  <span class="score-badge crit-badge">SEO {score}/100 — {get_score_label(score)}</span>
  <div style="margin-top:10px">'''
            for icon, t, detail in (data['seo_issues'] + data['perf_issues'])[:5]:
                html += f'<div class="issue"><span class="issue-icon">{icon}</span><strong>{t}</strong> — {detail}</div>'
            html += f'''</div>
  <a class="fix-btn" href="http://localhost:8080/api/report/fix/{lid}?tok=REPLACE_TOKEN">⚡ Auto-Fix</a>
  <a class="view-btn" href="https://www.etsy.com/your/shops/{SHOP_NAME}/tools/listings/{lid}/edit" target="_blank">Edit ↗</a>
</div>'''
        html += '</div>'

    # Needs work
    weak = [(l, d) for l, d in sorted_data if 60 <= d['seo_score'] < 80]
    if weak:
        html += f'<div class="section"><h2>🟡 Needs Work — {len(weak)} listings</h2>'
        for listing, data in weak[:8]:
            lid   = listing['listing_id']
            title = listing.get('title', '')[:80]
            score = data['seo_score']
            html += f'''<div class="listing">
  <div class="l-title">{title}{'…' if len(listing.get('title',''))>80 else ''}{sku_badge(inventory, lid)}</div>
  <div class="l-meta">ID: {lid} · {state_badge(listing.get('state',''))} · Views: {data['stats'].get('views',0)} · Favs: {data['stats'].get('favorites',0)} · {data['days_listed']}d listed</div>
  <span class="score-badge warn-badge">SEO {score}/100</span>
  <div style="margin-top:8px">'''
            for icon, t, detail in (data['seo_issues'] + data['perf_issues'])[:3]:
                html += f'<div class="issue"><span class="issue-icon">{icon}</span><strong>{t}</strong> — {detail}</div>'
            html += f'''</div>
  <a class="fix-btn" href="http://localhost:8080/api/report/fix/{lid}?tok=REPLACE_TOKEN">⚡ Auto-Fix</a>
  <a class="view-btn" href="https://www.etsy.com/your/shops/{SHOP_NAME}/tools/listings/{lid}/edit" target="_blank">Edit ↗</a>
</div>'''
        html += '</div>'

    # Top performers
    active_good = [(l, d) for l, d in sorted_data if d['seo_score'] >= 80 and l.get('state') == 'active']
    if active_good:
        html += f'<div class="section"><h2>🟢 Top Performers — {len(active_good)} active listings</h2>'
        for listing, data in sorted(active_good, key=lambda x: x[1]['stats'].get('views', 0), reverse=True)[:5]:
            lid   = listing['listing_id']
            title = listing.get('title', '')[:80]
            score = data['seo_score']
            html += f'''<div class="listing good">
  <div class="l-title">{title}{sku_badge(inventory, lid)}</div>
  <div class="l-meta">ID: {lid} · {state_badge('active')} · Views: {data['stats'].get('views',0)} · Favs: {data['stats'].get('favorites',0)}</div>
  <span class="score-badge top-badge">SEO {score}/100 — {get_score_label(score)}</span>
</div>'''
        html += '</div>'

    # Drafts
    drafts = [(l, d) for l, d in sorted_data if l.get('state') == 'draft']
    if drafts:
        html += f'<div class="section"><h2>📝 Drafts — {len(drafts)} listings ready to review</h2>'
        for listing, data in sorted(drafts, key=lambda x: x[1]['seo_score'], reverse=True):
            lid   = listing['listing_id']
            title = listing.get('title', '')[:80]
            score = data['seo_score']
            sc    = get_score_color(score)
            html += f'''<div class="listing" style="border-color:#f0d080;background:#fffdf4">
  <div class="l-title">{title}{sku_badge(inventory, lid)}</div>
  <div class="l-meta">ID: {lid} · {state_badge('draft')} · {data['days_listed']} days ago</div>
  <span class="score-badge" style="background:{sc}">SEO {score}/100 — {get_score_label(score)}</span>
  <div style="margin-top:8px">'''
            for icon, t, detail in data['seo_issues'][:3]:
                html += f'<div class="issue"><span class="issue-icon">{icon}</span><strong>{t}</strong> — {detail}</div>'
            html += f'''</div>
  <a class="view-btn" href="https://www.etsy.com/your/shops/{SHOP_NAME}/tools/listings/{lid}/edit" target="_blank">Edit Draft ↗</a>
  <a class="view-btn" href="https://www.etsy.com/your/shops/{SHOP_NAME}/tools/listings/{lid}" target="_blank">Preview ↗</a>
</div>'''
        html += '</div>'

    csv_note = f'{len(inventory)} SKUs in inventory' if inventory else 'No CSV — run build_inventory.py'
    html += f'''<div style="text-align:center;padding:16px;font-size:11px;color:#8a7560">
  Generated {today.strftime('%Y-%m-%d %H:%M')} EST ·
  {csv_note}<br>
  <a href="http://localhost:8080" style="color:#2d5a3d">Open Importer Tool</a> ·
  <a href="https://www.etsy.com/your/shops/{SHOP_NAME}/tools/listings" style="color:#2d5a3d">View All Listings</a>
</div>
</div></body></html>'''

    return html

# ── Email sender ──────────────────────────────────────────────────────────────
def send_email(html, today):
    subject = f'📊 Etsy Daily Report — {today.strftime("%b %d")} '
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = EMAIL_FROM
    msg['To']      = ', '.join(EMAIL_TO)
    msg.attach(MIMEText(html, 'html'))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.ehlo(); s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print(f'✅  Email sent to {", ".join(EMAIL_TO)}')
    except Exception as e:
        print(f'❌  Email failed: {e}')

def save_report(html, today):
    report_dir = os.path.join(BASE_DIR, 'reports')
    os.makedirs(report_dir, exist_ok=True)
    dated  = os.path.join(report_dir, f'report_{today.strftime("%Y-%m-%d")}.html')
    latest = os.path.join(report_dir, 'latest.html')
    for path in (dated, latest):
        with open(path, 'w') as f:
            f.write(html)
    print(f'✅  Report saved: {dated}')

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    today = datetime.datetime.now()
    print(f'\n{"="*55}')
    print(f'  Etsy Daily Report — {today.strftime("%Y-%m-%d %H:%M")}')
    print(f'{"="*55}')

    print('\n[1/4] Loading SKU inventory…')
    inventory = load_inventory()

    print('\n[2/4] Fetching Etsy data…')
    token_data   = load_token()
    access_token = refresh_access_token(token_data)
    headers      = get_headers(access_token)

    shop     = get_shop_stats(headers)
    listings = get_all_listings(headers)
    orders   = get_recent_orders(headers)
    listings = [l for l in listings if l.get('taxonomy_id') == 929]
    print(f'  {len(listings)} rug listings (taxonomy 929)')

    print(f'\n[3/5] Analyzing {len(listings)} listings…')
    listings_data = []
    for i, listing in enumerate(listings, 1):
        lid        = listing['listing_id']
        created_ts = listing.get('creation_tsz', 0) or listing.get('original_creation_tsz', 0)
        created_dt = datetime.datetime.fromtimestamp(created_ts) if created_ts else today
        days_listed = (today - created_dt).days

        stats                   = get_listing_stats(headers, lid)
        seo_score, seo_issues   = score_listing(listing)
        perf_issues             = analyze_performance(listing, stats, days_listed)

        listings_data.append((listing, {
            'seo_score':   seo_score,
            'seo_issues':  seo_issues,
            'perf_issues': perf_issues,
            'stats':       stats,
            'days_listed': days_listed,
        }))
        if i % 10 == 0:
            print(f'  Analyzed {i}/{len(listings)}…')

    print('\n[4/5] Checking alrug.com availability & prices…')
    alrug_results = run_alrug_check(inventory) if inventory else None

    print('\n[5/5] Building report…')
    html = build_html_report(shop, listings_data, orders, today, inventory, alrug_results)
    save_report(html, today)
    send_email(html, today)
    print('\n✅  Done!')

if __name__ == '__main__':
    main()
