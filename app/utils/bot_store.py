"""Database work for Bot Access. Rules live in bot_policy."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from app.models.db import get_db
from app.utils import bot_policy as policy

READ_LIMIT = 40


def _cur():
    return get_db().cursor()


def _cell(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return None
    return value


def _clean(row: dict | None) -> dict:
    return {key: _cell(val) for key, val in (row or {}).items()}


def _key_view(row: dict) -> dict:
    out = _clean(row)
    for secret in ("key_hash", "twofa_hash", "session_hash"):
        out.pop(secret, None)
    out["active"] = bool(row.get("active"))
    out["controls"] = policy.normalize_controls(row.get("controls_json"))
    return out


def list_members() -> list[dict]:
    try:
        cur = _cur()
        cur.execute(
            """
            SELECT id, username, first_name, last_name, role
            FROM users
            ORDER BY first_name ASC, last_name ASC, username ASC
            LIMIT 500
            """
        )
        rows = []
        for row in cur.fetchall() or []:
            item = _clean(row)
            item["label"] = policy.person_label(item)
            rows.append(item)
        return rows
    except Exception as exc:
        print(f"bot list_members: {exc}")
        return []


def ensure_login_columns() -> None:
    """Add the two-inbox columns on a database created before this sign-in."""
    columns = (
        ("email", "VARCHAR(160) NULL"),
        ("twofa_email", "VARCHAR(160) NULL"),
        ("twofa_hash", "CHAR(64) NULL"),
        ("twofa_expires", "DATETIME NULL"),
        ("twofa_attempts", "INT NOT NULL DEFAULT 0"),
        ("session_hash", "CHAR(64) NULL"),
        ("session_expires", "DATETIME NULL"),
    )
    try:
        cur = _cur()
        for column, definition in columns:
            cur.execute(
                """
                SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bot_access_keys' AND COLUMN_NAME = %s
                """,
                (column,),
            )
            if cur.fetchone():
                continue
            cur.execute(f"ALTER TABLE bot_access_keys ADD COLUMN {column} {definition}")
    except Exception as exc:
        print(f"bot login columns: {exc}")


def set_inboxes(key_id: int, key_email: str, twofa_email: str) -> tuple[bool, str]:
    problem = policy.inbox_problem(key_email, twofa_email)
    if problem:
        return False, problem
    try:
        ensure_login_columns()
        cur = _cur()
        cur.execute(
            "UPDATE bot_access_keys SET email=%s, twofa_email=%s WHERE id=%s",
            (policy.normalize_email(key_email), policy.normalize_email(twofa_email), int(key_id)),
        )
        return True, ""
    except Exception as exc:
        print(f"bot set_inboxes: {exc}")
        return False, "Those inboxes could not be saved."


def insert_bot(name: str, key_email: str, twofa_email: str, created_by: int | None,
               raw: str, digest: str, prefix: str) -> tuple[bool, str]:
    try:
        ensure_login_columns()
        cur = _cur()
        cur.execute(
            """
            INSERT INTO bot_access_keys
                (name, key_hash, key_prefix, active, controls_json, created_by, email, twofa_email)
            VALUES (%s, %s, %s, 1, %s, %s, %s, %s)
            """,
            (
                name,
                digest,
                prefix,
                json.dumps(policy.default_controls()),
                created_by,
                policy.normalize_email(key_email),
                policy.normalize_email(twofa_email),
            ),
        )
        return True, ""
    except Exception as exc:
        print(f"bot insert_bot: {exc}")
        return False, "That bot could not be saved."


def replace_api_key(key_id: int, digest: str, prefix: str) -> tuple[bool, str]:
    """New permanent key. Clears the open session and any unused 2FA key."""
    try:
        ensure_login_columns()
        cur = _cur()
        cur.execute(
            """
            UPDATE bot_access_keys
            SET key_hash=%s, key_prefix=%s,
                twofa_hash=NULL, twofa_expires=NULL, twofa_attempts=0,
                session_hash=NULL, session_expires=NULL
            WHERE id=%s
            """,
            (digest, prefix, int(key_id)),
        )
        if not cur.rowcount:
            return False, "That bot was not found."
        return True, ""
    except Exception as exc:
        print(f"bot replace_api_key: {exc}")
        return False, "That API key could not be saved."


def store_twofa(key_id: int, digest: str) -> bool:
    try:
        ensure_login_columns()
        cur = _cur()
        cur.execute(
            """
            UPDATE bot_access_keys
            SET twofa_hash=%s, twofa_expires=DATE_ADD(NOW(), INTERVAL %s SECOND),
                twofa_attempts=0, session_hash=NULL, session_expires=NULL
            WHERE id=%s
            """,
            (digest, int(policy.TWOFA_TTL_SECONDS), int(key_id)),
        )
        return True
    except Exception as exc:
        print(f"bot store_twofa: {exc}")
        return False


def open_session(key_id: int, digest: str) -> bool:
    try:
        cur = _cur()
        cur.execute(
            """
            UPDATE bot_access_keys
            SET session_hash=%s, session_expires=DATE_ADD(NOW(), INTERVAL %s SECOND),
                twofa_hash=NULL, twofa_expires=NULL, twofa_attempts=0
            WHERE id=%s
            """,
            (digest, int(policy.SESSION_TTL_SECONDS), int(key_id)),
        )
        return True
    except Exception as exc:
        print(f"bot open_session: {exc}")
        return False


def note_bad_twofa(key_id: int) -> None:
    try:
        cur = _cur()
        cur.execute(
            """
            UPDATE bot_access_keys
            SET twofa_attempts=twofa_attempts+1,
                twofa_hash=IF(twofa_attempts+1 >= 8, NULL, twofa_hash),
                twofa_expires=IF(twofa_attempts+1 >= 8, NULL, twofa_expires)
            WHERE id=%s
            """,
            (int(key_id),),
        )
    except Exception as exc:
        print(f"bot note_bad_twofa: {exc}")


def clear_twofa(key_id: int) -> None:
    """Drop a 2FA key that was stored but never emailed."""
    try:
        cur = _cur()
        cur.execute(
            """
            UPDATE bot_access_keys
            SET twofa_hash=NULL, twofa_expires=NULL, twofa_attempts=0
            WHERE id=%s
            """,
            (int(key_id),),
        )
    except Exception as exc:
        print(f"bot clear_twofa: {exc}")


def find_session(raw: str) -> dict | None:
    digest = policy.hash_key(raw or "")
    if not raw or not digest or not str(raw).startswith("mvos_s_"):
        return None
    try:
        ensure_login_columns()
        cur = _cur()
        cur.execute(
            """
            SELECT * FROM bot_access_keys
            WHERE session_hash=%s AND session_expires > NOW()
            LIMIT 1
            """,
            (digest,),
        )
        row = cur.fetchone()
        if not row:
            return None
        view = _key_view(row)
        view["voices"] = voices_for(int(view["id"]))
        return view
    except Exception as exc:
        print(f"bot find_session: {exc}")
        return None


def twofa_matches(row: dict, raw: str) -> str:
    """ok, missing, expired, or bad. The hash stays in the database."""
    digest = policy.hash_key(raw or "")
    if not row or not row.get("id") or not digest or not str(raw or "").startswith("mvos_2fa_"):
        return "missing" if not (raw or "").strip() else "bad"
    try:
        cur = _cur()
        cur.execute(
            """
            SELECT twofa_hash, twofa_expires > NOW() AS live
            FROM bot_access_keys WHERE id=%s
            """,
            (int(row["id"]),),
        )
        current = cur.fetchone() or {}
    except Exception as exc:
        print(f"bot twofa_matches: {exc}")
        return "bad"
    if not current.get("twofa_hash"):
        return "missing"
    if current.get("twofa_hash") != digest:
        return "bad"
    if not current.get("live"):
        return "expired"
    return "ok"


def list_usage(limit: int = 80) -> list[dict]:
    try:
        cap = max(1, min(int(limit or 80), 200))
        cur = _cur()
        cur.execute(
            """
            SELECT l.id, l.key_id, k.name AS bot_name, k.key_prefix, l.action, l.target_type,
                   l.target_id, l.ok, l.detail, l.snapshot_json, l.reversed_at, l.reversed_by,
                   l.created_at
            FROM bot_access_log l
            JOIN bot_access_keys k ON k.id = l.key_id
            ORDER BY l.id DESC
            LIMIT %s
            """,
            (cap,),
        )
        rows = []
        for row in cur.fetchall() or []:
            item = _log_view(row)
            item["bot_name"] = row.get("bot_name")
            item["key_prefix"] = row.get("key_prefix")
            rows.append(item)
        return rows
    except Exception as exc:
        print(f"bot list_usage: {exc}")
        return []


def issue_key(name: str, created_by: int | None) -> tuple[dict | None, str | None, str | None]:
    name = (name or "").strip()[:120]
    if not name:
        return None, None, "Give the bot a name."
    raw, digest, prefix = policy.new_key_material()
    try:
        cur = _cur()
        cur.execute(
            """
            INSERT INTO bot_access_keys (name, key_hash, key_prefix, active, controls_json, created_by)
            VALUES (%s, %s, %s, 1, %s, %s)
            """,
            (name, digest, prefix, json.dumps(policy.default_controls()), created_by),
        )
        cur.execute("SELECT * FROM bot_access_keys WHERE id=%s", (cur.lastrowid,))
        return _key_view(cur.fetchone() or {}), raw, None
    except Exception as exc:
        print(f"bot issue_key: {exc}")
        return None, None, "Could not issue that key."


def find_key(raw: str) -> dict | None:
    digest = policy.hash_key(raw or "")
    if not raw or not digest:
        return None
    try:
        cur = _cur()
        cur.execute("SELECT * FROM bot_access_keys WHERE key_hash=%s LIMIT 1", (digest,))
        row = cur.fetchone()
        if not row:
            return None
        view = _key_view(row)
        view["voices"] = voices_for(int(view["id"]))
        return view
    except Exception as exc:
        print(f"bot find_key: {exc}")
        return None


def get_key(key_id: int) -> dict | None:
    try:
        cur = _cur()
        cur.execute("SELECT * FROM bot_access_keys WHERE id=%s", (int(key_id),))
        row = cur.fetchone()
        if not row:
            return None
        view = _key_view(row)
        view["voices"] = voices_for(int(view["id"]))
        return view
    except Exception as exc:
        print(f"bot get_key: {exc}")
        return None


def voices_for(key_id: int) -> list[dict]:
    try:
        cur = _cur()
        cur.execute(
            """
            SELECT v.id, v.key_id, v.voice_type, v.user_id, v.label,
                   u.username, u.first_name, u.last_name
            FROM bot_access_voices v
            LEFT JOIN users u ON u.id = v.user_id
            WHERE v.key_id=%s
            ORDER BY v.voice_type ASC, v.id ASC
            """,
            (int(key_id),),
        )
        rows = []
        for row in cur.fetchall() or []:
            item = _clean(row)
            if item.get("voice_type") == "user":
                item["label"] = item.get("label") or policy.person_label(item)
            elif item.get("voice_type") == "church":
                author = policy.person_label(item) if item.get("user_id") else ""
                item["label"] = "Church" + (f" — authored by {author}" if author else "")
            rows.append(item)
        return rows
    except Exception as exc:
        print(f"bot voices_for: {exc}")
        return []


def save_key(key_id: int, active: bool, controls: dict, church_user_id: int | None,
             user_ids: list[int], church_requested: bool) -> tuple[bool, str | None]:
    """Save switches and voices. The message is a warning when the save still worked."""
    note = None
    try:
        cur = _cur()
        cur.execute("SELECT id FROM bot_access_keys WHERE id=%s", (int(key_id),))
        if not cur.fetchone():
            return False, "That bot key is gone."
        cur.execute(
            """
            UPDATE bot_access_keys
            SET active=%s, controls_json=%s
            WHERE id=%s
            """,
            (1 if active else 0, json.dumps(policy.normalize_controls(controls)), int(key_id)),
        )
        existing = voices_for(int(key_id))
        prior_church = next((v.get("user_id") for v in existing if v.get("voice_type") == "church"), None)
        if church_requested and not church_user_id:
            if prior_church:
                note = "Church posts need an author. The previous church author was kept."
                church_user_id = int(prior_church)
            else:
                note = "Church posts need an author, so the church voice was not added."
                church_requested = False
        elif not church_requested:
            church_user_id = None
        seen = []
        for uid in user_ids:
            if uid and uid not in seen:
                seen.append(int(uid))
        cur.execute("DELETE FROM bot_access_voices WHERE key_id=%s", (int(key_id),))
        if church_requested and church_user_id:
            cur.execute(
                """
                INSERT INTO bot_access_voices (key_id, voice_type, user_id, label)
                VALUES (%s, 'church', %s, 'Church')
                """,
                (int(key_id), int(church_user_id)),
            )
        for uid in seen:
            cur.execute(
                """
                INSERT INTO bot_access_voices (key_id, voice_type, user_id, label)
                VALUES (%s, 'user', %s, NULL)
                """,
                (int(key_id), int(uid)),
            )
        return True, note
    except Exception as exc:
        print(f"bot save_key: {exc}")
        return False, "Could not save that bot."


def list_keys() -> list[dict]:
    try:
        cur = _cur()
        cur.execute(
            """
            SELECT id, name, key_prefix, active, controls_json, created_by, email, twofa_email,
                   created_at, updated_at
            FROM bot_access_keys
            ORDER BY id DESC
            """
        )
        keys = [_key_view(row) for row in (cur.fetchall() or [])]
    except Exception as exc:
        print(f"bot list_keys: {exc}")
        return []
    if not keys:
        return []
    ids = [int(row["id"]) for row in keys]
    voice_map = {key_id: [] for key_id in ids}
    log_map = {key_id: [] for key_id in ids}
    try:
        marks = ",".join(["%s"] * len(ids))
        cur = _cur()
        cur.execute(
            f"""
            SELECT v.id, v.key_id, v.voice_type, v.user_id, v.label,
                   u.username, u.first_name, u.last_name
            FROM bot_access_voices v
            LEFT JOIN users u ON u.id = v.user_id
            WHERE v.key_id IN ({marks})
            ORDER BY v.id ASC
            """,
            ids,
        )
        for row in cur.fetchall() or []:
            item = _clean(row)
            voice_map.setdefault(int(item["key_id"]), []).append(item)
        cur.execute(
            f"""
            SELECT id, key_id, action, target_type, target_id, ok, detail,
                   snapshot_json, reversed_at, reversed_by, created_at
            FROM bot_access_log
            WHERE key_id IN ({marks})
            ORDER BY id DESC
            LIMIT 200
            """,
            ids,
        )
        for row in cur.fetchall() or []:
            item = _log_view(row)
            bucket = log_map.setdefault(int(item["key_id"]), [])
            if len(bucket) < 20:
                bucket.append(item)
    except Exception as exc:
        print(f"bot list_keys extras: {exc}")
    for row in keys:
        row["voices"] = voice_map.get(int(row["id"]), [])
        row["logs"] = log_map.get(int(row["id"]), [])
        row["church_user_id"] = next(
            (v.get("user_id") for v in row["voices"] if v.get("voice_type") == "church"),
            None,
        )
        row["user_voice_ids"] = [
            int(v["user_id"]) for v in row["voices"]
            if v.get("voice_type") == "user" and v.get("user_id")
        ]
    return keys


def _log_view(row: dict) -> dict:
    item = _clean(row)
    item["ok"] = bool(row.get("ok"))
    item["reversed"] = bool(row.get("reversed_at"))
    snap = row.get("snapshot_json")
    if isinstance(snap, str) and snap:
        try:
            item["snapshot"] = json.loads(snap)
        except ValueError:
            item["snapshot"] = None
    else:
        item["snapshot"] = None
    item.pop("snapshot_json", None)
    item["can_reverse"] = policy.undo_plan(item.get("action") or "", item["reversed"]) is not None and item["ok"]
    item["undo_label"] = policy.undo_label(item.get("action") or "", item["reversed"]) if item["can_reverse"] else None
    return item


def write_log(key_id: int, action: str, *, ok: bool, detail: str = "",
              target_type: str | None = None, target_id: int | None = None,
              snapshot: dict | None = None) -> int | None:
    try:
        cur = _cur()
        cur.execute(
            """
            INSERT INTO bot_access_log
                (key_id, action, target_type, target_id, ok, detail, snapshot_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                int(key_id),
                (action or "")[:40],
                (target_type or None),
                int(target_id) if target_id else None,
                1 if ok else 0,
                (detail or "")[:500],
                json.dumps(snapshot, default=str) if snapshot else None,
            ),
        )
        return int(cur.lastrowid)
    except Exception as exc:
        print(f"bot write_log: {exc}")
        return None


