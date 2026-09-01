# Display preferences: church default theme + personal overrides.
# Members can always pick their own theme; church default applies until they do
# (or after they choose "Use church default").

from __future__ import annotations

ALLOWED_THEMES = (
    "cyan-glow",      # Classic dark neon
    "soft-light",     # Daytime / brighter page
    "tropical",       # Teal + coral
    "purple-grace",   # Royal purple
    "amber-hope",     # Warm gold
    "forest",         # Green sanctuary
    "rose-dawn",      # Soft rose
)

ALLOWED_FONT_SCALES = ("sm", "md", "lg", "xl", "xxl")
ALLOWED_BIBLE_SCALES = ("sm", "md", "lg", "xl", "xxl")

DEFAULT_THEME = "cyan-glow"
DEFAULT_FONT_SCALE = "md"
DEFAULT_BIBLE_SCALE = "md"

# Sentinel in forms/API meaning "follow the church-wide default"
CHURCH_DEFAULT_TOKEN = "church"

THEME_LABELS = {
    "cyan-glow": "Classic",
    "soft-light": "Soft light",
    "tropical": "Tropical",
    "purple-grace": "Purple grace",
    "amber-hope": "Amber hope",
    "forest": "Forest",
    "rose-dawn": "Rose dawn",
}

FONT_LABELS = {
    "sm": "Small",
    "md": "Medium",
    "lg": "Large",
    "xl": "Extra large",
    "xxl": "Huge",  # elderly / high-visibility reading
}

BIBLE_LABELS = {
    "sm": "Small",
    "md": "Medium",
    "lg": "Large",
    "xl": "Extra large",
    "xxl": "Huge",
}


def normalize_theme(value) -> str:
    v = (value or "").strip().lower()
    if v in ("", CHURCH_DEFAULT_TOKEN, "default", "church-default"):
        return DEFAULT_THEME
    return v if v in ALLOWED_THEMES else DEFAULT_THEME


def normalize_font_scale(value) -> str:
    v = (value or "").strip().lower()
    return v if v in ALLOWED_FONT_SCALES else DEFAULT_FONT_SCALE


def normalize_bible_scale(value) -> str:
    v = (value or "").strip().lower()
    return v if v in ALLOWED_BIBLE_SCALES else DEFAULT_BIBLE_SCALE


def get_church_default_theme(settings_row: dict | None = None) -> str:
    """Church-wide default theme from settings (falls back to Classic)."""
    if settings_row is None:
        try:
            from flask import g
            settings_row = getattr(g, "settings", None) or {}
        except Exception:
            settings_row = {}
    if not settings_row:
        try:
            import pymysql
            from app.models.db import get_db
            cur = get_db().cursor(pymysql.cursors.DictCursor)
            cur.execute("SELECT default_ui_theme FROM settings WHERE id = 1")
            settings_row = cur.fetchone() or {}
        except Exception:
            settings_row = {}
    return normalize_theme(settings_row.get("default_ui_theme") or DEFAULT_THEME)


def resolve_theme_for_user_row(user_row: dict | None, church_default: str | None = None) -> str:
    """
    Personal theme if ui_use_personal_theme is set; otherwise church default.
    """
    church = normalize_theme(church_default or get_church_default_theme())
    if not user_row:
        return church
    use_personal = user_row.get("ui_use_personal_theme")
    # Missing column / None → follow church for brand-new installs
    if use_personal in (None, 0, "0", False):
        return church
    return normalize_theme(user_row.get("ui_theme") or church)


def apply_ui_prefs_to_session(
    session,
    user_row=None,
    theme=None,
    font_scale=None,
    bible_scale=None,
    *,
    use_personal: bool | None = None,
    church_default: str | None = None,
):
    """Write normalized prefs into the Flask session (permanent cookie)."""
    church = church_default or get_church_default_theme()
    if user_row is not None:
        resolved = resolve_theme_for_user_row(user_row, church)
        font_scale = user_row.get("ui_font_scale", font_scale)
        bible_scale = user_row.get("bible_font_scale", bible_scale)
        personal = bool(user_row.get("ui_use_personal_theme"))
        session["user_theme"] = resolved
        session["ui_use_personal_theme"] = 1 if personal else 0
        session["church_default_theme"] = normalize_theme(church)
    else:
        if theme is not None and str(theme).strip().lower() in (
            CHURCH_DEFAULT_TOKEN, "default", "church-default", ""
        ):
            session["user_theme"] = normalize_theme(church)
            session["ui_use_personal_theme"] = 0
        elif theme is not None:
            session["user_theme"] = normalize_theme(theme)
            if use_personal is not None:
                session["ui_use_personal_theme"] = 1 if use_personal else 0
        elif "user_theme" not in session:
            session["user_theme"] = normalize_theme(church)
        session["church_default_theme"] = normalize_theme(church)

    if font_scale is not None or user_row is not None:
        session["ui_font_scale"] = normalize_font_scale(font_scale)
    elif "ui_font_scale" not in session:
        session["ui_font_scale"] = DEFAULT_FONT_SCALE

    if bible_scale is not None or user_row is not None:
        session["bible_font_scale"] = normalize_bible_scale(bible_scale)
    elif "bible_font_scale" not in session:
        session["bible_font_scale"] = DEFAULT_BIBLE_SCALE

    session.permanent = True
    session.modified = True


