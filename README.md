# Etsy Rug Importer & Management Tool

A full-stack automation tool for managing an Etsy shop that sells handmade Oriental rugs sourced from [alrug.com](https://www.alrug.com). Built as a production system running 24/7 on a VPS.

## What it does

- **Imports rugs from alrug.com to Etsy** — browses collections, filters by price, generates SEO-optimized titles and tags, creates draft listings with photos
- **Inventory management** — tracks every Etsy listing with its alrug.com SKU in a persistent CSV, rebuilds automatically on each session
- **Daily SEO audit** — scores every listing against Etsy SEO best practices and emails a report
- **Alrug availability alerts** — checks every listing against alrug.com every 3 hours and sends an urgent email if a rug is sold or removed
- **Listing Writer** — fetches any alrug.com product and generates a ready-to-paste Claude prompt for writing the Etsy description
- **User authentication** — login with username, password, and Google Authenticator TOTP 2FA

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
- **APIs:** Etsy Open API v3, Shopify Storefront API (alrug.com), Gmail SMTP
- **Monitoring:** cron-job.org heartbeat, health endpoint

## File Structure

```
server.py           — Main Flask app, serves the importer UI, proxies API calls
auth.py             — Authentication layer (login, TOTP, user management)
build_inventory.py  — Rebuilds rug_inventory.csv from live Etsy data
report.py           — Daily SEO audit, emails HTML report
alert.py            — Checks alrug.com availability, sends urgent alerts
config.py           — Loads credentials from .env file
.env.example        — Template for credentials (copy to .env and fill in)
```

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/yourusername/etsy-rug-importer.git
cd etsy-rug-importer
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
# See nginx config example below

# Cron jobs
55 11 * * * cd /path/to/app && python3 build_inventory.py >> /var/log/etsy_build.log 2>&1
0  12 * * * cd /path/to/app && python3 report.py >> /var/log/etsy_report.log 2>&1
0 */3 * * * cd /path/to/app && python3 alert.py >> /var/log/etsy_alert.log 2>&1
```

## Key Features

### Duplicate Prevention
Before showing rugs in the import grid, the tool checks `rug_inventory.csv` and hides any rug already imported (matched by SKU). This prevents accidental duplicate listings.

### SKU Tracking
Every Etsy listing stores the alrug.com stock number (e.g. `AT22818`) in Etsy's SKU field. `build_inventory.py` reads this via the Etsy inventory API and stores it in the CSV alongside the alrug.com handle, enabling price comparison and availability checks.

### Alrug Availability Check
Uses alrug.com's Shopify suggest API (`/search/suggest.json`) which correctly returns `available: true/false` — unlike the products API which always returns `null`. Searches by SKU and matches by title to handle cases where the URL handle doesn't match the title SKU.

### SEO Scoring
Each listing is scored 0-100 against rules including title length, banned words (Iran/Persian/Persia per Etsy policy), tag count, style terms, color terms, size, room use case, origin, quality terms, and description length.

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

## Screenshots

*The tool running on a private VPS with HTTPS, 2FA login, and automated daily reports.*

## Author

Built as a production tool for a real Etsy shop. Part of my portfolio demonstrating full-stack Python development, API integration, and automated systems.
