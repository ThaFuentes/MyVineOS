# ================================================================
# poweredbytop/auth/session.py
# pbt_vetted Flag + Session Vetting System - Sovereign Security
# FULLY INTERNAL PER-SITE - NO HUB REDIRECTS
# 100% FRESH REBUILD - SECURITY FIRST - WORKS WITH FULL PIPELINE
# ================================================================
# MARIADB ONLY - EXACT DB TABLES ONLY - NO INSTANCE FOLDER - NO SQLITE - NO JSON
# INTEGRATES WITH core/security.py + reputation/scorer.py + models/connect_db.py
# ================================================================

from flask import session, request, g
from typing import Optional
import time

# ====================== SAFE IMPORTS ======================
from poweredbytop.config.settings import (
    SESSION_COOKIE_NAME,
    VETTED_SESSION_TTL,
    BRUTE_FORCE_MAX_ATTEMPTS,
    BRUTE_FORCE_JAIL_SECONDS,
    SESSION_COOKIE_SECURE,
)
from poweredbytop.utils.helpers import get_real_ip, logger

# Lazy load to prevent circular imports with reputation and core/security
def _get_reputation_functions():
    try:
        from poweredbytop.reputation.scorer import record_bad_behavior
        return record_bad_behavior
    except Exception:
        return None

# ====================== SESSION SECURITY CONFIG ======================
def apply_secure_session_config(app):
    """Apply hardened session settings at app level"""
    app.config['SESSION_COOKIE_NAME'] = SESSION_COOKIE_NAME
    app.config['SESSION_COOKIE_SECURE'] = SESSION_COOKIE_SECURE
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = VETTED_SESSION_TTL
    app.config['SESSION_REFRESH_EACH_REQUEST'] = False
    logger("Secure session configuration applied (INTERNAL PER-SITE MODE, SECURE=" + str(SESSION_COOKIE_SECURE) + ")")
    return True

# ====================== VETTING FLAG MANAGEMENT ======================
def mark_as_vetted(token: Optional[str] = None) -> bool:
    """Mark current session as vetted ONLY after full pipeline PASS in core/security.py"""
    client_ip = get_real_ip(request)
    record_bad = _get_reputation_functions()

    ua = request.headers.get("User-Agent", "")
    if ua and "bot" in ua.lower() or "crawler" in ua.lower() or "scrap" in ua.lower():
        logger(f"Suspicious UA blocked from vetting - IP {client_ip}")
        if record_bad:
            record_bad(client_ip)
        return False

    session['pbt_vetted'] = True
    session['pbt_vetted_ts'] = int(time.time())
    session['pbt_vetted_ip'] = client_ip
    logger(f"Session marked VETTED for REAL IP {client_ip}")
    return True

def is_vetted() -> bool:
    """Check if current request/session is vetted (called from core/security.py pipeline)"""
    if 'pbt_vetted' not in session:
        return False

    vetted_ts = session.get('pbt_vetted_ts', 0)
    if time.time() - vetted_ts > VETTED_SESSION_TTL:
        clear_vetted()
        return False

    stored_ip = session.get('pbt_vetted_ip')
    current_ip = get_real_ip(request)

    if stored_ip == "127.0.0.1":
        session['pbt_vetted_ip'] = current_ip
        logger(f"LEGACY IP UPGRADE: changed stored 127.0.0.1 to real IP {current_ip}")
        return True

    if stored_ip != current_ip:
        logger("Session IP mismatch - possible hijack attempt")
        record_bad = _get_reputation_functions()
        if record_bad:
            record_bad(current_ip)
        clear_vetted()
        return False

    return True

def clear_vetted():
    """Remove vetted status"""
    session.pop('pbt_vetted', None)
    session.pop('pbt_vetted_ts', None)
    session.pop('pbt_vetted_ip', None)

# ====================== BRUTE FORCE PROTECTION ======================
def record_login_attempt(success: bool):
    """Record login attempt - now ties directly into reputation scorer + security events"""
    client_ip = get_real_ip(request)
    record_bad = _get_reputation_functions()

    key = "login_attempts_" + client_ip
    attempts = session.get(key, 0)

    if success:
        session[key] = 0
        logger(f"Successful login - IP {client_ip}")
    else:
        attempts += 1
        session[key] = attempts
        logger(f"Failed login attempt #{attempts} - IP {client_ip}")

        if record_bad:
            record_bad(client_ip)

        if attempts >= BRUTE_FORCE_MAX_ATTEMPTS:
            session["locked_until_" + client_ip] = time.time() + BRUTE_FORCE_JAIL_SECONDS
            logger(f"IP {client_ip} LOCKED for {BRUTE_FORCE_JAIL_SECONDS}s")
            if record_bad:
                record_bad(client_ip)

def is_locked_out() -> bool:
    """Check if IP is currently locked out"""
    client_ip = get_real_ip(request)
    locked_until = session.get("locked_until_" + client_ip, 0)
    if locked_until > time.time():
        remaining = int(locked_until - time.time())
        logger(f"IP {client_ip} still locked out - {remaining}s remaining")
        return True
    return False

# ====================== INTERNAL VETTING CHECK ======================
def require_vetted():
    """Check if user is vetted - returns True/False (called from core/security.py full pipeline)"""
    if is_vetted():
        g.pbt_vetted = True
        return True
    g.pbt_vetted = False
    return False

# ====================== FINAL EXPORTS ======================
__all__ = [
    "apply_secure_session_config",
    "mark_as_vetted",
    "is_vetted",
    "clear_vetted",
    "record_login_attempt",
    "is_locked_out",
    "require_vetted"
]

logger("poweredbytop/auth/session.py - 100% fresh rebuild loaded successfully (ready for full pipeline)")