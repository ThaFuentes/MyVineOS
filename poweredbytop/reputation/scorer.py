# ================================================================
# poweredbytop/reputation/scorer.py
# REPUTATION SCORING + GRADE SYSTEM + ADAPTIVE CHECKING
# 100% FRESH REBUILD - DYNAMIC COLUMN MAPPING FOR YOUR EXACT TABLE
# ================================================================
# MARIADB ONLY - EXACT pbt_reputation TABLE ONLY - NO SCHEMA CHANGES
# ================================================================

import time
from datetime import datetime, timedelta

# ====================== SAFE IMPORTS ======================
from poweredbytop.models.connect_db import get_security_db
from poweredbytop.utils.helpers import logger
from poweredbytop.config.settings import (
    MAX_REPUTATION_SCORE,
    MIN_REPUTATION_SCORE,
    INITIAL_REPUTATION,
    GOOD_BEHAVIOR_BONUS,
    BAD_BEHAVIOR_PENALTY,
    REPUTATION_DECAY_PER_HOUR,
    FAST_LANE_THRESHOLD,
    STRICT_MODE_THRESHOLD,
)

REPUTATION_TABLE = "pbt_reputation"

# ====================== GRADE SYSTEM ======================
def _get_grade(score: int) -> str:
    if score >= 500:
        return "trusted"
    elif score >= 100:
        return "normal"
    elif score >= 50:
        return "watch"
    elif score >= 20:
        return "suspicious"
    else:
        return "temp_ban"

# ====================== PUBLIC API ======================
def get_reputation_score(ip: str) -> int:
    """Return current reputation score - dynamic column mapping for your exact table"""
    db = get_security_db()
    if db is None:
        return INITIAL_REPUTATION

    cursor = db.cursor()
    cursor.execute(f"SELECT * FROM {REPUTATION_TABLE} WHERE ip = %s", (ip,))
    row = cursor.fetchone()

    if not row:
        # First time seen
        cursor.execute(f"""
            INSERT INTO {REPUTATION_TABLE}
            (ip, score, grade, positive_requests, negative_points, first_seen, last_seen)
            VALUES (%s, %s, %s, 0, 0, NOW(), NOW())
        """, (ip, INITIAL_REPUTATION, "normal"))
        db.commit()
        return INITIAL_REPUTATION

    # Dynamic column mapping - robust to DictCursor (from connect_db) or tuple
    if isinstance(row, dict):
        row_dict = dict(row)  # already dict-like
    else:
        columns = [desc[0] for desc in cursor.description]
        row_dict = dict(zip(columns, row))

    # Force numeric types safely (pymysql returns strings)
    for key in ["score", "positive_requests", "negative_points", "ban_count"]:
        if row_dict.get(key) is not None:
            try:
                row_dict[key] = int(row_dict[key])
            except (ValueError, TypeError):
                row_dict[key] = 0

    # Auto-expire temp bans
    if row_dict.get("ban_until"):
        try:
            if datetime.now() > row_dict["ban_until"]:
                cursor.execute(f"""
                    UPDATE {REPUTATION_TABLE}
                    SET grade='suspicious', ban_until=NULL, ban_reason=NULL
                    WHERE ip=%s
                """, (ip,))
                db.commit()
        except Exception as e:
            logger("Reputation ban expiry check failed: " + str(e))

    # Decay negative points over time
    if row_dict.get("negative_points", 0) > 0 and row_dict.get("last_bad_behavior"):
        try:
            hours = (datetime.now() - row_dict["last_bad_behavior"]).total_seconds() / 3600
            decay_amount = int(hours * REPUTATION_DECAY_PER_HOUR)
            new_negative = max(0, row_dict["negative_points"] - decay_amount)
            cursor.execute(f"UPDATE {REPUTATION_TABLE} SET negative_points=%s WHERE ip=%s", (new_negative, ip))
            db.commit()
        except Exception as e:
            logger("Reputation decay failed: " + str(e))

    # Recalculate score
    positive = row_dict.get("positive_requests", 0)
    negative = row_dict.get("negative_points", 0)
    score = 100 + (positive * 2) - (negative * 10)
    score = max(MIN_REPUTATION_SCORE, min(MAX_REPUTATION_SCORE, score))

    grade = _get_grade(score)

    cursor.execute(f"UPDATE {REPUTATION_TABLE} SET score=%s, grade=%s, last_seen=NOW() WHERE ip=%s", (score, grade, ip))
    db.commit()

    return score

def is_fast_laned(ip: str) -> bool:
    return get_reputation_score(ip) >= FAST_LANE_THRESHOLD

def is_strict_check(ip: str) -> bool:
    return get_reputation_score(ip) < STRICT_MODE_THRESHOLD

def record_good_behavior(ip: str):
    db = get_security_db()
    if db is None:
        return
    cursor = db.cursor()
    cursor.execute(f"""
        INSERT INTO {REPUTATION_TABLE} (ip, positive_requests, last_seen)
        VALUES (%s, 1, NOW())
        ON DUPLICATE KEY UPDATE
            positive_requests = positive_requests + 1,
            negative_points = GREATEST(0, negative_points - 1),
            last_seen = NOW()
    """, (ip,))
    db.commit()

def record_bad_behavior(ip: str, reason: str = "suspicious"):
    db = get_security_db()
    if db is None:
        return
    cursor = db.cursor()
    cursor.execute(f"""
        INSERT INTO {REPUTATION_TABLE} (ip, negative_points, last_bad_behavior, last_seen)
        VALUES (%s, %s, NOW(), NOW())
        ON DUPLICATE KEY UPDATE
            negative_points = negative_points + %s,
            last_bad_behavior = NOW(),
            last_seen = NOW()
    """, (ip, BAD_BEHAVIOR_PENALTY, BAD_BEHAVIOR_PENALTY))
    db.commit()

def ban_ip(ip: str, reason: str, permanent: bool = False):
    db = get_security_db()
    if db is None:
        return
    cursor = db.cursor()
    if permanent:
        cursor.execute(f"""
            UPDATE {REPUTATION_TABLE}
            SET grade='perm_ban', ban_until=NULL, ban_reason=%s, ban_count=ban_count+1
            WHERE ip=%s
        """, (reason, ip))
    else:
        ban_until = datetime.now() + timedelta(hours=1)
        cursor.execute(f"""
            UPDATE {REPUTATION_TABLE}
            SET grade='temp_ban', ban_until=%s, ban_reason=%s, ban_count=ban_count+1
            WHERE ip=%s
        """, (ban_until, reason, ip))
    db.commit()

logger("poweredbytop/reputation/scorer.py - 100% fresh rebuild loaded successfully (dynamic column mapping fixed)")