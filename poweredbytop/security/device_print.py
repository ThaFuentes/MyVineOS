# ===========================================================
# poweredbytop/security/device_print.py
# Device + request fingerprints for smarter bans (office-safe).
# Ban the attacker pattern, not the whole office NAT IP alone.
# ===========================================================
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

from flask import g, has_request_context, request

from poweredbytop.models.connect_db import get_security_db, close_security_db
from poweredbytop.utils.helpers import get_real_ip, logger

DEVICE_TABLE = "pbt_device_prints"
DEVICE_BAN_TABLE = "pbt_device_bans"


def _h(parts: list[str]) -> str:
    raw = "|".join((p or "").strip().lower() for p in parts)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:40]


def build_device_fingerprint(ip: str | None = None) -> dict[str, str]:
    """
    Stable-ish print for this browser on this network.
    Does NOT use cookies (works pre-login). Safe defaults off-request.
    """
    if not has_request_context():
        return {
            "device_fp": _h([ip or "0.0.0.0", "no-request"]),
            "ua_hash": "",
            "ip": ip or "0.0.0.0",
        }
    ip = ip or get_real_ip()
    ua = (request.headers.get("User-Agent") or "")[:500]
    al = (request.headers.get("Accept-Language") or "")[:120]
    ae = (request.headers.get("Accept-Encoding") or "")[:80]
    # Optional client hint if browser sends it
    ch_ua = (request.headers.get("Sec-CH-UA") or "")[:200]
    platform = (request.headers.get("Sec-CH-UA-Platform") or "")[:80]
    ua_hash = _h([ua, al, ae, ch_ua, platform])
    # Device print = browser family + language + platform (NOT pure IP)
    # so two users on same office IP get different prints when UAs differ.
    device_fp = _h([ua_hash, al[:40], platform or "unknown"])
    return {
        "device_fp": device_fp,
        "ua_hash": ua_hash,
        "ip": ip,
        "ua": ua[:255],
        "accept_language": al[:80],
    }


