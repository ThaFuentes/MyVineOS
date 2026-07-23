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
    MAX_NEGATIVE_POINTS,
)

REPUTATION_TABLE = "pbt_reputation"


def _is_loopback_or_local(ip: str | None) -> bool:
    """Local/dev/proxy IPs should never be reputation-jailed."""
    s = (ip or "").strip().lower()
    if not s:
        return False
    if s in ("127.0.0.1", "::1", "localhost", "0.0.0.0", "::"):
        return True
    if s.startswith("127."):
        return True
    # IPv6 loopback / unique-local common in docker/dev
    if s.startswith("::ffff:127."):
        return True
    return False


def _compute_score(positive: int, negative: int) -> int:
    """
    Climb with good traffic toward MAX_REPUTATION_SCORE (1000).
    Negatives barely matter so soft noise does not punish people.
    """
    pos = max(0, int(positive or 0))
    neg = min(max(0, int(negative or 0)), int(MAX_NEGATIVE_POINTS))
    # Base + 2 pts per good request; tiny negative weight only if penalties enabled
    score = int(INITIAL_REPUTATION) + (pos * 2) - (neg * 1)
    return max(MIN_REPUTATION_SCORE, min(MAX_REPUTATION_SCORE, score))


# ====================== GRADE SYSTEM ======================
def _get_grade(score: int) -> str:
    if score >= 800:
        return "trusted"
    elif score >= 500:
        return "trusted"
    elif score >= 100:
        return "normal"
    elif score >= 50:
        return "watch"
    elif score >= 20:
        return "suspicious"
    else:
        return "temp_ban"


def _row_to_dict(cursor, row) -> dict:
    if isinstance(row, dict):
        return dict(row)
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def _force_numeric(row_dict: dict) -> dict:
    for key in ["score", "positive_requests", "negative_points", "ban_count"]:
        if row_dict.get(key) is not None:
            try:
                row_dict[key] = int(row_dict[key])
            except (ValueError, TypeError):
                row_dict[key] = 0
    return row_dict


def _recalc_and_store(cursor, db, ip: str, row_dict: dict) -> int:
    positive = int(row_dict.get("positive_requests", 0) or 0)
    negative = min(int(row_dict.get("negative_points", 0) or 0), int(MAX_NEGATIVE_POINTS))
    # Localhost / 127.x always climb freely and never sit in ban grades from soft noise
    if _is_loopback_or_local(ip):
        negative = 0
        score = _compute_score(positive, 0)
        # Ensure local always has at least a healthy floor and can reach the cap
        score = max(score, min(MAX_REPUTATION_SCORE, INITIAL_REPUTATION + positive * 2))
    else:
        score = _compute_score(positive, negative)
    grade = _get_grade(score)
    # Never auto-grade loopback into temp_ban from score math
    if _is_loopback_or_local(ip) and grade in ("temp_ban", "suspicious"):
        grade = "normal" if score < 500 else "trusted"
    cursor.execute(
        f"UPDATE {REPUTATION_TABLE} SET score=%s, grade=%s, last_seen=NOW() WHERE ip=%s",
        (score, grade, ip),
    )
    db.commit()
    return score


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
        # First time seen — local starts healthy
        start = INITIAL_REPUTATION
        grade = _get_grade(start)
        cursor.execute(f"""
            INSERT INTO {REPUTATION_TABLE}
            (ip, score, grade, positive_requests, negative_points, first_seen, last_seen)
            VALUES (%s, %s, %s, 0, 0, NOW(), NOW())
        """, (ip, start, grade))
        db.commit()
        return start

    row_dict = _force_numeric(_row_to_dict(cursor, row))

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

    # Decay negative points over time (loopback: wipe negatives)
    if _is_loopback_or_local(ip) and int(row_dict.get("negative_points", 0) or 0) > 0:
        cursor.execute(
            f"UPDATE {REPUTATION_TABLE} SET negative_points=0 WHERE ip=%s",
            (ip,),
        )
        db.commit()
        row_dict["negative_points"] = 0
    elif row_dict.get("negative_points", 0) > 0 and row_dict.get("last_bad_behavior"):
        try:
            hours = (datetime.now() - row_dict["last_bad_behavior"]).total_seconds() / 3600
            decay_amount = int(hours * REPUTATION_DECAY_PER_HOUR)
            new_negative = max(0, row_dict["negative_points"] - decay_amount)
            cursor.execute(
                f"UPDATE {REPUTATION_TABLE} SET negative_points=%s WHERE ip=%s",
                (new_negative, ip),
            )
            db.commit()
            row_dict["negative_points"] = new_negative
        except Exception as e:
            logger("Reputation decay failed: " + str(e))

    return _recalc_and_store(cursor, db, ip, row_dict)

def is_fast_laned(ip: str) -> bool:
    return get_reputation_score(ip) >= FAST_LANE_THRESHOLD

def is_strict_check(ip: str) -> bool:
    return get_reputation_score(ip) < STRICT_MODE_THRESHOLD

