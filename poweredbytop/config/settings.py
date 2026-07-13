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
DEBUG_MODE = False
REQUIRE_HTTPS = os.getenv('REQUIRE_HTTPS', 'true').lower() in ('1', 'true', 'yes', 'TRUE')

# ====================== FULL PIPELINE CONTROL ======================
FULL_SECURITY_PIPELINE_ENABLED = True
WRITE_PASS_FAIL_TO_DB = True
BLOCK_ON_ANY_FAILURE = True

# ====================== RATE LIMITING & DDoS / REFRESH SPAM ======================
GLOBAL_RATE_LIMIT = 300
PER_IP_RATE_LIMIT = 60
RATE_WINDOW_SECONDS = 60
STAGGER_DELAY_MS = 800
BURST_TOLERANCE = 5
JAIL_THRESHOLD = 10
JAIL_DURATION_SECONDS = 300
STAGGER_DELAY = 0.8

# ====================== BRUTE FORCE PROTECTION ======================
BRUTE_FORCE_MAX_ATTEMPTS = 5
BRUTE_FORCE_JAIL_SECONDS = 300

# ====================== REPUTATION SYSTEM ======================
MAX_REPUTATION_SCORE = 100
MIN_REPUTATION_SCORE = 0
FAST_LANE_THRESHOLD = 85
STRICT_MODE_THRESHOLD = 25
INITIAL_REPUTATION = 60
GOOD_BEHAVIOR_BONUS = 5
BAD_BEHAVIOR_PENALTY = 15
REPUTATION_DECAY_PER_HOUR = 1

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
# Keep this tight — overly broad keywords (java/php/httpclient) false-positive on real browsers/WebViews.
SUSPICIOUS_UA_KEYWORDS = ["bot", "crawler", "spider", "curl", "wget", "python-requests", "scrapy"]
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