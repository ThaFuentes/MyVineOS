# ================================================================
# poweredbytop/throttling/rate_limit.py
# Sliding Window Rate Limiting + Stagger + Jail System
# 100% FRESH REBUILD - SECURITY FIRST - MATCHES FULL PIPELINE
# ================================================================
# MARIADB ONLY - EXACT DB TABLES ONLY - NO INSTANCE FOLDER - NO SQLITE - NO JSON
# INTEGRATES WITH core/security.py + reputation/scorer.py
# ================================================================

import time
from collections import defaultdict
from flask import request, g

# ====================== SAFE IMPORTS ======================
from poweredbytop.config.settings import (
    GLOBAL_RATE_LIMIT,
    PER_IP_RATE_LIMIT,
    RATE_WINDOW_SECONDS,
    STAGGER_DELAY_MS,
    BURST_TOLERANCE,
    JAIL_THRESHOLD,
    JAIL_DURATION_SECONDS,
)
from poweredbytop.utils.helpers import get_real_ip, is_internal_request, logger
from poweredbytop.reputation.scorer import record_bad_behavior

# ====================== IN-MEMORY STORES (single server) ======================
global_requests = []
ip_requests: defaultdict[list] = defaultdict(list)
ip_jail: dict = {}

# ====================== SLIDING WINDOW HELPERS ======================
def _clean_old_requests(timestamps: list, window: int) -> list:
    now = time.time()
    return [ts for ts in timestamps if now - ts <= window]

def _check_limit(current_list: list, limit: int, window: int, burst: int = 0) -> bool:
    cleaned = _clean_old_requests(current_list, window)
    if len(cleaned) >= limit + burst:
        return False
    return True

# ====================== STAGGER HELPER ======================
def apply_stagger():
    """Anti-refresh-spam stagger - called after every request in core/security.py"""
    if STAGGER_DELAY_MS > 0:
        time.sleep(STAGGER_DELAY_MS / 1000.0)
    logger("STAGGER: Applied " + str(STAGGER_DELAY_MS) + "ms delay for IP " + get_real_ip(request)[:8] + "...")

# ====================== MAIN RATE LIMIT CHECK ======================
def check_rate_limit(ip: str) -> bool:
    """Called from core/security.py pipeline - returns True only on pass"""
    if not ip:
        ip = get_real_ip(request)

    now = time.time()

    if is_internal_request(request):
        g.rate_limited = False
        return True

    # JAIL CHECK
    if ip in ip_jail and ip_jail[ip] > now:
        remaining = int(ip_jail[ip] - now)
        logger("IP " + ip[:8] + "... is JAILED - " + str(remaining) + "s remaining")
        g.rate_limited = True
        record_bad_behavior(ip)
        return False

    # GLOBAL RATE LIMIT (DDoS protection)
    global global_requests
    global_requests = _clean_old_requests(global_requests, RATE_WINDOW_SECONDS)
    if not _check_limit(global_requests, GLOBAL_RATE_LIMIT, RATE_WINDOW_SECONDS):
        logger("GLOBAL rate limit exceeded - IP " + ip[:8] + "...")
        record_bad_behavior(ip)
        g.rate_limited = True
        return False

    # PER-IP RATE LIMIT
    ip_list = ip_requests[ip]
    ip_list = _clean_old_requests(ip_list, RATE_WINDOW_SECONDS)
    ip_requests[ip] = ip_list
    if not _check_limit(ip_list, PER_IP_RATE_LIMIT, RATE_WINDOW_SECONDS, BURST_TOLERANCE):
        logger("Per-IP rate limit hit - IP " + ip[:8] + "...")
        record_bad_behavior(ip)
        g.rate_limited = True
        return False

    # Record request
    global_requests.append(now)
    ip_requests[ip].append(now)
    g.rate_limited = False
    return True

# ====================== JAIL SYSTEM ======================
def jail_ip(client_ip: str = None):
    if not client_ip:
        client_ip = get_real_ip(request)
    if is_internal_request(request):
        return
    ip_jail[client_ip] = time.time() + JAIL_DURATION_SECONDS
    logger("IP " + client_ip[:8] + "... JAILED for " + str(JAIL_DURATION_SECONDS) + "s")
    record_bad_behavior(client_ip)

def is_jailed(client_ip: str = None) -> bool:
    if not client_ip:
        client_ip = get_real_ip(request)
    if is_internal_request(request):
        return False
    expiry = ip_jail.get(client_ip, 0)
    return expiry > time.time()

# ====================== FINAL EXPORTS ======================
__all__ = [
    "check_rate_limit",
    "apply_stagger",
    "jail_ip",
    "is_jailed"
]

logger("poweredbytop/throttling/rate_limit.py - 100% fresh rebuild loaded successfully (ready for full pipeline)")