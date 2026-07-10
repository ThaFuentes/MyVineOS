# ================================================================
# poweredbytop/core/security.py
# MERGED CORE SECURITY PIPELINE - FULL GATEKEEPER
# 100% FRESH REBUILD - RETURNS NONE + AUTO VETTING
# ================================================================
# MARIADB ONLY - EXACT DB TABLES ONLY - NO SCHEMA CHANGES
# ================================================================

import time
import os
from flask import g, request, abort, session
from datetime import datetime, timedelta

# ====================== SAFE IMPORTS ======================
from poweredbytop.config.settings import (
    FULL_SECURITY_PIPELINE_ENABLED,
    CLOUDFLARE_ENABLED,
    BLOCK_ON_ANY_FAILURE,
    WRITE_PASS_FAIL_TO_DB,
    SUSPICIOUS_UA_KEYWORDS,
    PER_IP_RATE_LIMIT,
    RATE_WINDOW_SECONDS,
    STAGGER_DELAY,
    BRUTE_FORCE_JAIL_SECONDS,
    DB_BULKHEAD_ENABLED,
    SQLI_PROTECTION_ENABLED,
    N1_QUERY_THRESHOLD,
    LOG_SECURITY_EVENTS,
    REQUIRE_HTTPS,
    CSRF_PROTECTION,
)
from poweredbytop.models.connect_db import get_security_db
from poweredbytop.utils.helpers import get_real_ip, logger, is_internal_request, is_suspicious_user_agent
from poweredbytop.firewall.tokens import validate_token
from poweredbytop.throttling.rate_limit import check_rate_limit, apply_stagger
from poweredbytop.auth.session import is_vetted, is_locked_out, require_vetted, mark_as_vetted
from poweredbytop.reputation.scorer import get_reputation_score, record_bad_behavior, record_good_behavior
import secrets
import hashlib

# ====================== EXACT DB LOGGING ======================
def log_traffic(vetted: bool = False, status: str = "checking", score: int = 100):
    if not WRITE_PASS_FAIL_TO_DB:
        return
    db = get_security_db()
    if db is None:
        logger("TRAFFIC LOG SKIPPED - NO DB")
        return
    try:
        ip = get_real_ip(request)
        domain = request.host or "unknown"
        now = datetime.now()
        expires = now + timedelta(minutes=5)
        vetted_at = now if vetted else now  # never null
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO pbt_traffic (ip, domain, vetted_at, expires_at)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                vetted_at = VALUES(vetted_at),
                expires_at = VALUES(expires_at)
        """, (ip, domain, vetted_at, expires))
        db.commit()
        logger("TRAFFIC LOGGED | IP=" + ip[:8] + "... | STATUS=" + status + " | VETTED=" + str(vetted))
    except Exception as e:
        logger("TRAFFIC LOG FAILED: " + str(e))

def log_security_event(event_type: str, details: str, severity: str = "medium"):
    if not LOG_SECURITY_EVENTS:
        return
    db = get_security_db()
    if db is None:
        return
    try:
        ip = get_real_ip(request)
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO pbt_security_events
            (event_type, ip, reputation_score, behavior_grade, notes)
            VALUES (%s, %s, %s, %s, %s)
        """, (event_type, ip, 100, "normal", details))
        db.commit()
        logger("SECURITY EVENT | TYPE=" + event_type + " | IP=" + ip[:8] + "...")
    except Exception as e:
        logger("SECURITY EVENT FAILED: " + str(e))

