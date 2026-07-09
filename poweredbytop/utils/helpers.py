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
    """Get real client IP from headers or remote_addr"""
    return (
        req.headers.get("CF-Connecting-IP") or
        req.headers.get("X-Real-IP") or 
        req.headers.get("X-Forwarded-For", "").split(",")[0] or 
        req.remote_addr
    )
# ====================== INTERNAL REQUEST BYPASS ======================
def is_internal_request(req):
    """Bypass for internal paths (static, health, favicon)"""
    return req.path.startswith(("/static/", "/health", "/favicon", "/robots.txt"))
# ====================== SUSPICIOUS USER AGENT CHECK ======================
def is_suspicious_user_agent(ua: str) -> bool:
    """Basic bot/user-agent detection"""
    if not ua:
        return False
    ua_lower = ua.lower()
    bad_agents = ["bot", "crawler", "spider", "curl", "wget", "python-requests", "scrapy"]
    return any(agent in ua_lower for agent in bad_agents)
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