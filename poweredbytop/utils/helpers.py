# ================================================================
# poweredbytop/utils/helpers.py
# INTERNAL PER-SITE HELPERS
# 100% FRESH - MARIADB ONLY
# ================================================================
# MARIADB ONLY - NO INSTANCE FOLDER - NO SQLITE - NO JSON
# ================================================================
import os
from flask import request
import hashlib
# ====================== SIMPLE LOGGER ======================
def logger(msg):
    """Simple logger - plain ascii only"""
    print(msg)
# ====================== REAL IP DETECTION ======================
def get_real_ip(req):
    """Get real client IP from headers or remote_addr (never empty for DB NOT NULL)."""
    raw = (
        req.headers.get("CF-Connecting-IP") or
        req.headers.get("X-Real-IP") or
        (req.headers.get("X-Forwarded-For") or "").split(",")[0] or
        req.remote_addr or
        ""
    )
    ip = (raw or "").strip()
    return ip if ip else "0.0.0.0"
# ====================== INTERNAL REQUEST BYPASS ======================
def is_internal_request(req):
    """Bypass for internal paths (static, health, favicon)"""
    return req.path.startswith(("/static/", "/health", "/favicon", "/robots.txt"))
# ====================== SUSPICIOUS USER AGENT CHECK ======================
def is_allowed_crawler(ua: str) -> bool:
    """Search engines we allow through (not members — but not 'attacks' either)."""
    if not ua:
        return False
    try:
        from poweredbytop.config.settings import ALLOWED_CRAWLER_UA
        low = ua.lower()
        return any(k in low for k in ALLOWED_CRAWLER_UA)
    except Exception:
        low = ua.lower()
        return any(k in low for k in ("googlebot", "bingbot", "applebot"))


def is_suspicious_user_agent(ua: str) -> bool:
    """
    Scraper/tool detection for anonymous traffic.
    Empty UA is NOT treated as bot (some privacy browsers strip it).
    Allowed search crawlers return False (handled separately if needed).
    """
    if not ua:
        return False
    ua_lower = ua.lower()
    if is_allowed_crawler(ua_lower):
        return False
    # Normal browsers: Mozilla/… Chrome/… Safari/… — never hard-flag on bare "bot"
    # unless they also look non-browser (curl etc.).
    try:
        from poweredbytop.config.settings import SUSPICIOUS_UA_KEYWORDS, SUSPICIOUS_UA_LOOSE
        strict = list(SUSPICIOUS_UA_KEYWORDS)
        loose = list(SUSPICIOUS_UA_LOOSE)
    except Exception:
        strict = ["curl", "wget", "python-requests", "scrapy", "headlesschrome", "selenium"]
        loose = ["crawler", "spider", "scraper"]
    if any(k in ua_lower for k in strict):
        return True
    # Loose tokens: only if UA does not look like a normal browser
    looks_browser = any(x in ua_lower for x in ("mozilla/", "chrome/", "safari/", "firefox/", "edg/"))
    if looks_browser:
        return False
    return any(k in ua_lower for k in loose)
# ====================== CONSTANT TIME COMPARE (for tokens) ======================
def constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks"""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a.encode(), b.encode()):
        result |= x ^ y
    return result == 0
# ====================== SANITIZE FOR LOG ======================
def sanitize_for_log(text: str) -> str:
    """Remove newlines and control characters for safe logging"""
    if not text:
        return ""
    return str(text).replace("\n", " ").replace("\r", " ")[:200]
# ====================== SECURE HASH ======================
def secure_hash(data: str) -> str:
    """Simple SHA256 hash for internal use"""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
# ====================== FINAL LOAD MESSAGE ======================
logger("poweredbytop/utils/helpers.py fully loaded (internal per-site mode - MARIADB)")