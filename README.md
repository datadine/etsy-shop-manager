# Etsy Shop Manager

A full-stack automation tool for managing an Etsy shop that sources products from a Shopify-based supplier. Built as a production system running 24/7 on a VPS.

The tool connects your supplier's Shopify store to your Etsy shop — browse supplier collections, import products as Etsy drafts, track inventory, monitor availability, and audit SEO quality automatically.

## What it does

- **Imports products from any Shopify supplier to Etsy** — browses collections, filters by price, generates SEO-optimized titles and tags, creates draft listings with photos
- **Inventory management** — tracks every Etsy listing with its supplier SKU in a persistent CSV, rebuilds automatically on each session
- **Daily SEO audit** — scores every listing against Etsy SEO best practices and emails a formatted HTML report
- **Availability alerts** — checks every listing against the supplier store every 3 hours and sends an urgent email if an item is sold or removed
- **Listing Writer** — fetches any supplier product and generates a ready-to-paste AI prompt for writing the Etsy description
- **User authentication** — login with username, password, and Google Authenticator TOTP 2FA
- **Admin panel** — create and manage users, reset 2FA, role-based access

## Architecture

```
Browser → Nginx (HTTPS) → auth.py (port 8000, auth layer) → server.py (port 8080, app)
                                                           ↓
                                              build_inventory.py (cron)
                                              report.py (cron)
                                              alert.py (cron)
```

## Tech Stack

- **Backend:** Python 3, Flask, Flask-CORS
- **Auth:** JWT tokens, bcrypt passwords, PyOTP (TOTP 2FA)
- **Frontend:** Vanilla JS, HTML/CSS (no frameworks)
- **Infrastructure:** Ubuntu 22.04 VPS, Nginx reverse proxy, Supervisor process manager, Let's Encrypt SSL
- **APIs:** Etsy Open API v3, Shopify Storefront API, Gmail SMTP
- **Monitoring:** External heartbeat (cron-job.org), `/health` endpoint

## File Structure

```
server.py           — Main Flask app, serves the importer UI, proxies API calls
auth.py             — Authentication layer (login, TOTP, user management)
build_inventory.py  — Rebuilds inventory.csv from live Etsy data
report.py           — Daily SEO audit, emails HTML report
alert.py            — Checks supplier availability, sends urgent alerts
config.py           — Loads credentials from .env file
.env.example        — Template for credentials (copy to .env and fill in)
```

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/yourusername/etsy-shop-manager.git
cd etsy-shop-manager
cp .env.example .env
# Edit .env with your credentials
```

### 2. Install dependencies

```bash
pip3 install flask flask-cors requests pyotp qrcode[pil] pillow bcrypt pyjwt
```

### 3. Run locally

```bash
python3 server.py        # Start the importer on http://localhost:8080
python3 auth.py          # Start auth layer on http://localhost:8000
```

### 4. Production (VPS)

```bash
# Supervisor keeps both services running
supervisorctl start etsy_app etsy_auth

# Nginx reverse proxy with SSL (Let's Encrypt)
certbot --nginx -d your-domain.com

# Cron jobs
55 11 * * * cd /path/to/app && python3 build_inventory.py >> /var/log/etsy_build.log 2>&1
0  12 * * * cd /path/to/app && python3 report.py >> /var/log/etsy_report.log 2>&1
0 */3 * * * cd /path/to/app && python3 alert.py >> /var/log/etsy_alert.log 2>&1
```

## Key Features

### Duplicate Prevention
Before showing items in the import grid, the tool checks the inventory CSV and hides any item already imported (matched by SKU). The inventory rebuilds automatically every time you load the import grid.

### SKU Tracking
Every Etsy listing stores the supplier stock number in Etsy's SKU field during import. `build_inventory.py` reads this via the Etsy inventory API and stores it in a local CSV alongside the supplier handle, enabling price comparison and availability checks.

### Supplier Availability Check
Uses the Shopify suggest API (`/search/suggest.json`) which correctly returns `available: true/false`. Searches by SKU and matches by title to handle cases where the URL handle does not match the title SKU.

### SEO Scoring
Each listing is scored 0-100 against configurable rules including title length, banned words, tag count, style terms, color terms, size, room use case, origin, quality terms, and description length.

### Listing Writer
Paste any supplier product URL, the tool fetches the product details via your own server (bypassing any IP blocks), and assembles a structured AI prompt ready to paste into Claude or any LLM to generate a complete Etsy listing.

## Supplier Compatibility

Works with any Shopify-based supplier that exposes:
- `/collections/{slug}/products.json` — for browsing collections
- `/products/{handle}.json` — for fetching individual products
- `/search/suggest.json` — for availability checks

## Environment Variables

| Variable | Description |
|---|---|
| `ETSY_KEY` | Etsy API keystring |
| `ETSY_SECRET` | Etsy shared secret |
| `SHOP_NAME` | Your Etsy shop name |
| `SHOP_ID` | Your Etsy shop ID |
| `SMTP_USER` | Gmail address for sending reports |
| `SMTP_PASS` | Gmail app password |
| `EMAIL_FROM` | From address |
| `EMAIL_TO` | Comma-separated recipient emails |
| `TOOL_URL` | Public URL of your deployed tool |

## Author

Built as a production tool for a live Etsy shop. Part of my portfolio demonstrating full-stack Python development, REST API integration, OAuth flows, and automated systems on Linux.