def list_log(key_id: int, limit: int = 50) -> list[dict]:
    try:
        cur = _cur()
        cur.execute(
            """
            SELECT id, key_id, action, target_type, target_id, ok, detail,
                   snapshot_json, reversed_at, reversed_by, created_at
            FROM bot_access_log
            WHERE key_id=%s
            ORDER BY id DESC
            LIMIT %s
            """,
            (int(key_id), int(limit)),
        )
        return [_log_view(row) for row in (cur.fetchall() or [])]
    except Exception as exc:
        print(f"bot list_log: {exc}")
        return []


def get_log(log_id: int) -> dict | None:
    try:
        cur = _cur()
        cur.execute(
            """
            SELECT id, key_id, action, target_type, target_id, ok, detail,
                   snapshot_json, reversed_at, reversed_by, created_at
            FROM bot_access_log WHERE id=%s
            """,
            (int(log_id),),
        )
        row = cur.fetchone()
        return _log_view(row) if row else None
    except Exception as exc:
        print(f"bot get_log: {exc}")
        return None


def set_post_removed(post_id: int, removed: bool) -> tuple[bool, str]:
    try:
        cur = _cur()
        cur.execute("SELECT id, removed_at FROM community_posts WHERE id=%s", (int(post_id),))
        row = cur.fetchone()
        if not row:
            return False, "That post is already gone."
        if removed:
            cur.execute("UPDATE community_posts SET removed_at=NOW() WHERE id=%s", (int(post_id),))
            return True, "Hid that post. The words are still saved."
        cur.execute("UPDATE community_posts SET removed_at=NULL WHERE id=%s", (int(post_id),))
        return True, "Put that post back on the wall."
    except Exception as exc:
        print(f"bot set_post_removed: {exc}")
        return False, "Could not change that post."


