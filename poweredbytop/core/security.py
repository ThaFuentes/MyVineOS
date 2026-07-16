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
    TOKEN_SECRET,
    REPUTATION_BLOCK_THRESHOLD,
)
from poweredbytop.models.connect_db import get_security_db
from poweredbytop.utils.helpers import (
    get_real_ip, logger, is_internal_request, is_suspicious_user_agent, is_allowed_crawler,
)
from poweredbytop.firewall.tokens import validate_token
from poweredbytop.throttling.rate_limit import check_rate_limit, apply_stagger
from poweredbytop.auth.session import is_vetted, is_locked_out, require_vetted, mark_as_vetted
from poweredbytop.reputation.scorer import get_reputation_score, record_bad_behavior, record_good_behavior
import secrets
import hashlib
import hmac

# Signed CSRF tokens remain valid this long even if the session cookie is dropped
# (common on some mobile browsers / in-app WebViews between GET form and POST).
CSRF_TOKEN_MAX_AGE_SECONDS = 2 * 60 * 60

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

def increment_attack_stat(stat_type: str, penalize: bool = True):
    """
    Count an attack type. Set penalize=False for secondary/cascade blocks
    (e.g. already-low reputation) so we do not death-spiral real users.
    """
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
        # Never pile penalties for cascade types that fire after score is already low
        no_pen = {
            "reputation_block", "refresh_spam", "n1_attack",
        }
        if penalize and stat_type not in no_pen:
            record_bad_behavior(ip)
        logger("ATTACK STAT INCREMENTED | TYPE=" + stat_type + " | IP=" + ip[:8] + "...")
    except Exception as e:
        logger("ATTACK STAT FAILED: " + str(e))


def _is_logged_in_member() -> bool:
    """Church members with a session must not be hard-blocked like anonymous scrapers."""
    try:
        return bool(session.get("user_id"))
    except Exception:
        return False

# ====================== CSRF PROTECTION ======================
def _csrf_secret_bytes() -> bytes:
    """Secret used to sign self-validating CSRF tokens (mobile-safe fallback)."""
    try:
        from flask import current_app
        key = current_app.secret_key
        if key:
            return key if isinstance(key, bytes) else str(key).encode("utf-8")
    except Exception:
        pass
    return str(TOKEN_SECRET or "pbt-csrf-fallback").encode("utf-8")


def _sign_csrf_payload(raw: str, ts: str) -> str:
    msg = f"{raw}:{ts}".encode("utf-8")
    return hmac.new(_csrf_secret_bytes(), msg, hashlib.sha256).hexdigest()


def get_csrf_token():
    """
    Generate CSRF token for forms.
    Returns a signed token (raw:timestamp:sig) so login/register still work when
    mobile browsers drop the session cookie between GET and POST.
    """
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_hex(32)
    # Ensure the session cookie is written on the form-render response
    session.permanent = True
    session.modified = True
    raw = session["csrf_token"]
    ts = str(int(time.time()))
    sig = _sign_csrf_payload(raw, ts)
    return f"{raw}:{ts}:{sig}"


