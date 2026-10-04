"""Maya's permission checklist for the church app (My Vine Church).

One bot key (bot_access_keys row) is designated as Maya by the Owner. Every
/api/bot/maya/* call checks, live from the database, that the session belongs
to that key and that the route's switch is on. Normal switches default ON;
High risk switches default OFF and need the Owner's password or 2FA code to
turn on. Switches whose endpoint is not built are listed but always off.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.models.db import get_db

_TABLES_READY = False


def _p(pid, group, label, detail, *, high=False, implemented=True):
    return {"id": pid, "group": group, "label": label, "detail": detail, "high_risk": bool(high),
            "default": not high, "implemented": bool(implemented)}


ACT_WORDS = {
    "read": ("See {n}", "List and open {n}."),
    "create": ("Add {n}", "Create {n}. Shows in the app attributed to Maya's acting account."),
    "edit": ("Edit {n}", "Change existing {n}."),
    "delete": ("Remove {n}", "Hide/soft-delete {n}. The row is kept and can be restored."),
    "restore": ("Restore {n}", "Put removed {n} back."),
    "publish": ("Publish / unpublish {n}", "Make {n} live or take them down (active flag / visibility)."),
    "approve": ("Approve / hold {n}", "Approve, hold or reject {n} waiting for review."),
    "comment": ("Comment on {n}", "Add comments as Maya's acting account."),
}


def _area(area, group, noun, actions, extra="", unbuilt=()):
    out = []
    for act in actions:
        label, detail = ACT_WORDS[act]
        out.append(_p(f"{area}.{act}", group, label.format(n=noun), (detail.format(n=noun) + " " + extra).strip(),
                      implemented=act not in unbuilt))
    return out


CATALOG: list[dict] = []
CATALOG += _area("announcements", "Announcements", "announcements",
                 ("read", "create", "edit", "publish", "delete", "restore", "comment"))
CATALOG += _area("prayers", "Prayer requests", "prayer requests",
                 ("read", "create", "edit", "approve", "delete", "restore"))
CATALOG += _area("events", "Events", "events", ("read", "create", "edit", "publish", "delete", "restore"))
CATALOG += _area("wall", "Wall posts", "wall posts", ("read", "create", "delete", "restore"),
                 "Posts go out only under a voice the owner attached on Bot access.")
CATALOG += _area("comments", "Comments", "comments", ("read", "delete", "restore"),
                 "Comments on events, sermons, dreams, prophecies, announcements, prayers, photos and wall posts.")
CATALOG += _area("dreams", "Dreams", "dreams", ("read", "delete", "restore"))
CATALOG += _area("prophecies", "Prophecies", "prophecies", ("read", "delete", "restore"))
CATALOG += _area("sermons", "Sermons", "published sermons", ("read", "delete", "restore"))
CATALOG += _area("builder", "Sermon builder", "sermon drafts", ("read", "create", "edit"),
                 "Drafts, sections, illustrations and research notes. Changes can be undone from the log.")
CATALOG += [
    _p("lineup.read", "Sermon builder", "See the preaching lineup", "Who preaches what, upcoming dates."),
    _p("lineup.edit", "Sermon builder", "Set the preaching lineup", "Assign a date. Undo restores the date."),
    _p("verses.read", "Sermon builder", "Look up Bible verses", "Reference lookup."),
]
CATALOG += [
    _p("moderation.read", "Moderation", "See the moderation queue", "Removed items, open actions and who did them."),
    _p("moderation.restore", "Moderation", "Restore removed items", "Same Restore button as the moderation desk."),
    _p("moderation.review", "Moderation", "Review moderation actions", "Reverse or uphold an action in the ledger."),
]
CATALOG += _area("church_page", "Church page", "the church page", ("read", "edit"), "About text and verse.")
CATALOG += [
    _p("notifications.read", "Notifications", "See Maya's notifications", "The bell list for Maya's acting account."),
    _p("log.read", "Activity log", "See Maya's own log", "Everything this key did, with undo."),
    _p("log.undo", "Activity log", "Undo Maya's own actions", "POST reverse on a log entry."),
]
CATALOG += _area("members", "Members (directory)", "the member directory", ("read",),
                 "Names, usernames and roles. Email/phone need the separate high-risk switch.")
CATALOG += [
    _p("groups.read", "Groups", "See groups", "Group names and visibility."),
    _p("attendance.read", "Attendance", "See attendance totals", "Head counts per service date."),
    _p("worship.read", "Worship", "See worship songs", "Song list."),
    _p("tickets.read", "Tickets", "See support tickets", "Titles, status, priority."),
    _p("inventory.read", "Inventory", "See church inventory", "Items and stock levels."),
    _p("audit.read", "Audit", "See the change log", "Who changed what in the office."),
    _p("security.read", "Security", "See security events", "Blocked requests and attack stats. Never keys or passwords."),
]
# Listed so the owner sees the whole surface; no endpoint yet -> always off.
CATALOG += [
    _p("albums.upload", "Photos & albums", "Upload photos", "Not wired to the API yet.", implemented=False),
    _p("albums.replace", "Photos & albums", "Replace photos", "Not wired to the API yet.", implemented=False),
    _p("albums.delete", "Photos & albums", "Remove photos", "Not wired to the API yet.", implemented=False),
    _p("groups.edit", "Groups", "Edit groups", "Not wired to the API yet.", implemented=False),
    _p("worship.edit", "Worship", "Edit setlists and songs", "Not wired to the API yet.", implemented=False),
    _p("tickets.edit", "Tickets", "Work support tickets", "Not wired to the API yet.", implemented=False),
    _p("volunteers.edit", "Volunteers", "Schedule volunteers", "Not wired to the API yet.", implemented=False),
    _p("communications.send", "Communications", "Send email/SMS blasts", "Not wired to the API yet.", implemented=False),
]
# ----- High risk: default OFF, Owner re-confirms with password or 2FA -----
CATALOG += [
    _p("members.contact", "Members (high risk)", "See member email and phone", "Contact details in the directory.", high=True),
    _p("users.approve", "Users & roles (high risk)", "Approve new accounts", "Approve a pending signup as Member/Visitor/Staff. Never Admin/Owner.", high=True),
    _p("users.ban", "Users & roles (high risk)", "Ban / unban accounts", "Never the Owner, never an Admin, never Maya's own acting account. Unban restores.", high=True),
    _p("users.role", "Users & roles (high risk)", "Change roles / permissions", "Not wired: role changes stay on the Members page.", high=True, implemented=False),
    _p("settings.security", "Settings (high risk)", "Change site/security settings", "Not wired: settings, keys and 2FA policy stay owner-only in the browser.", high=True, implemented=False),
    _p("giving.read", "Money (high risk)", "See giving and donations", "Donation rows (name, amount, date, method).", high=True),
    _p("bills.read", "Money (high risk)", "See recurring bills", "Vendors, amounts, due dates. Never bill logins.", high=True),
    _p("giving.write", "Money (high risk)", "Record or change donations / payments", "Not wired: payments and donation edits stay in the office.", high=True, implemented=False),
    _p("hard_delete", "Hard delete (high risk)", "Permanently delete", "Announcements and events can be destroyed (a full snapshot is kept in Maya's log). Cannot be undone.", high=True),
]

CATALOG_BY_ID = {p["id"]: p for p in CATALOG}

HARD_LIMITS = [
    "Maya cannot open or change this checklist and cannot pick which key is Maya.",
    "Maya cannot read or export raw secrets: API/2FA/session keys, password hashes, TOTP secrets, SMTP or payment credentials, bill logins.",
    "Maya cannot change her own account, role, ban state or keys (she rotates her own key with POST /api/bot/password-reset only).",
    "Every Maya call is written to bot_access_log (and the office change log / moderation ledger for writes). Removals are soft and restorable; permanent delete needs the high-risk switch.",
]
FORBIDDEN_IDS = frozenset({"maya.permissions.edit", "keys.read", "secrets.read", "self.role", "self.password"})


def groups() -> list[dict]:
    out, index = [], {}
    for perm in CATALOG:
        grp = index.get(perm["group"])
        if grp is None:
            grp = {"name": perm["group"], "perms": [], "high_risk": False}
            index[perm["group"]] = grp
            out.append(grp)
        grp["perms"].append(perm)
        grp["high_risk"] = grp["high_risk"] or perm["high_risk"]
    return out


# ----------------------------------------------------------------- tables

DDL = [
    """
    CREATE TABLE IF NOT EXISTS maya_bot_settings (
      id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
      key_id INT NOT NULL,
      acting_user_id INT NULL,
      enabled TINYINT(1) NOT NULL DEFAULT 1,
      set_by INT NULL,
      created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS maya_bot_permissions (
      id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
      key_id INT NOT NULL,
      perm VARCHAR(64) NOT NULL,
      enabled TINYINT(1) NOT NULL DEFAULT 0,
      expires_at DATETIME NULL,
      updated_by INT NULL,
      updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      UNIQUE KEY uq_maya_perm (key_id, perm)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS maya_bot_perm_log (
      id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
      key_id INT NULL,
      changed_by INT NULL,
      perm VARCHAR(64) NOT NULL,
      old_value TINYINT(1) NULL,
      new_value TINYINT(1) NULL,
      high_risk TINYINT(1) NOT NULL DEFAULT 0,
      confirmed_with VARCHAR(16) NULL,
      ip VARCHAR(64) NULL,
      created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
      KEY idx_maya_perm_log_when (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]


def ensure_tables() -> None:
    global _TABLES_READY
    if _TABLES_READY:
        return
    cur = get_db().cursor()
    for sql in DDL:
        cur.execute(sql)
    # Tables made before auto-off timers existed.
    cur.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'maya_bot_permissions' AND COLUMN_NAME = 'expires_at'"
    )
    if not cur.fetchone():
        cur.execute("ALTER TABLE maya_bot_permissions ADD COLUMN expires_at DATETIME NULL AFTER enabled")
    _TABLES_READY = True


def _cur():
    ensure_tables()
    return get_db().cursor()


def settings_row() -> dict | None:
    """The Maya designation. Falls back to the first active key named like 'maya'."""
    cur = _cur()
    cur.execute("SELECT * FROM maya_bot_settings ORDER BY id ASC LIMIT 1")
    row = cur.fetchone()
    if row:
        return row
    cur.execute(
        "SELECT id, created_by FROM bot_access_keys WHERE active=1 AND LOWER(name) LIKE %s ORDER BY id ASC LIMIT 1",
        ("%maya%",),
    )
    key = cur.fetchone()
    if not key:
        return None
    return {"id": None, "key_id": int(key["id"]), "acting_user_id": key.get("created_by"), "enabled": 1,
            "implicit": True}


def is_maya(row: dict | None) -> bool:
    if not row or not row.get("active"):
        return False
    s = settings_row()
    return bool(s and s.get("enabled") and int(s["key_id"]) == int(row["id"]))


def acting_user_id(row: dict) -> int | None:
    s = settings_row() or {}
    uid = s.get("acting_user_id") or row.get("created_by")
    try:
        return int(uid) if uid else None
    except (TypeError, ValueError):
        return None


def set_maya(key_id: int, acting_user: int | None, *, owner_id: int) -> tuple[bool, str]:
    cur = _cur()
    cur.execute("SELECT id FROM bot_access_keys WHERE id=%s", (int(key_id),))
    if not cur.fetchone():
        return False, "That bot key is gone."
    cur.execute("SELECT id, key_id FROM maya_bot_settings ORDER BY id ASC LIMIT 1")
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE maya_bot_settings SET key_id=%s, acting_user_id=%s, enabled=1, set_by=%s WHERE id=%s",
                    (int(key_id), acting_user, owner_id, int(row["id"])))
    else:
        cur.execute("INSERT INTO maya_bot_settings (key_id, acting_user_id, enabled, set_by) VALUES (%s,%s,1,%s)",
                    (int(key_id), acting_user, owner_id))
    _log(key_id, owner_id, "maya.account", bool(row), True, False, None)
    return True, "Saved. That key is Maya now."


EXPIRY_UNITS = {"hours": 1, "days": 24, "weeks": 24 * 7, "months": 24 * 30}
HIGH_RISK_DEFAULT_EXPIRY = ("hours", 24)
MAX_EXPIRY_HOURS = 24 * 366


def _now():
    return datetime.utcnow()


def parse_expiry(unit, number, *, now=None):
    """('days', 3) -> UTC datetime. 'none'/blank -> None. Bad input -> ValueError."""
    unit = (str(unit or "")).strip().lower()
    if unit in ("", "none", "never", "no_expiry"):
        return None
    if unit not in EXPIRY_UNITS:
        raise ValueError("Pick hours, days, weeks or months.")
    try:
        n = int(str(number).strip())
    except (TypeError, ValueError):
        raise ValueError("The timer needs a whole number.")
    if n < 1:
        raise ValueError("The timer must be at least 1.")
    return (now or _now()) + timedelta(hours=min(n * EXPIRY_UNITS[unit], MAX_EXPIRY_HOURS))


def remaining_text(expires_at, now=None) -> str:
    if not expires_at:
        return "no expiry"
    secs = int((expires_at - (now or _now())).total_seconds())
    if secs <= 0:
        return "expired"
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    if days:
        return f"{days}d {hours}h left"
    if hours:
        return f"{hours}h {rem // 60}m left"
    return f"{max(rem // 60, 1)}m left"


def _expire(cur, key_id, perm) -> None:
    """Flip one expired switch off and audit it as auto-expired."""
    cur.execute("UPDATE maya_bot_permissions SET enabled=0, expires_at=NULL WHERE key_id=%s AND perm=%s",
                (int(key_id), perm))
    _log(key_id, None, perm, True, False, (CATALOG_BY_ID.get(perm) or {}).get("high_risk", False), "auto-expired")


def expire_due(now=None) -> int:
    """Cron/lazy cleanup across all keys. Returns how many switches went off."""
    cur = _cur()
    cur.execute("SELECT key_id, perm FROM maya_bot_permissions WHERE enabled=1 AND expires_at IS NOT NULL "
                "AND expires_at <= %s", (now or _now(),))
    rows = cur.fetchall() or []
    for row in rows:
        _expire(cur, row["key_id"], row["perm"])
    return len(rows)


def perm_rows(key_id: int) -> dict:
    cur = _cur()
    cur.execute("SELECT perm, enabled, expires_at FROM maya_bot_permissions WHERE key_id=%s", (int(key_id),))
    return {r["perm"]: r for r in cur.fetchall() or []}


def perm_state(key_id: int, *, cleanup: bool = True) -> dict[str, bool]:
    """Live on every call. Expired switches are OFF at once; cleanup flips the row and audits it."""
    now = _now()
    state = {p["id"]: bool(p["default"]) for p in CATALOG}
    expired = []
    for pid, row in perm_rows(key_id).items():
        if pid not in state:
            continue
        on = bool(row["enabled"])
        exp = row.get("expires_at")
        if on and exp is not None and exp <= now:
            on = False
            expired.append(pid)
        state[pid] = on
    for pid, perm in CATALOG_BY_ID.items():
        if not perm["implemented"]:
            state[pid] = False
    if expired and cleanup:
        try:
            cur = _cur()
            for pid in expired:
                _expire(cur, key_id, pid)
        except Exception as exc:  # the live answer is already OFF
            print(f"maya lazy expiry: {exc}")
    return state


def perm_expiry(key_id: int) -> dict:
    now = _now()
    return {pid: r["expires_at"] for pid, r in perm_rows(key_id).items()
            if r["enabled"] and r.get("expires_at") is not None and r["expires_at"] > now}


def allowed(row: dict | None, perm_id: str) -> bool:
    if perm_id in FORBIDDEN_IDS or perm_id not in CATALOG_BY_ID:
        return False
    if not is_maya(row):
        return False
    return bool(perm_state(int(row["id"])).get(perm_id))


def _log(key_id, owner_id, perm, old, new, high, confirmed_with, ip=None):  # noqa: PLR0913
    cur = _cur()
    cur.execute(
        "INSERT INTO maya_bot_perm_log (key_id, changed_by, perm, old_value, new_value, high_risk, confirmed_with, ip) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (key_id, owner_id, perm[:64], 1 if old else 0, 1 if new else 0, 1 if high else 0, confirmed_with, ip),
    )


def save_state(key_id: int, wanted: dict[str, bool], *, owner: dict, confirmed_with: str | None,
               ip: str | None = None, expiry: dict | None = None) -> tuple[list[str], list[str]]:
    """Owner save. (changed, refused).

    High risk off->on (or a longer high-risk timer) needs confirmed_with.
    expiry maps perm -> UTC datetime or None. High-risk switches that are on
    always carry a timer (24 hours when none is given). Off clears the timer.
    """
    if not owner or (owner.get("role") or "") != "Owner":
        raise PermissionError("Only the Owner can change Maya's permissions.")
    expiry = expiry or {}
    now = _now()
    current = perm_state(key_id)
    rows = perm_rows(key_id)
    cur = _cur()
    changed, refused = [], []
    for pid, perm in CATALOG_BY_ID.items():
        if pid not in wanted:
            continue
        new, old = bool(wanted[pid]) and perm["implemented"], bool(current.get(pid))
        row = rows.get(pid)
        if new and not old and perm["high_risk"] and not confirmed_with:
            refused.append(pid)
            continue
        want_exp = None
        if new:
            if pid in expiry:
                want_exp = expiry[pid]
            elif old and row is not None:
                want_exp = row.get("expires_at")
            if perm["high_risk"] and want_exp is None:
                want_exp = parse_expiry(*HIGH_RISK_DEFAULT_EXPIRY, now=now)
        old_exp = row.get("expires_at") if (row is not None and old) else None
        if (new and old and perm["high_risk"] and not confirmed_with and want_exp is not None
                and (old_exp is None or want_exp > old_exp)):
            refused.append(pid)
            continue
        if new == old and row is not None and want_exp == old_exp:
            continue
        cur.execute(
            "INSERT INTO maya_bot_permissions (key_id, perm, enabled, expires_at, updated_by) VALUES (%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE enabled=VALUES(enabled), expires_at=VALUES(expires_at), "
            "updated_by=VALUES(updated_by)",
            (int(key_id), pid, 1 if new else 0, want_exp if new else None, owner.get("id")),
        )
        if new != old or want_exp != old_exp:
            how = confirmed_with if (new and perm["high_risk"] and not old) else None
            if new and want_exp is not None:
                how = ((how + ",") if how else "") + "timer"
            _log(key_id, owner.get("id"), pid, old, new, perm["high_risk"], how[:16] if how else None, ip)
            changed.append(pid)
    if changed:
        try:
            from app.models.log import log_change

            log_change(owner.get("id"), "maya_permissions", change_details=f"Changed {len(changed)} Maya permission(s)")
        except Exception as exc:
            print(f"maya perms log_change: {exc}")
    return changed, refused


def recent_log(limit: int = 40) -> list[dict]:
    cur = _cur()
    cur.execute(
        "SELECT l.*, u.username AS owner_username FROM maya_bot_perm_log l "
        "LEFT JOIN users u ON u.id = l.changed_by ORDER BY l.id DESC LIMIT %s",
        (int(limit),),
    )
    return cur.fetchall() or []


def capabilities(row: dict) -> dict:
    state = perm_state(int(row["id"]))
    exp = perm_expiry(int(row["id"]))
    return {
        "groups": [
            {"group": g["name"], "permissions": [
                {"id": p["id"], "label": p["label"], "detail": p["detail"], "high_risk": p["high_risk"],
                 "implemented": p["implemented"], "on": bool(state.get(p["id"])),
                 "expires_at": (exp[p["id"]].isoformat() + "Z") if p["id"] in exp else None,
                 "remaining": remaining_text(exp.get(p["id"])) if state.get(p["id"]) else None,
                 "timer_required": p["high_risk"]} for p in g["perms"]]}
            for g in groups()
        ],
        "on": sorted(k for k, v in state.items() if v),
        "hard_limits": HARD_LIMITS,
    }


def confirm_owner(owner: dict | None, password: str = "", code: str = "") -> str | None:
    """'password' or 'totp' when the Owner re-proved who they are."""
    if not owner or (owner.get("role") or "") != "Owner":
        return None
    if password:
        try:
            from werkzeug.security import check_password_hash

            if owner.get("password") and check_password_hash(owner["password"], password):
                return "password"
        except Exception:
            pass
    if code and owner.get("totp_enabled"):
        try:
            from app.utils.totp_auth import decrypt_totp_secret, verify_totp_code

            if verify_totp_code(decrypt_totp_secret(owner.get("totp_secret") or ""), code.strip()):
                return "totp"
        except Exception:
            pass
    return None