def load_ui_prefs_for_user(user_id: int) -> dict | None:
    """Fetch theme/font prefs from users table (or None if unavailable)."""
    if not user_id:
        return None
    try:
        import pymysql
        from app.models.db import get_db

        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        try:
            cur.execute(
                """
                SELECT ui_theme, ui_use_personal_theme, ui_font_scale, bible_font_scale
                  FROM users
                 WHERE id = %s
                 LIMIT 1
                """,
                (user_id,),
            )
        except Exception:
            cur.execute(
                """
                SELECT ui_theme, ui_font_scale, bible_font_scale
                  FROM users
                 WHERE id = %s
                 LIMIT 1
                """,
                (user_id,),
            )
        row = cur.fetchone()
        if row is not None and "ui_use_personal_theme" not in row:
            # Pre-migration: treat stored theme as personal
            row["ui_use_personal_theme"] = 1
        return row
    except Exception as exc:
        print(f"load_ui_prefs_for_user: {exc}")
        return None


def sync_ui_prefs_from_db(session) -> None:
    """
    Ensure session display prefs match the DB for the logged-in user.
    Guests without guest_display_prefs get the church default theme.
    """
    church = get_church_default_theme()
    session["church_default_theme"] = church

    user_id = session.get("user_id")
    if user_id:
        row = load_ui_prefs_for_user(user_id)
        if row:
            apply_ui_prefs_to_session(session, user_row=row, church_default=church)
        elif "user_theme" not in session:
            apply_ui_prefs_to_session(session, theme=CHURCH_DEFAULT_TOKEN, church_default=church)
        return

    # Visitors: keep an explicit guest choice; otherwise church default
    if session.get("guest_display_prefs"):
        session["user_theme"] = normalize_theme(session.get("user_theme") or church)
        return
    session["user_theme"] = church
    session["ui_font_scale"] = session.get("ui_font_scale") or DEFAULT_FONT_SCALE
    session["bible_font_scale"] = session.get("bible_font_scale") or DEFAULT_BIBLE_SCALE


def save_user_ui_prefs(
    user_id: int,
    theme: str,
    font_scale: str,
    bible_scale: str,
    *,
    use_personal: bool | None = None,
) -> dict:
    """
    Persist prefs to DB.
    theme may be CHURCH_DEFAULT_TOKEN / empty → follow church default.
    Returns the effective theme + flags.
    """
    from app.models.db import get_db

    raw = (theme or "").strip().lower()
    follow_church = raw in ("", CHURCH_DEFAULT_TOKEN, "default", "church-default")
    if use_personal is False:
        follow_church = True
    if use_personal is True:
        follow_church = False

    church = get_church_default_theme()
    if follow_church:
        stored_theme = church  # keep a concrete value for older code paths
        personal_flag = 0
        effective = church
    else:
        stored_theme = normalize_theme(theme)
        personal_flag = 1
        effective = stored_theme

    font_scale = normalize_font_scale(font_scale)
    bible_scale = normalize_bible_scale(bible_scale)

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            UPDATE users
               SET ui_theme = %s,
                   ui_use_personal_theme = %s,
                   ui_font_scale = %s,
                   bible_font_scale = %s
             WHERE id = %s
            """,
            (stored_theme, personal_flag, font_scale, bible_scale, user_id),
        )
    except Exception:
        # Column missing during partial migrate
        cur.execute(
            """
            UPDATE users
               SET ui_theme = %s,
                   ui_font_scale = %s,
                   bible_font_scale = %s
             WHERE id = %s
            """,
            (stored_theme, font_scale, bible_scale, user_id),
        )
    if cur.rowcount == 0:
        raise RuntimeError(f"No user row updated for id={user_id}")
    db.commit()

    return {
        "theme": effective,
        "font_scale": font_scale,
        "bible_scale": bible_scale,
        "use_personal": bool(personal_flag),
        "church_default": church,
    }


def save_church_default_theme(theme: str) -> str:
    """Owner/Admin: set site-wide default theme."""
    from app.models.db import get_db

    theme = normalize_theme(theme)
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM settings WHERE id = 1")
    if not cur.fetchone():
        cur.execute("INSERT INTO settings (id) VALUES (1)")
    try:
        cur.execute(
            "UPDATE settings SET default_ui_theme = %s WHERE id = 1",
            (theme,),
        )
    except Exception as e:
        raise RuntimeError(f"Could not save default theme (run DB migration): {e}") from e
    db.commit()
    return theme
