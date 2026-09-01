# ================================================================
# poweredbytop/firewall/tokens.py
# HMAC-SHA256 Token System - Sovereign Security Core
# 100% FRESH REBUILD - EMPTY TOKEN NOW PASSES (NORMAL BROWSER TRAFFIC)
# ================================================================
# MARIADB ONLY - EXACT DB TABLES ONLY - NO INSTANCE FOLDER - NO SQLITE - NO JSON
# INTEGRATES WITH core/security.py + reputation/scorer.py
# ================================================================

import time
import base64
import hashlib
import hmac
from typing import Optional

# ====================== SAFE IMPORTS ======================
from poweredbytop.config.settings import (
    TOKEN_SECRET,
    TOKEN_LIFETIME_SECONDS,
    HMAC_ALGORITHM,
)
from poweredbytop.utils.helpers import get_real_ip, logger
from poweredbytop.reputation.scorer import record_bad_behavior

# ====================== TOKEN GENERATION ======================
def generate_token(client_ip: str, additional_data: str = "") -> str:
    """Generate HMAC-SHA256 token bound to IP + timestamp"""
    if not TOKEN_SECRET or len(TOKEN_SECRET) < 32:
        logger("CRITICAL: TOKEN_SECRET is missing or too weak - aborting token generation")
        raise ValueError("Invalid TOKEN_SECRET - check settings.py")

    timestamp = int(time.time())
    payload = f"{client_ip}|{timestamp}|{additional_data}".encode("utf-8")
    signature = hmac.new(
        TOKEN_SECRET.encode("utf-8"),
        payload,
        getattr(hashlib, HMAC_ALGORITHM)
    ).digest()
    token = base64.urlsafe_b64encode(payload + signature).decode("utf-8").rstrip("=")
    return token

# ====================== TOKEN VALIDATION ======================
def validate_token(token: str, client_ip: str) -> bool:
    """Validate token - EMPTY TOKEN NOW PASSES (this is what lets normal browser requests get vetted)"""
    if not token or not client_ip:
        logger("No token provided - normal browser request allowed (vetting can proceed)")
        return True

    try:
        # Fix padding for base64
        padding = len(token) % 4
        if padding:
            token += "=" * (4 - padding)

        decoded = base64.urlsafe_b64decode(token)
        payload = decoded[:-32]
        signature = decoded[-32:]

        expected_sig = hmac.new(
            TOKEN_SECRET.encode("utf-8"),
            payload,
            getattr(hashlib, HMAC_ALGORITHM)
        ).digest()

        if not hmac.compare_digest(signature, expected_sig):
            logger("Invalid token signature from IP " + client_ip[:8] + "...")
            record_bad_behavior(client_ip)
            return False

        # Parse payload
        parts = payload.decode("utf-8").split("|", 2)
        original_ip = parts[0]
        original_ts = int(parts[1])

        if original_ip != client_ip:
            logger("Token IP mismatch: expected " + original_ip[:8] + "..., got " + client_ip[:8] + "...")
            record_bad_behavior(client_ip)
            return False

        age = int(time.time()) - original_ts
        if age < 0 or age > TOKEN_LIFETIME_SECONDS:
            logger("Token expired or future-dated (age=" + str(age) + "s)")
            record_bad_behavior(client_ip)
            return False

        logger("Token validated successfully for IP " + client_ip[:8] + "...")
        return True

    except Exception as e:
        logger("Token validation failed: " + str(e))
        record_bad_behavior(client_ip)
        return False

# ====================== FINAL EXPORTS ======================
__all__ = ["generate_token", "validate_token"]

logger("poweredbytop/firewall/tokens.py - 100% fresh rebuild loaded successfully (empty token now passes)")