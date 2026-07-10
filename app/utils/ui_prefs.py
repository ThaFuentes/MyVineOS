# app/utils/ui_prefs.py
# Personal display preferences: theme + site font scale + Bible reader scale.
# Logged-in members only; values stored on users and mirrored into session.

from __future__ import annotations

ALLOWED_THEMES = (
    "cyan-glow",   # default dark neon
    "soft-light",  # brighter soft page
    "tropical",    # teal / coral / warm green
)

ALLOWED_FONT_SCALES = ("sm", "md", "lg", "xl")
ALLOWED_BIBLE_SCALES = ("sm", "md", "lg", "xl", "xxl")

DEFAULT_THEME = "cyan-glow"
DEFAULT_FONT_SCALE = "md"
DEFAULT_BIBLE_SCALE = "md"

THEME_LABELS = {
    "cyan-glow": "Classic (bright)",
    "soft-light": "Soft light",
    "tropical": "Tropical",
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
    """Write normalized prefs into the Flask session."""
    if user_row is not None:
        theme = user_row.get("ui_theme", theme)
        font_scale = user_row.get("ui_font_scale", font_scale)
        bible_scale = user_row.get("bible_font_scale", bible_scale)
    session["user_theme"] = normalize_theme(theme)
    session["ui_font_scale"] = normalize_font_scale(font_scale)
    session["bible_font_scale"] = normalize_bible_scale(bible_scale)


def save_user_ui_prefs(user_id: int, theme: str, font_scale: str, bible_scale: str) -> dict:
    """Persist prefs to DB. Returns the normalized dict saved."""
    import pymysql
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
    db.commit()
    return {
        "theme": theme,
        "font_scale": font_scale,
        "bible_scale": bible_scale,
    }
