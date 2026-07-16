# ================================================================
# poweredbytop/config/settings.py
# ALL CONSTANTS FOR FULL SOVEREIGN SECURITY PIPELINE
# 100% FRESH REBUILD - CLEAN - NO DUPLICATES - SECURITY FIRST
# ================================================================
# MARIADB ONLY - EXACT DB TABLES ONLY - WORKS WITH core/security.py
# ================================================================

import os
import logging

logger = logging.getLogger("poweredbytop.config")

# ====================== CORE SECURITY FLAGS ======================
CLOUDFLARE_ENABLED = False
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() in ('1', 'true', 'yes', 'TRUE')
# HTTPS: default ON only in production. Local/http proxies stay usable for real members.
# Set REQUIRE_HTTPS=true explicitly behind a TLS terminator in prod.
_default_https = 'true' if os.getenv('FLASK_ENV', '').lower() == 'production' else 'false'
REQUIRE_HTTPS = os.getenv('REQUIRE_HTTPS', _default_https).lower() in ('1', 'true', 'yes', 'TRUE')

# ====================== FULL PIPELINE CONTROL ======================
FULL_SECURITY_PIPELINE_ENABLED = True
WRITE_PASS_FAIL_TO_DB = True
# Hard 403 only for true blocks; soft paths should not "death spiral" church visitors.
BLOCK_ON_ANY_FAILURE = True

# ====================== RATE LIMITING & DDoS / REFRESH SPAM ======================
# Churches share Wi‑Fi + mobile CGNAT. Prefer high ceilings; abuse still hits jail.
GLOBAL_RATE_LIMIT = 800
PER_IP_RATE_LIMIT = 240
RATE_WINDOW_SECONDS = 60
# Never sleep on every request — that made the whole site feel "broken" for humans.
STAGGER_DELAY_MS = 0
BURST_TOLERANCE = 50
JAIL_THRESHOLD = 20
JAIL_DURATION_SECONDS = 90
STAGGER_DELAY = 0.0

# ====================== BRUTE FORCE PROTECTION ======================
# Login lockouts: protect pastors from password spray without trapping whole family Wi‑Fi forever.
BRUTE_FORCE_MAX_ATTEMPTS = 10
BRUTE_FORCE_JAIL_SECONDS = 120

# ====================== REPUTATION SYSTEM ======================
# Score death-spirals were the main false-positive source for real users.
MAX_REPUTATION_SCORE = 100
MIN_REPUTATION_SCORE = 0
FAST_LANE_THRESHOLD = 70
STRICT_MODE_THRESHOLD = 15
INITIAL_REPUTATION = 85
GOOD_BEHAVIOR_BONUS = 6
BAD_BEHAVIOR_PENALTY = 2          # attack signals still count; recover quickly
REPUTATION_DECAY_PER_HOUR = 20    # shared church/public Wi‑Fi recovers same day
# Only hard-block anonymous *mutations* below this (GETs stay open for humans).
REPUTATION_BLOCK_THRESHOLD = 8
# Cap stored negatives so shared mobile IPs can recover
MAX_NEGATIVE_POINTS = 35

# ====================== DB GUARD / N+1 / SQL INJECTION PROTECTION ======================
DB_MAX_CONNECTIONS = 20
MAX_DB_CONNECTIONS = 20
DB_CONNECTION_TIMEOUT = 5
DB_QUERY_TIMEOUT_SECONDS = 30
N1_QUERY_THRESHOLD = 15
DB_BULKHEAD_ENABLED = True
SQLI_PROTECTION_ENABLED = True

# ====================== TOKEN / FIREWALL ======================
TOKEN_SECRET = os.getenv("PBT_TOKEN_SECRET", "CHANGE-THIS-TO-64-CHAR-RANDOM-STRING-NOW")
TOKEN_LIFETIME_SECONDS = 3600
HMAC_ALGORITHM = "sha256"

# ====================== BOT / SCRAPER / HACKER PROTECTION ======================
# Prefer tool/scraper tokens over bare "bot" alone where possible.
# Logged-in members and vetted browser sessions skip hard UA blocks (see security.py).
SUSPICIOUS_UA_KEYWORDS = [
    "curl", "wget", "python-requests", "scrapy", "httpclient",
    "headlesschrome", "phantomjs", "selenium",
    "bytespider", "semrush", "ahrefs", "mj12bot", "dotbot",
]
# Bare tokens matched with word-ish checks in helpers (avoids random browser false hits).
SUSPICIOUS_UA_LOOSE = ["crawler", "spider", "scraper"]
# Well-known search crawlers: log but do not hard-block (SEO + not "members").
ALLOWED_CRAWLER_UA = ["googlebot", "bingbot", "applebot", "duckduckbot", "yandexbot"]
ALLOWED_COUNTRIES = []
BLOCKED_COUNTRIES = []

# ====================== SESSION & AUTH ======================
# Cookie sessions are per-browser/device. Concurrent multi-device logins are supported
# (phone + laptop + tablet). There is no single server-side "one session only" token.
SESSION_COOKIE_NAME = "pbt_vetted_session"
VETTED_SESSION_TTL = 86400 * 14  # 14 days permanent session lifetime per device
CSRF_PROTECTION = True
SESSION_COOKIE_SECURE = os.getenv('REQUIRE_HTTPS', 'False').lower() in ('1', 'true', 'yes', 'TRUE') or os.getenv('FLASK_ENV') == 'production'  # Set True in prod HTTPS
# Do NOT bind vetted/auth session validity to client IP. Mobile carriers, Wi‑Fi,
# VPN, and multi-device use (home + phone LTE) all change IPs constantly.
BIND_SESSION_TO_IP = os.getenv('PBT_BIND_SESSION_TO_IP', 'false').lower() in ('1', 'true', 'yes', 'TRUE')
# Each device refreshes its own cookie lifetime independently while in use.
SESSION_REFRESH_EACH_REQUEST = True

# ====================== LOGGING ======================
LOG_LEVEL = "INFO"
LOG_SECURITY_EVENTS = True

# ====================== FALLBACK ======================
GRACEFUL_DEGRADATION = True
HUB_TIMEOUT_SECONDS = 3.0

# ====================== PRINT ON LOAD ======================
logger.info("poweredbytop/config/settings.py - 100% FRESH REBUILD LOADED")
logger.info("CLOUDFLARE_ENABLED=False | FULL_SECURITY_PIPELINE_ENABLED=True | WRITE_PASS_FAIL_TO_DB=True")
logger.info("GLOBAL_RATE_LIMIT=" + str(GLOBAL_RATE_LIMIT) + " | PER_IP_RATE_LIMIT=" + str(PER_IP_RATE_LIMIT))
logger.info("DB_QUERY_TIMEOUT_SECONDS=" + str(DB_QUERY_TIMEOUT_SECONDS))
logger.info("All constants ready for core/security.py + full request pipeline")