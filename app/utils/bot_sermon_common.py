"""Shared helpers for the church bot sermon desk."""

from __future__ import annotations

import html
import json
from datetime import date, datetime, time
from decimal import Decimal

TEXT_CAP = 20000
SNAP_CAP = 60000
VERSE_CAP = 40
SECTION_TYPES = (
    "introduction",
    "point",
    "scripture",
    "application",
    "illustration",
    "conclusion",
    "other",
)
SERMON_VISIBILITY = ("private", "collaborators", "pastoral_group")
SHARE_VISIBILITY = ("private", "pastoral_group")
SERMON_FIELDS = (
    "title",
    "preacher_id",
    "primary_passage",
    "service_date",
    "visibility",
    "header_text",
    "footer_text",
    "conclusion_text",
    "series_tags",
    "notes",
)
SECTION_FIELDS = (
    "section_type",
    "title",
    "content",
    "scripture_reference",
    "source",
    "notes",
)
ILLUSTRATION_FIELDS = ("title", "content", "source", "tags", "notes", "user_id")
VAULT_FIELDS = (
    "user_id",
    "title",
    "content",
    "reference",
    "notes",
    "tags",
    "section_type",
    "scripture_reference",
    "source_url",
    "visibility",
)
HIDE_TABLES = {
    "sermon.create": "pastoral_sermons",
    "illustration.create": "illustration_library",
    "section.add": "sermon_sections",
    "vault.create": "pastoral_vault",
}
_SOFT_TABLES = (
    "pastoral_sermons",
    "sermon_sections",
    "illustration_library",
    "pastoral_vault",
)
_ready = False

_HTML_STARTS = ("<p", "<div", "<blockquote", "<h1", "<h2", "<h3", "<ul", "<ol", "<br", "<strong", "<em")
_SPEAKER_ROLES = {
    "preacher",
    "pastor",
    "speaker",
    "minister",
    "guest speaker",
    "guest preacher",
    "guest pastor",
    "guest minister",
}


def as_html(text: str) -> str:
    """Wrap plain words so the sermon builder shows them. Leave real HTML alone."""
    raw = (text or "")[:TEXT_CAP]
    lead = raw.lstrip()[:12].lower()
    if lead.startswith(_HTML_STARTS):
        return raw
    body = html.escape(raw).replace("\n", "<br>")
    return f"<p>{body}</p>"


def verse_span(start: int, end: int, cap: int = VERSE_CAP):
    """Inclusive verse range, or None when it is longer than the cap."""
    if end < start:
        start, end = end, start
    if end - start + 1 > cap:
        return None
    return start, end


def _speaker_role(role: str) -> bool:
    text = (role or "").lower().strip()
    if text in _SPEAKER_ROLES:
        return True
    return "preach" in text or text.endswith("minister") or " minister" in text


def assignments_with_speaker(assignments, preacher_id, guest_name, change_speaker: bool) -> list[dict]:
    """Copy the role list. A member wins over a guest name. Other roles stay."""
    rows = []
    placed = False
    for raw in assignments or []:
        role = str(raw.get("role_name") or "").strip()
        if not role:
            continue
        user_id = _int_or_none(raw.get("user_id"))
        guest = str(raw.get("guest_name") or "").strip() or None
        if change_speaker and not placed and _speaker_role(role):
            placed = True
            if preacher_id:
                user_id, guest = int(preacher_id), None
            else:
                user_id, guest = None, (guest_name or None)
        if user_id:
            guest = None
        rows.append({"role_name": role, "user_id": user_id, "guest_name": guest})
    if change_speaker and not placed:
        rows.append({
            "role_name": "Minister",
            "user_id": int(preacher_id) if preacher_id else None,
            "guest_name": None if preacher_id else (guest_name or None),
        })
    return rows


def _fail(error: str, status: int = 400, action: str | None = None) -> dict:
    out = {"ok": False, "error": error, "status": status}
    if action:
        out["action"] = action
    return out


def _ok(data: dict, log: dict | None = None) -> dict:
    return {"ok": True, "data": data, "log": log}


def _jsonish(value):
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return None
    return str(value)


