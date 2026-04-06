#!/usr/bin/env python3
"""
build_inventory.py
==================
Builds (or rebuilds) rug_inventory.csv from scratch by hitting the live
Etsy API directly.  Run this any time — it is safe to re-run repeatedly.

  - Fetches every active AND draft listing from your Etsy shop
  - For each listing, fetches the inventory endpoint to get the real SKU
    (the alrug stock number, e.g. AT22818, stored in Etsy's SKU field)
  - Writes rug_inventory.csv with: etsy_listing_id, sku, etsy_title,
    etsy_state, etsy_price_usd, etsy_views, etsy_favorites, created_date

If the CSV already exists, existing rows are PRESERVED and only updated /
new rows are added — so you never lose history.

If the CSV is deleted entirely, re-running this script rebuilds it from
whatever is currently live on Etsy.

Usage:
    python3 build_inventory.py

Requires:
    - etsy_token.json (written by server.py after OAuth)
    - pip install requests
"""

import os, json, csv, sys, time, datetime, requests
import config

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, 'etsy_token.json')
CSV_FILE   = os.path.join(BASE_DIR, 'rug_inventory.csv')

ETSY_KEY  = config.ETSY_KEY
ETSY_SEC  = config.ETSY_SECRET
SHOP_ID   = config.SHOP_ID
ETSY_BASE = 'https://openapi.etsy.com/v3/application'

ALRUG = 'https://www.alrug.com'

# The CSV schema — column order is fixed, never change it
CSV_COLUMNS = [
    'etsy_listing_id',   # Etsy's own listing number  e.g. 4483020936
    'sku',               # alrug stock number stored in Etsy's SKU field  e.g. AT22818
    'alrug_handle',      # alrug.com URL handle  e.g. hand-knotted-tribal-bokhara-...
    'alrug_price_usd',   # Current price on alrug.com
    'etsy_title',        # Full listing title on Etsy
    'etsy_state',        # active / draft
    'etsy_price_usd',    # Price on Etsy in USD
    'etsy_views',        # Lifetime views (0 for drafts)
    'etsy_favorites',    # Lifetime favorites (0 for drafts)
    'created_date',      # Date first created on Etsy  YYYY-MM-DD
    'last_updated',      # Date this row was last refreshed  YYYY-MM-DD
]

# ── Token helpers ──────────────────────────────────────────────────────────────
def load_token():
    if not os.path.exists(TOKEN_FILE):
        sys.exit(f'ERROR: {TOKEN_FILE} not found. Run the importer tool first to connect.')
    with open(TOKEN_FILE) as f:
        return json.load(f)

def refresh_token(token_data):
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
    new = r.json()
    token_data['access_token']  = new['access_token']
    token_data['refresh_token'] = new.get('refresh_token', token_data['refresh_token'])
    token_data['saved_at']      = datetime.datetime.now().isoformat()
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token_data, f, indent=2)
    print('  Token refreshed.')
    return new['access_token']

def auth_headers(access_token):
    return {
        'Authorization': f'Bearer {access_token}',
        'x-api-key':     f'{ETSY_KEY}:{ETSY_SEC}',
    }

# ── Etsy API calls ─────────────────────────────────────────────────────────────
def fetch_all_listings(headers):
    """Fetch every active + draft listing from the shop."""
    all_listings = []
    for state in ('active', 'draft'):
        offset = 0
        while True:
            r = requests.get(
                f'{ETSY_BASE}/shops/{SHOP_ID}/listings',
                headers=headers,
                params={'limit': 100, 'offset': offset, 'state': state},
                timeout=20,
            )
            if not r.ok:
                print(f'  WARNING: {state} listings HTTP {r.status_code} — {r.text[:100]}')
                break
            batch = r.json().get('results', [])
            all_listings.extend(batch)
            print(f'  {state}: fetched {len(batch)} (offset {offset})')
            if len(batch) < 100:
                break
            offset += 100
            time.sleep(0.2)
    return all_listings