def record_good_behavior(ip: str):
    db = get_security_db()
    if db is None or not ip:
        return
    cursor = db.cursor()
    # Heal any residual negatives when the visitor is using the site normally
    heal = max(1, int(GOOD_BEHAVIOR_BONUS // 2) or 1)
    # Loopback: clear negatives completely and count positives freely
    if _is_loopback_or_local(ip):
        heal = max(heal, int(MAX_NEGATIVE_POINTS))
    cursor.execute(f"""
        INSERT INTO {REPUTATION_TABLE} (ip, positive_requests, negative_points, last_seen, score, grade)
        VALUES (%s, 1, 0, NOW(), %s, %s)
        ON DUPLICATE KEY UPDATE
            positive_requests = positive_requests + 1,
            negative_points = GREATEST(0, negative_points - %s),
            last_seen = NOW()
    """, (ip, INITIAL_REPUTATION, _get_grade(INITIAL_REPUTATION), heal))
    db.commit()
    # Immediately recompute score so UI / next read sees growth (up to 1000)
    cursor.execute(f"SELECT * FROM {REPUTATION_TABLE} WHERE ip = %s", (ip,))
    row = cursor.fetchone()
    if row:
        row_dict = _force_numeric(_row_to_dict(cursor, row))
        _recalc_and_store(cursor, db, ip, row_dict)

def record_bad_behavior(ip: str, reason: str = "suspicious"):
    """
    Soft "bad request" noise must NOT punish real people or localhost.

    With BAD_BEHAVIOR_PENALTY=0 this is effectively a no-op on score.
    Loopback / 127.x never receives penalties.
    Rate limits and hard blocks still work independently of reputation.
    """
    if not ip or _is_loopback_or_local(ip):
        return
    pen = int(BAD_BEHAVIOR_PENALTY or 0)
    if pen <= 0:
        # Do not lower reputation for ordinary bad requests
        return
    db = get_security_db()
    if db is None:
        return
    cap = max(pen, int(MAX_NEGATIVE_POINTS))
    cursor = db.cursor()
    cursor.execute(f"""
        INSERT INTO {REPUTATION_TABLE} (ip, negative_points, last_bad_behavior, last_seen, score, grade)
        VALUES (%s, %s, NOW(), NOW(), %s, 'watch')
        ON DUPLICATE KEY UPDATE
            negative_points = LEAST(%s, negative_points + %s),
            last_bad_behavior = NOW(),
            last_seen = NOW()
    """, (ip, pen, INITIAL_REPUTATION, cap, pen))
    db.commit()

def ban_ip(ip: str, reason: str, permanent: bool = False, hours: int = 1):
    db = get_security_db()
    if db is None:
        return
    cursor = db.cursor()
    # Ensure row exists
    cursor.execute(f"""
        INSERT INTO {REPUTATION_TABLE} (ip, score, grade, positive_requests, negative_points, first_seen, last_seen)
        VALUES (%s, %s, 'normal', 0, 0, NOW(), NOW())
        ON DUPLICATE KEY UPDATE last_seen = NOW()
    """, (ip, INITIAL_REPUTATION))
    if permanent:
        cursor.execute(f"""
            UPDATE {REPUTATION_TABLE}
            SET grade='perm_ban', ban_until=NULL, ban_reason=%s, ban_count=ban_count+1
            WHERE ip=%s
        """, (reason, ip))
    else:
        ban_until = datetime.now() + timedelta(hours=max(1, int(hours or 1)))
        cursor.execute(f"""
            UPDATE {REPUTATION_TABLE}
            SET grade='temp_ban', ban_until=%s, ban_reason=%s, ban_count=ban_count+1
            WHERE ip=%s
        """, (ban_until, reason, ip))
    db.commit()


def unban_ip(ip: str, restore_score: int | None = 80) -> bool:
    """
    Clear temp/perm ban for an IP and optionally restore a usable reputation score
    so legitimate users are not stuck blocked after a false positive.
    """
    db = get_security_db()
    if db is None:
        return False
    cursor = db.cursor()
    score = INITIAL_REPUTATION if restore_score is None else int(restore_score)
    score = max(MIN_REPUTATION_SCORE, min(MAX_REPUTATION_SCORE, score))
    grade = _get_grade(score)
    cursor.execute(f"""
        UPDATE {REPUTATION_TABLE}
        SET grade=%s,
            ban_until=NULL,
            ban_reason=NULL,
            negative_points=LEAST(negative_points, 5),
            score=%s,
            last_seen=NOW()
        WHERE ip=%s
    """, (grade, score, ip))
    affected = cursor.rowcount
    db.commit()
    return affected > 0


def trust_ip(ip: str, score: int = 500) -> bool:
    """Boost an IP into a healthy lane (for known-good church members / office IP)."""
    db = get_security_db()
    if db is None:
        return False
    cursor = db.cursor()
    score = max(MIN_REPUTATION_SCORE, min(MAX_REPUTATION_SCORE, int(score)))
    grade = _get_grade(score)
    # positive_requests consistent with score formula so get_reputation won't yank it down
    pos_for_score = max(0, (score - int(INITIAL_REPUTATION)) // 2)
    cursor.execute(f"""
        INSERT INTO {REPUTATION_TABLE}
            (ip, score, grade, positive_requests, negative_points, ban_until, ban_reason, first_seen, last_seen)
        VALUES (%s, %s, %s, %s, 0, NULL, NULL, NOW(), NOW())
        ON DUPLICATE KEY UPDATE
            score=%s,
            grade=%s,
            positive_requests=GREATEST(positive_requests, %s),
            negative_points=0,
            ban_until=NULL,
            ban_reason=NULL,
            last_seen=NOW()
    """, (ip, score, grade, pos_for_score, score, grade, pos_for_score))
    db.commit()
    return True


logger(
    "poweredbytop/reputation/scorer.py - loaded "
    f"(max_score={MAX_REPUTATION_SCORE}, no soft bad-request penalties, loopback protected)"
)