def _plain(row: dict | None, keys: tuple[str, ...] | None = None) -> dict:
    source = row or {}
    chosen = keys or tuple(source.keys())
    return {key: _jsonish(source.get(key)) for key in chosen}


def _clip(value, cap: int):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:cap]


def _int_or_none(value):
    if value in (None, "", 0, "0"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _limit(value, default: int = 40) -> int:
    try:
        number = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        number = default
    return max(1, min(number, 100))


def _like(value: str) -> str:
    cleaned = (value or "").replace("%", "").replace("_", "").replace("\\", "")
    return f"%{cleaned[:80]}%"


def _parse_date(value, required: bool = False):
    if value in (None, ""):
        if required:
            return None, "Send date as YYYY-MM-DD."
        return None, None
    text = str(value).strip()[:10]
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None, "Send the date as YYYY-MM-DD."
    return text, None


def _tags(raw):
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except ValueError:
            pass
        return [part.strip() for part in raw.split(",") if part.strip()]
    return []


def _tags_json(raw) -> str:
    return json.dumps(_tags(raw))


def _db():
    from app.models.db import get_db
    return get_db()


def ensure_soft_columns() -> str | None:
    """Add removed_at when the sermon tables exist and the column does not."""
    global _ready
    if _ready:
        return None
    try:
        cur = _db().cursor()
        for table in _SOFT_TABLES:
            cur.execute(
                """
                SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                """,
                (table,),
            )
            if not cur.fetchone():
                return "The sermon desk tables are not on this church yet."
            cur.execute(
                """
                SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = 'removed_at'
                """,
                (table,),
            )
            if cur.fetchone():
                continue
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN removed_at DATETIME NULL")
            except Exception as exc:
                if "1060" not in str(exc) and "Duplicate" not in str(exc):
                    raise
        _ready = True
        return None
    except Exception as exc:
        print(f"bot sermon columns: {exc}")
        return "The sermon desk is not ready yet."


def _person(token):
    if token in (None, ""):
        return None, None
    text = str(token).strip()
    cur = _db().cursor()
    if text.isdigit():
        cur.execute("SELECT id FROM users WHERE id=%s", (int(text),))
    else:
        cur.execute("SELECT id FROM users WHERE username=%s LIMIT 1", (text,))
    row = cur.fetchone()
    if not row:
        return None, "That person is not in the directory."
    return int(row["id"]), None


def _blank_name(value):
    text = str(value or "").strip()
    return text or None


def _sermon_exists(sermon_id: int) -> bool:
    cur = _db().cursor()
    cur.execute(
        "SELECT id FROM pastoral_sermons WHERE id=%s AND removed_at IS NULL",
        (int(sermon_id),),
    )
    return cur.fetchone() is not None


def _sermon_row(sermon_id: int):
    cur = _db().cursor()
    cur.execute(
        """
        SELECT id, title, preacher_id, primary_passage, service_date, visibility,
               header_text, footer_text, conclusion_text, series_tags, notes, created_by
        FROM pastoral_sermons
        WHERE id=%s AND removed_at IS NULL
        """,
        (int(sermon_id),),
    )
    return cur.fetchone()


def _sermon_brief(sermon_id):
    sid = _int_or_none(sermon_id)
    if not sid:
        return None
    cur = _db().cursor()
    cur.execute(
        """
        SELECT id, title, primary_passage
        FROM pastoral_sermons
        WHERE id=%s AND removed_at IS NULL
        """,
        (sid,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "title": row.get("title"),
        "passage": row.get("primary_passage"),
    }


def _update_fields(table: str, row_id: int, fields: dict, allowed: tuple[str, ...]) -> None:
    sets = []
    params = []
    for key in allowed:
        if key not in fields:
            continue
        sets.append(f"{key}=%s")
        params.append(fields[key])
    if not sets:
        return
    params.append(int(row_id))
    _db().cursor().execute(
        f"UPDATE {table} SET {', '.join(sets)} WHERE id=%s",
        params,
    )


def _too_big(snapshot: dict) -> bool:
    return len(json.dumps(snapshot, default=str)) > SNAP_CAP
