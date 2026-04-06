#!/usr/bin/env python3
"""
alert.py
========
Runs every 3 hours. Only sends email if a rug is removed
or sold out at alrug.com. Silent otherwise.
"""

import os, csv, time, json, datetime, requests, smtplib
import config
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CSV_FILE   = os.path.join(BASE_DIR, 'rug_inventory.csv')
TOKEN_FILE = os.path.join(BASE_DIR, 'etsy_token.json')
ALRUG      = 'https://www.alrug.com'

SMTP_HOST  = 'smtp.gmail.com'
SMTP_PORT  = 587
SMTP_USER  = config.SMTP_USER
SMTP_PASS  = config.SMTP_PASS
EMAIL_FROM = config.EMAIL_FROM
EMAIL_TO   = config.EMAIL_TO
SHOP_NAME  = config.SHOP_NAME

def check_alrug(handle, csv_sku):
    if not handle:
        return 'no_handle'
    try:
        sku_from_handle = handle.split('-no-')[-1].upper() if '-no-' in handle else ''
        search_terms = list(dict.fromkeys(t for t in [csv_sku, sku_from_handle] if t))
        for term in search_terms:
            r = requests.get(
                f'{ALRUG}/search/suggest.json',
                params={'q': term, 'resources[type]': 'product', 'resources[limit]': 5},
                timeout=12, headers={'User-Agent': 'Mozilla/5.0'}
            )
            if r.ok:
                products = r.json().get('resources', {}).get('results', {}).get('products', [])
                match = next((p for p in products if term.lower() in p.get('title', '').lower()), None)
                if not match:
                    match = next((p for p in products if term.lower() in p.get('handle', '').lower()), None)
                if match:
                    return 'ok' if match.get('available') else 'sold_out'
            time.sleep(0.4)
        return 'not_found'
    except Exception:
        return 'error'

def send_alert(issues):
    today = datetime.datetime.now().strftime('%b %d, %Y %H:%M')
    rows = ''
    for row, status in issues:
        eid   = row.get('etsy_listing_id', '')
        sku   = row.get('sku', '')
        title = (row.get('etsy_title') or '')[:70]
        label = '🔴 Removed from alrug' if status == 'not_found' else '🟠 Sold out on alrug'
        rows += f'''<div style="border:1.5px solid #f5aaaa;border-radius:9px;padding:13px 15px;margin-bottom:10px;background:#fef8f8">
  <div style="font-size:13px;font-weight:700;margin-bottom:4px">{title}</div>
  <div style="font-size:11px;color:#8a7560;margin-bottom:8px">SKU: {sku} · Etsy ID: {eid} · {label}</div>
  <a href="https://www.etsy.com/your/shops/{SHOP_NAME}/tools/listings/{eid}/edit" style="display:inline-block;padding:5px 12px;background:#b02020;color:#fff;border-radius:6px;font-size:11px;font-weight:700;text-decoration:none">Remove from Etsy</a>
</div>'''

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:Helvetica Neue,Arial,sans-serif;background:#f5f0e8;margin:0;padding:20px;color:#1c1410">
<div style="max-width:600px;margin:0 auto">
  <div style="background:#b02020;border-radius:12px;padding:24px 28px;margin-bottom:20px;color:#fff">
    <h1 style="font-size:20px;margin:0 0 4px;font-weight:700">⚠️ Urgent: Rugs Need Attention</h1>
    <p style="margin:0;font-size:13px;opacity:.8">{today} · {len(issues)} listing(s) affected</p>
  </div>
  <div style="background:#fff;border-radius:12px;padding:20px;border:1.5px solid #e8dfd0">
    <p style="font-size:13px;margin-bottom:16px">The following rugs are no longer available on alrug.com and should be removed from your Etsy shop:</p>
    {rows}
  </div>
  <div style="text-align:center;padding:16px;font-size:11px;color:#8a7560">
    Auto Alert · <a href="{TOOL_URL}" style="color:#2d5a3d">Open Tool</a>
  </div>
</div>
</body></html>"""

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'⚠️ Action Required: {len(issues)} Etsy listing(s) need removal'
    msg['From']    = EMAIL_FROM
    msg['To']      = ', '.join(EMAIL_TO)
    msg.attach(MIMEText(html, 'html'))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.ehlo(); s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print(f'Alert sent — {len(issues)} issues')
    except Exception as e:
        print(f'Email failed: {e}')

def main():
    if not os.path.exists(CSV_FILE):
        print('No CSV found, skipping')
        return

    rows = []
    with open(CSV_FILE, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    print(f'Checking {len(rows)} listings against alrug.com...')
    issues = []
    for row in rows:
        status = check_alrug(row.get('alrug_handle', ''), row.get('sku', ''))
        if status in ('not_found', 'sold_out'):
            issues.append((row, status))
            print(f"  {status.upper()}: SKU {row.get('sku')} — {row.get('etsy_title','')[:50]}")
        else:
            print(f"  ok: SKU {row.get('sku')}")

    if issues:
        print(f'Sending alert for {len(issues)} issues...')
        send_alert(issues)
    else:
        print('All good — no alert sent')

if __name__ == '__main__':
    main()
