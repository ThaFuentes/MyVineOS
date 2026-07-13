# ================================================================
# poweredbytop/auth/session.py
# pbt_vetted Flag + Session Vetting System - Sovereign Security
# FULLY INTERNAL PER-SITE - NO HUB REDIRECTS
# ================================================================
# MULTI-DEVICE POLICY
# --------------------
# Sessions are signed cookies in each browser/app. Logging in on a phone does
# NOT log out a laptop (and vice versa). There is no server-side exclusive
# session token per user. IP is tracked for logs only — it must not kill a
# valid session when the user switches networks or devices.
# ================================================================

from flask import session, request, g
from typing import Optional
import time
import secrets

# ====================== SAFE IMPORTS ======================
from poweredbytop.config.settings import (
    SESSION_COOKIE_NAME,
    VETTED_SESSION_TTL,
    BRUTE_FORCE_MAX_ATTEMPTS,
    BRUTE_FORCE_JAIL_SECONDS,
    SESSION_COOKIE_SECURE,
    BIND_SESSION_TO_IP,
    SESSION_REFRESH_EACH_REQUEST,
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
    """Apply hardened session settings at app level (multi-device safe)."""
    app.config['SESSION_COOKIE_NAME'] = SESSION_COOKIE_NAME
    app.config['SESSION_COOKIE_SECURE'] = SESSION_COOKIE_SECURE
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = VETTED_SESSION_TTL
    # Refresh independently per device so phone + desktop both stay alive
    app.config['SESSION_REFRESH_EACH_REQUEST'] = bool(SESSION_REFRESH_EACH_REQUEST)
    logger(
        "Secure session configuration applied (multi-device OK, IP_BIND="
        + str(BIND_SESSION_TO_IP)
        + ", SECURE="
        + str(SESSION_COOKIE_SECURE)
        + ")"
    )
    return True


# ====================== VETTING FLAG MANAGEMENT ======================
def mark_as_vetted(token: Optional[str] = None) -> bool:
    """
    Mark current browser session as vetted.
    Only affects THIS device's cookie — other logged-in devices are unchanged.
    """
    client_ip = get_real_ip(request)
    record_bad = _get_reputation_functions()

    ua = (request.headers.get("User-Agent") or "").lower()
    # Parentheses required: otherwise "or crawler" runs even when ua is empty/falsy.
    if ua and any(x in ua for x in ("bot", "crawler", "scrapy", "spider")):
        logger(f"Suspicious UA blocked from vetting - IP {client_ip}")
        if record_bad:
            record_bad(client_ip)
        return False

    session['pbt_vetted'] = True
    session['pbt_vetted_ts'] = int(time.time())
    # Last-seen IP for diagnostics only (not an exclusive lock)
    session['pbt_vetted_ip'] = client_ip
    session['pbt_last_ip'] = client_ip
    if not session.get('pbt_device_id'):
        # Stable id for this browser cookie — not used to enforce single-device
        session['pbt_device_id'] = secrets.token_hex(8)
    session.permanent = True
    session.modified = True
    logger(f"Session marked VETTED (device={session.get('pbt_device_id')}, ip={client_ip})")
    return True


def is_vetted() -> bool:
    """
    Check if current request/session is vetted.
    Multi-device safe: does not require a fixed IP unless BIND_SESSION_TO_IP is on.
    """
    if 'pbt_vetted' not in session:
        return False

    vetted_ts = session.get('pbt_vetted_ts', 0)
    if time.time() - vetted_ts > VETTED_SESSION_TTL:
        clear_vetted()
        return False

    current_ip = get_real_ip(request)
    # Always remember last IP for logs / support, never as an exclusive key
    if current_ip:
        session['pbt_last_ip'] = current_ip

    if BIND_SESSION_TO_IP:
        stored_ip = session.get('pbt_vetted_ip')
        if stored_ip == "127.0.0.1" and current_ip:
            session['pbt_vetted_ip'] = current_ip
            return True
        if stored_ip and current_ip and stored_ip != current_ip:
            # Soft rebind even when binding is enabled (carriers / multi-network)
            logger(f"Session IP change {stored_ip} -> {current_ip}; rebinding (BIND_SESSION_TO_IP)")
            session['pbt_vetted_ip'] = current_ip
            return True
    else:
        # Default multi-device / multi-network mode: never fail on IP change
        if current_ip:
            session['pbt_vetted_ip'] = current_ip

    return True


def clear_vetted():
    """Remove vetted status from THIS device session only."""
    session.pop('pbt_vetted', None)
    session.pop('pbt_vetted_ts', None)
    session.pop('pbt_vetted_ip', None)
    # Keep pbt_device_id / pbt_last_ip if present — harmless metadata


# ====================== BRUTE FORCE PROTECTION ======================
def record_login_attempt(success: bool):
    """
    Record login attempt for THIS browser session + IP reputation.
    Does not log out or invalidate other devices for the same user account.
    """
    client_ip = get_real_ip(request)
    record_bad = _get_reputation_functions()

    key = "login_attempts_" + (client_ip or "unknown")
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
            session["locked_until_" + (client_ip or "unknown")] = time.time() + BRUTE_FORCE_JAIL_SECONDS
            logger(f"IP {client_ip} LOCKED for {BRUTE_FORCE_JAIL_SECONDS}s (this browser cookie only for lock key; reputation is IP-wide)")
            if record_bad:
                record_bad(client_ip)


def is_locked_out() -> bool:
    """Check if this browser session is currently locked out for the client IP."""
    client_ip = get_real_ip(request) or "unknown"
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
    "require_vetted",
]

logger("poweredbytop/auth/session.py loaded (multi-device concurrent sessions supported)")