def ensure_device_tables() -> None:
    db = get_security_db()
    if db is None:
        return
    try:
        cur = db.cursor()
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {DEVICE_TABLE} (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                device_fp VARCHAR(40) NOT NULL,
                ip VARCHAR(45) NOT NULL,
                ua_hash VARCHAR(40) NULL,
                user_agent VARCHAR(255) NULL,
                accept_language VARCHAR(80) NULL,
                user_id INT NULL,
                hit_count INT NOT NULL DEFAULT 1,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_path VARCHAR(255) NULL,
                last_method VARCHAR(10) NULL,
                risk_score INT NOT NULL DEFAULT 0,
                notes TEXT NULL,
                UNIQUE KEY uq_device_ip (device_fp, ip),
                KEY idx_pbt_dev_ip (ip),
                KEY idx_pbt_dev_fp (device_fp),
                KEY idx_pbt_dev_user (user_id),
                KEY idx_pbt_dev_last (last_seen)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {DEVICE_BAN_TABLE} (
                device_fp VARCHAR(40) PRIMARY KEY,
                ban_until DATETIME NULL,
                ban_reason VARCHAR(500) NULL,
                ban_count INT NOT NULL DEFAULT 0,
                permanent TINYINT(1) NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                KEY idx_pbt_devban_until (ban_until)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        db.commit()
    except Exception as e:
        logger(f"[DEVICE] ensure tables failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        close_security_db(db)


def record_device_sighting(
    *,
    user_id: int | None = None,
    path: str | None = None,
    method: str | None = None,
    risk_delta: int = 0,
    notes: str | None = None,
) -> dict[str, Any]:
    """Upsert device+ip sighting. Never raises."""
    ensure_device_tables()
    info = build_device_fingerprint()
    ip = info["ip"]
    fp = info["device_fp"]
    try:
        g.pbt_device_fp = fp
        g.pbt_device_info = info
    except Exception:
        pass

    db = get_security_db()
    if db is None:
        return info
    try:
        cur = db.cursor()
        path_s = (path or (request.path if has_request_context() else ""))[:255]
        method_s = (method or (request.method if has_request_context() else "GET"))[:10]
        ua = (info.get("ua") or "")[:255]
        al = (info.get("accept_language") or "")[:80]
        ua_hash = info.get("ua_hash") or ""
        note = (notes or "")[:500] if notes else None
        # risk_score only climbs on risk_delta > 0
        cur.execute(
            f"""
            INSERT INTO {DEVICE_TABLE}
                (device_fp, ip, ua_hash, user_agent, accept_language, user_id,
                 hit_count, first_seen, last_seen, last_path, last_method, risk_score, notes)
            VALUES (%s,%s,%s,%s,%s,%s,1,NOW(),NOW(),%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                hit_count = hit_count + 1,
                last_seen = NOW(),
                last_path = VALUES(last_path),
                last_method = VALUES(last_method),
                user_agent = COALESCE(VALUES(user_agent), user_agent),
                accept_language = COALESCE(VALUES(accept_language), accept_language),
                user_id = COALESCE(VALUES(user_id), user_id),
                risk_score = LEAST(1000, risk_score + VALUES(risk_score)),
                notes = COALESCE(VALUES(notes), notes)
            """,
            (
                fp,
                ip,
                ua_hash,
                ua or None,
                al or None,
                int(user_id) if user_id else None,
                path_s or None,
                method_s or None,
                max(0, int(risk_delta or 0)),
                note,
            ),
        )
        db.commit()
    except Exception as e:
        logger(f"[DEVICE] record failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        close_security_db(db)
    return info


def is_device_banned(device_fp: str | None = None) -> dict[str, Any]:
    """Return ban info if this device fingerprint is actively banned."""
    ensure_device_tables()
    fp = device_fp or (getattr(g, "pbt_device_fp", None) if has_request_context() else None)
    if not fp:
        info = build_device_fingerprint()
        fp = info["device_fp"]
    db = get_security_db()
    if db is None:
        return {"is_banned": False, "device_fp": fp}
    try:
        cur = db.cursor()
        cur.execute(
            f"""
            SELECT device_fp, ban_until, ban_reason, ban_count, permanent
            FROM {DEVICE_BAN_TABLE} WHERE device_fp = %s
            """,
            (fp,),
        )
        row = cur.fetchone() or {}
        if not row:
            return {"is_banned": False, "device_fp": fp}
        permanent = bool(row.get("permanent"))
        until = row.get("ban_until")
        now = datetime.now()
        active = permanent or (until is not None and until > now)
        return {
            "is_banned": active,
            "device_fp": fp,
            "ban_until": until,
            "ban_reason": row.get("ban_reason"),
            "ban_count": int(row.get("ban_count") or 0),
            "permanent": permanent,
        }
    except Exception as e:
        logger(f"[DEVICE] is_device_banned failed: {e}")
        return {"is_banned": False, "device_fp": fp}
    finally:
        close_security_db(db)


def ban_device(
    device_fp: str,
    reason: str,
    *,
    hours: int = 6,
    permanent: bool = False,
) -> None:
    ensure_device_tables()
    if not device_fp:
        return
    db = get_security_db()
    if db is None:
        return
    try:
        cur = db.cursor()
        if permanent:
            cur.execute(
                f"""
                INSERT INTO {DEVICE_BAN_TABLE}
                    (device_fp, ban_until, ban_reason, ban_count, permanent)
                VALUES (%s, NULL, %s, 1, 1)
                ON DUPLICATE KEY UPDATE
                    ban_until=NULL, ban_reason=VALUES(ban_reason),
                    ban_count=ban_count+1, permanent=1, updated_at=NOW()
                """,
                (device_fp, (reason or "device ban")[:500]),
            )
        else:
            hours = max(1, min(int(hours or 6), 168))
            until = datetime.now() + timedelta(hours=hours)
            cur.execute(
                f"""
                INSERT INTO {DEVICE_BAN_TABLE}
                    (device_fp, ban_until, ban_reason, ban_count, permanent)
                VALUES (%s, %s, %s, 1, 0)
                ON DUPLICATE KEY UPDATE
                    ban_until=GREATEST(COALESCE(ban_until, %s), %s),
                    ban_reason=VALUES(ban_reason),
                    ban_count=ban_count+1,
                    permanent=0,
                    updated_at=NOW()
                """,
                (
                    device_fp,
                    until,
                    (reason or "device ban")[:500],
                    until,
                    until,
                ),
            )
        db.commit()
        logger(f"[DEVICE] BANNED fp={device_fp[:12]}... permanent={permanent} reason={reason[:80]}")
    except Exception as e:
        logger(f"[DEVICE] ban_device failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        close_security_db(db)


def unban_device(device_fp: str) -> bool:
    ensure_device_tables()
    if not device_fp:
        return False
    db = get_security_db()
    if db is None:
        return False
    try:
        cur = db.cursor()
        cur.execute(f"DELETE FROM {DEVICE_BAN_TABLE} WHERE device_fp = %s", (device_fp,))
        db.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger(f"[DEVICE] unban failed: {e}")
        return False
    finally:
        close_security_db(db)


def ip_has_established_good_history(ip: str, *, min_positive: int = 50) -> bool:
    """True if this IP is a known-good office-style address (many good hits)."""
    if not ip:
        return False
    db = get_security_db()
    if db is None:
        return False
    try:
        cur = db.cursor()
        cur.execute(
            """
            SELECT positive_requests, score, grade
            FROM pbt_reputation WHERE ip = %s
            """,
            (ip,),
        )
        row = cur.fetchone() or {}
        pos = int(row.get("positive_requests") or 0)
        score = int(row.get("score") or 0)
        grade = (row.get("grade") or "").lower()
        return pos >= min_positive or score >= 400 or grade in ("trusted", "good")
    except Exception:
        return False
    finally:
        close_security_db(db)


def count_devices_on_ip(ip: str) -> int:
    ensure_device_tables()
    if not ip:
        return 0
    db = get_security_db()
    if db is None:
        return 0
    try:
        cur = db.cursor()
        cur.execute(
            f"SELECT COUNT(DISTINCT device_fp) AS c FROM {DEVICE_TABLE} WHERE ip = %s",
            (ip,),
        )
        row = cur.fetchone() or {}
        return int(row.get("c") or 0)
    except Exception:
        return 0
    finally:
        close_security_db(db)


def request_audit_context() -> dict[str, Any]:
    """Compact context for security_events / audit logs."""
    info = build_device_fingerprint()
    path = ""
    method = "GET"
    if has_request_context():
        path = (request.path or "")[:255]
        method = (request.method or "GET")[:10]
    user_id = None
    try:
        from flask import session as flask_session
        uid = flask_session.get("user_id")
        user_id = int(uid) if uid is not None else None
    except Exception:
        user_id = None
    return {
        "ip": info.get("ip"),
        "device_fp": info.get("device_fp"),
        "ua_hash": info.get("ua_hash"),
        "user_agent": (info.get("ua") or "")[:255],
        "path": path,
        "method": method,
        "user_id": user_id,
    }
