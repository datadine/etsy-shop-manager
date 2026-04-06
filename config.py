"""
config.py
=========
Loads configuration from .env file or environment variables.
Copy .env.example to .env and fill in your values.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _load_env():
    """Load .env file into environment if it exists."""
    env_file = os.path.join(BASE_DIR, '.env')
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    os.environ.setdefault(key.strip(), value.strip())

_load_env()

def get(key, default=''):
    return os.environ.get(key, default)

# ── Etsy ──────────────────────────────────────────────────────────────────────
ETSY_KEY   = get('ETSY_KEY')
ETSY_SECRET = get('ETSY_SECRET')
SHOP_NAME  = get('SHOP_NAME')
SHOP_ID    = int(get('SHOP_ID', '0') or '0')
ETSY_BASE  = 'https://openapi.etsy.com/v3/application'

# ── Email ─────────────────────────────────────────────────────────────────────
SMTP_HOST  = 'smtp.gmail.com'
SMTP_PORT  = 587
SMTP_USER  = get('SMTP_USER')
SMTP_PASS  = get('SMTP_PASS')
EMAIL_FROM = get('EMAIL_FROM')
EMAIL_TO   = [e.strip() for e in get('EMAIL_TO', '').split(',') if e.strip()]

# ── Tool ──────────────────────────────────────────────────────────────────────
TOOL_URL   = get('TOOL_URL', 'http://localhost:8000')
