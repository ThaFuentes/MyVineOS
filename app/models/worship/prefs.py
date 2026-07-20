# Per-user Worship prompter preferences (layout + sizes + advance defaults).
# Intentionally small and isolated — only used by worship prompter / prefs API.

import json
import pymysql
from app.models.db import get_db

VALID_DISPLAY = frozenset({'stacked', 'inline', 'lyrics'})
VALID_ADVANCE = frozenset({'manual', 'fixed', 'speed', 'recorded'})

DEFAULTS = {
    'display_mode': 'stacked',
    'chord_size': 28,
    'lyric_size': 36,
    'advance_mode': 'manual',
    'fixed_seconds': 8.0,
    'speed_value': 4,
}


def _clamp_size(v, default=36):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(12, min(96, n))


def ensure_prefs_table():
    """Safe runtime migration if builddb has not run yet."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS worship_user_prefs (
                user_id INT UNSIGNED PRIMARY KEY,
                display_mode VARCHAR(24) NOT NULL DEFAULT 'stacked',
                chord_size SMALLINT UNSIGNED NOT NULL DEFAULT 28,
                lyric_size SMALLINT UNSIGNED NOT NULL DEFAULT 36,
                advance_mode VARCHAR(24) NOT NULL DEFAULT 'manual',
                fixed_seconds DECIMAL(6,2) NOT NULL DEFAULT 8.00,
                speed_value SMALLINT UNSIGNED NOT NULL DEFAULT 4,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    try:
        cur.execute(
            "ALTER TABLE worship_songs ADD COLUMN slide_timings_json LONGTEXT NULL"
        )
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def get_user_prefs(user_id: int | None) -> dict:
    ensure_prefs_table()
    prefs = dict(DEFAULTS)
    if not user_id:
        return prefs
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute("SELECT * FROM worship_user_prefs WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
    except Exception:
        return prefs
    if not row:
        return prefs
    mode = (row.get('display_mode') or 'stacked').strip().lower()
    prefs['display_mode'] = mode if mode in VALID_DISPLAY else 'stacked'
    prefs['chord_size'] = _clamp_size(row.get('chord_size'), 28)
    prefs['lyric_size'] = _clamp_size(row.get('lyric_size'), 36)
    adv = (row.get('advance_mode') or 'manual').strip().lower()
    prefs['advance_mode'] = adv if adv in VALID_ADVANCE else 'manual'
    try:
        prefs['fixed_seconds'] = float(row.get('fixed_seconds') or 8)
    except (TypeError, ValueError):
        prefs['fixed_seconds'] = 8.0
    prefs['fixed_seconds'] = max(1.0, min(120.0, prefs['fixed_seconds']))
    try:
        prefs['speed_value'] = max(1, min(10, int(row.get('speed_value') or 4)))
    except (TypeError, ValueError):
        prefs['speed_value'] = 4
    return prefs


def save_user_prefs(user_id: int, data: dict) -> dict:
    ensure_prefs_table()
    if not user_id:
        return dict(DEFAULTS)
    current = get_user_prefs(user_id)
    mode = (data.get('display_mode') or current['display_mode'] or 'stacked').strip().lower()
    if mode not in VALID_DISPLAY:
        mode = current['display_mode']
    chord_size = _clamp_size(data.get('chord_size', current['chord_size']), current['chord_size'])
    lyric_size = _clamp_size(data.get('lyric_size', current['lyric_size']), current['lyric_size'])
    adv = (data.get('advance_mode') or current['advance_mode'] or 'manual').strip().lower()
    if adv not in VALID_ADVANCE:
        adv = current['advance_mode']
    try:
        fixed = float(data.get('fixed_seconds', current['fixed_seconds']))
    except (TypeError, ValueError):
        fixed = current['fixed_seconds']
    fixed = max(1.0, min(120.0, fixed))
    try:
        speed = max(1, min(10, int(data.get('speed_value', current['speed_value']))))
    except (TypeError, ValueError):
        speed = current['speed_value']

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO worship_user_prefs
            (user_id, display_mode, chord_size, lyric_size, advance_mode, fixed_seconds, speed_value)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            display_mode = VALUES(display_mode),
            chord_size = VALUES(chord_size),
            lyric_size = VALUES(lyric_size),
            advance_mode = VALUES(advance_mode),
            fixed_seconds = VALUES(fixed_seconds),
            speed_value = VALUES(speed_value)
    """, (user_id, mode, chord_size, lyric_size, adv, fixed, speed))
    db.commit()
    return get_user_prefs(user_id)


def get_song_slide_timings(song_id: int) -> list:
    """List of absolute ms offsets from song start (index 0 should be 0)."""
    ensure_prefs_table()
    if not song_id:
        return []
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute(
            "SELECT slide_timings_json FROM worship_songs WHERE id = %s",
            (song_id,),
        )
        row = cur.fetchone()
    except Exception:
        return []
    if not row:
        return []
    raw = row.get('slide_timings_json')
    try:
        data = json.loads(raw or '[]')
    except (TypeError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        data = data.get('offsets_ms') or data.get('slides_ms') or []
    if not isinstance(data, list):
        return []
    out = []
    for v in data:
        try:
            out.append(max(0, int(v)))
        except (TypeError, ValueError):
            continue
    return out


def save_song_slide_timings(song_id: int, offsets_ms: list) -> list:
    ensure_prefs_table()
    clean = []
    for v in offsets_ms or []:
        try:
            clean.append(max(0, int(v)))
        except (TypeError, ValueError):
            continue
    if clean and clean[0] != 0:
        clean = [0] + clean
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE worship_songs SET slide_timings_json = %s WHERE id = %s",
        (json.dumps(clean), song_id),
    )
    db.commit()
    return clean