def mark_reversed(log_id: int, actor: str, clear: bool) -> None:
    cur = _cur()
    if clear:
        cur.execute(
            "UPDATE bot_access_log SET reversed_at=NULL, reversed_by=NULL WHERE id=%s",
            (int(log_id),),
        )
        return
    cur.execute(
        "UPDATE bot_access_log SET reversed_at=NOW(), reversed_by=%s WHERE id=%s",
        ((actor or "")[:80], int(log_id)),
    )


def read_area(area: str, limit: int = READ_LIMIT) -> tuple[list[dict], bool, str]:
    sql = policy.READS.get(area)
    if not sql:
        return [], False, "That read is not on the bot."
    try:
        cap = max(1, min(int(limit or READ_LIMIT), 100))
        cur = _cur()
        cur.execute(sql, (cap,))
        return [_clean(row) for row in (cur.fetchall() or [])], True, ""
    except Exception as exc:
        print(f"bot read_area {area}: {exc}")
        return [], False, "That table could not be read."


def publish_post(voice: dict, post: dict) -> tuple[int | None, str | None]:
    try:
        from app.models.church_community import record_posting
        from app.models.social import create_post
        post_id = create_post(
            int(voice["user_id"]),
            post["kind"],
            post["title"],
            post["body"],
            "",
            post["visibility"],
        )
    except Exception as exc:
        print(f"bot publish_post: {exc}")
        return None, "Could not save that post."
    if not post_id:
        return None, "Could not save that post. A blocked word or an empty body will do that."
    try:
        record_posting(post["kind"], int(post_id), voice["posted_as"], 0, int(voice["user_id"]))
    except Exception as exc:
        print(f"bot publish stamp: {exc}")
        return int(post_id), "The post was saved, but it was not stamped on that wall."
    return int(post_id), None


