# app/utils/ui_prefs.py
# Personal display preferences: theme + site font scale + Bible reader scale.
# Logged-in members only; values stored on users and mirrored into session.

from __future__ import annotations

# cyan-glow remains the site default (original dark neon look).
ALLOWED_THEMES = (
    "cyan-glow",      # Default — original cyan dark
    "soft-light",     # Daytime / brighter page
    "tropical",       # Teal + coral
    "purple-grace",   # Royal purple
    "amber-hope",     # Warm gold
    "forest",         # Green sanctuary
    "rose-dawn",      # Soft rose
)

ALLOWED_FONT_SCALES = ("sm", "md", "lg", "xl")
ALLOWED_BIBLE_SCALES = ("sm", "md", "lg", "xl", "xxl")

DEFAULT_THEME = "cyan-glow"
DEFAULT_FONT_SCALE = "md"
DEFAULT_BIBLE_SCALE = "md"

THEME_LABELS = {
    "cyan-glow": "Classic (default)",
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
    return v if v in ALLOWED_THEMES else DEFAULT_THEME


def normalize_font_scale(value) -> str:
    v = (value or "").strip().lower()
    return v if v in ALLOWED_FONT_SCALES else DEFAULT_FONT_SCALE


def normalize_bible_scale(value) -> str:
    v = (value or "").strip().lower()
    return v if v in ALLOWED_BIBLE_SCALES else DEFAULT_BIBLE_SCALE


def apply_ui_prefs_to_session(session, user_row=None, theme=None, font_scale=None, bible_scale=None):
    """Write normalized prefs into the Flask session (permanent cookie)."""
    if user_row is not None:
        theme = user_row.get("ui_theme", theme)
        font_scale = user_row.get("ui_font_scale", font_scale)
        bible_scale = user_row.get("bible_font_scale", bible_scale)
    session["user_theme"] = normalize_theme(theme)
    session["ui_font_scale"] = normalize_font_scale(font_scale)
    session["bible_font_scale"] = normalize_bible_scale(bible_scale)
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
        cur.execute(
            """
            SELECT ui_theme, ui_font_scale, bible_font_scale
              FROM users
             WHERE id = %s
             LIMIT 1
            """,
            (user_id,),
        )
        return cur.fetchone()
    except Exception as exc:
        # Columns may not exist yet on an old DB — ignore quietly
        print(f"load_ui_prefs_for_user: {exc}")
        return None


def sync_ui_prefs_from_db(session) -> None:
    """
    Ensure session display prefs match the DB for the logged-in user.
    Call on each request so themes survive new tabs, restarts, and partial sessions.
    """
    user_id = session.get("user_id")
    if not user_id:
        return
    row = load_ui_prefs_for_user(user_id)
    if row:
        apply_ui_prefs_to_session(session, user_row=row)
    elif "user_theme" not in session:
        apply_ui_prefs_to_session(session)


def save_user_ui_prefs(user_id: int, theme: str, font_scale: str, bible_scale: str) -> dict:
    """Persist prefs to DB. Returns the normalized dict saved."""
    from app.models.db import get_db

    theme = normalize_theme(theme)
    font_scale = normalize_font_scale(font_scale)
    bible_scale = normalize_bible_scale(bible_scale)

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE users
           SET ui_theme = %s,
               ui_font_scale = %s,
               bible_font_scale = %s
         WHERE id = %s
        """,
        (theme, font_scale, bible_scale, user_id),
    )
    if cur.rowcount == 0:
        raise RuntimeError(f"No user row updated for id={user_id}")
    db.commit()

    # Verify write (catches silent failures / wrong DB)
    cur2 = db.cursor()
    cur2.execute(
        "SELECT ui_theme, ui_font_scale, bible_font_scale FROM users WHERE id = %s",
        (user_id,),
    )
    row = cur2.fetchone()
    if row:
        # row may be tuple depending on cursor
        saved_theme = row[0] if not isinstance(row, dict) else row.get("ui_theme")
        if saved_theme != theme:
            raise RuntimeError(
                f"Theme save mismatch: wanted {theme!r}, DB has {saved_theme!r}"
            )

    return {
        "theme": theme,
        "font_scale": font_scale,
        "bible_scale": bible_scale,
    }
