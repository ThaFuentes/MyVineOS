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

from flask import session, request, g, has_request_context
from typing import Optional
import time
import secrets
import re

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
    try:
        app.before_request(enforce_bound_session)
    except Exception as hook_err:
        logger(f"login bind hook failed: {hook_err}")
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
    # Sliding window: using the site keeps this device signed in.
    session['pbt_vetted_ts'] = int(time.time())
    session.permanent = True

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


# ====================== LOGIN COOKIE BIND (session['user_id']) ======================
# Same-device roaming is allowed. Stolen cookie on a new device + new network is not.
_SESS_UID = "pbt_sess_uid"
_SESS_FAM = "pbt_sess_fam"
_SESS_FP = "pbt_sess_fp"
_SESS_IP = "pbt_sess_ip"
_BIND_SKIP_PREFIXES = (
    "/static/",
    "/favicon",
    "/health",
    "/robots.txt",
    "/.well-known/",
)


def _ips_same_client(stored: str | None, current: str | None) -> bool:
    if not stored or not current:
        return False
    if stored == current:
        return True
    if ":" not in stored and ":" not in current:
        return False
    try:
        import ipaddress
        a = ipaddress.ip_address(stored.split("%")[0])
        b = ipaddress.ip_address(current.split("%")[0])
        if a.version == 6 and b.version == 6:
            return (int(a) >> 64) == (int(b) >> 64)
        return a == b
    except Exception:
        return False


def _device_family() -> str:
    if not has_request_context():
        return ""
    al = (request.headers.get("Accept-Language") or "")[:40].lower()
    platform = (request.headers.get("Sec-CH-UA-Platform") or "").strip().strip('"').lower()[:80]
    ch = request.headers.get("Sec-CH-UA") or ""
    brands = ",".join(re.findall(r'"([^"]+)"', ch)).lower()
    if not brands:
        ua = (request.headers.get("User-Agent") or "").lower()
        if "edg/" in ua:
            brands = "edge"
        elif "chrome/" in ua:
            brands = "chrome"
        elif "firefox/" in ua:
            brands = "firefox"
        elif "safari/" in ua:
            brands = "safari"
        else:
            brands = (ua[:48] or "unknown")
    return "|".join((brands[:80], al[:40], platform or "unknown"))


def _current_device_fp() -> str:
    try:
        from poweredbytop.security.device_print import build_device_fingerprint
        return (build_device_fingerprint().get("device_fp") or "")[:40]
    except Exception:
        return ""


def _session_user_id():
    try:
        uid = session.get("user_id")
        return int(uid) if uid is not None else None
    except (TypeError, ValueError):
        return None


def bind_login_session(user=None) -> None:
    if not has_request_context():
        return
    uid = None
    if user is not None:
        if isinstance(user, dict):
            uid = user.get("id")
        else:
            uid = getattr(user, "id", None)
    if uid is None:
        uid = _session_user_id()
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return
    if uid <= 0:
        return
    session[_SESS_UID] = uid
    session[_SESS_FAM] = _device_family()
    session[_SESS_FP] = _current_device_fp()
    session[_SESS_IP] = get_real_ip(request)
    session.permanent = True
    session.modified = True


def clear_login_bind() -> None:
    if not has_request_context():
        return
    for k in (_SESS_UID, _SESS_FAM, _SESS_FP, _SESS_IP):
        session.pop(k, None)


def check_login_session() -> bool:
    if not has_request_context():
        return True
    path = request.path or ""
    if any(path.startswith(p) for p in _BIND_SKIP_PREFIXES):
        return True
    uid = _session_user_id()
    if not uid:
        return True
    if _SESS_UID not in session:
        bind_login_session()
        return True
    try:
        bound_uid = int(session.get(_SESS_UID) or 0)
    except (TypeError, ValueError):
        bound_uid = 0
    if bound_uid and bound_uid != uid:
        logger(f"Session bind fail: cookie user {bound_uid} != loaded user {uid}")
        try:
            from poweredbytop.core.security import log_security_event
            log_security_event(
                "session_bind_fail",
                f"cookie user {bound_uid} != loaded user {uid}",
                severity="high",
            )
        except Exception:
            pass
        return False

    ip = get_real_ip(request)
    bound_ip = session.get(_SESS_IP) or ""
    fam = _device_family()
    bound_fam = session.get(_SESS_FAM) or ""
    fp = _current_device_fp()
    bound_fp = session.get(_SESS_FP) or ""
    same_net = _ips_same_client(bound_ip, ip) or (bound_ip == ip)
    same_fam = bool(bound_fam) and bound_fam == fam
    same_fp = bool(bound_fp) and fp and bound_fp == fp
    if same_fp or same_fam:
        if not same_net:
            session[_SESS_IP] = ip
        session[_SESS_FAM] = fam
        if fp:
            session[_SESS_FP] = fp
        session.modified = True
        return True
    if same_net:
        bind_login_session()
        return True
    # Phone LTE/Wi-Fi + Safari UA drift used to look like a stolen cookie and
    # kicked ministers out mid-morning. Rebind this device instead of logging out.
    logger(f"Session bind rebind (family/ip drift) user={uid}")
    bind_login_session()
    return True


def enforce_bound_session():
    if check_login_session():
        return None
    clear_login_bind()
    clear_vetted()
    session.pop("user_id", None)
    session.pop("username", None)
    session.pop("user_role", None)
    return None


# ====================== FINAL EXPORTS ======================
__all__ = [
    "apply_secure_session_config",
    "mark_as_vetted",
    "is_vetted",
    "clear_vetted",
    "record_login_attempt",
    "is_locked_out",
    "require_vetted",
    "bind_login_session",
    "clear_login_bind",
    "check_login_session",
    "enforce_bound_session",
]

logger("poweredbytop/auth/session.py loaded (multi-device + login cookie bind)")
