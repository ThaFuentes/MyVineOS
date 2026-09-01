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
def _parse_ip(raw):
    text = (raw or "").strip().strip("[]")
    if not text:
        return None
    try:
        import ipaddress

        return ipaddress.ip_address(text.split("%")[0])
    except Exception:
        return None


def _ip_is_public_enough(addr) -> bool:
    """True for internet / CGNAT. False for loopback and true RFC1918 / ULA."""
    if addr is None:
        return False
    if addr.is_unspecified or addr.is_loopback or addr.is_link_local:
        return False
    if addr.version == 4:
        n = int(addr)
        if (n >> 24) == 10:
            return False
        if 2752 <= (n >> 20) <= 2753:
            return False
        if (n >> 16) == 0xC0A8:
            return False
        return True
    if addr.version == 6:
        return (int(addr) >> 121) != 126
    return True


def get_real_ip(req=None):
    """Client IP. Prefer the first public address in CF / X-Real-IP / XFF.

    HostM often prepends 127.0.0.1 or a LAN hop. Taking that first hop
    made every church event look like LAN on the threat map.
    """
    if req is None:
        try:
            from flask import has_request_context, request as flask_request
            if has_request_context():
                req = flask_request
        except Exception:
            req = None
    if req is None:
        return "0.0.0.0"
    try:
        candidates = []
        for h in ("CF-Connecting-IP", "X-Real-IP", "True-Client-IP"):
            v = req.headers.get(h)
            if v:
                candidates.append(v)
        xff = req.headers.get("X-Forwarded-For") or ""
        for part in xff.split(","):
            if part.strip():
                candidates.append(part)
        ra = getattr(req, "remote_addr", None)
        if ra:
            candidates.append(ra)
        first_valid = None
        for raw in candidates:
            addr = _parse_ip(raw)
            if addr is None:
                continue
            if first_valid is None:
                first_valid = str(addr)
            if _ip_is_public_enough(addr):
                return str(addr)
        return first_valid or "0.0.0.0"
    except Exception:
        return "0.0.0.0"
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

def _trusted_ip_set() -> set:
    """Owner/ops allowlist from PBT_TRUSTED_IPS env (comma-separated)."""
    import os
    raw = (os.getenv("PBT_TRUSTED_IPS") or "").strip()
    if not raw:
        return set()
    out = set()
    for part in raw.replace(";", ",").replace(" ", ",").split(","):
        ip = part.strip()
        if ip:
            out.add(ip)
    return out


def is_trusted_ip(ip=None) -> bool:
    """True if this client IP is on the operator allowlist (PBT_TRUSTED_IPS)."""
    if not ip:
        try:
            ip = get_real_ip()
        except Exception:
            return False
    ip = (ip or "").strip()
    if not ip:
        return False
    return ip in _trusted_ip_set()