def increment_attack_stat(stat_type: str):
    db = get_security_db()
    if db is None:
        return
    try:
        ip = get_real_ip(request)
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO pbt_attack_stats (attack_type, encrypted_count, total_attempts, blocked_count, last_attack_ip, last_attack_time)
            VALUES (%s, %s, 1, 1, %s, NOW())
            ON DUPLICATE KEY UPDATE
                total_attempts = total_attempts + 1,
                blocked_count = blocked_count + 1,
                last_attack_ip = VALUES(last_attack_ip),
                last_attack_time = NOW()
        """, (stat_type, b'', ip))
        db.commit()
        record_bad_behavior(ip)
        logger("ATTACK STAT INCREMENTED | TYPE=" + stat_type + " | IP=" + ip[:8] + "...")
    except Exception as e:
        logger("ATTACK STAT FAILED: " + str(e))

# ====================== CSRF PROTECTION ======================
def get_csrf_token():
    """Generate or return existing CSRF token for forms (call from templates via context)"""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']

def validate_csrf(token: str) -> bool:
    """Validate submitted CSRF token"""
    if not CSRF_PROTECTION:
        return True
    if not token:
        return False
    expected = session.get('csrf_token')
    if not expected:
        return False
    # Constant time compare to prevent timing attacks
    return secrets.compare_digest(expected, token or '')

# ====================== FULL SECURITY PIPELINE ======================
def run_full_security_pipeline():
    if not FULL_SECURITY_PIPELINE_ENABLED:
        return True

    ip = get_real_ip(request)

    if is_internal_request(request):
        log_traffic(vetted=True, status="internal_bypass")
        return True

    path = request.path or ""
    action = (request.form.get("action") or "").lower()
    is_public_guest_mutation = path.startswith("/public/") and action in ("comment", "reply", "potluck")

    # Auth entrypoints (login/register/reset flows) must be reachable even before vetting, on http dev, or low-rep recovery
    # (they perform their own auth checks + record_login_attempt inside the view; PBT still applies rate/UA/lock/CSRF to them)
    is_auth_entry = bool(request.endpoint and str(request.endpoint).startswith('auth.'))
    # Logged-in display prefs (theme/font) — allow over http in local DEBUG so themes actually save
    is_ui_prefs = (
        request.method == 'POST'
        and path.rstrip('/').endswith('/profile/ui-preferences')
        and bool(session.get('user_id'))
    )
    debug_http = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
    is_safe_mutation = (
        is_public_guest_mutation
        or is_auth_entry
        or (is_ui_prefs and debug_http)
    )

    def _request_is_https(req):
        """Robust https detection including common reverse proxies (Cloudflare, nginx, passenger/LiteSpeed)"""
        if req.is_secure:
            return True
        xf = (req.headers.get('X-Forwarded-Proto') or req.environ.get('HTTP_X_FORWARDED_PROTO') or '').lower().split(',')[0].strip()
        if xf == 'https':
            return True
        if req.environ.get('wsgi.url_scheme') == 'https':
            return True
        return False

    # HTTPS enforcement -- exempt public guest mutations + auth entry so login/register work over http in dev/proxy setups
    if REQUIRE_HTTPS and not _request_is_https(request) and not is_safe_mutation:
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            log_security_event("https_required", "Insecure POST blocked")
            return False

    ua = request.headers.get("User-Agent", "")
    if is_suspicious_user_agent(ua) or any(kw in ua.lower() for kw in SUSPICIOUS_UA_KEYWORDS):
        log_security_event("suspicious_ua", "Bot/scraper/hacker UA detected")
        increment_attack_stat("bot_attempt")
        return False

    if not check_rate_limit(ip):
        g.rate_limited = True
        log_security_event("rate_limit_exceeded", "IP exceeded rate limit")
        increment_attack_stat("ddos_attempts")
        apply_stagger()
        debug_mode = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
        if not debug_mode:
            return False

    if is_locked_out():
        log_security_event("brute_force_lock", "IP is currently locked out")
        increment_attack_stat("brute_force")
        return False

    score = get_reputation_score(ip)
    if score < 50 and not is_safe_mutation:
        log_security_event("low_reputation", f"Reputation score {score} below threshold")
        increment_attack_stat("reputation_block")
        debug_mode = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
        if not debug_mode:
            return False

    # CSRF for state changing requests
    if request.method in ('POST', 'PUT', 'DELETE', 'PATCH') and CSRF_PROTECTION:
        csrf_token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
        if not validate_csrf(csrf_token):
            log_security_event("csrf_failure", "CSRF token missing or invalid on " + request.method)
            increment_attack_stat("csrf_attack")
            return False

    token = request.headers.get("X-PBT-Token") or request.args.get("pbt_token")
    if token:
        if not validate_token(token, ip):
            log_security_event("invalid_token", "Token validation failed")
            increment_attack_stat("token_attack")
            return False

    # AUTO VET THE SESSION ON FIRST GOOD REQUEST
    if not is_vetted():
        mark_as_vetted()
        logger("AUTO-MARKED SESSION AS VETTED for IP " + ip)

    if not require_vetted() and not is_safe_mutation:
        log_security_event("not_vetted", "Session not vetted")
        return False

    if DB_BULKHEAD_ENABLED:
        if hasattr(g, 'query_count') and g.query_count > N1_QUERY_THRESHOLD:
            log_security_event("n1_query_detected", "N+1 query threshold exceeded")
            increment_attack_stat("n1_attack")
            return False

    record_good_behavior(ip)
    log_traffic(vetted=True, status="full_pass", score=score)
    g.pbt_vetted = True
    logger("FULL PIPELINE PASS | IP=" + ip[:8] + "... | SCORE=" + str(score))
    return True

def before_request_security():
    """MUST return None for Flask - this stops the exception"""
    start = time.time()
    if not run_full_security_pipeline():
        if BLOCK_ON_ANY_FAILURE:
            log_traffic(vetted=False, status="blocked")
            abort(403)
        return None
    apply_stagger()
    logger("SECURITY PIPELINE COMPLETED in " + str(round((time.time() - start) * 1000)) + "ms")
    return None

def teardown_security(exception=None):
    if hasattr(g, 'rate_limited') and g.rate_limited:
        log_traffic(vetted=False, status="rate_limited")
        increment_attack_stat("refresh_spam")
    elif exception:
        log_security_event("exception", str(exception)[:200])
        log_traffic(vetted=False, status="error")

logger("poweredbytop/core/security.py - 100% fresh rebuild loaded (auto-vetting + returns None + no more exception events)")