def fetch_sku(headers, listing_id):
    """
    Fetch the SKU stored in Etsy's inventory for a listing.
    Returns the SKU string, or '' if none is set.
    Etsy stores it in: inventory.products[0].sku
    """
    r = requests.get(
        f'{ETSY_BASE}/listings/{listing_id}/inventory',
        headers=headers,
        timeout=10,
    )
    if not r.ok:
        return ''
    data = r.json()
    products = data.get('products') or []
    if products:
        return (products[0].get('sku') or '').strip()
    return ''

def fetch_stats(headers, listing_id):
    """Fetch views and favorites for one listing."""
    r = requests.get(
        f'{ETSY_BASE}/shops/{SHOP_ID}/listings/{listing_id}',
        headers=headers,
        params={'includes': ['Stats']},
        timeout=10,
    )
    if r.ok:
        d = r.json()
        return d.get('views', 0), d.get('num_favorers', 0)
    return 0, 0

def lookup_alrug_handle(sku):
    """
    Search alrug.com for a product by SKU (e.g. AT22818).
    Returns (handle, price) or ('', None) if not found.
    Tries two methods:
      1. Shopify suggest API — fast
      2. Collections search fallback
    """
    if not sku:
        return '', None
    try:
        # Method 1: suggest API
        r = requests.get(
            f'{ALRUG}/search/suggest.json',
            params={'q': sku, 'resources[type]': 'product', 'resources[limit]': 5},
            timeout=12,
            headers={'User-Agent': 'Mozilla/5.0'},
        )
        if r.ok:
            products = r.json().get('resources', {}).get('results', {}).get('products', [])
            sku_upper = sku.upper()
            for p in products:
                if sku_upper in p.get('handle', '').upper() or sku_upper in p.get('title', '').upper():
                    handle = p['handle']
                    price  = _get_price_from_handle(handle)
                    return handle, price

        # Method 2: collections/all search
        r2 = requests.get(
            f'{ALRUG}/collections/all/products.json',
            params={'q': sku, 'limit': 5},
            timeout=12,
            headers={'User-Agent': 'Mozilla/5.0'},
        )
        if r2.ok:
            sku_upper = sku.upper()
            for p in r2.json().get('products', []):
                if sku_upper in p.get('handle', '').upper() or sku_upper in p.get('title', '').upper():
                    handle = p['handle']
                    price  = _price_from_variants(p.get('variants', []))
                    return handle, price

    except Exception:
        pass
    return '', None