def validate_csrf(token: str) -> bool:
    """Validate CSRF: session match OR self-validating signed token (mobile fallback)."""
    if not CSRF_PROTECTION:
        return True
    if not token:
        return False

    token = str(token).strip()
    expected = session.get("csrf_token")

    # Exact match against whatever we stored (legacy raw or prior signed value)
    if expected and secrets.compare_digest(str(expected), token):
        return True

    parts = token.split(":")
    if len(parts) == 3:
        raw, ts, sig = parts
        if not raw or not ts or not sig:
            return False
        try:
            age = abs(time.time() - int(ts))
        except (TypeError, ValueError):
            return False
        if age > CSRF_TOKEN_MAX_AGE_SECONDS:
            return False
        expected_sig = _sign_csrf_payload(raw, ts)
        if not secrets.compare_digest(expected_sig, sig):
            return False
        # Signed token is cryptographically valid (works even if session cookie dropped).
        return True

    # Legacy: form posted raw session token only
    if expected and secrets.compare_digest(str(expected), token):
        return True
    return False

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
    is_public_guest_mutation = path.startswith("/public/") and action in (
        "comment", "reply", "potluck", "submit_request"
    )

    # Auth entrypoints must stay reachable on mobile, shared carrier IPs (CGNAT),
    # and when session cookies are flaky between form GET and POST.
    is_auth_entry = bool(request.endpoint and str(request.endpoint).startswith("auth."))
    if not is_auth_entry:
        p = path.rstrip("/")
        is_auth_entry = p in (
            "/login", "/register", "/logout", "/login/2fa",
            "/request-reset-password", "/forgot-username",
            "/resend-verification", "/verify-email",
        ) or p.startswith("/reset-password") or p.startswith("/verify-email")

    # Display prefs + moderated guest prayer (theme/login-friendly church UX)
    path_norm = path.rstrip("/")
    is_ui_prefs = request.method == "POST" and path_norm.endswith("/ui-preferences")
    is_public_ui_prefs = is_ui_prefs and "/public/" in path_norm
    is_member_ui_prefs = is_ui_prefs and bool(session.get("user_id"))
    is_guest_prayer_add = request.method == "POST" and path_norm == "/prayers/add"
    member = _is_logged_in_member()
    # "Safe" means: never hard-block for HTTPS/reputation quirks (still CSRF-checked below)
    is_safe_mutation = (
        is_public_guest_mutation
        or is_auth_entry
        or is_public_ui_prefs
        or is_member_ui_prefs
        or is_ui_prefs
        or is_guest_prayer_add
        or member  # signed-in church members always usable even on http reverse-proxy mishaps
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

    # HTTPS: only hard-block *anonymous* mutations when REQUIRE_HTTPS is on.
    # Never brick logged-in members, login/register, or theme prefs (common proxy misconfig).
    if REQUIRE_HTTPS and not _request_is_https(request):
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH') and not is_safe_mutation:
            log_security_event("https_required", "Insecure anonymous POST blocked")
            return False
        elif request.method in ('POST', 'PUT', 'DELETE', 'PATCH') and member:
            log_security_event("https_required_soft", "Member POST over HTTP allowed (proxy/dev)", severity="low")

    ua = request.headers.get("User-Agent", "") or ""
    vetted = False
    try:
        vetted = bool(is_vetted())
    except Exception:
        vetted = False

    # UA hard-block: tools/scrapers only. Never block members, auth, or known browsers.
    if not is_auth_entry and not member and not vetted:
        if is_allowed_crawler(ua):
            pass
        elif is_suspicious_user_agent(ua):
            log_security_event("suspicious_ua", "Bot/scraper UA detected")
            increment_attack_stat("bot_attempt")
            # Only hard-block tool UAs on mutations; allow GET so church sites stay readable
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                return False

    if not check_rate_limit(ip):
        g.rate_limited = True
        log_security_event("rate_limit_exceeded", "IP exceeded rate limit")
        increment_attack_stat("ddos_attempts", penalize=not member)
        # Auth + members always continue. Guests: allow GET; soft-block spam POSTs only.
        if is_auth_entry or member or request.method in ("GET", "HEAD", "OPTIONS"):
            pass
        else:
            return False

    if is_locked_out():
        log_security_event("brute_force_lock", "IP is currently locked out")
        increment_attack_stat("brute_force", penalize=not member)
        # Members always continue. Auth pages stay open so people can still sign in.
        # Only block other anonymous mutations while the IP is in jail.
        if member or is_auth_entry:
            pass
        elif request.method in ("POST", "PUT", "DELETE", "PATCH"):
            return False

    score = get_reputation_score(ip)
    rep_floor = int(REPUTATION_BLOCK_THRESHOLD) if REPUTATION_BLOCK_THRESHOLD is not None else 8
    # Low reputation: hard-block only anonymous mutations. Members + GETs stay open.
    if score < rep_floor and not member and not is_auth_entry and not vetted:
        log_security_event("low_reputation", f"reputation score {score} below threshold {rep_floor}")
        increment_attack_stat("reputation_block", penalize=False)
        if request.method not in ("GET", "HEAD", "OPTIONS") and not is_safe_mutation:
            return False

    # CSRF for state changing requests
    if request.method in ("POST", "PUT", "DELETE", "PATCH") and CSRF_PROTECTION:
        csrf_token = (
            request.form.get("csrf_token")
            or request.headers.get("X-CSRF-Token")
            or request.headers.get("X-CSRFToken")
        )
        if not validate_csrf(csrf_token):
            log_security_event("csrf_failure", "CSRF token missing or invalid on " + request.method)
            # Auth entry: soft-fail so mobile WebViews can still log in (session cookie races).
            # Real app forms for members still hard-require CSRF.
            if is_auth_entry:
                logger("CSRF soft-allow on auth entry (mobile-friendly)")
            else:
                if not member:
                    increment_attack_stat("csrf_attack")
                return False

    token = request.headers.get("X-PBT-Token") or request.args.get("pbt_token")
    if token:
        if not validate_token(token, ip):
            log_security_event("invalid_token", "Token validation failed")
            increment_attack_stat("token_attack", penalize=not member)
            # Invalid custom token: ignore for browsers that send junk; only block if token required
            if not member and request.method not in ("GET", "HEAD", "OPTIONS"):
                return False

    # AUTO VET THE SESSION ON FIRST GOOD REQUEST
    if not is_vetted():
        mark_as_vetted()
        logger("AUTO-MARKED SESSION AS VETTED for IP " + (ip or "")[:8])

    # After auto-vet, guests should pass. Never block members for vetting.
    if not require_vetted() and not member and not is_auth_entry:
        if request.method not in ("GET", "HEAD", "OPTIONS") and not is_safe_mutation:
            log_security_event("not_vetted", "Session not vetted on mutation")
            return False
        # Soft: re-mark and continue for reads
        try:
            mark_as_vetted()
        except Exception:
            pass

    if DB_BULKHEAD_ENABLED:
        if hasattr(g, 'query_count') and g.query_count > N1_QUERY_THRESHOLD:
            log_security_event("n1_query_detected", "N+1 query threshold exceeded")
            increment_attack_stat("n1_attack", penalize=False)
            # Never hard-block members or GETs on internal query counting
            if not member and request.method not in ("GET", "HEAD", "OPTIONS"):
                return False

    record_good_behavior(ip)
    log_traffic(vetted=True, status="full_pass", score=score)
    g.pbt_vetted = True
    logger("FULL PIPELINE PASS | IP=" + (ip or "")[:8] + "... | SCORE=" + str(score))
    return True

def before_request_security():
    """MUST return None for Flask - this stops the exception"""
    start = time.time()
    if not run_full_security_pipeline():
        if BLOCK_ON_ANY_FAILURE:
            log_traffic(vetted=False, status="blocked")
            abort(403)
        return None
    # Optional soft stagger only (default 0ms). Never delay static or auth.
    path = (request.path or "")
    if (
        STAGGER_DELAY and STAGGER_DELAY > 0
        and not path.startswith(("/static/", "/favicon", "/sw.js"))
        and not (request.endpoint and str(request.endpoint).startswith("auth."))
        and not _is_logged_in_member()
    ):
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