def list_voice_posts(voice: dict, limit: int = 20) -> list[dict]:
    cap = max(1, min(int(limit or 20), 50))
    if voice.get("posted_as") == "church":
        try:
            from app.models.social import list_posts_by_voice
            rows = list_posts_by_voice("church", 0, cap, None) or []
        except Exception as exc:
            print(f"bot list church posts: {exc}")
            return []
        out = []
        for row in rows:
            out.append({
                "id": _cell(row.get("id")),
                "kind": row.get("kind"),
                "title": row.get("title"),
                "body": (row.get("body") or "")[:500],
                "visibility": row.get("visibility"),
                "created_at": _cell(row.get("created_at")),
                "as": "church",
            })
        return out
    try:
        cur = _cur()
        cur.execute(
            """
            SELECT p.id, p.kind, p.title, p.body, p.visibility, p.created_at
            FROM community_posts p
            LEFT JOIN content_posting cp
              ON cp.content_id = p.id AND cp.content_type = p.kind
            WHERE p.user_id=%s AND p.removed_at IS NULL
              AND (cp.posted_as IS NULL OR cp.posted_as = 'member')
            ORDER BY p.id DESC
            LIMIT %s
            """,
            (int(voice["user_id"]), cap),
        )
        out = []
        for row in cur.fetchall() or []:
            item = _clean(row)
            item["body"] = (item.get("body") or "")[:500]
            item["as"] = voice.get("as")
            out.append(item)
        return out
    except Exception as exc:
        print(f"bot list_voice_posts: {exc}")
        return []