def _get_price_from_handle(handle):
    """Fetch price for a known handle."""
    try:
        r = requests.get(f'{ALRUG}/products/{handle}.json',
                         timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if r.ok:
            return _price_from_variants(r.json().get('product', {}).get('variants', []))
    except Exception:
        pass
    return None

def _price_from_variants(variants):
    try:
        return float(variants[0]['price']) if variants else None
    except (KeyError, ValueError, TypeError):
        return None

# ── CSV helpers ────────────────────────────────────────────────────────────────
def load_existing_csv():
    """Load existing CSV into a dict keyed by etsy_listing_id string."""
    existing = {}
    if not os.path.exists(CSV_FILE):
        return existing
    with open(CSV_FILE, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            existing[row['etsy_listing_id']] = row
    print(f'  Loaded {len(existing)} existing rows from CSV.')
    return existing

def save_csv(rows_dict):
    """Write the inventory dict back to CSV sorted by listing id."""
    rows = sorted(rows_dict.values(), key=lambda r: int(r.get('etsy_listing_id', 0)))
    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    print(f'\n✅  Saved {len(rows)} rows → {CSV_FILE}')

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    today = datetime.date.today().isoformat()

    print('\n' + '='*55)
    print('  build_inventory.py — Etsy → rug_inventory.csv')
    print('='*55)

    # 1. Auth
    print('\n[1/4] Refreshing Etsy token…')
    token_data   = load_token()
    access_token = refresh_token(token_data)
    hdrs         = auth_headers(access_token)

    # 2. Load what we already have (so we never lose history)
    print('\n[2/4] Loading existing CSV (if any)…')
    inventory = load_existing_csv()

    # 3. Fetch all listings from Etsy
    print('\n[3/4] Fetching all listings from Etsy…')
    listings = fetch_all_listings(hdrs)
    # Keep only rug taxonomy (929) — skip non-rug listings
    listings = [l for l in listings if l.get('taxonomy_id') == 929]
    print(f'  Total rug listings (taxonomy 929): {len(listings)}')

    # 4. For each listing, fetch SKU + stats + alrug handle, then upsert into inventory
    print(f'\n[4/4] Fetching SKU + alrug handle + stats for each listing…')
    new_count     = 0
    updated_count = 0

    for i, listing in enumerate(listings, 1):
        lid_int = listing['listing_id']
        lid     = str(lid_int)
        state   = listing.get('state', '')
        title   = listing.get('title', '')

        # Price
        price_obj = listing.get('price') or {}
        if isinstance(price_obj, dict):
            amount  = price_obj.get('amount', 0)
            divisor = price_obj.get('divisor', 100)
            price   = f'{amount / divisor:.2f}' if divisor else str(amount)
        else:
            price = str(price_obj)

        # Created date
        created_ts = listing.get('creation_tsz') or listing.get('original_creation_tsz') or 0
        created_date = (
            datetime.datetime.fromtimestamp(created_ts).strftime('%Y-%m-%d')
            if created_ts else today
        )

        # SKU from Etsy inventory API
        sku = fetch_sku(hdrs, lid_int)
        time.sleep(0.15)

        # Views + favorites
        views, favorites = fetch_stats(hdrs, lid_int)
        time.sleep(0.15)

        # alrug handle — reuse existing if already found, otherwise look it up
        existing     = inventory.get(lid, {})
        alrug_handle = existing.get('alrug_handle', '').strip()
        alrug_price  = existing.get('alrug_price_usd', '')

        if not alrug_handle and sku:
            alrug_handle, found_price = lookup_alrug_handle(sku)
            if found_price:
                alrug_price = str(found_price)
            if alrug_handle:
                print(f'         → found alrug handle: {alrug_handle}')
            else:
                print(f'         → alrug handle not found for SKU {sku}')
            time.sleep(0.4)   # be polite to alrug.com

        is_new = lid not in inventory
        inventory[lid] = {
            'etsy_listing_id': lid,
            'sku':             sku,
            'alrug_handle':    alrug_handle,
            'alrug_price_usd': alrug_price,
            'etsy_title':      title,
            'etsy_state':      state,
            'etsy_price_usd':  price,
            'etsy_views':      str(views),
            'etsy_favorites':  str(favorites),
            'created_date':    existing.get('created_date') or created_date,
            'last_updated':    today,
        }

        status = 'NEW' if is_new else 'UPD'
        if is_new:
            new_count += 1
        else:
            updated_count += 1

        handle_short = (alrug_handle[:35] + '…') if len(alrug_handle) > 35 else (alrug_handle or '(no handle)')
        print(f'  [{i:>3}/{len(listings)}] {status}  Etsy {lid}  SKU: {sku or "(none)":12}  {state:6}  {handle_short}')

    # Remove listings that no longer exist on Etsy (deleted drafts etc.)
    live_ids   = {str(l['listing_id']) for l in listings}
    removed    = [eid for eid in list(inventory) if eid not in live_ids]
    for eid in removed:
        row = inventory.pop(eid)
        print(f'  REMOVED  Etsy {eid}  (no longer on Etsy) — {row.get("etsy_title","")[:50]}')

    # Save
    save_csv(inventory)

    print(f'\n  Summary: {new_count} new  |  {updated_count} updated  |  {len(removed)} removed')
    print(f'  CSV is now the source of truth.')
    print(f'  Re-run this script any time to rebuild from Etsy.\n')

if __name__ == '__main__':
    main()
