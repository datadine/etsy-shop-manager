import json
"""
server.py
=========
Local Flask server for the Etsy Importer tool.
Proxies Etsy API, HPD, and Alrug calls — bypassing browser CORS restrictions.

Usage:
    pip install flask requests
    python3 server.py

Then open: http://localhost:8080
"""

import time, json, requests
import config
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE_DIR)
CORS(app)

# ── Credentials (from your working etsy_sync.py) ──────────────────────────────
ETSY_KEY     = config.ETSY_KEY
ETSY_SECRET  = config.ETSY_SECRET
ETSY_HEADERS = {'x-api-key': f'{ETSY_KEY}:{ETSY_SECRET}'}
ETSY_BASE    = 'https://openapi.etsy.com/v3/application'
_shop_id_cache = {}
_shipping_profile_cache = {}
_readiness_cache = {}
_production_partner_cache = {}

def write_headers():
    h = {'x-api-key': f'{ETSY_KEY}:{ETSY_SECRET}', 'Content-Type': 'application/json'}
    auth = request.headers.get('Authorization')
    if auth:
        h['Authorization'] = auth
    return h

# ── Serve the HTML tool (embedded — no file path issues) ──────────────────────

ALRUG_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Alrug → Etsy</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--g:#2D5A3D;--g2:#4A8C61;--g3:#1A3D28;--sand:#F5F0E8;--sandm:#E8DFD0;--sandd:#D4C8B4;--ink:#1C1410;--inkm:#4A3A28;--inkl:#8A7560;--white:#FFFDF9;--clay:#B85C38;--red:#B02020;--amb:#C8860A}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'IBM Plex Sans',sans-serif;background:var(--sand);color:var(--ink);min-height:100vh}
.hdr{background:var(--g3);padding:0 32px;display:flex;align-items:center;justify-content:space-between;height:58px;position:sticky;top:0;z-index:100;border-bottom:2px solid var(--g2)}
.logo{font-family:'Playfair Display',serif;font-size:17px;color:var(--sand)}
.nav a{color:rgba(255,255,255,.45);font-size:12px;font-weight:600;text-decoration:none;padding:5px 11px;border-radius:6px;margin-left:4px;transition:.15s}
.nav a:hover{background:rgba(255,255,255,.08);color:#fff}
.nav a.on{background:rgba(74,140,97,.25);color:#8fd4a8}
.hdr-r{display:flex;align-items:center;gap:10px}
.chip{background:rgba(45,90,61,.3);border:1px solid var(--g2);color:#8fd4a8;border-radius:20px;padding:3px 11px;font-size:11px;font-weight:600}
.pill{display:flex;align-items:center;gap:5px;font-size:11px;color:#888}
.dot{width:7px;height:7px;border-radius:50%;background:#444}
.dot.on{background:#4caf50;box-shadow:0 0 6px #4caf50;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.layout{display:grid;grid-template-columns:230px 1fr;min-height:calc(100vh - 58px)}
.sb{background:var(--g3);padding:22px 14px;position:sticky;top:58px;height:calc(100vh - 58px);overflow-y:auto;border-right:1px solid rgba(255,255,255,.05)}
.sbl{font-size:9px;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;color:rgba(255,255,255,.2);margin-bottom:9px}
.sbs{margin-bottom:22px}
.snav{display:flex;flex-direction:column;gap:2px}
.si{display:flex;align-items:center;gap:8px;padding:7px 9px;border-radius:7px;color:rgba(255,255,255,.22);font-size:12px;transition:.15s;cursor:pointer}
.si:hover{color:rgba(255,255,255,.45)}
.si.on{background:rgba(74,140,97,.18);color:#8fd4a8}
.sn{width:19px;height:19px;border-radius:50%;background:rgba(255,255,255,.05);display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;flex-shrink:0;font-family:'IBM Plex Mono',monospace}
.si.on .sn{background:var(--g2);color:#fff}
.cbox{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:9px}
.crow{display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid rgba(255,255,255,.04);font-size:10px}
.crow:last-child{border:none}
.ck{color:rgba(255,255,255,.28)}
.cv{color:var(--sand);font-weight:600;font-family:'IBM Plex Mono',monospace;font-size:9px}
.cv.g{color:#4caf50}
.cv.o{color:#8fd4a8}
.main{padding:30px 38px;max-width:740px}
.panel{display:none}
.panel.on{display:block;animation:fi .2s ease}
@keyframes fi{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
.ph{margin-bottom:20px}
.ph h2{font-family:'Playfair Display',serif;font-size:26px;margin-bottom:5px}
.ph p{font-size:13px;color:var(--inkm);line-height:1.6}
.field{margin-bottom:13px}
.field label{display:block;font-size:10px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:var(--inkl);margin-bottom:5px}
.field input,.field select,.field textarea{width:100%;padding:10px 12px;border:1.5px solid var(--sandd);border-radius:8px;font-family:'IBM Plex Sans',sans-serif;font-size:14px;background:var(--white);color:var(--ink);transition:.18s}
.field input:focus,.field select:focus,.field textarea:focus{outline:none;border-color:var(--g2);box-shadow:0 0 0 3px rgba(45,90,61,.1)}
.field input::placeholder,.field textarea::placeholder{color:#c0b4a4}
.field .hint{font-size:11px;color:var(--inkl);margin-top:4px;line-height:1.5}
.r3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:11px}
.r2{display:grid;grid-template-columns:1fr 1fr;gap:11px}
.card{background:var(--white);border:1.5px solid var(--sandm);border-radius:12px;padding:19px;margin-bottom:15px;box-shadow:0 2px 18px rgba(28,20,16,.08)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:11px 22px;border-radius:8px;font-family:'IBM Plex Sans',sans-serif;font-size:14px;font-weight:600;border:none;cursor:pointer;transition:.18s;width:100%}
.btn-p{background:var(--g);color:#fff}
.btn-p:hover:not(:disabled){background:var(--g3);transform:translateY(-1px);box-shadow:0 5px 16px rgba(45,90,61,.28)}
.btn-p:disabled{background:var(--sandd);color:var(--inkl);cursor:not-allowed}
.btn-o{background:transparent;color:var(--g);border:1.5px solid var(--g);width:auto;padding:7px 15px;font-size:13px}
.btn-o:hover{background:rgba(45,90,61,.06)}
.btn-sm{width:auto;padding:7px 14px;font-size:12px}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:5px}
.chip2{padding:3px 9px;border-radius:20px;font-size:11px;font-weight:600;cursor:pointer;background:var(--sandm);color:var(--inkm);border:1.5px solid var(--sandd);transition:.13s;font-family:'IBM Plex Sans',sans-serif}
.chip2:hover{border-color:var(--g2);color:var(--g3)}
.chip2.on{background:var(--g);border-color:var(--g);color:#fff}
.ibox{background:#f2f8f4;border:1.5px solid #b2d8c0;border-radius:9px;padding:13px 15px;margin-bottom:15px}
.ibox-t{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.9px;color:var(--g);margin-bottom:7px}
.irow{display:flex;gap:8px;font-size:12px;color:var(--inkm);padding:2px 0;line-height:1.5}
.wbox{background:#fff8ec;border:1.5px solid #f0d080;border-radius:9px;padding:12px 14px;margin-bottom:15px;font-size:12px;color:#7a5500;line-height:1.6}
.obox{background:#f2f8f4;border:1.5px dashed rgba(45,90,61,.28);border-radius:10px;padding:16px;margin-bottom:13px}
.codeBox{background:var(--ink);color:#88ff99;border-radius:7px;padding:9px 12px;font-family:'IBM Plex Mono',monospace;font-size:10px;word-break:break-all;line-height:1.6;margin-bottom:11px}
.hint2{background:#f0f8f2;border-radius:7px;padding:8px 11px;font-size:12px;color:#1a4a2a;margin-top:7px;line-height:1.55}
.seg{display:flex;gap:0;margin-bottom:15px;border-radius:9px;overflow:hidden;border:1.5px solid var(--sandd)}
.seg-btn{flex:1;padding:10px;text-align:center;font-size:13px;font-weight:600;cursor:pointer;background:var(--white);color:var(--inkl);border:none;font-family:'IBM Plex Sans',sans-serif;transition:.15s}
.seg-btn.on{background:var(--g);color:#fff}
.seg-btn:not(.on):hover{background:var(--sand)}
.console{background:#0d1117;border-radius:10px;padding:12px 14px;font-family:'IBM Plex Mono',monospace;font-size:11px;min-height:200px;max-height:300px;overflow-y:auto;margin-bottom:13px;line-height:1.8;border:1px solid rgba(255,255,255,.06)}
.console .log{color:#88ff99}.console .err{color:#ff7070}.console .info{color:#79b8ff}.console .warn{color:#ffd060}.console .dim{color:#252d3a}
.prog{margin-bottom:15px}
.prog-meta{display:flex;justify-content:space-between;font-size:12px;font-weight:600;color:var(--inkm);margin-bottom:5px}
.prog-track{background:var(--sandm);border-radius:99px;height:7px;overflow:hidden}
.prog-fill{height:100%;background:linear-gradient(90deg,var(--g),var(--g2));border-radius:99px;width:0%;transition:width .4s ease}
.sum{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin-bottom:18px}
.sbox{background:var(--white);border:1.5px solid var(--sandm);border-radius:10px;padding:13px 9px;text-align:center}
.snum{font-family:'Playfair Display',serif;font-size:28px;line-height:1;margin-bottom:3px}
.slbl{font-size:9px;color:var(--inkl);font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.snum.g{color:var(--g)}.snum.r{color:var(--red)}.snum.o{color:var(--amb)}
.rgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(165px,1fr));gap:10px}
.rcard{background:var(--white);border:1.5px solid var(--sandm);border-radius:10px;overflow:hidden;transition:.18s}
.rcard:hover{transform:translateY(-2px);box-shadow:0 7px 24px rgba(28,20,16,.12)}
.rcard.success{border-color:#9dd4b3}.rcard.error{border-color:#f5aaaa}.rcard.skipped{opacity:.5}
.rimg{width:100%;height:110px;object-fit:cover;background:var(--sandm);display:block}
.rbody{padding:8px}
.rname{font-size:11px;font-weight:600;line-height:1.3;margin-bottom:4px}
.rprice{font-size:12px;font-weight:700;color:var(--g);margin-bottom:4px}
.rbadge{display:inline-flex;align-items:center;font-size:9px;font-weight:700;padding:2px 7px;border-radius:20px;text-transform:uppercase}
.bd{background:#e6f4ee;color:var(--g)}.be{background:#fdecea;color:var(--red)}.bs{background:#f0ebe1;color:var(--inkl)}
.rlink{display:inline-block;font-size:10px;color:var(--g);text-decoration:underline;margin-top:3px}
.selgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:9px;margin-bottom:18px}
::-webkit-scrollbar{width:5px}
::-webkit-scrollbar-thumb{background:rgba(45,90,61,.18);border-radius:3px}

.scard{background:var(--white);border:1.5px solid var(--sandm);border-radius:10px;overflow:hidden}
.scard-hdr{padding:8px 12px;font-size:10px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:#fff}
.m1 .scard-hdr,.scard-hdr.m1{background:#6b8f71}
.m2 .scard-hdr,.scard-hdr.m2{background:#5b7fa6}
.m3 .scard-hdr,.scard-hdr.m3{background:#a67c52}
.m4 .scard-hdr,.scard-hdr.m4{background:var(--g)}
.scard-body{padding:11px 12px}
.scard-title{font-size:12px;font-weight:700;margin-bottom:4px}
.scard-desc{font-size:10px;color:var(--inkl);line-height:1.5;margin-bottom:6px}
.scard-count{font-size:11px;font-weight:700;color:var(--g)}
</style>
</head>
<body>
<header class="hdr">
  <div class="logo">Alrug → Etsy</div>
  <nav class="nav">
    <a href="http://localhost:8080/alrug" class="on">🪵 Alrug</a>
    <a href="http://localhost:8080/hpd">🪟 HPD</a>
  </nav>
  <div class="hdr-r">
    <a href="/admin" style="background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);color:rgba(255,255,255,.7);padding:4px 12px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;font-family:inherit;text-decoration:none;margin-right:6px">Admin</a><button onclick="doLogout()" type="button" style="background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);color:rgba(255,255,255,.7);padding:4px 12px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;font-family:inherit">Sign Out</button>
    <div class="pill"><div class="dot" id="sDot"></div><span id="sTxt">Not connected</span></div>
    <div class="chip" id="sChip">—</div>
  </div>
</header>
<div class="layout">
<aside class="sb">
  <div class="sbs"><div class="sbl">Steps</div>
    <nav class="snav">
      <div class="si on" id="n1" onclick="showP(1)"><div class="sn">1</div>Connect</div>
      <div class="si"    id="n2" onclick="showP(2)"><div class="sn">2</div>Configure</div>
      <div class="si"    id="n3" onclick="showP(3)"><div class="sn">3</div>Select Rugs</div>
      <div class="si"    id="n4" onclick="showP(4)"><div class="sn">4</div>Importing</div>
      <div class="si"    id="n5" onclick="showP(5)"><div class="sn">5</div>Review</div>
      <div class="si"    id="n7" onclick="showP(7)"><div class="sn">6</div>Listings</div>
      <div class="si"    id="n8" onclick="showP(8)"><div class="sn">7</div>Listing Writer</div>
    </nav>
  </div>
  <div class="sbs"><div class="sbl">Settings</div>
    <div class="cbox">
      <div class="crow"><span class="ck">Min</span><span class="cv" id="cfMin">$0</span></div>
      <div class="crow"><span class="ck">Max</span><span class="cv" id="cfMax">$200</span></div>
      <div class="crow"><span class="ck">Markup</span><span class="cv" id="cfMu">25%</span></div>
      <div class="crow"><span class="ck">Category</span><span class="cv g">Rugs 929</span></div>
      <div class="crow"><span class="ck">Status</span><span class="cv o">Draft</span></div>
    </div>
  </div>
  <div class="sbs"><div class="sbl">Stats</div>
    <div class="cbox">
      <div class="crow"><span class="ck">Fetched</span><span class="cv" id="stFetch">—</span></div>
      <div class="crow"><span class="ck">Drafted</span><span class="cv g" id="stDraft">—</span></div>
      <div class="crow"><span class="ck">Skipped</span><span class="cv" id="stSkip">—</span></div>
      <div class="crow"><span class="ck">Errors</span><span class="cv" id="stErr">—</span></div>
    </div>
  </div>
</aside>
<main class="main">

<!-- PANEL 1: CONNECT -->
<div class="panel on" id="p1">
  <div class="ph"><h2>Connect to Etsy</h2><p>Enter credentials, generate the auth URL, grant access, paste the code.</p></div>
  <div class="card">
    <div class="r3">
      <div class="field"><label>API Keystring</label><input id="apiKey" value="YOUR_ETSY_API_KEY"></div>
      <div class="field"><label>Shared Secret</label><input type="password" id="secret" value=""></div>
      <div class="field"><label>Shop Name</label><input id="shopName" value=""></div>
    </div>
    <button class="btn btn-p" style="margin-bottom:12px" onclick="genAuth()">🔐 Generate Auth URL</button>
    <div id="authStep2" style="display:none">
      <div class="field"><label>Auth URL</label><div class="codeBox" id="authUrl"></div>
        <button class="btn btn-o btn-sm" onclick="openAuth()">🌐 Open Authorization Page</button>
      </div>
      <div class="field" style="margin-top:11px"><label>Paste Code from Redirect URL</label>
        <input id="authCode" placeholder="Paste code here…">
        <div class="hint2">Stop Apache, grant access, copy value after <code>?code=</code> and before <code>&state=</code></div>
      </div>
      <button class="btn btn-p" onclick="doExchange()">✓ Connect &amp; Continue</button>
    </div>
  </div>
</div>

<!-- PANEL 2: CONFIGURE -->
<div class="panel" id="p2">
  <div class="ph"><h2>Configure Import</h2><p>Choose your source and price range, then load rugs.</p></div>
  <div class="seg">
    <button class="seg-btn on" id="tabUrl" onclick="setMode('url')">🔗 Collection URL</button>
    <button class="seg-btn"    id="tabSku" onclick="setMode('sku')">🔢 Product Numbers</button>
  </div>
  <div id="mUrl">
    <div class="card">
      <div class="field"><label>Alrug URL or Collection Slug</label>
        <input id="colUrl" value="area-rugs" oninput="updateSB()" placeholder="e.g. tribal-rug or https://www.alrug.com/collections/tribal-rug">
        <div class="hint">Paste a full URL or just the slug after /collections/</div>
      </div>
    </div>
  </div>
  <div id="mSku" style="display:none">
    <div class="card">
      <div class="field"><label>Product Handles or Stock Numbers</label>
        <textarea id="skuList" rows="4" placeholder="One per line&#10;AT43966&#10;AT94504&#10;hand-knotted-tribal-kazak-wool-rug"></textarea>
        <div class="hint">Enter Alrug product handles or stock numbers (AT-XXXXX), one per line</div>
      </div>
    </div>
  </div>
  <div class="card">
    <div class="r3">
      <div class="field"><label>Min Source Price ($)</label>
        <input type="number" id="minP" value="0" min="0" oninput="updateSB()">
        <div class="chips" id="minChips">
          <button class="chip2 on" onclick="setPre('minP','minChips',this,0)">Any</button>
          <button class="chip2"    onclick="setPre('minP','minChips',this,25)">$25</button>
          <button class="chip2"    onclick="setPre('minP','minChips',this,50)">$50</button>
          <button class="chip2"    onclick="setPre('minP','minChips',this,100)">$100</button>
        </div>
      </div>
      <div class="field"><label>Max Source Price ($)</label>
        <input type="number" id="maxP" value="200" min="1" oninput="updateSB()">
        <div class="chips" id="maxChips">
          <button class="chip2"    onclick="setPre('maxP','maxChips',this,100)">$100</button>
          <button class="chip2 on" onclick="setPre('maxP','maxChips',this,200)">$200</button>
          <button class="chip2"    onclick="setPre('maxP','maxChips',this,300)">$300</button>
          <button class="chip2"    onclick="setPre('maxP','maxChips',this,500)">$500</button>
          <button class="chip2"    onclick="setPre('maxP','maxChips',this,9999)">Any</button>
        </div>
      </div>
      <div class="field"><label>Markup (%)</label>
        <input type="number" id="mu" value="25" min="1" max="999" oninput="updateSB()">
        <div class="chips" id="muChips">
          <button class="chip2"    onclick="setPre('mu','muChips',this,10)">10%</button>
          <button class="chip2"    onclick="setPre('mu','muChips',this,20)">20%</button>
          <button class="chip2 on" onclick="setPre('mu','muChips',this,25)">25%</button>
          <button class="chip2"    onclick="setPre('mu','muChips',this,30)">30%</button>
          <button class="chip2"    onclick="setPre('mu','muChips',this,50)">50%</button>
        </div>
      </div>
    </div>
  </div>
  <div class="ibox">
    <div class="ibox-t">✅ Every draft includes</div>
    <div class="irow"><span>🗂️</span>Category: Floor &amp; Rugs → Rugs (929)</div>
    <div class="irow"><span>🧵</span>Materials: wool</div>
    <div class="irow"><span>🖼️</span>Up to 8 photos · 🚚 Free shipping · Draft</div>
    <div class="irow"><span>🎨</span>Color, pattern, shape, dimensions auto-set</div>
    <div class="irow"><span>🗂️</span>Shop section auto-matched to your categories</div>
  </div>
  <button class="btn btn-p" id="loadBtn" onclick="loadRugs()">🔍 Load Rugs for Selection</button>
</div>

<!-- PANEL 3: SELECT -->
<div class="panel" id="p3">
  <div class="ph"><h2>Select Rugs</h2><p id="selSub">Choose which rugs to import.</p></div>
  <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap">
    <button class="btn btn-o btn-sm" onclick="selAll()">Select All</button>
    <button class="btn btn-o btn-sm" onclick="selNone()">Select None</button>
    <span id="selCnt" style="font-size:12px;color:var(--inkl)">0 selected</span>
    <button class="btn btn-o btn-sm" onclick="showP(2)" style="margin-left:auto">← Back</button>
    <button class="btn btn-p btn-sm" onclick="doImport()">🚀 Import Selected</button>
  </div>
  <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px">
    <input id="gridSearch" placeholder="🔍 Filter by title or stock number…" oninput="gridFilter=this.value.toLowerCase();gridPage=1;renderGrid()" style="flex:1;padding:8px 12px;border:1.5px solid var(--sandd);border-radius:8px;font-size:13px;font-family:'IBM Plex Sans',sans-serif">
    <span id="gridCount" style="font-size:11px;color:var(--inkl);white-space:nowrap"></span>
  </div>
  <div class="selgrid" id="selGrid"></div>
  <div id="gridPager" style="display:flex;gap:6px;align-items:center;justify-content:center;margin:12px 0;flex-wrap:wrap"></div>
  <div style="display:flex;gap:9px;margin-top:4px">
    <button class="btn btn-o btn-sm" onclick="showP(2)">← Back</button>
    <button class="btn btn-p" onclick="doImport()">🚀 Import Selected</button>
  </div>
</div>

<!-- PANEL 4: IMPORTING -->
<div class="panel" id="p4">
  <div class="ph"><h2>Importing…</h2><p>Creating drafts in Etsy. Don't close this tab.</p></div>
  <button class="btn btn-o btn-sm" style="margin-bottom:14px" onclick="showP(2)">← Back</button>
  <div class="prog"><div class="prog-meta"><span id="pTxt">Initializing…</span><span id="pPct">0%</span></div><div class="prog-track"><div class="prog-fill" id="pFill"></div></div></div>
  <div class="console" id="con"><div class="dim">// Ready…</div></div>
  <div class="rgrid" id="rGrid"></div>
</div>

<!-- PANEL 5: REVIEW -->
<div class="panel" id="p5">
  <div class="ph"><h2>Import Complete 🎉</h2><p>Listings saved as Drafts in your Etsy shop.</p></div>
  <div class="sum">
    <div class="sbox"><div class="snum"   id="smT">0</div><div class="slbl">Fetched</div></div>
    <div class="sbox"><div class="snum g" id="smD">0</div><div class="slbl">Drafted</div></div>
    <div class="sbox"><div class="snum o" id="smS">0</div><div class="slbl">Skipped</div></div>
    <div class="sbox"><div class="snum r" id="smE">0</div><div class="slbl">Errors</div></div>
  </div>
  <div style="display:flex;gap:9px;margin-bottom:18px;flex-wrap:wrap">
    <a id="etsyLink" href="#" target="_blank" class="btn btn-p btn-sm" style="display:inline-flex">View Drafts in Etsy →</a>
    <button class="btn btn-o btn-sm" onclick="showP(2)">← Import More</button>

  </div>
  <div class="rgrid" id="rGrid2"></div>
</div>

<!-- PANEL 7: LISTINGS MANAGER -->
<div class="panel" id="p7">
  <div class="ph"><h2>📋 Listings Manager</h2><p>All your current Etsy listings and drafts. Click Edit to update a listing directly on Etsy.</p></div>
  <div id="listingsEmpty" style="text-align:center;padding:60px 20px">
    <div style="font-size:48px;margin-bottom:16px">📋</div>
    <div style="font-size:15px;font-weight:700;color:var(--ink);margin-bottom:8px">Your Etsy Listings</div>
    <div style="font-size:13px;color:var(--inkl);margin-bottom:24px">Active listings and drafts from your shop</div>
    <button class="btn btn-p" style="width:auto;padding:12px 32px" onclick="loadListings()">Load Listings</button>
  </div>
  <div id="listingsLoaded" style="display:none">
    <div style="display:flex;gap:9px;align-items:center;margin-bottom:18px;flex-wrap:wrap">
      <button class="btn btn-p btn-sm" onclick="loadListings()">🔄 Refresh</button>
      <span id="listingsSt" style="font-size:12px;color:var(--inkl)"></span>
    </div>
    <div id="listingsGrid"></div>
  </div>
</div>

<!-- PANEL 8: LISTING WRITER -->
<div class="panel" id="p8">
  <div class="ph"><h2>✍️ Listing Writer</h2><p>Paste an alrug.com product URL, fetch the details, then copy the ready-made prompt straight into Claude.</p></div>

  <div class="card">
    <div class="field">
      <label>Alrug.com Product URL</label>
      <input id="lwUrl" placeholder="https://www.alrug.com/products/hand-knotted-tribal-bokhara-..." oninput="lwClear()">
      <div class="hint">Paste the full product URL or just the handle</div>
    </div>
    <button class="btn btn-p" id="lwBtn" onclick="lwFetch()">🔍 Fetch Product</button>
  </div>

  <div id="lwError" class="wbox" style="display:none"></div>

  <div id="lwResult" style="display:none">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;flex-wrap:wrap;gap:8px">
      <div style="font-size:13px;font-weight:700;color:var(--g)" id="lwProductTitle"></div>
      <button class="btn btn-p btn-sm" onclick="lwCopy()" id="lwCopyBtn">📋 Copy Prompt</button>
    </div>
    <div style="background:#0d1117;border-radius:10px;padding:14px;font-family:'IBM Plex Mono',monospace;font-size:11px;line-height:1.7;color:#c9d1d9;max-height:480px;overflow-y:auto;white-space:pre-wrap;border:1px solid rgba(255,255,255,.06)" id="lwPrompt"></div>
    <div id="lwCopied" style="display:none;text-align:center;padding:8px;font-size:12px;font-weight:700;color:var(--g);margin-top:6px">✅ Copied to clipboard — paste into Claude</div>
  </div>
</div>


</main>
</div>
<script>
const API = '/api';
let tok='', apiK='', shop='', cv='', ps='';
let mode='url', elig=[], sel=new Set(), mu=1.25, col='area-rugs';
let stats={t:0,d:0,s:0,e:0};
const PAGE_SIZE=30; let gridPage=1, gridFilter='';

// ── Navigation ──
function showP(n){
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('on'));
  document.getElementById('p'+n).classList.add('on');
  document.querySelectorAll(".si").forEach(el=>el.classList.toggle("on", el.id==="n"+n));

  if(n===7){var e=document.getElementById("listingsEmpty");var l=document.getElementById("listingsLoaded");if(e)e.style.display="block";if(l)l.style.display="none";}
  if(n===7){var e=document.getElementById("listingsEmpty");var l=document.getElementById("listingsLoaded");if(e)e.style.display="block";if(l)l.style.display="none";}
}

// ── Sidebar ──
function updateSB(){
  document.getElementById('cfMin').textContent='$'+(document.getElementById('minP').value||0);
  document.getElementById('cfMax').textContent='$'+(document.getElementById('maxP').value||200);
  document.getElementById('cfMu').textContent=(document.getElementById('mu').value||25)+'%';
}

function setPre(id,gid,btn,v){
  document.getElementById(id).value=v;
  document.querySelectorAll('#'+gid+' .chip2').forEach(c=>c.classList.remove('on'));
  btn.classList.add('on'); updateSB();
}

function setMode(m){
  mode=m;
  document.getElementById('mUrl').style.display=m==='url'?'':'none';
  document.getElementById('mSku').style.display=m==='sku'?'':'none';
  document.getElementById('tabUrl').classList.toggle('on',m==='url');
  document.getElementById('tabSku').classList.toggle('on',m==='sku');
}

// ── Auth ──
function b64u(buf){return btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'');}
async function genAuth(){
  apiK = document.getElementById('apiKey').value.trim();
  const sec = document.getElementById('secret').value.trim();
  shop = document.getElementById('shopName').value.trim().toLowerCase().replace(/\s+/g,'');
  if(!apiK||!sec||!shop){alert('Fill in all three fields.');return;}
  const arr=new Uint8Array(32); crypto.getRandomValues(arr); cv=b64u(arr);
  const dig=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(cv));
  const ch=b64u(dig);
  ps=b64u(crypto.getRandomValues(new Uint8Array(8)));
  const url=`https://www.etsy.com/oauth/connect?response_type=code&redirect_uri=${encodeURIComponent(window.location.origin)}&scope=${encodeURIComponent('listings_w listings_r listings_d shops_r')}&client_id=${apiK}&state=${ps}&code_challenge=${ch}&code_challenge_method=S256`;
  document.getElementById('authUrl').textContent=url;
  document.getElementById('authStep2').style.display='';
}
function openAuth(){window.open(document.getElementById('authUrl').textContent,'_blank');}
async function doExchange(){
  const code=document.getElementById('authCode').value.trim();
  if(!code){alert('Paste the code first.');return;}
  try{
    const r=await fetch(`${API}/oauth/token`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_id:apiK,redirect_uri:window.location.origin,code,code_verifier:cv})});
    const d=await r.json();
    if(d.access_token){tok=d.access_token;markConn();showP(2);}
    else alert('Failed: '+(d.error_description||JSON.stringify(d)));
  }catch(e){alert('Error: '+e.message);}
}
function markConn(){
  document.getElementById('sDot').className='dot on';
  document.getElementById('sTxt').textContent='Connected ✓';
  document.getElementById('sChip').textContent=shop;
  document.getElementById('etsyLink').href=`https://www.etsy.com/your/shops/${shop}/tools/listings?status=draft`;
}

// ── Load rugs ──
async function loadRugs(){
  const btn=document.getElementById('loadBtn');
  btn.disabled=true; btn.textContent='⏳ Step 1/3: Syncing inventory…';
  try{
    const rebuildR=await fetch(`${API}/inventory/rebuild`, {method:'POST'});
    const rebuildD=await rebuildR.json();
    btn.textContent='✅ Inventory synced — Step 2/3: Fetching rugs…';
  }catch(e){
    btn.textContent='⚠️ Sync failed — Step 2/3: Fetching rugs…';
  }
  const minV=parseFloat(document.getElementById('minP').value)||0;
  const maxV=parseFloat(document.getElementById('maxP').value)||9999;
  mu=1+(parseFloat(document.getElementById('mu').value)||25)/100;
  let prods=[];
  if(mode==='sku'){
    const lines=document.getElementById('skuList').value.split('\n').map(l=>l.trim()).filter(Boolean);
    if(!lines.length){alert('Enter at least one product number or handle.');btn.disabled=false;btn.textContent='🔍 Load Rugs for Selection';return;}
    for(let h of lines){
      // Extract slug if full URL was pasted
      if(h.includes('alrug.com')){
        const m=h.match(/products\/([^?#/]+)/);
        if(m) h=m[1];
      }
      // If it looks like just a number/code with no letters prefix, add nothing
      h=h.trim();
      try{
        const r=await fetch(`${API}/product?domain=www.alrug.com&handle=${encodeURIComponent(h)}`);
        const d=await r.json();
        if(d.product){prods.push(d.product);}
        else console.warn('Not found:',h,d.error||'no product');
      }catch(e){console.error('Error for',h,e.message);}
    }
    if(!prods.length){alert('No products found. Check the handles/numbers and try again.');btn.disabled=false;btn.textContent='🔍 Load Rugs for Selection';return;}
  } else {
    let c=document.getElementById('colUrl').value.trim()||'area-rugs';
    // Handle search URLs like https://alrug.com/search?q=red+baluchi
    if(c.includes('/search') || c.includes('?q=')){
      const qm=c.match(/[?&]q=([^&]+)/);
      const q=qm?qm[1]:'';
      if(q){
        col='search:'+decodeURIComponent(q);
        const r=await fetch(`${API}/search?domain=www.alrug.com&q=${encodeURIComponent(decodeURIComponent(q))}`);
        const d=await r.json();
        prods=d.products||[];
      }
    } else {
      if(c.includes('alrug.com')){const m=c.match(/collections\/([^/?]+)/);if(m)c=m[1];}
      col=c;
      let page=1,go=true;
      while(go){
        try{const r=await fetch(`${API}/products?domain=www.alrug.com&collection=${encodeURIComponent(c)}&page=${page}`);const d=await r.json();
          if(d.products&&d.products.length){prods=prods.concat(d.products);go=d.products.length===250?(page++,true):false;}else go=false;
        }catch(e){go=false;}
      }
    }
  }
  // Price filter
  elig=prods.filter(p=>{const ps2=p.variants.map(v=>parseFloat(v.price)).filter(n=>!isNaN(n));return ps2.length>0&&Math.min(...ps2)<=maxV&&Math.max(...ps2)>=minV;});
  // Image filter — skip rugs with less than 2 images
  elig=elig.filter(p=>(p.images||[]).length>=2);
  // Already-imported filter — hide SKUs already in rug_inventory.csv
  try{
    const invR=await fetch(`${API}/inventory/skus`);
    const invD=await invR.json();
    const importedSkus=new Set((invD.skus||[]).map(s=>s.toUpperCase()));
    elig=elig.filter(p=>{
      const stk=(p.title.match(/No\.?\s*([A-Z0-9]+)\s*$/i)||['',''])[1].toUpperCase();
      return !stk||!importedSkus.has(stk);
    });
  }catch(e){}
  sel=new Set(elig.map(p=>p.id));
  document.getElementById('selSub').textContent=`${elig.length} rugs available to import (already imported rugs hidden).`;
  gridPage=1; gridFilter=''; if(document.getElementById('gridSearch'))document.getElementById('gridSearch').value='';
  elig.sort((a,b)=>scoreSellability(b).score-scoreSellability(a).score);
  renderGrid();
  btn.disabled=false; btn.textContent='🔍 Load Rugs for Selection';
  showP(3);
}

// ═══════════════════════════════════════════════════════════
// SELLABILITY SCORER — based on Etsy top seller research
// Scores 0-100, shows green ✓ (70+) or yellow ~ (50-69)
// ═══════════════════════════════════════════════════════════
function scoreSellability(product) {
  const t = product.title.toLowerCase();
  const tagList = Array.isArray(product.tags)
    ? product.tags.map(x=>x.toLowerCase())
    : String(product.tags||'').split(',').map(x=>x.trim().toLowerCase());
  const reasons = [];
  let score = 0;

  // ── 1. RUG TYPE (max 25) ──
  const typeScores = {
    bokhara:25, bukhara:25, kazak:23, kazakh:23, kilim:22,
    gabbeh:20, baluchi:20, balochi:20, oushak:18, ushak:18,
    ziegler:17, kashan:16, kohistani:15, jaldar:15, mashwani:14,
    tribal:12, abstract:10
  };
  let typeScore = 10, typeName = 'generic';
  for (const [key, pts] of Object.entries(typeScores)) {
    if (t.includes(key) || tagList.includes(key)) {
      typeScore = pts; typeName = key; break;
    }
  }
  score += typeScore;
  if (typeScore >= 20) reasons.push(`✓ ${typeName} rugs sell well on Etsy`);
  else if (typeScore < 15) reasons.push(`↓ ${typeName||'generic'} type has lower demand`);

  // ── 2. SIZE (max 25) ──
  const szm = product.title.match(/(\d+)[''`]\s*(\d+)["]\s*[xX]\s*(\d+)[''`]\s*(\d+)["]/);
  let sizeScore = 8, sizeName = 'unknown';
  if (szm) {
    const wft = parseInt(szm[1]), lft = parseInt(szm[3]);
    const wIn = wft*12+parseInt(szm[2]), lIn = lft*12+parseInt(szm[4]);
    const isRunner = t.includes('runner') || (wft <= 3 && lft >= 7);
    const sqFt = (wIn*lIn)/144;
    sizeName = `${wft}x${lft}`;
    if (isRunner)              { sizeScore=22; reasons.push('✓ Runner rugs are consistently popular'); }
    else if (sqFt>=35&&sqFt<56){ sizeScore=25; reasons.push('✓ 5x8/6x9 — #1 selling size on Etsy'); }
    else if (sqFt>=56&&sqFt<90){ sizeScore=23; reasons.push('✓ 6x9/8x10 — top selling living room size'); }
    else if (sqFt>=20&&sqFt<35){ sizeScore=20; reasons.push('✓ 4x6 — popular accent size'); }
    else if (sqFt>=90)         { sizeScore=12; reasons.push('~ Large rug — good margin, slower sale'); }
    else if (sqFt>=10&&sqFt<20){ sizeScore=15; reasons.push('~ Small size — lower margin'); }
    else                       { sizeScore=10; reasons.push('↓ Very small — limited buyer pool'); }
  } else {
    reasons.push('? Size not detected from title');
  }
  score += sizeScore;

  // ── 3. COLOR (max 20) ──
  const colorScores = {
    red:20, rust:18, terracotta:18, navy:19, blue:19,
    beige:17, ivory:17, cream:17, multi:15, multicolor:15,
    brown:13, tan:13, grey:12, gray:12, green:11,
    gold:10, black:9, orange:9, white:8, pink:7
  };
  let colorScore = 8, colorName = '';
  for (const c of tagList.concat(t.split(' '))) {
    if (colorScores[c] !== undefined) {
      colorScore = colorScores[c]; colorName = c; break;
    }
  }
  score += colorScore;
  if (colorScore >= 18) reasons.push(`✓ ${colorName} — most searched rug color`);
  else if (colorScore >= 15) reasons.push(`✓ ${colorName} — popular rug color`);
  else if (colorScore < 10) reasons.push(`~ ${colorName||'neutral'} color — smaller buyer pool`);

  // ── 4. PRICE SWEET SPOT (max 15) ──
  const prices = (product.variants||[]).map(v=>parseFloat(v.price)).filter(n=>!isNaN(n));
  const srcPrice = prices.length ? Math.min(...prices) : 0;
  const ep = srcPrice * 1.25; // estimated with 25% markup
  let priceScore = 5;
  if      (ep >= 75  && ep < 150)  { priceScore=15; reasons.push('✓ Price in impulse-buy sweet spot ($75-$150)'); }
  else if (ep >= 150 && ep < 250)  { priceScore=12; reasons.push('✓ Good price range ($150-$250)'); }
  else if (ep >= 50  && ep < 75)   { priceScore=10; reasons.push('~ Below $75 — fast sale, thin margin'); }
  else if (ep >= 250 && ep < 400)  { priceScore=8;  reasons.push('~ $250-$400 — slower, needs strong photos'); }
  else if (ep >= 400 && ep < 600)  { priceScore=5;  reasons.push('↓ $400+ — needs established trust'); }
  else if (ep >= 600)              { priceScore=3;  reasons.push('↓ $600+ — collector market, very slow'); }
  score += priceScore;

  // ── 5. PATTERN (max 15) ──
  const patScores = {geometric:15,tribal:14,floral:12,medallion:11,boteh:10,paisley:10,abstract:9,solid:7};
  let patScore = 8, patName = '';
  for (const [key, pts] of Object.entries(patScores)) {
    if (t.includes(key) || tagList.includes(key)) {
      patScore = pts; patName = key; break;
    }
  }
  score += patScore;
  if (patScore >= 14) reasons.push(`✓ ${patName} pattern — top searched`);

  // ── Final badge ──
  let badge = '', badgeColor = '';
  if      (score >= 70) { badge='✓ High Demand';   badgeColor='#1a7a3a'; }
  else if (score >= 50) { badge='~ Good Potential'; badgeColor='#c8860a'; }
  else                  { badge='↓ Lower Demand';   badgeColor='#888'; }

  return { score, badge, badgeColor, reasons, sizeName, colorName, typeName };
}


function renderGrid(){
  const g=document.getElementById('selGrid'); g.innerHTML='';
  const filtered = gridFilter
    ? elig.filter(p=>p.title.toLowerCase().includes(gridFilter)||p.handle.toLowerCase().includes(gridFilter))
    : elig;
  const totalPages = Math.ceil(filtered.length/PAGE_SIZE);
  const pageItems  = filtered.slice((gridPage-1)*PAGE_SIZE, gridPage*PAGE_SIZE);
  document.getElementById('gridCount').textContent = `${filtered.length} rugs · page ${gridPage}/${totalPages||1}`;

  // Pagination controls
  const pager=document.getElementById('gridPager'); pager.innerHTML='';
  if(totalPages>1){
    const btn=(label,pg,disabled)=>{const b=document.createElement('button');b.textContent=label;b.disabled=disabled;b.style.cssText=`padding:5px 11px;border-radius:7px;border:1.5px solid var(--sandd);background:${pg===gridPage?'var(--g)':'var(--white)'};color:${pg===gridPage?'#fff':'var(--ink)'};font-size:12px;font-weight:600;cursor:${disabled?'default':'pointer'};font-family:'IBM Plex Sans',sans-serif`;if(!disabled)b.onclick=()=>{gridPage=pg;renderGrid();document.getElementById('p3').scrollIntoView({behavior:'smooth'});};pager.appendChild(b);};
    btn('←',gridPage-1,gridPage===1);
    const start=Math.max(1,gridPage-2),end=Math.min(totalPages,start+4);
    for(let i=start;i<=end;i++)btn(i,i,false);
    btn('→',gridPage+1,gridPage===totalPages);
  }

  pageItems.forEach(p=>{
    const img=p.images&&p.images[0]?p.images[0].src:'';
    const prices=p.variants.map(v=>parseFloat(v.price)).filter(n=>!isNaN(n));
    const pr=prices.length?Math.min(...prices):0;
    const ep=(pr*mu).toFixed(2);
    const ct=p.title.replace(/\s*-\s*No\.?\s*[A-Z0-9]+\s*$/i,'').trim();
    const stk=(p.title.match(/No\.?\s*([A-Z0-9]+)\s*$/i)||['',''])[1].toUpperCase();
    const chk=sel.has(p.id);
    const sell = scoreSellability(p);
    const card=document.createElement('div');
    card.style.cssText=`background:var(--white);border:2px solid ${chk?'var(--g)':'var(--sandm)'};border-radius:10px;overflow:hidden;cursor:pointer;transition:border-color .15s;position:relative`;
    card.onclick=()=>toggleSel(p.id,card);
    // Score badge tooltip
    const tipHtml = sell.reasons.map(r=>`<div>${r}</div>`).join('');
    card.innerHTML=(img?`<img src="${img}" style="width:100%;height:105px;object-fit:cover;display:block" loading="lazy">`:`<div style="width:100%;height:105px;background:var(--sandm)"></div>`)
      +`<div style="position:absolute;top:5px;right:5px;background:${sell.badgeColor};color:#fff;border-radius:20px;padding:2px 7px;font-size:9px;font-weight:700;cursor:help" title="Score: ${sell.score}/100&#10;${sell.reasons.join('&#10;')}">${sell.badge} ${sell.score}</div>`
      +`<div style="padding:7px"><div style="font-size:10px;font-weight:600;line-height:1.3;margin-bottom:2px">${ct.substring(0,48)}</div>`
      +`<div style="display:flex;align-items:center;gap:4px;margin-bottom:3px">`
      +`<span style="font-size:9px;color:var(--inkl);font-family:'IBM Plex Mono',monospace">${stk}</span>`
      +`<a href="https://www.alrug.com/products/${p.handle}" target="_blank" onclick="event.stopPropagation()" title="View on Alrug" style="color:var(--inkl);text-decoration:none;font-size:11px;line-height:1" onmouseover="this.style.color='var(--g)'" onmouseout="this.style.color='var(--inkl)'">🔗</a>`
      +`</div>`
      +`<div style="font-size:11px;font-weight:700;color:var(--g)">$${ep}</div>`
      +`<div style="font-size:9px;color:var(--inkl)">src $${pr.toFixed(2)}</div>`
      +`<div class="lbl" style="margin-top:4px;font-size:9px;font-weight:700;color:${chk?'var(--g)':'var(--inkl)'}">${chk?'✓ Selected':'○ Skip'}</div></div>`;
    g.appendChild(card);
  });
  document.getElementById('selCnt').textContent=sel.size+' selected';
}
function toggleSel(id,card){
  if(sel.has(id)){sel.delete(id);card.style.borderColor='var(--sandm)';card.querySelector('.lbl').textContent='○ Skip';card.querySelector('.lbl').style.color='var(--inkl)';}
  else{sel.add(id);card.style.borderColor='var(--g)';card.querySelector('.lbl').textContent='✓ Selected';card.querySelector('.lbl').style.color='var(--g)';}
  document.getElementById('selCnt').textContent=sel.size+' selected';
}
function selAll(){elig.forEach(p=>sel.add(p.id));renderGrid();}
function selNone(){sel.clear();renderGrid();}

// ── Field extraction ──
const SECTIONS={29601457:['gabbeh'],29601505:['jaldar'],29601453:['baluchi','balochi'],29601479:['runner'],30093767:['kashan'],29493424:['kilim'],30083880:['kohistani'],30446656:['fine baluchi'],29601473:['bokhara','bukhara'],30101910:['oushak','ushak'],30135445:['saddle bag','saddlebag'],30398231:['ziegler'],30315786:['kazak','kazakh'],30315876:['abstract'],37971857:['balisht'],38600961:['barjasta'],38601099:['bisque'],38637157:['mashwani'],38956324:['moroccan']};
function matchSec(title){const t=title.toLowerCase();for(const [id,kws] of Object.entries(SECTIONS)){if(kws.some(k=>t.includes(k)))return parseInt(id);}return null;}

function parseFtIn(str){
  if(!str)return null; str=String(str).trim();
  const m=str.match(/(\d+)['`]\s*(\d+)/); if(m)return parseInt(m[1])*12+parseInt(m[2]);
  const ft=str.match(/^(\d+(?:\.\d+)?)[`']/); if(ft)return Math.round(parseFloat(ft[1])*12);
  const cm=str.match(/([\d.]+)\s*cm/i); if(cm)return Math.round(parseFloat(cm[1])/2.54);
  const n=str.match(/^([\d.]+)$/); if(n)return Math.round(parseFloat(n[1]));
  return null;
}

function getFields(product){
  const html=product.body_html||'', title=product.title.toLowerCase(), f={};

  // ── Read from Alrug tags (most reliable source) ──
  // Tags like: ['Blue', 'Red', 'Ivory', 'Rectangle', 'Tribal', 'Wool', 'Hand Knotted', 'Kilim']
  const tagList = Array.isArray(product.tags)
    ? product.tags.map(t=>t.toLowerCase())
    : String(product.tags||'').split(',').map(t=>t.trim().toLowerCase());

  const COLOR_TAGS   = ['beige','black','blue','brown','gold','gray','grey','green','ivory','cream','multi','multicolor','navy','orange','pink','purple','red','rose','rust','silver','tan','teal','terracotta','white','yellow'];
  const PATTERN_TAGS = ['geometric','floral','abstract','tribal','medallion','boteh','paisley','herati','prayer','oriental','moroccan','bordered','striped','ikat'];
  const SHAPE_TAGS   = ['rectangle','rectangular','round','circle','oval','square','runner'];

  // Primary color — can have multiple, pick first known
  const colorTags = tagList.filter(t => COLOR_TAGS.includes(t));
  if (colorTags.length >= 1) f.color = colorTags[0]; // use first/dominant color
  
  // Pattern from tags
  for (const t of tagList) if (PATTERN_TAGS.includes(t)) { f.pattern = t; break; }

  // Shape from tags
  for (const t of tagList) if (SHAPE_TAGS.includes(t)) { f.shape = t; break; }

  // Pile: flat for kilims
  f.pile = tagList.includes('kilim') || title.includes('kilim') ? 'flat' : 'medium';

  // Extract origin from description text e.g. "from Afghanistan" or "from Pakistan"
  const descText = (html.replace(/<[^>]+>/g,' ')||'').toLowerCase();
  if      (descText.includes('from afghanistan') || descText.includes('afghanistan.') || descText.includes('woven in afghanistan')) f.origin = 'Afghan';
  else if (descText.includes('from pakistan')    || descText.includes('pakistan.')    || descText.includes('woven in pakistan'))    f.origin = 'Pakistani';
  else if (descText.includes('from turkey')      || descText.includes('turkey.')      || descText.includes('turkish'))              f.origin = 'Turkish';
  else if (descText.includes('from morocco')     || descText.includes('morocco.')     || descText.includes('moroccan'))             f.origin = 'Moroccan';
  else if (title.includes('afghan'))    f.origin = 'Afghan';
  else if (title.includes('pakistan'))  f.origin = 'Pakistani';
  else if (title.includes('turkish'))   f.origin = 'Turkish';
  else if (title.includes('moroccan'))  f.origin = 'Moroccan';

  // Fallback to title if tags didn't give us color/pattern/shape
  if (!f.color)   { for (const c of COLOR_TAGS)   if (title.includes(c)) { f.color   = c; break; } }
  if (!f.pattern) { for (const p of PATTERN_TAGS) if (title.includes(p)) { f.pattern = p; break; } }
  if (!f.shape)   { for (const s of SHAPE_TAGS)   if (title.includes(s)) { f.shape   = s; break; } }

  // Default color to multi for tribal/kazak rugs
  if (!f.color) f.color = 'beige'; // default for undetected colors

  // ── Dimensions from title e.g. "1' 11" x 2' 9"" ──
  const raw2=product.title;
  const dm=raw2.match(/(\d+)[''`]\s*(\d+)/g);
  if (dm && dm.length >= 2) {
    const p1=dm[0].match(/(\d+)[''`]\s*(\d+)/), p2=dm[1].match(/(\d+)[''`]\s*(\d+)/);
    if(p1&&p2){f.wi=parseInt(p1[1])*12+parseInt(p1[2]);f.li=parseInt(p2[1])*12+parseInt(p2[2]);}
  }

  return f;
}

const COLOR_IDS={beige:1213,black:1,blue:2,brown:3,gold:1214,gray:5,grey:5,green:4,ivory:1213,multi:1220,multicolor:1220,navy:2,orange:6,pink:7,purple:8,red:9,rust:6,tan:3,teal:4,terracotta:6,white:10,yellow:11,cream:1213};
const PAT_IDS={abstract:395,floral:424,geometric:426,tribal:2336,moroccan:2335,oriental:2336,paisley:445,striped:465,solid:460,bordered:2333,ikat:435,medallion:2336,boteh:445,herati:435,prayer:2334};
const SHAPE_IDS={rectangular:361,rectangle:361,round:326,circle:326,oval:353,square:371,runner:361};

async function setProps(lid,product){
  const f=getFields(product);
  const H={'Content-Type':'application/json','Authorization':`Bearer ${tok}`};
  const pr=async(pid,vids,vals,scale)=>{
    const b={value_ids:vids,values:vals.map(String)};
    if(scale)b.scale_id=scale;
    try{const r=await fetch(`${API}/etsy/property/${lid}/${pid}`,{method:'PUT',headers:H,body:JSON.stringify(b)});return r.ok;}catch(e){return false;}
  };

  // when_made + section
  try{
    const sec=matchSec(product.title);
    const ub={when_made:'2020_2026',who_made:'collective',is_supply:false};
    if(sec)ub.shop_section_id=sec;
    const r=await fetch(`${API}/etsy/update/${lid}`,{method:'PATCH',headers:H,body:JSON.stringify(ub)});
    const d=await r.json();
    const sn=sec?(Object.entries(SECTIONS).find(([id])=>id==sec)||[])[1]?.[0]:'none';
    if(r.ok)clog('log',`  📅 2020-2026 · 🗂️ ${sn}`);
    else clog('warn',`  ⚠️ Update: ${d.error||r.status}`);
  }catch(e){clog('warn','  ⚠️ '+e.message);}
  await sleep(200);

  // Color
  const cid=COLOR_IDS[(f.color||'').toLowerCase()];
  if(cid){await pr(200,[cid],[f.color]);clog('log',`  🎨 ${f.color}`);}
  await sleep(150);

  // Pattern
  const pid2=PAT_IDS[(f.pattern||'').toLowerCase()];
  if(pid2){await pr(99837394318,[pid2],[f.pattern]);clog('log',`  🔲 ${f.pattern}`);}
  await sleep(150);

  // Shape
  const shid=SHAPE_IDS[(f.shape||'').toLowerCase()]||361;
  await pr(47626759726,[shid],[f.shape||'Rectangle']);
  await sleep(150);

  // Pile height
  await pr(570246213612,f.pile==='flat'?[5117]:[5120],[f.pile==='flat'?'Flat':'Medium']);
  await sleep(150);

  // Dimensions
  if(f.wi){await pr(47626759898,[],[String(f.wi)],5);}
  if(f.li){await pr(47626759838,[],[String(f.li)],5);}
  if(f.wi&&f.li)clog('log',`  📐 ${f.wi}" x ${f.li}"`);
  await sleep(150);

  // Materials → Wool
  await pr(148789511893,[288],['Wool']);
  await sleep(150);

  // Sustainability → Organic cotton
  await pr(570246213604,[5009],['Organic cotton']);
  await sleep(150);

  // Indoor
  await pr(570246213613,[5129],['Indoor']);
  await sleep(150);

  // Rug type
  const rt=product.title.toLowerCase().includes('runner')?2375:2373;
  await pr(148789511877,[rt],[rt===2375?'Runner':'Area']);
  await sleep(150);


  clog('dim','  ✅ Properties set');
}

// ── Description & Tags ──
// ── Banned words — remove from all text to protect Etsy account ──
const BANNED = [
  'persian','iran','iranian','isfahan','tabriz','qom','tehran',
  'persia','persian-style','persian style','persian rug'
];
function sanitize(text){
  if(!text) return '';
  let t = text;
  for(const w of BANNED){
    // Case-insensitive replace with safe alternative
    const re = new RegExp('\\b'+w+'\\b', 'gi');
    if(w.includes('iran') || w === 'persia'){
      t = t.replace(re, '');  // remove entirely
    } else if(w.includes('persian')){
      t = t.replace(re, 'traditional');  // replace with safe word
    } else {
      t = t.replace(re, '');
    }
  }
  return t.replace(/\s+/g,' ').replace(/,\s*,/g,',').trim();
}

function desc(product){
  const NL=String.fromCharCode(10);
  const html=product.body_html||'';
  const raw=sanitize(html.replace(/<[^>]+>/g,' ').replace(/&amp;/g,'&').replace(/&nbsp;/g,' ').replace(/\s+/g,' ').trim());
  const f={};
  const tdTag='td',trTag='tr';
  const re=new RegExp('<'+trTag+'[^>]*>\\s*<'+tdTag+'[^>]*>([^<]+)</'+tdTag+'>\\s*<'+tdTag+'[^>]*>([^<]+)</'+tdTag+'>','gi');
  [...html.matchAll(re)].forEach(m=>{f[m[1].trim()]=m[2].trim();});
  const ct=product.title.replace(/\s*-\s*No\.?\s*[A-Z0-9]+\s*$/i,'').trim();
  const fl=Object.entries(f).map(([k,v])=>k+': '+v);
  const parts=[raw||'A beautifully crafted area rug.',''];
  if(fl.length){parts.push('PRODUCT DETAILS','------------------------------',...fl,'');}
  parts.push('CARE INSTRUCTIONS','------------------------------','Spot clean or professional rug cleaning recommended','Vacuum regularly without beater bar','Use a rug pad for best results','','FREE SHIPPING - ships within 3-5 business days.','','Questions? Message us!');
  return parts.join(NL);
}
// ═══════════════════════════════════════════════════════
// TERMS LIBRARY — based on top Etsy sellers research
// ═══════════════════════════════════════════════════════
const STYLE_TERMS = {
  kazak:      {adj:'Kazak',         origin:'Afghan',   weave:'Hand Knotted', vibe:'tribal geometric'},
  kazakh:     {adj:'Kazak',         origin:'Afghan',   weave:'Hand Knotted', vibe:'tribal geometric'},
  baluchi:    {adj:'Baluchi',       origin:'Afghan',   weave:'Hand Knotted', vibe:'tribal rustic'},
  balochi:    {adj:'Baluchi',       origin:'Afghan',   weave:'Hand Knotted', vibe:'tribal rustic'},
  gabbeh:     {adj:'Gabbeh',        origin:'Afghan',   weave:'Hand Knotted', vibe:'boho rustic'},
  kilim:      {adj:'Kilim',         origin:'Afghan',   weave:'Hand Woven',   vibe:'boho flat weave'},
  bokhara:    {adj:'Bokhara',       origin:'Pakistani', weave:'Hand Knotted', vibe:'turkmen traditional'},
  bukhara:    {adj:'Bokhara',       origin:'Pakistani', weave:'Hand Knotted', vibe:'turkmen traditional'},
  oushak:     {adj:'Oushak',        origin:'Turkish',   weave:'Hand Knotted', vibe:'vintage traditional'},
  ushak:      {adj:'Oushak',        origin:'Turkish',   weave:'Hand Knotted', vibe:'vintage traditional'},
  ziegler:    {adj:'Ziegler',       origin:'Pakistani', weave:'Hand Knotted', vibe:'vintage floral'},
  kashan:     {adj:'Kashan',        origin:'Pakistani', weave:'Hand Knotted', vibe:'traditional floral'},
  kohistani:  {adj:'Kohistani',     origin:'Afghan',    weave:'Hand Knotted', vibe:'tribal rustic'},
  jaldar:     {adj:'Jaldar',        origin:'Pakistani', weave:'Hand Knotted', vibe:'tribal geometric'},
  mashwani:   {adj:'Mashwani',      origin:'Pakistani', weave:'Hand Knotted', vibe:'tribal kilim'},
  moroccan:   {adj:'Moroccan',      origin:'Moroccan', weave:'Hand Woven',   vibe:'boho geometric'},
  tribal:     {adj:'Tribal',        origin:'Afghan',   weave:'Hand Knotted', vibe:'boho tribal'},
  turkmen:    {adj:'Turkmen',       origin:'Afghan',   weave:'Hand Knotted', vibe:'traditional tribal'},
  balisht:    {adj:'Balisht',       origin:'Afghan',   weave:'Hand Knotted', vibe:'tribal rustic'},
  barjasta:   {adj:'Barjasta',      origin:'Afghan',   weave:'Hand Knotted', vibe:'tribal traditional'},
  abstract:   {adj:'Abstract',      origin:'Afghan',   weave:'Hand Knotted', vibe:'modern boho'},
};

const COLOR_VIBES = {
  red:        ['red wool rug','rust boho rug','warm living room rug'],
  blue:       ['blue area rug','navy tribal rug','cool bedroom rug'],
  green:      ['green wool rug','forest boho rug','earthy area rug'],
  grey:       ['grey area rug','neutral wool rug','modern tribal rug'],
  gray:       ['gray area rug','neutral wool rug','modern tribal rug'],
  beige:      ['beige area rug','neutral boho rug','farmhouse rug'],
  ivory:      ['ivory area rug','cream wool rug','neutral farmhouse rug'],
  cream:      ['cream wool rug','neutral area rug','farmhouse boho rug'],
  brown:      ['brown wool rug','earthy tribal rug','rustic area rug'],
  gold:       ['gold area rug','warm boho rug','yellow tribal rug'],
  rust:       ['rust area rug','terracotta rug','warm boho carpet'],
  terracotta: ['terracotta rug','rust boho rug','warm area rug'],
  navy:       ['navy area rug','dark blue rug','deep tribal rug'],
  teal:       ['teal area rug','blue green rug','boho teal carpet'],
  black:      ['black wool rug','dark area rug','bold tribal rug'],
  white:      ['white wool rug','light area rug','minimalist rug'],
  multi:      ['colorful area rug','multicolor wool rug','boho tribal rug'],
  orange:     ['orange area rug','warm boho rug','rust tribal rug'],
  pink:       ['pink wool rug','blush area rug','soft boho rug'],
  purple:     ['purple area rug','violet wool rug','rich boho rug'],
};

const ROOM_TERMS = ['living room rug','bedroom rug','entryway rug','hallway runner','dining room rug','home office rug','kitchen rug'];
const GIFT_TERMS = ['housewarming gift','unique home decor','handmade gift','one of a kind rug'];
const QUALITY_TERMS = ['vegetable dyed','natural dyes','chemical free','pet friendly rug','hand spun wool'];

function seoTitle(product, ct){
  const t = product.title.toLowerCase();
  const tagList = Array.isArray(product.tags)
    ? product.tags.map(x=>x.toLowerCase())
    : String(product.tags||'').split(',').map(x=>x.trim().toLowerCase());
  const f = getFields(product); // get origin, color, pattern from description

  // Detect style
  let styleKey = '', styleData = null;
  for (const [key, data] of Object.entries(STYLE_TERMS)) {
    if (t.includes(key) || tagList.includes(key)) { styleKey=key; styleData=data; break; }
  }

  // Detect color
  const colorKeys = Object.keys(COLOR_VIBES);
  let color = '';
  for (const c of colorKeys) if (tagList.includes(c) || t.includes(c)) { color=c; break; }

  // Size from title e.g. 1' 11" x 2' 9"
  const szm = product.title.match(/(\d+)[''`]\s*(\d+)["]\s*[xX]\s*(\d+)[''`]\s*(\d+)["]/);
  let size = '', sizeLabel = '';
  if (szm) {
    const wIn = parseInt(szm[1])*12+parseInt(szm[2]);
    const lIn = parseInt(szm[3])*12+parseInt(szm[4]);
    const wft = parseInt(szm[1]), lft = parseInt(szm[3]);
    size = `${wft}x${lft}`;
    const sqFt = (wIn*lIn)/144;
    if (t.includes('runner'))     sizeLabel = 'Runner';
    else if (sqFt < 12)           sizeLabel = 'Small';
    else if (sqFt < 35)           sizeLabel = 'Medium';
    else if (sqFt < 63)           sizeLabel = 'Large';
    else                          sizeLabel = 'Oversized';
  }

  const isKilim  = t.includes('kilim');
  const isRunner = t.includes('runner');
  const origin   = (f && f.origin) ? f.origin : (styleData ? styleData.origin : 'Afghan');
  const weave    = styleData ? styleData.weave  : 'Hand Knotted';
  const style    = styleData ? styleData.adj    : 'Tribal';
  const colorCap = color ? color.charAt(0).toUpperCase()+color.slice(1)+' ' : '';
  const type     = isKilim ? 'Kilim' : 'Wool Rug';

  // Format: [Size] [Color] [Style] Rug, [Weave] [Origin] [Type], [SizeLabel] [Room]
  const p1 = `${size ? size+' ' : ''}${colorCap}${style} Rug`;
  const p2 = `${weave} ${origin} ${type}`;
  const exSz=product.title.match(/(\d+[''`]\s*\d+)\s*[xX]\s*(\d+[''`]\s*\d+)/);
  const exSize=exSz?exSz[1].replace(/[''`]/,"'")+' x '+exSz[2].replace(/[''`]/,"'")+' ft':'';
  const p3=`${sizeLabel?sizeLabel+' ':''}${isRunner?'Hallway Runner':'Area Carpet'}${exSize?' '+exSize:''}`;
  return sanitize([p1, p2, p3].filter(Boolean).join(', '));
}

function tags(product){
  const t = product.title.toLowerCase();
  const tagList = Array.isArray(product.tags)
    ? product.tags.map(x=>x.toLowerCase())
    : String(product.tags||'').split(',').map(x=>x.trim().toLowerCase());

  // Detect style and color
  let styleKey='', styleData=null;
  for (const [key,data] of Object.entries(STYLE_TERMS)) {
    if (t.includes(key)||tagList.includes(key)){styleKey=key;styleData=data;break;}
  }
  const colorKeys = Object.keys(COLOR_VIBES);
  let color='';
  for (const c of colorKeys) if (tagList.includes(c)||t.includes(c)){color=c;break;}

  const isKilim  = t.includes('kilim');
  const isRunner = t.includes('runner');
  const origin   = styleData ? styleData.origin.toLowerCase() : 'afghan';
  const style    = styleData ? styleData.adj.toLowerCase()   : 'tribal';
  const vibe     = styleData ? styleData.vibe                : 'boho tribal';

  // Size
  const szm = product.title.match(/(\d+)[''`]\s*(\d+)["]\s*[xX]\s*(\d+)[''`]\s*(\d+)["]/);
  let sizeTag = '';
  if (szm) { sizeTag = `${szm[1]}x${szm[3]} area rug`; }

  // Build 13 targeted tags
  const pool = [
    color ? `${color} ${style} rug` : `${style} wool rug`,
    color ? `${color} area rug`     : `${origin} area rug`,
    isKilim  ? 'kilim flat weave'   : `${origin} wool rug`,
    isRunner ? 'hallway runner rug' : 'handmade area rug',
    `hand knotted ${style}`,
    `${vibe} rug`,
    sizeTag || `${origin} carpet`,
    isRunner ? 'kitchen runner rug' : 'living room rug',
    color ? `${color} wool rug`     : 'tribal wool rug',
    isKilim ? 'boho flat rug'       : 'boho home decor',
    'housewarming gift',
    `${origin} handmade rug`,
    isRunner ? 'entryway runner'    : 'bedroom area rug',
  ].filter(Boolean);

  return [...new Set(pool)].slice(0,13).map(s=>s.substring(0,20));
}



// ── Import ──
function doImport(){
  if(!sel.size){alert('Select at least one rug.');return;}
  document.getElementById('con').innerHTML='<div class="dim">// Starting import…</div>';
  document.getElementById('rGrid').innerHTML='';
  document.getElementById('rGrid2').innerHTML='';
  stats={t:0,d:0,s:0,e:0};
  ['stFetch','stDraft','stSkip','stErr'].forEach(id=>document.getElementById(id).textContent='—');
  setP(0,1,'Initializing…'); showP(4);
  runImport(elig.filter(p=>sel.has(p.id)));
}

function clog(type,msg){
  const c=document.getElementById('con'),d=document.createElement('div');
  d.className=type;d.textContent=`[${new Date().toLocaleTimeString('en-US',{hour12:false})}] ${msg}`;
  c.appendChild(d);c.scrollTop=c.scrollHeight;
  document.getElementById('stDraft').textContent=stats.d;
  document.getElementById('stSkip').textContent=stats.s;
  document.getElementById('stErr').textContent=stats.e;
}
function setP(cur,tot,lbl){
  const pct=tot>0?Math.round((cur/tot)*100):0;
  document.getElementById('pFill').style.width=pct+'%';
  document.getElementById('pPct').textContent=pct+'%';
  document.getElementById('pTxt').textContent=lbl||`${cur} of ${tot}`;
}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

async function runImport(prods){
  const maxV=parseFloat(document.getElementById('maxP').value)||9999;
  const muV=1+(parseFloat(document.getElementById('mu').value)||25)/100;
  stats.t=prods.length;
  document.getElementById('stFetch').textContent=stats.t;
  clog('log',`✅ ${prods.length} rugs selected for import`);

  for(let i=0;i<prods.length;i++){
    const p=prods[i];
    setP(i,prods.length,`${i+1}/${prods.length}: ${p.title.substring(0,35)}…`);
    const fv=p.variants.find(v=>!isNaN(parseFloat(v.price))&&parseFloat(v.price)<=maxV);
    if(!fv){clog('warn',`  ⏭ Skipped — no qualifying price`);stats.s++;addCard(p,'skipped',null,null,'No qualifying price');continue;}
    const orig=parseFloat(fv.price), ep=parseFloat((orig*muV).toFixed(2));
    const ct=p.title.replace(/\s*-\s*No\.?\s*[A-Z0-9]+\s*$/i,'').trim();
    const stk=(p.title.match(/No\.?\s*([A-Z0-9]+)\s*$/i)||['',''])[1].toUpperCase();
    clog('info',`📝 "${ct.substring(0,48)}" — $${ep}`);

    // Dup check
    try{const invR=await fetch(`${API}/inventory/check?sku=${encodeURIComponent(stk)}`);const invD=await invR.json();if(invD.exists){clog('warn',`  ⏭ SKU ${stk} already imported`);stats.s++;addCard(p,'skipped',null,null,'Already imported');continue;}}catch(e){}

    try{
      const body={
        quantity:1,
        title:sanitize(seoTitle(p,ct)).substring(0,140),
        description:desc(p),
        price:ep,
        who_made:'collective',
        when_made:'made_to_order',
        taxonomy_id:929,
        tags:tags(p),
        materials:['wool'],
        state:'draft',
        type:'physical',
        is_personalizable:false,
        is_digital:false,
        should_auto_renew:true,
        sku:stk||p.handle
      };
      const cr=await fetch(`${API}/etsy/create`,{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${tok}`},body:JSON.stringify({...body,_shop:shop})});
      const cl=await cr.json();
      if(!cr.ok||!cl.listing_id)throw new Error(cl.error_description||cl.error||`HTTP ${cr.status}`);
      const lid=cl.listing_id;
      clog('log',`  ✅ Draft created — ID ${lid}`);

      // Set SKU via inventory (only way Etsy actually stores it)
      if(stk){
        try{
          // First get current readiness_state_id from the listing
          const invBody = {
            products:[{
              sku:stk,
              property_values:[],
              offerings:[{price:ep,quantity:1,is_enabled:true,readiness_state_id:1472868231198}]
            }],
            price_on_property:[]
          };
          const skuR=await fetch(`${API}/etsy/inventory/${lid}`,{
            method:'PUT',
            headers:{'Content-Type':'application/json','x-api-key':apiK,'Authorization':`Bearer ${tok}`},
            body:JSON.stringify(invBody)
          });
          if(skuR.ok) clog('log',`  🏷️ SKU: ${stk}`);
          else{const se=await skuR.json();clog('warn',`  ⚠️ SKU: ${se.error||se.error_description||JSON.stringify(se).substring(0,80)}`);}
        }catch(se){clog('warn',`  ⚠️ SKU error: ${se.message}`);}
        await sleep(200);
      }

      // Sync save


      // Set listing properties
      await setProps(lid,p);

      // Photos
      const photos=(p.images||[]).slice(0,8); let pc=0;
      for(let pi=0;pi<photos.length;pi++){
        try{const pr2=await fetch(`${API}/etsy/image/${shop}/${lid}`,{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${tok}`},body:JSON.stringify({url:photos[pi].src,rank:pi+1})});if(pr2.ok)pc++;}catch(e){}
        await sleep(150);
      }
      clog('log',`  🖼️ ${pc}/${photos.length} photos`);
      stats.d++; addCard(p,'success',lid,ep);
    }catch(e){clog('err',`  ❌ ${e.message}`);stats.e++;addCard(p,'error',null,null,e.message);}
    await sleep(700);
  }
  setP(90,100,'⏳ Updating inventory...');
  try{ await fetch(`${API}/inventory/rebuild`,{method:'POST'}); }catch(e){}
  clog('log',`🎉 ${stats.d} drafted · ${stats.s} skipped · ${stats.e} errors`);
  ['smT','smD','smS','smE'].forEach((id,i)=>document.getElementById(id).textContent=[stats.t,stats.d,stats.s,stats.e][i]);
  document.getElementById('rGrid2').innerHTML=document.getElementById('rGrid').innerHTML;
  await sleep(300);
  setP(100,100,'✅ Complete!');
  await sleep(800); showP(5);
}

function addCard(p,status,lid,ep,err){
  const img=p.images&&p.images[0]?p.images[0].src:'';
  const ct=p.title.replace(/\s*-\s*No\.?\s*[A-Z0-9]+\s*$/i,'').trim();
  const badge=status==='success'?'<span class="rbadge bd">✓ Draft</span>':status==='error'?'<span class="rbadge be">✕ Error</span>':'<span class="rbadge bs">— Skip</span>';
  const link=lid?`<a class="rlink" href="https://www.etsy.com/your/shops/${shop}/tools/listings/${lid}" target="_blank">View in Etsy →</a>`:'';
  const stk2=(p.title.match(/No\.?\s*([A-Z0-9]+)\s*$/i)||["",""])[1].toUpperCase();
  const alrugLink=`<a class="rlink" href="https://www.alrug.com/products/${p.handle}" target="_blank" style="margin-left:8px">${stk2||"Alrug"} -></a>`;
  const errN=err?`<div style="font-size:10px;color:var(--red);margin-top:3px">${String(err).substring(0,85)}</div>`:'';
  const card=document.createElement('div');
  card.className='rcard '+status;
  card.innerHTML=(img?`<img class="rimg" src="${img}" alt="" loading="lazy">`:'<div class="rimg"></div>')
    +`<div class="rbody"><div class="rname">${ct.substring(0,50)}</div>`
    +(ep?`<div class="rprice">$${Number(ep).toFixed(2)}</div>`:'')
    +badge+errN+link+alrugLink+'</div>';
  document.getElementById('rGrid').appendChild(card);
}

// ── Sync Check ──
async function runSync(){
  const st=document.getElementById('syncSt'),res=document.getElementById('syncRes');
  st.textContent='Loading…'; res.innerHTML='';
  const sr=await fetch(`${API}/sync/list`);const saved=await sr.json();
  if(!saved.length){res.innerHTML='<div class="wbox">No imported rugs on record yet.</div>';st.textContent='';return;}
  st.textContent='Fetching Alrug inventory…';
  const cols={};saved.forEach(r=>{const c=r.collection||'area-rugs';if(!cols[c])cols[c]=[];cols[c].push(r);});
  const alrug={};
  for(const c in cols){
    let page=1,go=true;
    while(go){
      try{const r=await fetch(`${API}/products?domain=www.alrug.com&collection=${encodeURIComponent(c)}&page=${page}`);const d=await r.json();
        if(d.products&&d.products.length){d.products.forEach(p=>{const av=p.variants&&p.variants.some(v=>v.available!==false);alrug[p.id]={av};alrug[p.handle]={av};});go=d.products.length===250?(page++,true):false;}else go=false;
      }catch(e){go=false;}
    }
  }
  const missing=[],soldOut=[],ok=[];
  saved.forEach(r=>{const m=alrug[r.alrug_id]||alrug[r.alrug_handle];if(!m)missing.push(r);else if(!m.av)soldOut.push(r);else ok.push(r);});
  st.textContent=`${missing.length} removed · ${soldOut.length} sold out · ${ok.length} available`;
  function mkCard(r,bc,badge){
    const ct=(r.title||'').replace(/\s*-\s*No\.?\s*[A-Z0-9]+\s*$/i,'').trim();
    return `<div style="background:var(--white);border:1.5px solid ${bc};border-radius:10px;padding:12px 15px;display:flex;align-items:center;gap:11px;flex-wrap:wrap;margin-bottom:8px">
      <div style="flex:1;min-width:0"><div style="font-size:12px;font-weight:600">${ct.substring(0,58)} <span style="font-size:10px;padding:2px 7px;border-radius:20px;background:${bc}33;color:${bc};font-weight:700">${badge}</span></div>
      <div style="font-size:10px;color:var(--inkl);margin-top:2px">Etsy ID: ${r.etsy_listing_id} · ${r.saved_at?r.saved_at.substring(0,10):''}</div></div>
      <a href="https://www.etsy.com/your/shops/${shop||''}/tools/listings/${r.etsy_listing_id}" target="_blank" style="font-size:11px;color:var(--g);text-decoration:underline">View</a>
      <button onclick="delSync(${r.etsy_listing_id},this)" style="background:var(--red);color:#fff;border:none;border-radius:6px;padding:5px 11px;font-size:11px;font-weight:600;cursor:pointer">Delete</button>
      <button onclick="dimSync(${r.etsy_listing_id},this)" style="background:var(--sandm);color:var(--inkm);border:none;border-radius:6px;padding:5px 11px;font-size:11px;font-weight:600;cursor:pointer">Dismiss</button>
    </div>`;
  }
  let html='';
  if(missing.length){html+=`<div style="font-size:13px;font-weight:700;color:var(--red);margin-bottom:8px">🗑️ ${missing.length} removed from Alrug</div>`;missing.forEach(r=>{html+=mkCard(r,'#f5aaaa','Removed');});html+='<br>';}
  if(soldOut.length){html+=`<div style="font-size:13px;font-weight:700;color:var(--amb);margin-bottom:8px">⚠️ ${soldOut.length} sold out</div>`;soldOut.forEach(r=>{html+=mkCard(r,'#f0d080','Sold Out');});html+='<br>';}
  if(ok.length){html+=`<div style="font-size:13px;font-weight:700;color:var(--g)">✅ ${ok.length} still available</div>`;}
  res.innerHTML=html;
}
async function delSync(id,btn){
  if(!confirm(`Delete Etsy listing ${id}?`))return;
  btn.textContent='…';btn.disabled=true;
  const r=await fetch(`${API}/etsy/delete/${id}`,{method:'DELETE',headers:{'Authorization':`Bearer ${tok}`}});
  const d=await r.json();
  if(d.ok){await fetch(`${API}/sync/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({etsy_listing_id:id})});btn.closest('div[style]').style.opacity='.4';btn.textContent='Deleted';}
  else{btn.textContent='Failed';btn.disabled=false;}
}
async function dimSync(id,btn){
  await fetch(`${API}/sync/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({etsy_listing_id:id})});
  btn.closest('div[style]').style.opacity='.4';btn.textContent='Dismissed';
}

// ── Strategy panel ──
let strategyListings = [], stratSel = new Set();

async function loadStrategyListings() {
  const grid = document.getElementById('strategyGrid');
  grid.innerHTML = '<div style="color:var(--inkl);font-size:13px">Loading…</div>';
  document.getElementById('strategyActions').style.display = 'none';

  try {
    const r = await fetch(`${API}/sync/list`);
    strategyListings = await r.json();
  } catch(e) { grid.innerHTML = '<div style="color:var(--red)">Failed to load sync list</div>'; return; }

  if (!strategyListings.length) {
    grid.innerHTML = '<div class="wbox">No imported listings yet. Import some rugs first.</div>';
    return;
  }

  // Count by month
  const now = Date.now();
  const counts = {m1:0,m2:0,m3:0,m4:0};
  strategyListings.forEach(r => {
    const age = (now - new Date(r.saved_at||0).getTime()) / (1000*60*60*24*30);
    if (age >= 3) counts.m4++;
    else if (age >= 2) counts.m3++;
    else if (age >= 1) counts.m2++;
    else counts.m1++;
  });
  ['m1','m2','m3','m4'].forEach(m => {
    const el = document.getElementById(m+'count');
    if (el) el.textContent = counts[m];
  });

  stratSel = new Set(strategyListings.map(r => r.etsy_listing_id));
  renderStrategyGrid();
  document.getElementById('strategyActions').style.display = '';
  updateStrategyCnt();
}

function renderStrategyGrid() {
  const grid = document.getElementById('strategyGrid');
  grid.innerHTML = '';
  strategyListings.forEach(r => {
    const chk = stratSel.has(r.etsy_listing_id);
    const age = Math.round((Date.now() - new Date(r.saved_at||0).getTime()) / (1000*60*60*24));
    const isDead = age > 60;
    const card = document.createElement('div');
    card.style.cssText = `display:flex;align-items:center;gap:10px;padding:10px 13px;background:var(--white);border:1.5px solid ${chk?'var(--g)':'var(--sandm)'};border-radius:9px;margin-bottom:7px;cursor:pointer;transition:.15s`;
    card.onclick = () => toggleStratSel(r.etsy_listing_id, card);
    const ct = (r.title||'').replace(/\s*-\s*No\.?\s*[A-Z0-9]+\s*$/i,'').trim();
    card.innerHTML = `
      <input type="checkbox" ${chk?'checked':''} style="flex-shrink:0;width:15px;height:15px;accent-color:var(--g)" onclick="event.stopPropagation()">
      <div style="flex:1;min-width:0">
        <div style="font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${ct.substring(0,70)}</div>
        <div style="font-size:10px;color:var(--inkl);margin-top:2px">
          ID: ${r.etsy_listing_id} · ${age} days ago · $${r.price||'?'}
          ${isDead?'<span style="color:var(--red);font-weight:700;margin-left:6px">⚠ Dead — consider relisting</span>':''}
        </div>
      </div>
      <a href="https://www.etsy.com/your/shops/${shop||''}/tools/listings/${r.etsy_listing_id}/edit" target="_blank" onclick="event.stopPropagation()" style="font-size:11px;color:var(--g);text-decoration:none;white-space:nowrap">Edit ↗</a>
    `;
    grid.appendChild(card);
  });
}

function toggleStratSel(id, card) {
  if (stratSel.has(id)) { stratSel.delete(id); card.style.borderColor='var(--sandm)'; card.querySelector('input').checked=false; }
  else { stratSel.add(id); card.style.borderColor='var(--g)'; card.querySelector('input').checked=true; }
  updateStrategyCnt();
}
function selAllStrategy()  { strategyListings.forEach(r=>stratSel.add(r.etsy_listing_id)); renderStrategyGrid(); updateStrategyCnt(); }
function selNoneStrategy() { stratSel.clear(); renderStrategyGrid(); updateStrategyCnt(); }
function updateStrategyCnt() { document.getElementById('strategyCnt').textContent = stratSel.size + ' selected'; }

function sclog(msg, type='log') {
  const c = document.getElementById('strategyCon');
  const d = document.createElement('div');
  d.className = type;
  d.textContent = `[${new Date().toLocaleTimeString('en-US',{hour12:false})}] ${msg}`;
  c.appendChild(d); c.scrollTop = c.scrollHeight;
}

async function runBulkUpdate() {
  if (!stratSel.size) { alert('Select listings to update.'); return; }
  if (!tok) { alert('Connect to Etsy first (Step 1).'); return; }

  const toUpdate = strategyListings.filter(r => stratSel.has(r.etsy_listing_id));
  sclog(`Starting bulk update on ${toUpdate.length} listings…`, 'info');

  const AUTH = {'Content-Type':'application/json','Authorization':`Bearer ${tok}`};
  let done=0, failed=0;

  for (const r of toUpdate) {
    const lid = r.etsy_listing_id;
    const ct  = (r.title||'').replace(/\s*-\s*No\.?\s*[A-Z0-9]+\s*$/i,'').trim();
    // Build a fake product object from sync data for our SEO functions
    const fakeProduct = {
      title: r.title || ct,
      tags:  r.collection || '',
      body_html: '',
      variants: [{price: r.price||'0'}],
      images: [],
      handle: r.alrug_handle || ''
    };

    try {
      const newTitle = seoTitle(fakeProduct, ct).substring(0, 140);
      const newTags  = tags(fakeProduct);

      const ur = await fetch(`${API}/etsy/update/${lid}`, {
        method: 'PATCH',
        headers: AUTH,
        body: JSON.stringify({ title: newTitle, tags: newTags })
      });
      const ud = await ur.json();
      if (ur.ok) {
        done++;
        sclog(`  ✅ ${lid}: "${newTitle.substring(0,50)}…"`, 'log');
      } else {
        failed++;
        sclog(`  ❌ ${lid}: ${ud.error||ur.status}`, 'err');
      }
    } catch(e) {
      failed++;
      sclog(`  ❌ ${lid}: ${e.message}`, 'err');
    }
    await sleep(400);
  }
  sclog(`Done — ${done} updated, ${failed} failed`, 'info');
}


async function loadImported() {
  const st  = document.getElementById('syncSt');
  const res = document.getElementById('syncRes');
  st.textContent = 'Loading…'; res.innerHTML = '';
  document.getElementById('syncSummary').style.display = 'none';

  // Load sync list
  const sr = await fetch(`${API}/sync/list`);
  const saved = await sr.json();
  if (!saved.length) {
    res.innerHTML = '<div class="wbox">No imported rugs on record.</div>';
    st.textContent = ''; return;
  }

  st.textContent = `Checking Etsy status for ${saved.length} rugs…`;

  // Check each listing status on Etsy
  const AUTH = {'Authorization': `Bearer ${tok}`};
  let active=0, draft=0, unknown=0;
  let html = '';

  for (const r of saved) {
    const lid = r.etsy_listing_id;
    const ct  = (r.title||'').replace(/\s*-\s*No\.?\s*[A-Z0-9]+\s*$/i,'').trim();
    let state = 'unknown', stateClr = '#8a7560', stateLbl = '❓ Unknown';

    try {
      const er = await fetch(`${API}/etsy/listing/${lid}`, {headers: AUTH});
      if (er.ok) {
        const ed = await er.json();
        state = ed.state || 'unknown';
        if (state === 'active')  { stateClr='#2d5a3d'; stateLbl='🟢 Active';  active++; }
        else if (state === 'draft') { stateClr='#c8860a'; stateLbl='📝 Draft'; draft++;  }
        else                     { stateClr='#8a7560'; stateLbl='❓ '+state;  unknown++; }
      } else {
        stateLbl = '❓ Not found on Etsy'; unknown++;
      }
    } catch(e) { unknown++; }

    const savedDate = r.saved_at ? r.saved_at.substring(0,10) : '—';
    const stk = (r.alrug_handle||'').match(/no-([a-z0-9]+)$/i)?.[1]?.toUpperCase() || '—';

    html += `<div style="background:var(--white);border:1.5px solid var(--sandm);border-radius:10px;padding:12px 15px;margin-bottom:9px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
      <div style="flex:1;min-width:0">
        <div style="font-size:12px;font-weight:600;margin-bottom:3px">${ct.substring(0,65)}</div>
        <div style="font-size:10px;color:var(--inkl)">
          SKU: ${stk} · Etsy ID: ${lid} · Imported: ${savedDate} · $${r.price||'?'}
        </div>
      </div>
      <span style="background:${stateClr}22;color:${stateClr};padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;white-space:nowrap">${stateLbl}</span>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        ${state === 'active' ? `<a href="https://www.etsy.com/your/shops/${shop}/tools/listings/${lid}" target="_blank" style="font-size:11px;padding:5px 10px;border-radius:6px;background:var(--g);color:#fff;text-decoration:none;font-weight:600">View ↗</a>` : ''}
        ${state === 'draft'  ? `<button onclick="deleteFromEtsy(${lid},this)" style="font-size:11px;padding:5px 10px;border-radius:6px;background:#b02020;color:#fff;border:none;cursor:pointer;font-weight:600">Delete Draft</button>` : ''}
        <button onclick="removeFromTracker(${lid},this)" style="font-size:11px;padding:5px 10px;border-radius:6px;background:var(--sandm);color:var(--ink);border:none;cursor:pointer;font-weight:600">Remove from Tracker</button>
        <a href="https://www.alrug.com/products/${r.alrug_handle||''}" target="_blank" style="font-size:11px;padding:5px 10px;border-radius:6px;background:var(--sandm);color:var(--ink);text-decoration:none;font-weight:600">Alrug ↗</a>
      </div>
    </div>`;
  }

  document.getElementById('scActive').textContent  = active;
  document.getElementById('scDraft').textContent   = draft;
  document.getElementById('scUnknown').textContent = unknown;
  document.getElementById('syncSummary').style.display = '';
  res.innerHTML = html;
  st.textContent = `${saved.length} rugs · ${active} active · ${draft} drafts · ${unknown} unknown`;
}

async function deleteFromEtsy(lid, btn) {
  if (!confirm(`Delete Etsy listing ${lid} permanently?`)) return;
  btn.textContent = '…'; btn.disabled = true;
  const r = await fetch(`${API}/etsy/delete/${lid}`, {method:'DELETE', headers:{'Authorization':`Bearer ${tok}`}});
  if (r.ok) {
    // Also remove from tracker automatically
    await fetch(`${API}/sync/delete`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({etsy_listing_id:lid})});
    btn.closest('div[style]').remove();
    // Reload to update counts
    await loadImported();
  } else {
    btn.textContent = 'Failed';
    btn.disabled = false;
  }
}

async function removeFromTracker(lid, btn) {
  if (!confirm(`Remove listing ${lid} from sync tracker?\nThis lets you reimport it fresh.`)) return;
  btn.textContent = '…'; btn.disabled = true;
  await fetch(`${API}/sync/delete`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({etsy_listing_id:lid})});
  btn.textContent = 'Removed ✓';
  btn.style.background = '#888';
  // Update counts
  loadImported();
}


updateSB();

// Auto-connect on page load using saved token
(async function autoConnect(){
  try{
    const r = await fetch("/api/auth/status");
    const d = await r.json();
    if(d.connected && d.access_token){
      tok = d.access_token;
      if(d.client_id) apiK = d.client_id;
      if(d.shop_name){ shop = d.shop_name; }
      document.getElementById("sDot").classList.add("on");
      document.getElementById("sTxt").textContent = d.shop_name || "Connected";
      document.getElementById("sChip").textContent = d.shop_name || "Connected";
      showP(2);
      console.log("Auto-connected:", d.shop_name);
    }
  }catch(e){ console.log("Auto-connect failed:", e.message); }
})();


async function loadListings(){
  const st=document.getElementById("listingsSt");
  const grid=document.getElementById("listingsGrid");
  const empty=document.getElementById("listingsEmpty");
  const loaded=document.getElementById("listingsLoaded");
  if(empty) empty.style.display="none";
  if(loaded) loaded.style.display="block";
  const btn=document.querySelector("#p7 .btn-p");
  if(btn){btn.disabled=true;btn.textContent="Syncing...";}
  st.textContent="Syncing inventory...";
  grid.innerHTML="";
  if(btn){btn.textContent="Waiting for Etsy...";}
  st.textContent="Waiting for Etsy to sync...";
  await new Promise(r=>setTimeout(r,5000));
  if(btn){btn.textContent="Waiting for Etsy...";}
  st.textContent="Waiting for Etsy to sync...";
  await new Promise(r=>setTimeout(r,5000));
  try{ await fetch(`${API}/inventory/rebuild`,{method:"POST"}); }catch(e){}
  if(btn){btn.textContent="Loading...";}
  st.textContent="Loading listings...";
  try{
    const r=await fetch("/api/inventory/list");
    const d=await r.json();
    const rows=d.rows||[];
    st.textContent=rows.length+" listings";
    if(!rows.length){grid.innerHTML="<div class=wbox>No listings found. Run build inventory first.</div>";return;}
    rows.forEach(row=>{
      const state=row.etsy_state||"unknown";
      const sbg=state==="active"?"#b2d8c0":"#f0d080";
      const sclr=state==="active"?"#1a4a2a":"#7a5500";
      const slbl=state==="active"?"ACTIVE":"DRAFT";
      const editUrl="https://www.etsy.com/your/shops/me/listing-editor/edit/"+row.etsy_listing_id;
      grid.innerHTML+=`<div style="border:1.5px solid var(--sandm);border-radius:9px;padding:13px 15px;margin-bottom:10px;background:var(--white)"><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><span style="font-size:13px;font-weight:700;flex:1">${(row.etsy_title||"").substring(0,70)}</span><span style="background:${sbg};color:${sclr};padding:1px 8px;border-radius:10px;font-size:10px;font-weight:700">${slbl}</span></div><div style="font-size:11px;color:var(--inkl);margin-bottom:8px">SKU: <strong>${row.sku||"—"}</strong> &nbsp;·&nbsp; Etsy ID: ${row.etsy_listing_id} &nbsp;·&nbsp; Price: $${row.etsy_price_usd||"—"} &nbsp;·&nbsp; Views: ${row.etsy_views||0} &nbsp;·&nbsp; Favs: ${row.etsy_favorites||0}</div><a href="${editUrl}" target="_blank" style="display:inline-block;padding:5px 13px;background:var(--g);color:#fff;border-radius:6px;font-size:11px;font-weight:700;text-decoration:none">Edit on Etsy</a>${row.alrug_handle?`<a href="https://www.alrug.com/products/${row.alrug_handle}" target="_blank" style="display:inline-block;padding:5px 13px;background:var(--sandm);color:var(--ink);border-radius:6px;font-size:11px;font-weight:700;text-decoration:none;margin-left:6px;border:1.5px solid var(--sandd)">${row.sku||"Alrug"} -></a>`:""}</div>`;
    });
  }catch(e){st.textContent="Error";grid.innerHTML="<div class=wbox>"+e.message+"</div>";}
  if(btn){btn.disabled=false;btn.textContent="🔄 Refresh Listings";}
}

async function doLogout(){
  try{ await fetch("/auth/logout",{method:"POST",credentials:"include"});}catch(e){}
  document.cookie="auth_token=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/";
  window.location.href="/login";
}
function lwClear(){
  document.getElementById('lwError').style.display='none';
  document.getElementById('lwResult').style.display='none';
  document.getElementById('lwCopied').style.display='none';
}

function lwExtractHandle(input){
  input = input.trim();
  const m = input.match(/\/products\/([^/?#]+)/);
  if(m) return m[1];
  if(!input.includes('/')) return input;
  return input;
}

async function lwFetch(){
  const raw = document.getElementById('lwUrl').value.trim();
  if(!raw){ alert('Please paste an alrug.com product URL'); return; }
  const handle = lwExtractHandle(raw);
  const btn = document.getElementById('lwBtn');
  btn.disabled=true; btn.textContent='Fetching…';
  lwClear();
  try{
    const r = await fetch(`${API}/product?domain=www.alrug.com&handle=${encodeURIComponent(handle)}`);
    const d = await r.json();
    if(!r.ok || !d.product){ throw new Error(d.error || 'Product not found'); }
    lwRender(d.product);
  }catch(e){
    document.getElementById('lwError').textContent = '❌ ' + e.message;
    document.getElementById('lwError').style.display='block';
  }finally{
    btn.disabled=false; btn.textContent='🔍 Fetch Product';
  }
}

function lwStripHtml(html){
  return (html||'').replace(/<[^>]+>/g,' ').replace(/&amp;/g,'&').replace(/&nbsp;/g,' ').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/\s{2,}/g,' ').trim();
}

function lwRender(p){
  const title   = p.title || '';
  const bodyRaw = lwStripHtml(p.body_html || '');
  const tags    = Array.isArray(p.tags) ? p.tags : String(p.tags||'').split(',').map(s=>s.trim()).filter(Boolean);
  const price   = p.variants?.[0]?.price || '?';
  const images  = (p.images||[]).map(i=>i.src).slice(0,3);

  const prompt = `I sell handmade Oriental rugs on Etsy. Here is the product title from my supplier:

${title}

Write me a complete Etsy listing with the following:

1. A listing TITLE (max 140 characters) optimized for Etsy search, with the most important keywords first, separated by commas. Include: size, color, style/design, construction method, material, and use case.

2. A description HEADER (keyword-rich pipe-separated line that goes at the very top of the description, used for SEO).

3. A full DESCRIPTION that includes:
   - An engaging opening paragraph describing the rug and its appeal
   - A section explaining the style/design heritage and why it is special
   - A "Why You Will Love It" section explaining who it is perfect for and what decor styles it suits
   - A "Perfect For" section listing room types and use cases
   - A "Rug Specifications" section listing all specs pulled from the product title
   - An "Authenticity" section reassuring buyers this is genuinely handmade
   - A care tips section
   - A closing line inviting buyers to message with questions

4. A list of 13 ETSY TAGS, comma-separated, optimized for search traffic (Etsy allows 13 tags, max 20 characters each).

Rules:
- No em dashes anywhere
- Write naturally and warmly, not like a robot
- Every section must serve the buyer or help with SEO, nothing filler
- Focus on keywords real shoppers type: size (like 2x6, 3x5), color, style (bokhara, kilim, tribal), construction (hand knotted, flatweave), material (wool), origin (afghan, pakistani), and use case (hallway runner, bedroom rug, entryway)
- Do not use the words Iran, Persian or Persia as Etsy has banned these words`;

  document.getElementById('lwProductTitle').textContent = title;
  document.getElementById('lwPrompt').textContent = prompt;
  document.getElementById('lwResult').style.display='block';
}

async function lwCopy(){
  const text = document.getElementById('lwPrompt').textContent;
  try{
    await navigator.clipboard.writeText(text);
    document.getElementById('lwCopied').style.display='block';
    setTimeout(()=>document.getElementById('lwCopied').style.display='none', 3000);
  }catch(e){
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta);
    ta.select(); document.execCommand('copy');
    document.body.removeChild(ta);
    document.getElementById('lwCopied').style.display='block';
    setTimeout(()=>document.getElementById('lwCopied').style.display='none', 3000);
  }
}

</script>
</body>
</html>

"""

HPD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HPD → Etsy Importer</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,600;0,700;1,600&family=IBM+Plex+Sans:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {
  --clay:      #B85C38;
  --clay-lt:   #D97A52;
  --clay-dk:   #8C3E20;
  --sand:      #F5F0E8;
  --sand-mid:  #E8DFD0;
  --sand-dk:   #D4C8B4;
  --ink:       #1C1410;
  --ink-mid:   #4A3A28;
  --ink-lt:    #8A7560;
  --white:     #FFFDF9;
  --forest:    #2D5A3D;
  --red:       #B02020;
  --amber:     #C8860A;
  --r:         12px;
  --sh:        0 2px 20px rgba(28,20,16,.09);
  --sh-lg:     0 8px 40px rgba(28,20,16,.13);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'IBM Plex Sans',sans-serif;background:var(--sand);color:var(--ink);min-height:100vh}
.hdr{background:var(--ink);padding:0 36px;display:flex;align-items:center;justify-content:space-between;height:60px;position:sticky;top:0;z-index:100;border-bottom:2px solid var(--clay)}
.hdr-logo{font-family:'Playfair Display',serif;font-size:18px;color:var(--sand);display:flex;align-items:center;gap:10px}
.hdr-logo .arr{color:var(--clay-lt);font-style:italic}
.hdr-right{display:flex;align-items:center;gap:12px}
.shop-chip{background:rgba(184,92,56,.22);border:1px solid var(--clay);color:var(--clay-lt);border-radius:20px;padding:3px 12px;font-size:11px;font-weight:600;letter-spacing:.4px}
.conn-pill{display:flex;align-items:center;gap:6px;font-size:11px;color:#555}
.dot{width:7px;height:7px;border-radius:50%;background:#444}
.dot.live{background:#4CAF50;box-shadow:0 0 6px #4CAF50;animation:pulse 2s infinite}
.hdr-nav{display:flex;gap:4px}
.hdr-nav a{color:rgba(255,255,255,.4);font-size:12px;font-weight:600;text-decoration:none;padding:5px 12px;border-radius:6px;transition:all .15s}
.hdr-nav a:hover{background:rgba(255,255,255,.08);color:#fff}
.hdr-nav a.active{background:rgba(184,92,56,.25);color:var(--clay-lt)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.layout{display:grid;grid-template-columns:240px 1fr;min-height:calc(100vh - 60px)}
.sb{background:var(--ink);padding:24px 16px;border-right:1px solid rgba(255,255,255,.05);position:sticky;top:60px;height:calc(100vh - 60px);overflow-y:auto}
.sb-lbl{font-size:9px;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;color:#2E2418;margin-bottom:10px}
.sb-sec{margin-bottom:24px}
.step-nav{display:flex;flex-direction:column;gap:2px}
.step-item{display:flex;align-items:center;gap:9px;padding:8px 10px;border-radius:8px;color:#2E2418;font-size:12px;transition:all .15s}
.step-item.active{background:rgba(184,92,56,.18);color:var(--clay-lt)}
.step-num{width:20px;height:20px;border-radius:50%;background:rgba(255,255,255,.05);display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;flex-shrink:0;font-family:'IBM Plex Mono',monospace}
.step-item.active .step-num{background:var(--clay);color:#fff}
.cfg-box{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:9px;padding:10px}
.cfg-row{display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.04);font-size:10px}
.cfg-row:last-child{border:none}
.cfg-k{color:#2E2418}
.cfg-v{color:var(--sand);font-weight:600;font-family:'IBM Plex Mono',monospace;font-size:9px}
.cfg-v.g{color:#4CAF50}
.cfg-v.o{color:var(--clay-lt)}
.main{padding:32px 40px;max-width:700px}
.panel{display:none}
.panel.active{display:block;animation:fadeIn .2s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.ph{margin-bottom:22px}
.ph h2{font-family:'Playfair Display',serif;font-size:27px;margin-bottom:6px;line-height:1.2}
.ph p{font-size:13px;color:var(--ink-mid);line-height:1.65}
.field{margin-bottom:14px}
.field label{display:block;font-size:10px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:var(--ink-lt);margin-bottom:5px}
.field input,.field select{width:100%;padding:10px 13px;border:1.5px solid var(--sand-dk);border-radius:8px;font-family:'IBM Plex Sans',sans-serif;font-size:14px;background:var(--white);color:var(--ink);transition:border-color .18s,box-shadow .18s}
.field input:focus,.field select:focus{outline:none;border-color:var(--clay);box-shadow:0 0 0 3px rgba(184,92,56,.10)}
.field input::placeholder{color:#C0B4A4}
.field .hint{font-size:11px;color:var(--ink-lt);margin-top:4px;line-height:1.5}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.row3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
.card{background:var(--white);border:1.5px solid var(--sand-mid);border-radius:var(--r);padding:20px;margin-bottom:16px;box-shadow:var(--sh)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:11px 24px;border-radius:8px;font-family:'IBM Plex Sans',sans-serif;font-size:14px;font-weight:600;border:none;cursor:pointer;transition:all .18s;width:100%}
.btn-primary{background:var(--clay);color:#fff}
.btn-primary:hover:not(:disabled){background:var(--clay-dk);transform:translateY(-1px);box-shadow:0 6px 18px rgba(184,92,56,.3)}
.btn-primary:disabled{background:var(--sand-dk);color:var(--ink-lt);cursor:not-allowed;transform:none;box-shadow:none}
.btn-outline{background:transparent;color:var(--clay);border:1.5px solid var(--clay);width:auto;padding:8px 16px;font-size:13px}
.btn-outline:hover{background:rgba(184,92,56,.06)}
.btn-sm{width:auto;padding:8px 16px;font-size:12px}
.preset-row{display:flex;flex-wrap:wrap;gap:5px;margin-top:6px}
.preset{padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;cursor:pointer;background:var(--sand-mid);color:var(--ink-mid);border:1.5px solid var(--sand-dk);transition:all .13s;font-family:'IBM Plex Sans',sans-serif;line-height:1.6}
.preset:hover{background:rgba(184,92,56,.12);border-color:var(--clay);color:var(--clay-dk)}
.preset.active{background:var(--clay);border-color:var(--clay);color:#fff}
.info-box{background:#F2F8F4;border:1.5px solid #B2D8C0;border-radius:9px;padding:14px 16px;margin-bottom:16px}
.info-box-title{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.9px;color:var(--forest);margin-bottom:8px}
.info-row{display:flex;gap:9px;font-size:12px;color:var(--ink-mid);padding:2px 0;line-height:1.55}
.auth-tab.active{background:var(--clay);color:#fff}
.auth-tab:not(.active):hover{background:var(--sand)}
.code-box{background:var(--ink);color:#88ff99;border-radius:7px;padding:10px 13px;font-family:'IBM Plex Mono',monospace;font-size:10px;word-break:break-all;line-height:1.65;margin-bottom:12px}
.url-highlight{background:#FFF3CD;border-radius:7px;padding:9px 12px;font-size:12px;color:#7B4A00;margin-top:8px;line-height:1.6}
.oauth-box{background:#FDF8F2;border:1.5px dashed rgba(184,92,56,.3);border-radius:10px;padding:18px;margin-bottom:14px}
.console{background:#0D1117;border-radius:10px;padding:13px 15px;font-family:'IBM Plex Mono',monospace;font-size:11px;min-height:220px;max-height:320px;overflow-y:auto;margin-bottom:14px;line-height:1.85;border:1px solid rgba(255,255,255,.06)}
.console .log{color:#88ff99}
.console .err{color:#ff7070}
.console .info{color:#79b8ff}
.console .warn{color:#ffd060}
.console .dim{color:#252D3A}
.prog-wrap{margin-bottom:16px}
.prog-meta{display:flex;justify-content:space-between;font-size:12px;font-weight:600;color:var(--ink-mid);margin-bottom:6px}
.prog-track{background:var(--sand-mid);border-radius:99px;height:8px;overflow:hidden}
.prog-fill{height:100%;background:linear-gradient(90deg,var(--clay),#E8905A);border-radius:99px;width:0%;transition:width .45s ease}
.sum-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px}
.sum-box{background:var(--white);border:1.5px solid var(--sand-mid);border-radius:10px;padding:14px 10px;text-align:center;box-shadow:var(--sh)}
.sum-num{font-family:'Playfair Display',serif;font-size:30px;line-height:1;margin-bottom:3px}
.sum-lbl{font-size:9px;color:var(--ink-lt);font-weight:700;text-transform:uppercase;letter-spacing:.6px}
.sum-num.g{color:var(--forest)}
.sum-num.r{color:var(--red)}
.sum-num.o{color:var(--amber)}
.results-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(175px,1fr));gap:11px}
.r-card{background:var(--white);border:1.5px solid var(--sand-mid);border-radius:10px;overflow:hidden;transition:all .18s}
.r-card:hover{transform:translateY(-3px);box-shadow:var(--sh-lg)}
.r-card.success{border-color:#9DD4B3}
.r-card.error{border-color:#F5AAAA}
.r-card.skipped{opacity:.5}
.r-img{width:100%;height:115px;object-fit:cover;background:var(--sand-mid);display:block}
.r-body{padding:9px}
.r-name{font-size:11px;font-weight:600;line-height:1.35;margin-bottom:5px}
.r-prices{display:flex;gap:6px;align-items:center;margin-bottom:4px}
.p-orig{font-size:10px;color:var(--ink-lt);text-decoration:line-through}
.p-etsy{font-size:12px;font-weight:700;color:var(--clay)}
.r-meta{font-size:10px;color:var(--ink-lt);line-height:1.4;margin-bottom:5px}
.r-badge{display:inline-flex;align-items:center;gap:4px;font-size:9px;font-weight:700;padding:3px 7px;border-radius:20px;text-transform:uppercase;letter-spacing:.5px}
.b-draft{background:#E6F4EE;color:var(--forest)}
.b-error{background:#FDECEA;color:var(--red)}
.b-skip{background:#F0EBE1;color:var(--ink-lt)}
.r-link{display:inline-block;font-size:10px;color:var(--clay);text-decoration:underline;margin-top:4px}
::-webkit-scrollbar{width:5px}
::-webkit-scrollbar-thumb{background:rgba(184,92,56,.2);border-radius:3px}
</style>
</head>
<body>

<header class="hdr">
  <div class="hdr-logo">HPD <span class="arr">→</span> Etsy</div>
  <nav class="hdr-nav">
    <a href="http://localhost:8080/alrug">🪵 Alrug</a>
    <a href="http://localhost:8080/hpd" class="active">🪟 HPD</a>
  </nav>
  <div class="hdr-right">
    <div class="conn-pill"><div class="dot" id="statusDot"></div><span id="statusText">Not connected</span></div>
    <div class="shop-chip" id="shopChip">—</div>
  </div>
</header>

<div class="layout">
  <aside class="sb">
    <div class="sb-sec">
      <div class="sb-lbl">Steps</div>
      <nav class="step-nav">
        <div class="step-item active" id="nav1"><div class="step-num">1</div>Connect Etsy</div>
        <div class="step-item"        id="nav2"><div class="step-num">2</div>Configure</div>
        <div class="step-item"        id="nav3"><div class="step-num">3</div>Importing</div>
        <div class="step-item"        id="nav4"><div class="step-num">4</div>Review</div>
      </nav>
    </div>
    <div class="sb-sec">
      <div class="sb-lbl">Settings</div>
      <div class="cfg-box">
        <div class="cfg-row"><span class="cfg-k">Collection</span><span class="cfg-v o">BOGO</span></div>
        <div class="cfg-row"><span class="cfg-k">Max Price</span><span class="cfg-v" id="cfgMax">$200</span></div>
        <div class="cfg-row"><span class="cfg-k">Markup</span><span class="cfg-v" id="cfgMarkup">25%</span></div>
        <div class="cfg-row"><span class="cfg-k">Category</span><span class="cfg-v g">Curtains ✓</span></div>
        <div class="cfg-row"><span class="cfg-k">Status</span><span class="cfg-v o">Draft</span></div>
        <div class="cfg-row"><span class="cfg-k">Size Variants</span><span class="cfg-v g">Auto ✓</span></div>
      </div>
    </div>
    <div class="sb-sec">
      <div class="sb-lbl">Run Stats</div>
      <div class="cfg-box">
        <div class="cfg-row"><span class="cfg-k">Fetched</span><span class="cfg-v"   id="sTotal">—</span></div>
        <div class="cfg-row"><span class="cfg-k">Drafted</span><span class="cfg-v g" id="sDrafted">—</span></div>
        <div class="cfg-row"><span class="cfg-k">Skipped</span><span class="cfg-v"   id="sSkipped">—</span></div>
        <div class="cfg-row"><span class="cfg-k">Errors</span><span class="cfg-v"    id="sErrors">—</span></div>
      </div>
    </div>
  </aside>

  <main class="main">

    <!-- ══ PANEL 1: CONNECT ══ -->
    <div class="panel active" id="panel1">
      <div class="ph">
        <h2>Connect to Etsy</h2>
        <p>Enter your credentials, generate the auth URL, grant access, then paste the code back.</p>
      </div>
      <div class="card">
        <div class="row3">
          <div class="field">
            <label>API Keystring</label>
            <input type="text" id="oauthApiKey" value="YOUR_ETSY_API_KEY" />
          </div>
          <div class="field">
            <label>Shared Secret</label>
            <input type="password" id="oauthSecret" value="" />
          </div>
          <div class="field">
            <label>Shop Name</label>
            <input type="text" id="oauthShopName" value="" />
          </div>
        </div>
        <button class="btn btn-primary" style="margin-bottom:12px" onclick="startOAuth()">🔐 Generate Auth URL</button>
        <div id="oauthStep2" style="display:none">
          <div class="field">
            <label>Authorization URL</label>
            <div class="code-box" id="oauthUrl"></div>
            <button class="btn btn-outline" style="margin-top:8px;width:auto" onclick="openOAuth()">🌐 Open Authorization Page</button>
          </div>
          <div class="field" style="margin-top:12px">
            <label>Paste Code from Redirect URL</label>
            <input type="text" id="oauthCode" placeholder="Paste the code from the redirect URL…" />
            <div class="hint">Stop Apache briefly, grant access, copy value after <code>?code=</code> and before <code>&state=</code></div>
          </div>
          <button class="btn btn-primary" onclick="exchangeCode()">✓ Exchange Code &amp; Connect</button>
        </div>
      </div>
    </div>

    <!-- ══ PANEL 2: CONFIGURE ══ -->
    <div class="panel" id="panel2">
      <div class="ph">
        <h2>Configure Import</h2>
        <p>HPD imports from the Buy One Get One Free collection. Set your price cap and markup.</p>
      </div>
      <div class="card">
        <div class="row3">
          <div class="field">
            <label>Max Source Price ($)</label>
            <input type="number" id="maxPrice" value="200" min="1" oninput="updateSidebar()" />
            <div class="preset-row" id="maxChips">
              <button class="preset"        onclick="setPreset('maxPrice','maxChips',this,100)">$100</button>
              <button class="preset active" onclick="setPreset('maxPrice','maxChips',this,200)">$200</button>
              <button class="preset"        onclick="setPreset('maxPrice','maxChips',this,300)">$300</button>
              <button class="preset"        onclick="setPreset('maxPrice','maxChips',this,9999)">Any</button>
            </div>
          </div>
          <div class="field">
            <label>Markup (%)</label>
            <input type="number" id="markup" value="25" min="1" max="999" oninput="updateSidebar()" />
            <div class="preset-row" id="markupChips">
              <button class="preset"        onclick="setPreset('markup','markupChips',this,10)">10%</button>
              <button class="preset"        onclick="setPreset('markup','markupChips',this,20)">20%</button>
              <button class="preset active" onclick="setPreset('markup','markupChips',this,25)">25%</button>
              <button class="preset"        onclick="setPreset('markup','markupChips',this,30)">30%</button>
              <button class="preset"        onclick="setPreset('markup','markupChips',this,50)">50%</button>
            </div>
          </div>
          <div class="field">
            <label>Batch Size</label>
            <select id="batch">
              <option value="2" selected>2 — test run</option>
              <option value="5">5 listings</option>
              <option value="10">10 listings</option>
              <option value="25">25 listings</option>
              <option value="9999">All eligible</option>
            </select>
          </div>
        </div>
      </div>
      <div class="info-box">
        <div class="info-box-title">✅ Every HPD draft includes</div>
        <div class="info-row"><span>📐</span>All panel sizes as Etsy Dimensions — price varies by size</div>
        <div class="info-row"><span>🖼️</span>Up to 6 product photos from HPD</div>
        <div class="info-row"><span>🏷️</span>13 SEO tags — curtains, drapes, faux linen + color tags</div>
        <div class="info-row"><span>🗂️</span>Category: Curtains &amp; Window Treatments → Curtains (ID 2182)</div>
        <div class="info-row"><span>🧵</span>Materials: polyester, faux linen</div>
        <div class="info-row"><span>🚚</span>Free shipping · Qty 999 per size · Saved as Draft</div>
      </div>
      <button class="btn btn-primary" onclick="goToImport()">🚀 Start Import</button>
    </div>

    <!-- ══ PANEL 3: IMPORTING ══ -->
    <div class="panel" id="panel3">
      <div class="ph">
        <h2>Importing…</h2>
        <p>Creating draft listings in your Etsy shop. Don't close this tab.</p>
      </div>
      <button class="btn btn-outline btn-sm" style="margin-bottom:16px" onclick="showPanel(2)">← Back to Configure</button>
      <div class="prog-wrap">
        <div class="prog-meta"><span id="progText">Initializing…</span><span id="progPct">0%</span></div>
        <div class="prog-track"><div class="prog-fill" id="progFill"></div></div>
      </div>
      <div class="console" id="console"><div class="dim">// Ready…</div></div>
      <div class="results-grid" id="resultsGrid"></div>
    </div>

    <!-- ══ PANEL 4: REVIEW ══ -->
    <div class="panel" id="panel4">
      <div class="ph">
        <h2>Import Complete 🎉</h2>
        <p>All successful listings are saved as <strong>Drafts</strong> in your Etsy shop.</p>
      </div>
      <div class="sum-grid">
        <div class="sum-box"><div class="sum-num"   id="sumTotal">0</div>  <div class="sum-lbl">Fetched</div></div>
        <div class="sum-box"><div class="sum-num g" id="sumDrafted">0</div><div class="sum-lbl">Drafted ✓</div></div>
        <div class="sum-box"><div class="sum-num o" id="sumSkipped">0</div><div class="sum-lbl">Skipped</div></div>
        <div class="sum-box"><div class="sum-num r" id="sumErrors">0</div> <div class="sum-lbl">Errors</div></div>
      </div>
      <div style="display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap">
        <a id="etsyDraftsLink" href="#" target="_blank" class="btn btn-primary btn-sm" style="display:inline-flex">View Drafts in Etsy →</a>
        <button class="btn btn-outline btn-sm" onclick="showPanel(2)">← Import More</button>
      </div>
      <div class="results-grid" id="resultsGrid2"></div>
    </div>

  </main>
</div>

<script>
const API = '/api';
let accessToken='', apiKeyVal='', shopNameVal='', codeVerifier='', pkceState='';
let stats={total:0,drafted:0,skipped:0,errors:0};

function showPanel(n) {
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.getElementById('panel'+n).classList.add('active');
  document.querySelectorAll('.step-item').forEach((el,i)=>el.classList.toggle('active',i+1===n));
}
function updateSidebar() {
  document.getElementById('cfgMax').textContent    = '$'+(document.getElementById('maxPrice')?.value||200);
  document.getElementById('cfgMarkup').textContent = (document.getElementById('markup')?.value||25)+'%';
}
function setPreset(inputId,chipsId,btn,val) {
  document.getElementById(inputId).value=val;
  document.querySelectorAll('#'+chipsId+' .preset').forEach(c=>c.classList.remove('active'));
  btn.classList.add('active'); updateSidebar();
}


function b64url(buf){return btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'');}
async function genPKCE(){
  const arr=new Uint8Array(32);crypto.getRandomValues(arr);codeVerifier=b64url(arr);
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(codeVerifier));return b64url(digest);
}
async function startOAuth() {
  apiKeyVal   = document.getElementById('oauthApiKey').value.trim();
  const secret = document.getElementById('oauthSecret').value.trim();
  shopNameVal = document.getElementById('oauthShopName').value.trim().toLowerCase().replace(/\s+/g,'');
  if (!apiKeyVal || !secret || !shopNameVal) { alert('Fill in all three fields.'); return; }
  const challenge = await genPKCE();
  pkceState = b64url(crypto.getRandomValues(new Uint8Array(8)));
  const url = `https://www.etsy.com/oauth/connect?response_type=code`
    + `&redirect_uri=${encodeURIComponent(window.location.origin)}`
    + `&scope=${encodeURIComponent('listings_w listings_r listings_d shops_r')}`
    + `&client_id=${apiKeyVal}&state=${pkceState}`
    + `&code_challenge=${challenge}&code_challenge_method=S256`;
  document.getElementById('oauthUrl').textContent = url;
  document.getElementById('oauthStep2').style.display = '';
}
function openOAuth(){window.open(document.getElementById('oauthUrl').textContent,'_blank');}
async function exchangeCode(){
  const code=document.getElementById('oauthCode').value.trim();
  if(!code){alert('Paste the code first.');return;}
  try{
    const r=await fetch(`${API}/oauth/token`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_id:apiKeyVal,redirect_uri:window.location.origin,code,code_verifier:codeVerifier})});
    const d=await r.json();
    if(d.access_token){accessToken=d.access_token;markConnected();showPanel(2);}
    else alert('Token exchange failed: '+(d.error_description||JSON.stringify(d)));
  }catch(e){alert('Error: '+e.message);}
}
function markConnected(){
  document.getElementById('statusDot').className='dot live';
  document.getElementById('statusText').textContent='Connected ✓';
  document.getElementById('shopChip').textContent=shopNameVal;
  document.getElementById('etsyDraftsLink').href=`https://www.etsy.com/your/shops/${shopNameVal}/tools/listings?status=draft`;
}

function clog(type,msg){
  const c=document.getElementById('console');
  const d=document.createElement('div');d.className=type;
  d.textContent=`[${new Date().toLocaleTimeString('en-US',{hour12:false})}] ${msg}`;
  c.appendChild(d);c.scrollTop=c.scrollHeight;
  document.getElementById('sDrafted').textContent=stats.drafted;
  document.getElementById('sSkipped').textContent=stats.skipped;
  document.getElementById('sErrors').textContent=stats.errors;
}
function setProgress(cur,total,label){
  const pct=total>0?Math.round((cur/total)*100):0;
  document.getElementById('progFill').style.width=pct+'%';
  document.getElementById('progPct').textContent=pct+'%';
  document.getElementById('progText').textContent=label||`${cur} of ${total}`;
}
function resetStats(){stats={total:0,drafted:0,skipped:0,errors:0};['sTotal','sDrafted','sSkipped','sErrors'].forEach(id=>document.getElementById(id).textContent='—');}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

function hpdDescription(product,sizeVariants){
  const NL=String.fromCharCode(10);
  const raw=(product.body_html||'').replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim();
  const sizes=sizeVariants.map(s=>s.size+' - $'+s.etsyPrice.toFixed(2)).join(NL);
  return [product.title,'',raw||'Premium quality window curtain.','','AVAILABLE SIZES & PRICES:',sizes,'','MATERIAL & CARE:','Textured Faux Linen | 100% Polyester','70% Room Darkening Opacity','Dry clean only','','HANGING OPTIONS:','Pole Pocket, Back Tabs, Hook Belt','','SOLD PER PANEL. Curtain hooks not included.','','FREE SHIPPING - ships within 2-3 business days.','','Questions? Message us!'].join(NL);
}
function hpdTags(product){
  const base=['curtains','drapes','window treatment','room darkening','faux linen','home decor','window curtain','panel curtain','bedroom curtain','living room','boho curtain','modern curtain','window drape'];
  const colors=['birch','oatmeal','oyster','indigo','heather','grey','green','blue','tan','mink','navy','clay','black','white','teal','gold','denim'];
  for(const w of product.title.toLowerCase().split(' ')) if(colors.includes(w)){base.unshift(w+' curtain');break;}
  return [...new Set(base)].slice(0,13).map(t=>t.substring(0,20));
}

function goToImport(){
  document.getElementById('console').innerHTML='<div class="dim">// Starting import…</div>';
  document.getElementById('resultsGrid').innerHTML='';
  document.getElementById('resultsGrid2').innerHTML='';
  resetStats();setProgress(0,1,'Initializing…');
  showPanel(3);runImport();
}

async function runImport(){
  const maxPrice=parseFloat(document.getElementById('maxPrice').value)||9999;
  const markupPct=parseFloat(document.getElementById('markup').value)||25;
  const markup=1+markupPct/100;
  const batchSize=parseInt(document.getElementById('batch').value);

  clog('info','📦 Fetching HPD BOGO collection…');
  let products=[],page=1,fetching=true;
  while(fetching){
    try{
      const r=await fetch(`${API}/products?domain=www.halfpricedrapes.com&collection=buy-one-get-one-free&page=${page}`);
      if(!r.ok) throw new Error(`HTTP ${r.status}`);
      const d=await r.json();
      if(d.products?.length){products=products.concat(d.products);clog('log',`  Page ${page}: ${d.products.length} products`);fetching=d.products.length===250?(page++,true):false;}
      else fetching=false;
    }catch(e){clog('err',`  Fetch error: ${e.message}`);fetching=false;}
  }
  if(!products.length){clog('err','❌ No products fetched.');setProgress(0,1,'❌ Failed');return;}

  const eligible=products.filter(p=>{const prices=p.variants.map(v=>parseFloat(v.price)).filter(n=>!isNaN(n));return prices.length>0&&Math.min(...prices)<=maxPrice;});
  const toProcess=eligible.slice(0,batchSize);
  stats.total=toProcess.length;
  document.getElementById('sTotal').textContent=stats.total;
  clog('info',`🔍 ${eligible.length} eligible, processing ${toProcess.length}`);

  for(let i=0;i<toProcess.length;i++){
    const product=toProcess[i];
    setProgress(i+1,toProcess.length,`${i+1}/${toProcess.length}: ${product.title.substring(0,38)}…`);

    const seen=new Set();const sizeVariants=[];
    for(const v of product.variants){
      const size=v.option1||v.title||'One Size';
      if(seen.has(size))continue;
      const orig=parseFloat(v.price);
      if(isNaN(orig)||orig>maxPrice)continue;
      seen.add(size);
      sizeVariants.push({size,origPrice:orig,etsyPrice:parseFloat((orig*markup).toFixed(2)),sku:v.sku||`${product.handle}-${size.replace(/\s+/g,'-')}`});
    }
    if(!sizeVariants.length){clog('warn',`  ⏭ Skipped (no qualifying variants): "${product.title.substring(0,40)}"`);stats.skipped++;addCard(product,'skipped',null,sizeVariants,'No qualifying variants');continue;}
    clog('info',`📝 "${product.title.substring(0,48)}" — ${sizeVariants.length} sizes from $${sizeVariants[0].etsyPrice.toFixed(2)}`);

    try{
      const body={quantity:999,title:product.title.substring(0,140),description:hpdDescription(product,sizeVariants),price:sizeVariants[0].etsyPrice,who_made:'someone_else',when_made:'made_to_order',taxonomy_id:2182,tags:hpdTags(product),materials:['polyester','faux linen'],state:'draft',type:'physical',is_personalizable:false,is_digital:false,should_auto_renew:true};
      const cResp=await fetch(`${API}/etsy/create`,{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${accessToken}`},body:JSON.stringify({...body,_shop:shopNameVal})});
      const listing=await cResp.json();
      if(!cResp.ok||!listing.listing_id) throw new Error(listing.error_description||listing.error||`HTTP ${cResp.status}`);
      const lid=listing.listing_id;
      clog('log',`  ✅ Draft created — ID ${lid}`);

      // Size variants
      if(sizeVariants.length>1){
        try{
          const invR=await fetch(`${API}/etsy/inventory/${lid}`,{method:'PUT',headers:{'Content-Type':'application/json','x-api-key':apiKeyVal,'Authorization':`Bearer ${accessToken}`},body:JSON.stringify({products:sizeVariants.map(sv=>({sku:sv.sku,property_values:[{property_id:200,property_name:'Dimensions',values:[sv.size]}],offerings:[{price:sv.etsyPrice,quantity:999,is_enabled:true}]})),price_on_property:[200]})});
          if(invR.ok) clog('log',`  📐 ${sizeVariants.length} size variants set`);
          else{const e2=await invR.json();clog('warn',`  ⚠️ Variants: ${e2.error_description||'error'}`);}
        }catch(ve){clog('warn',`  ⚠️ Variant error: ${ve.message}`);}
        await sleep(300);
      }

      // Photos
      const photos=(product.images||[]).slice(0,6);let photoCount=0;
      for(let pi=0;pi<photos.length;pi++){
        try{const pR=await fetch(`${API}/etsy/image/${shopNameVal}/${lid}`,{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${accessToken}`},body:JSON.stringify({url:photos[pi].src,rank:pi+1})});if(pR.ok)photoCount++;}catch(pe){}
        await sleep(150);
      }
      clog('log',`  🖼️  ${photoCount}/${photos.length} photos · 🏷️ ${hpdTags(product).length} tags`);
      stats.drafted++;addCard(product,'success',lid,sizeVariants);
    }catch(e){clog('err',`  ❌ ${product.title.substring(0,45)}: ${e.message}`);stats.errors++;addCard(product,'error',null,null,e.message);}
    await sleep(700);
  }

  setProgress(toProcess.length,toProcess.length,'✅ Import complete!');
  clog('log',`\n🎉 Done! ${stats.drafted} drafted · ${stats.skipped} skipped · ${stats.errors} errors`);
  document.getElementById('sumTotal').textContent=stats.total;
  document.getElementById('sumDrafted').textContent=stats.drafted;
  document.getElementById('sumSkipped').textContent=stats.skipped;
  document.getElementById('sumErrors').textContent=stats.errors;
  document.getElementById('resultsGrid2').innerHTML=document.getElementById('resultsGrid').innerHTML;
  await sleep(900);showPanel(4);
}

function addCard(product,status,lid,sizeVariants,err){
  const img=product.images?.[0]?.src||'';
  const minOrig=sizeVariants?.length?Math.min(...sizeVariants.map(s=>s.origPrice)):0;
  const minEtsy=sizeVariants?.length?Math.min(...sizeVariants.map(s=>s.etsyPrice)):0;
  const sizeList=sizeVariants?.map(s=>s.size).join(', ')||'';
  const badge={success:'<span class="r-badge b-draft">✓ Draft</span>',error:'<span class="r-badge b-error">✕ Error</span>',skipped:'<span class="r-badge b-skip">— Skipped</span>'}[status];
  const link=lid?`<a class="r-link" href="https://www.etsy.com/your/shops/${shopNameVal}/tools/listings/${lid}" target="_blank">View in Etsy →</a>`:'';
  const errN=err?`<div style="font-size:10px;color:var(--red);margin-top:4px">${String(err).substring(0,90)}</div>`:'';
  const card=document.createElement('div');
  card.className=`r-card ${status}`;
  card.innerHTML=`
    ${img?`<img class="r-img" src="${img}" alt="" loading="lazy">`:'<div class="r-img"></div>'}
    <div class="r-body">
      <div class="r-name">${product.title.substring(0,52)}${product.title.length>52?'…':''}</div>
      ${sizeVariants?.length?`<div class="r-prices"><span class="p-orig">$${minOrig.toFixed(2)}</span><span class="p-etsy">$${minEtsy.toFixed(2)}${sizeVariants.length>1?'+':''}</span></div><div class="r-meta">📐 ${sizeVariants.length} size${sizeVariants.length>1?'s':''}: ${sizeList.substring(0,36)}</div>`:''}
      ${badge}${errN}${link}
    </div>`;
  document.getElementById('resultsGrid').appendChild(card);
}

updateSidebar();



// ── Panel 8: Listing Writer ──────────────────────────────────────────────────
  try{ await fetch('/auth/logout', {method:'POST', credentials:'include'}); }catch(e){}
  document.cookie='auth_token=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/';
  window.location.href='/login';
}
</script>
</body>
</html>
"""



@app.route('/')
def index():
    return ALRUG_HTML, 200, {'Content-Type': 'text/html'}

@app.route('/alrug')
def alrug():
    return ALRUG_HTML, 200, {'Content-Type': 'text/html'}

@app.route('/hpd')
def hpd():
    return HPD_HTML, 200, {'Content-Type': 'text/html'}

@app.route('/etsy_importer.html')
def importer():
    return ALRUG_HTML, 200, {'Content-Type': 'text/html'}

# ── /api/ping — verify Etsy credentials ───────────────────────────────────────


@app.route("/health")
def health():
    import datetime
    def last_run(logfile):
        try:
            mtime = os.path.getmtime(logfile)
            return datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        except:
            return "never"
    return jsonify({
        "status": "ok",
        "build_last_run": last_run("/var/log/etsy_build.log"),
        "report_last_run": last_run("/var/log/etsy_report.log"),
        "alert_last_run": last_run("/var/log/etsy_alert.log"),
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    })


@app.route("/api/auth/status")
def auth_status():
    try:
        token_file = os.path.join(BASE_DIR, "etsy_token.json")
        if not os.path.exists(token_file):
            return jsonify({"connected": False})
        with open(token_file) as f:
            token_data = json.load(f)
        access_token = token_data.get("access_token", "")
        if not access_token:
            return jsonify({"connected": False})
        r = requests.get(
            f"{ETSY_BASE}/users/me",
            headers={"Authorization": f"Bearer {access_token}", "x-api-key": f"{ETSY_KEY}:{ETSY_SECRET}"},
            timeout=10
        )
        if r.ok:
            shops_r = requests.get(
                f"{ETSY_BASE}/users/me/shops",
                headers={"Authorization": f"Bearer {access_token}", "x-api-key": f"{ETSY_KEY}:{ETSY_SECRET}"},
                timeout=10
            )
            shop_name = ""
            if shops_r.ok:
                shops = shops_r.json().get("results", [])
                if shops:
                    shop_name = shops[0].get("shop_name", "")
            return jsonify({"connected": True, "access_token": access_token, "shop_name": config.SHOP_NAME, "client_id": token_data.get("client_id", ETSY_KEY)})
        return jsonify({"connected": False})
    except Exception as e:
        return jsonify({"connected": False, "error": str(e)})

@app.route('/api/ping')
def ping():
    try:
        r = requests.get(f'{ETSY_BASE}/openapi-ping', headers=ETSY_HEADERS, timeout=10)
        return jsonify({'ok': r.ok, 'status': r.status_code, 'body': r.json()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ── /api/shop/<name> — verify shop exists ─────────────────────────────────────

@app.route('/api/shop/<shop_name>')
def get_shop(shop_name):
    try:
        r = requests.get(f'{ETSY_BASE}/shops/{shop_name}', headers=ETSY_HEADERS, timeout=10)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── /api/etsy/listings — fetch listings from an Etsy shop ─────────────────────

@app.route('/api/etsy/listings')
def etsy_listings():
    shop   = request.args.get('shop', '')
    limit  = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    if not shop:
        return jsonify({'error': 'shop param required'}), 400
    try:
        # Get shop_id first
        r = requests.get(f'{ETSY_BASE}/shops/{shop}', headers=ETSY_HEADERS, timeout=15)
        if not r.ok:
            return jsonify({'error': f'Shop not found: {r.status_code}'}), r.status_code
        shop_id = r.json().get('shop_id')
        if not shop_id:
            return jsonify({'error': 'shop_id not found in response'}), 500

        # Fetch listings
        r2 = requests.get(
            f'{ETSY_BASE}/shops/{shop_id}/listings/active',
            headers=ETSY_HEADERS,
            params={'limit': limit, 'offset': offset, 'includes': 'images'},
            timeout=30
        )
        data = r2.json()
        return jsonify(data), r2.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── /api/etsy/create — create a draft listing ─────────────────────────────────

@app.route('/api/etsy/create', methods=['POST'])
def etsy_create():
    body     = request.json
    shop     = body.pop('_shop', '')
    print(f'DEBUG create called: shop={shop}, body_keys={list(body.keys())}')
    if not shop:
        return jsonify({'error': '_shop required'}), 400
    try:
        # Resolve shop name to numeric shop_id (cached)
        print(f'DEBUG shop lookup: {shop}, cached={shop in _shop_id_cache}')
        if shop not in _shop_id_cache:
            try:
                # Use OAuth token to get shop ID via /application/users/me
                sr = requests.get(f'{ETSY_BASE}/users/me', headers=write_headers(), timeout=10)
                print(f'DEBUG user response: {sr.status_code} {sr.text[:300]}')
                if not sr.ok:
                    return jsonify({'error': f'User lookup failed: {sr.status_code}'}), sr.status_code
                user_id = sr.json().get('user_id')
                # Now get shop by user_id
                sr2 = requests.get(f'{ETSY_BASE}/users/{user_id}/shops', headers=write_headers(), timeout=10)
                print(f'DEBUG shops response: {sr2.status_code} {sr2.text[:300]}')
                if not sr2.ok:
                    return jsonify({'error': f'Shops lookup failed: {sr2.status_code}'}), sr2.status_code
                shops_data = sr2.json()
                sid = shops_data.get('shop_id') or (shops_data.get('results') or [{}])[0].get('shop_id')
                _shop_id_cache[shop] = sid
            except Exception as se:
                print(f'DEBUG shop exception: {se}')
                return jsonify({'error': f'Shop lookup exception: {se}'}), 500
        shop_id = _shop_id_cache.get(shop)
        print(f'DEBUG shop_id resolved: {shop_id}')
        if not shop_id:
            return jsonify({'error': 'shop_id not found'}), 500

        # Auto-fetch shipping profile if not provided
        if 'shipping_profile_id' not in body:
            if shop_id not in _shipping_profile_cache:
                try:
                    spr = requests.get(f'{ETSY_BASE}/shops/{shop_id}/shipping-profiles',
                                       headers=write_headers(), timeout=10)
                    print(f'DEBUG shipping profiles: {spr.status_code} {spr.text[:300]}')
                    profiles = spr.json().get('results', []) if spr.ok else []
                    _shipping_profile_cache[shop_id] = profiles[0]['shipping_profile_id'] if profiles else None
                except Exception as spe:
                    print(f'DEBUG shipping exception: {spe}')
            sp_id = _shipping_profile_cache.get(shop_id)
            if sp_id:
                body['shipping_profile_id'] = sp_id
            else:
                return jsonify({'error': 'No shipping profile found. Please create one in your Etsy shop first.'}), 400

        # Auto-fetch readiness_state_id if not provided
        if 'readiness_state_id' not in body:
            if shop_id not in _readiness_cache:
                try:
                    rr = requests.get(f'{ETSY_BASE}/shops/{shop_id}/readiness-state-definitions',
                                      headers=write_headers(), params={'legacy': 'false'}, timeout=10)
                    print(f'DEBUG readiness: {rr.status_code} {rr.text[:400]}')
                    data = rr.json() if rr.ok else {}
                    profiles = data.get('results', [])
                    _readiness_cache[shop_id] = profiles[0].get('readiness_state_id') if profiles else None
                except Exception as re:
                    print(f'DEBUG readiness exception: {re}')
            rs_id = _readiness_cache.get(shop_id)
            if rs_id:
                body['readiness_state_id'] = rs_id

        # Auto-fetch and randomly assign a production partner
        if shop_id not in _production_partner_cache:
            try:
                import random
                ppr = requests.get(f'{ETSY_BASE}/shops/{shop_id}/production-partners',
                                   headers=write_headers(), timeout=10)
                print(f'DEBUG production partners: {ppr.status_code} {ppr.text[:300]}')
                partners = ppr.json().get('results', []) if ppr.ok else []
                _production_partner_cache[shop_id] = [p['production_partner_id'] for p in partners]
            except Exception as ppe:
                print(f'DEBUG production partner exception: {ppe}')
                _production_partner_cache[shop_id] = []
        partners = _production_partner_cache.get(shop_id, [])
        if partners:
            import random
            body['production_partner_ids'] = [random.choice(partners)]
        r = requests.post(
            f'{ETSY_BASE}/shops/{shop_id}/listings',
            headers=write_headers(),
            json=body,
            timeout=30
        )
        print(f'DEBUG body sent: {json.dumps({k:v for k,v in body.items() if k in ["who_made","when_made","taxonomy_id","type","is_digital"]})}') 
        print(f'DEBUG etsy create {r.status_code}: {r.text[:400]}')
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── /api/etsy/inventory — set size variants ───────────────────────────────────

@app.route('/api/etsy/inventory/<int:listing_id>', methods=['PUT'])
def etsy_inventory(listing_id):
    body = request.json
    try:
        r = requests.put(
            f'{ETSY_BASE}/listings/{listing_id}/inventory',
            headers=write_headers(),
            json=body,
            timeout=30
        )
        print(f'DEBUG inventory {r.status_code}: {r.text[:200]}')
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── /api/etsy/image — upload image to listing ─────────────────────────────────

@app.route('/api/etsy/image/<shop>/<int:listing_id>', methods=['POST'])
def etsy_image(shop, listing_id):
    body = request.json
    image_url = body.get('url')
    rank = body.get('rank', 1)
    try:
        shop_id = _shop_id_cache.get(shop, shop)
        # Download image from source URL
        img_resp = requests.get(image_url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        if not img_resp.ok:
            return jsonify({'error': f'Failed to download image: {img_resp.status_code}'}), 400
        # Detect content type
        content_type = img_resp.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()
        ext = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/gif': 'gif', 'image/webp': 'webp'}.get(content_type, 'jpg')
        filename = f'image_{rank}.{ext}'
        # Upload as multipart to Etsy
        h = {'x-api-key': f'{ETSY_KEY}:{ETSY_SECRET}'}
        auth = request.headers.get('Authorization')
        if auth:
            h['Authorization'] = auth
        r = requests.post(
            f'{ETSY_BASE}/shops/{shop_id}/listings/{listing_id}/images',
            headers=h,
            files={'image': (filename, img_resp.content, content_type)},
            data={'rank': rank, 'overwrite': True},
            timeout=60
        )
        print(f'DEBUG image {r.status_code}: {r.text[:200]}')
        return jsonify(r.json()), r.status_code
    except Exception as e:
        print(f'DEBUG image exception: {e}')
        return jsonify({'error': str(e)}), 500

# ── /api/oauth/token — exchange OAuth code for access token ──────────────────

@app.route('/api/oauth/token', methods=['POST'])
def oauth_token():
    body = request.json
    try:
        r = requests.post(
            'https://openapi.etsy.com/v3/public/oauth/token',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'grant_type':    'authorization_code',
                'client_id':     body.get('client_id', ETSY_KEY),
                'redirect_uri':  body.get('redirect_uri', window.location.origin),
                'code':          body['code'],
                'code_verifier': body['code_verifier'],
            },
            timeout=15
        )
        data = r.json()
        # Save tokens to file for daily report script
        if data.get('refresh_token'):
            token_file = os.path.join(BASE_DIR, 'etsy_token.json')
            with open(token_file, 'w') as tf:
                json.dump({
                    'access_token':  data.get('access_token'),
                    'refresh_token': data.get('refresh_token'),
                    'client_id':     body.get('client_id', ETSY_KEY),
                    'saved_at':      __import__('datetime').datetime.now().isoformat()
                }, tf, indent=2)
            print(f'DEBUG token saved to {token_file}')
        return jsonify(data), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── /api/product — fetch single product by handle ────────────────────────────
@app.route('/api/product')
def product_single():
    domain = request.args.get('domain', '')
    handle = request.args.get('handle', '').strip()
    if not domain or not handle:
        return jsonify({'error': 'domain and handle required'}), 400
    try:
        # Try direct handle first
        url = f'https://{domain}/products/{handle}.json'
        r   = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        if r.ok and r.json().get('product'):
            return jsonify(r.json()), r.status_code
        # Search by stock number using suggest.json
        handle_lower = handle.lower()
        search_url = f'https://{domain}/search/suggest.json?q={handle}&resources[type]=product&resources[limit]=10'
        r2 = requests.get(search_url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        if r2.ok:
            results = r2.json().get('resources', {}).get('results', {}).get('products', [])
            if results:
                # Find exact match by stock number in handle or title
                handle_upper = handle.upper()
                best = None
                for res in results:
                    if handle_upper in res.get('handle','').upper() or handle_upper in res.get('title','').upper():
                        best = res
                        break
                if not best:
                    best = results[0]  # fallback to first result
                pr = requests.get(f'https://{domain}/products/{best["handle"]}.json', timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
                if pr.ok and pr.json().get('product'):
                    prod = pr.json()['product']
                    return jsonify(pr.json()), 200
        # Fallback: try collections search
        r3 = requests.get(f'https://{domain}/collections/all/products.json?q={handle}&limit=5', timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        if r3.ok:
            products = r3.json().get('products', [])
            for p in products:
                if handle_lower in p.get('title','').lower() or handle_lower in p.get('handle','').lower():
                    return jsonify({'product': p}), 200
        return jsonify({'error': f'Product not found: {handle}'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── /api/search — search Alrug by query ─────────────────────────────────────
@app.route('/api/search')
def search_products():
    domain = request.args.get('domain', 'www.alrug.com')
    q      = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'q required'}), 400
    try:
        all_products = []
        page = 1
        while True:
            # Use collections/all with q param for full paginated results
            url = f'https://{domain}/collections/all/products.json?q={requests.utils.quote(q)}&limit=250&page={page}'
            r = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
            if r.ok:
                products = r.json().get('products', [])
                all_products.extend(products)
                if len(products) < 250: break
                page += 1
            else:
                break
        return jsonify({'products': all_products}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── /api/products — fetch Shopify-style products.json from HPD or Alrug ───────

@app.route('/api/products')
def products():
    domain     = request.args.get('domain', '')
    collection = request.args.get('collection', '')
    page       = request.args.get('page', 1)
    if not domain or not collection:
        return jsonify({'error': 'domain and collection required'}), 400
    try:
        url = f'https://{domain}/collections/{collection}/products.json?limit=250&page={page}'
        r   = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── Run ───────────────────────────────────────────────────────────────────────

# ── /api/etsy/sections — get shop sections ───────────────────────────────────
@app.route('/api/etsy/sections')
def etsy_sections():
    try:
        shop_id = next(iter(_shop_id_cache.values()), config.SHOP_ID)
        r = requests.get(f'{ETSY_BASE}/shops/{shop_id}/sections', headers=ETSY_HEADERS, timeout=10)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/etsy/update/<int:listing_id>', methods=['PATCH'])
def etsy_update(listing_id):
    body = request.json
    try:
        shop_id = next(iter(_shop_id_cache.values()), config.SHOP_ID)
        r = requests.patch(
            f'{ETSY_BASE}/shops/{shop_id}/listings/{listing_id}',
            headers=write_headers(),
            json=body,
            timeout=15
        )
        print(f'DEBUG update {r.status_code} body={list(body.keys())}: {r.text[:150]}')
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/etsy/property/<int:listing_id>/<int:property_id>', methods=['PUT'])
def etsy_property(listing_id, property_id):
    body = request.json
    try:
        r = requests.put(
            f'{ETSY_BASE}/shops/{config.SHOP_ID}/listings/{listing_id}/properties/{property_id}',
            headers=write_headers(),
            json=body,
            timeout=15
        )
        print(f'DEBUG prop {property_id}: {r.status_code} {r.text[:150]}')
        return jsonify(r.json() if r.content else {}), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── /api/etsy/listing — get single listing state ─────────────────────────────
@app.route('/api/etsy/listing/<int:listing_id>')
def etsy_listing(listing_id):
    try:
        r = requests.get(
            f'{ETSY_BASE}/listings/{listing_id}',
            headers=write_headers(),
            timeout=10
        )
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── /api/sync/save — save imported rug record ────────────────────────────────
import json as _json
SYNC_FILE = os.path.join(BASE_DIR, 'imported_rugs.json')

def load_sync():
    try:
        with open(SYNC_FILE, 'r') as f: return _json.load(f)
    except: return []

def save_sync(records):
    with open(SYNC_FILE, 'w') as f: _json.dump(records, f, indent=2)

@app.route('/api/sync/save', methods=['POST'])
def sync_save():
    data = request.json  # {alrug_id, alrug_handle, title, etsy_listing_id, collection, price}
    records = load_sync()
    # Avoid duplicates
    records = [r for r in records if r.get('etsy_listing_id') != data.get('etsy_listing_id')]
    records.append(data)
    save_sync(records)
    return jsonify({'ok': True, 'count': len(records)})

@app.route('/api/inventory/rebuild', methods=['POST'])
def inventory_rebuild():
    import subprocess
    try:
        subprocess.run(['python3', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_inventory.py')], stdout=open('/var/log/etsy_build.log', 'a'), stderr=subprocess.STDOUT, timeout=120)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/api/inventory/list", methods=["GET"])
def inventory_list():
    import csv as _csv
    csv_file = os.path.join(BASE_DIR, "rug_inventory.csv")
    if not os.path.exists(csv_file):
        return jsonify({"rows": []})
    rows = []
    with open(csv_file, newline="", encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            rows.append(dict(row))
    return jsonify({"rows": rows})

@app.route('/api/inventory/skus', methods=['GET'])
def inventory_skus():
    import csv as _csv
    csv_file = os.path.join(BASE_DIR, 'rug_inventory.csv')
    if not os.path.exists(csv_file):
        return jsonify({'skus': []})
    skus = []
    with open(csv_file, newline='', encoding='utf-8') as f:
        for row in _csv.DictReader(f):
            sku = row.get('sku', '').strip()
            if sku:
                skus.append(sku)
    return jsonify({'skus': skus})

@app.route('/api/inventory/check', methods=['GET'])
def inventory_check():
    import csv as _csv
    sku = request.args.get('sku', '').strip().upper()
    if not sku:
        return jsonify({'exists': False})
    csv_file = os.path.join(BASE_DIR, 'rug_inventory.csv')
    if not os.path.exists(csv_file):
        return jsonify({'exists': False})
    with open(csv_file, newline='', encoding='utf-8') as f:
        for row in _csv.DictReader(f):
            if row.get('sku', '').upper() == sku:
                return jsonify({'exists': True, 'etsy_id': row.get('etsy_listing_id', '')})
    return jsonify({'exists': False})


@app.route('/api/sync/list', methods=['GET'])
def sync_list():
    return jsonify(load_sync())

@app.route('/api/sync/delete', methods=['POST'])
def sync_delete():
    data = request.json
    etsy_id = data.get('etsy_listing_id')
    records = [r for r in load_sync() if r.get('etsy_listing_id') != etsy_id]
    save_sync(records)
    return jsonify({'ok': True})

# ── /api/etsy/delete-listing — delete an Etsy listing ────────────────────────
@app.route('/api/etsy/delete/<int:listing_id>', methods=['DELETE'])
def etsy_delete(listing_id):
    try:
        shop_id = next(iter(_shop_id_cache.values()), config.SHOP_ID)
        r = requests.delete(
            f'{ETSY_BASE}/shops/{shop_id}/listings/{listing_id}',
            headers=write_headers(),
            timeout=15
        )
        return jsonify({'ok': r.ok, 'status': r.status_code})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 55)
    print("  Etsy Importer — Local Server")
    print("  Open: http://localhost:8080")
    print("=" * 55)
    app.run(host='localhost', port=8080, debug=False)
