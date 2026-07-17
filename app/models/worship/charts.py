# Per-role worship charts: lyrics, vocals, guitars, bass, keys — not one jumbo blob.

from __future__ import annotations

import json
import re
import uuid

import pymysql

from app.models.db import get_db
from app.models.worship.sections import (
    default_play_order_from_sections,
    normalize_sections,
    parse_play_order,
)

# Built-in chart roles. Team can add custom chart_key later via "other".
DEFAULT_CHART_DEFS = [
    {
        'chart_key': 'full_band',
        'display_name': 'Full band (default)',
        'instrument_family': 'full',
        'is_primary': 1,
        'show_chords': 1,
        'show_lyrics': 1,
        'notation': 'chordpro',
    },
    {
        'chart_key': 'lyrics',
        'display_name': 'Lyrics only',
        'instrument_family': 'lyrics',
        'is_primary': 0,
        'show_chords': 0,
        'show_lyrics': 1,
        'notation': 'text',
    },
    {
        'chart_key': 'lead_vocal',
        'display_name': 'Lead vocals + cues',
        'instrument_family': 'vocals',
        'is_primary': 0,
        'show_chords': 0,
        'show_lyrics': 1,
        'notation': 'text',
    },
    {
        'chart_key': 'harmony_vocal',
        'display_name': 'Harmony / BGVs',
        'instrument_family': 'vocals',
        'is_primary': 0,
        'show_chords': 0,
        'show_lyrics': 1,
        'notation': 'text',
    },
    {
        'chart_key': 'lead_guitar',
        'display_name': 'Lead guitar',
        'instrument_family': 'guitar',
        'is_primary': 0,
        'show_chords': 1,
        'show_lyrics': 1,
        'notation': 'chordpro',
    },
    {
        'chart_key': 'rhythm_guitar',
        'display_name': 'Rhythm guitar',
        'instrument_family': 'guitar',
        'is_primary': 0,
        'show_chords': 1,
        'show_lyrics': 1,
        'notation': 'chordpro',
    },
    {
        'chart_key': 'bass',
        'display_name': 'Bass',
        'instrument_family': 'bass',
        'is_primary': 0,
        'show_chords': 1,
        'show_lyrics': 0,
        'notation': 'nashville',
    },
    {
        'chart_key': 'keys',
        'display_name': 'Keys / piano',
        'instrument_family': 'keys',
        'is_primary': 0,
        'show_chords': 1,
        'show_lyrics': 1,
        'notation': 'chordpro',
    },
    {
        'chart_key': 'drums',
        'display_name': 'Drums',
        'instrument_family': 'drums',
        'is_primary': 0,
        'show_chords': 0,
        'show_lyrics': 0,
        'notation': 'drums',
    },
]

_CHORDPRO_CHORD = re.compile(r'\[[A-G][#b]?(?:m|maj|min|dim|aug|sus|add|M)?\d*(?:/[A-G][#b]?)?\]')


def ensure_charts_table():
    """Idempotent create for environments that already ran older builddb."""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS worship_song_charts (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            song_id INT UNSIGNED NOT NULL,
            chart_key VARCHAR(40) NOT NULL,
            display_name VARCHAR(120) NOT NULL,
            instrument_family VARCHAR(32) NOT NULL DEFAULT 'full',
            is_primary TINYINT(1) NOT NULL DEFAULT 0,
            show_chords TINYINT(1) NOT NULL DEFAULT 1,
            show_lyrics TINYINT(1) NOT NULL DEFAULT 1,
            capo SMALLINT NULL,
            notation VARCHAR(24) NOT NULL DEFAULT 'chordpro',
            sections_json LONGTEXT NOT NULL,
            play_order_json LONGTEXT NULL,
            chart_filename VARCHAR(255) NULL,
            notes TEXT NULL,
            created_by INT UNSIGNED NULL,
            updated_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_worship_song_chart (song_id, chart_key),
            INDEX idx_worship_chart_song (song_id)
        ) ENGINE=InnoDB
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS worship_user_chart_notes (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            chart_id INT UNSIGNED NOT NULL,
            user_id INT UNSIGNED NOT NULL,
            note_text TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_worship_user_chart (chart_id, user_id)
        ) ENGINE=InnoDB
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS worship_ccli_settings (
            id TINYINT UNSIGNED PRIMARY KEY DEFAULT 1,
            ccli_license_number VARCHAR(64) NULL,
            organization_name VARCHAR(255) NULL,
            notes TEXT NULL,
            updated_by INT UNSIGNED NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
    """)
    db.commit()


def strip_chordpro_chords(text: str) -> str:
    """Lyrics-only view: remove [Am] style chords, keep words."""
    if not text:
        return ''
    out = _CHORDPRO_CHORD.sub('', text)
    out = re.sub(r'[ \t]{2,}', ' ', out)
    out = re.sub(r' *\n *', '\n', out)
    return out.strip()


def sections_lyrics_only(sections: list) -> list:
    cleaned = []
    for sec in sections or []:
        s = dict(sec)
        s['content'] = strip_chordpro_chords(s.get('content') or '')
        cleaned.append(s)
    return cleaned


def _parse_sections(raw) -> list:
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw or '[]')
    except (json.JSONDecodeError, TypeError):
        return []


def _attach_chart(row: dict | None) -> dict | None:
    if not row:
        return None
    secs = normalize_sections(_parse_sections(row.get('sections_json')), None)
    row['sections'] = secs
    po = parse_play_order(row.get('play_order_json'))
    if not po:
        po = default_play_order_from_sections(secs)
    row['play_order'] = po
    return row


def list_charts(song_id: int) -> list:
    ensure_charts_table()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        """
        SELECT * FROM worship_song_charts
        WHERE song_id = %s
        ORDER BY is_primary DESC, instrument_family, display_name
        """,
        (song_id,),
    )
    rows = cur.fetchall() or []
    return [_attach_chart(r) for r in rows]


def get_chart(chart_id: int) -> dict | None:
    ensure_charts_table()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM worship_song_charts WHERE id = %s", (chart_id,))
    return _attach_chart(cur.fetchone())


def get_chart_by_key(song_id: int, chart_key: str) -> dict | None:
    ensure_charts_table()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT * FROM worship_song_charts WHERE song_id = %s AND chart_key = %s",
        (song_id, chart_key),
    )
    return _attach_chart(cur.fetchone())


def _seed_layers_on_sections(sections: list) -> list:
    """Ensure each section has layers so the Music Studio can open with real notes."""
    out = []
    for sec in sections or []:
        s = dict(sec)
        layers = s.get('layers') if isinstance(s.get('layers'), dict) else {}
        content = s.get('content') or ''
        lyrics = (layers.get('lyrics') or '').strip()
        chords = (layers.get('chords') or '').strip()
        if not lyrics and content:
            # Build lyrics + chord overlay from ChordPro so notes sit above words
            import re as _re
            plain = []
            chord_line = []
            for line in str(content).replace('\r\n', '\n').split('\n'):
                ly, ch = '', ''
                i = 0
                while i < len(line):
                    if line[i] == '[':
                        end = line.find(']', i)
                        if end > i:
                            chord = line[i + 1:end]
                            while len(ch) < len(ly):
                                ch += ' '
                            ch += chord
                            i = end + 1
                            continue
                    ly += line[i]
                    if len(ch) < len(ly):
                        ch += ' '
                    i += 1
                plain.append(ly)
                chord_line.append(ch.rstrip())
            lyrics = '\n'.join(plain)
            if not chords:
                chords = '\n'.join(chord_line)
        layers = {
            'lyrics': lyrics or content,
            'chords': chords,
            'melody': layers.get('melody') or '',
            'guitar_tab': layers.get('guitar_tab') or '',
            'bass_tab': layers.get('bass_tab') or '',
            'drums': layers.get('drums') or {},
        }
        s['layers'] = layers
        if not s.get('content') and lyrics:
            s['content'] = content or lyrics
        out.append(s)
    return out


def ensure_default_charts_for_song(
    song_id: int,
    user_id: int | None = None,
    *,
    initial_sections: list | None = None,
    initial_play_order: list | None = None,
) -> list:
    """
    Create standard role charts if missing.
    Uses initial_sections (from create/import) or migrates song sections_json.
    Always seeds layers so Music Studio has chords/notes/TAB structure.
    """
    ensure_charts_table()
    existing = {c['chart_key']: c for c in list_charts(song_id)}
    if len(existing) >= len(DEFAULT_CHART_DEFS):
        return list(existing.values())

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT sections_json, play_order_json, lyrics_raw FROM worship_songs WHERE id = %s",
        (song_id,),
    )
    song = cur.fetchone() or {}
    if initial_sections is not None:
        base_sections = normalize_sections(initial_sections, None)
    else:
        base_sections = normalize_sections(_parse_sections(song.get('sections_json')), song.get('lyrics_raw'))
    base_sections = _seed_layers_on_sections(base_sections)
    if initial_play_order:
        base_order = list(initial_play_order)
    else:
        base_order = parse_play_order(song.get('play_order_json')) or default_play_order_from_sections(base_sections)
    lyrics_sections = _seed_layers_on_sections(sections_lyrics_only(base_sections))

    cur2 = db.cursor()
    for defn in DEFAULT_CHART_DEFS:
        key = defn['chart_key']
        if key in existing:
            continue
        if key == 'full_band':
            secs, order = base_sections, base_order
        elif key in ('lyrics', 'lead_vocal', 'harmony_vocal'):
            secs, order = lyrics_sections, base_order
        else:
            # Instrument charts start from full band so notes/TAB can be customized per role
            secs, order = base_sections, base_order
        cur2.execute(
            """
            INSERT INTO worship_song_charts
                (song_id, chart_key, display_name, instrument_family, is_primary,
                 show_chords, show_lyrics, notation, sections_json, play_order_json,
                 notes, created_by, updated_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                song_id,
                key,
                defn['display_name'],
                defn['instrument_family'],
                int(defn.get('is_primary') or 0),
                int(defn.get('show_chords') if defn.get('show_chords') is not None else 1),
                int(defn.get('show_lyrics') if defn.get('show_lyrics') is not None else 1),
                defn.get('notation') or 'chordpro',
                json.dumps(secs or []),
                json.dumps(order or []),
                None,
                user_id,
                user_id,
            ),
        )
    db.commit()
    return list_charts(song_id)


def save_chart(
    song_id: int,
    chart_key: str,
    data: dict,
    user_id: int,
    chart_id: int | None = None,
) -> int:
    """Create or update one role chart."""
    ensure_charts_table()
    from app.models.worship.sections import parse_lyrics_to_sections

    sections = normalize_sections(data.get('sections') or [], data.get('lyrics_raw'))
    if not sections and data.get('lyrics_raw'):
        sections = parse_lyrics_to_sections(data['lyrics_raw'])
    for i, sec in enumerate(sections):
        if not sec.get('id'):
            sec['id'] = f"s{uuid.uuid4().hex[:8]}"
        sec['sort'] = i + 1
    valid_ids = {s.get('id') for s in sections if s.get('id')}
    play_order = parse_play_order(data.get('play_order'))
    play_order = [sid for sid in play_order if sid in valid_ids]
    if not play_order:
        play_order = default_play_order_from_sections(sections)

    display_name = (data.get('display_name') or chart_key).strip()[:120]
    family = (data.get('instrument_family') or 'full').strip()[:32]
    notation = (data.get('notation') or 'chordpro').strip()[:24]
    notes = (data.get('notes') or '').strip() or None
    capo = data.get('capo')
    try:
        capo = int(capo) if capo not in (None, '') else None
    except (TypeError, ValueError):
        capo = None
    show_chords = 1 if data.get('show_chords', True) else 0
    show_lyrics = 1 if data.get('show_lyrics', True) else 0
    is_primary = 1 if data.get('is_primary') else 0

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    if chart_id:
        cur.execute("SELECT id FROM worship_song_charts WHERE id = %s AND song_id = %s", (chart_id, song_id))
        if not cur.fetchone():
            raise ValueError('Chart not found for this song.')
        if is_primary:
            cur2 = db.cursor()
            cur2.execute(
                "UPDATE worship_song_charts SET is_primary = 0 WHERE song_id = %s AND id <> %s",
                (song_id, chart_id),
            )
        cur2 = db.cursor()
        cur2.execute(
            """
            UPDATE worship_song_charts SET
                display_name=%s, instrument_family=%s, is_primary=%s,
                show_chords=%s, show_lyrics=%s, capo=%s, notation=%s,
                sections_json=%s, play_order_json=%s, notes=%s, updated_by=%s
            WHERE id=%s
            """,
            (
                display_name, family, is_primary, show_chords, show_lyrics, capo, notation,
                json.dumps(sections), json.dumps(play_order), notes, user_id, chart_id,
            ),
        )
        db.commit()
        # Keep song-level sections in sync with primary chart for setlists/podium
        if is_primary or chart_key == 'full_band':
            _sync_song_from_primary(song_id, user_id)
        return int(chart_id)

    # Upsert by key
    cur.execute(
        "SELECT id FROM worship_song_charts WHERE song_id = %s AND chart_key = %s",
        (song_id, chart_key),
    )
    row = cur.fetchone()
    if row:
        return save_chart(song_id, chart_key, {**data, 'is_primary': is_primary}, user_id, chart_id=int(row['id']))

    if is_primary:
        cur2 = db.cursor()
        cur2.execute("UPDATE worship_song_charts SET is_primary = 0 WHERE song_id = %s", (song_id,))
    cur2 = db.cursor()
    cur2.execute(
        """
        INSERT INTO worship_song_charts
            (song_id, chart_key, display_name, instrument_family, is_primary,
             show_chords, show_lyrics, capo, notation, sections_json, play_order_json,
             notes, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            song_id, chart_key[:40], display_name, family, is_primary,
            show_chords, show_lyrics, capo, notation,
            json.dumps(sections), json.dumps(play_order), notes, user_id, user_id,
        ),
    )
    db.commit()
    new_id = int(cur2.lastrowid)
    if is_primary or chart_key == 'full_band':
        _sync_song_from_primary(song_id, user_id)
    return new_id


def _sync_song_from_primary(song_id: int, user_id: int | None = None):
    """Mirror primary (or full_band) chart into worship_songs for legacy prompter."""
    charts = list_charts(song_id)
    primary = next((c for c in charts if c.get('is_primary')), None)
    if not primary:
        primary = next((c for c in charts if c.get('chart_key') == 'full_band'), None)
    if not primary:
        return
    sections = primary.get('sections') or []
    play_order = primary.get('play_order') or []
    chunks = []
    for sec in sections:
        label = sec.get('label') or sec.get('type') or 'Section'
        chunks.append(f"[{label}]\n{(sec.get('content') or '').strip()}")
    lyrics_raw = '\n\n'.join(chunks) if chunks else None
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE worship_songs
        SET sections_json=%s, play_order_json=%s, lyrics_raw=%s, updated_by=%s
        WHERE id=%s
        """,
        (json.dumps(sections), json.dumps(play_order), lyrics_raw, user_id, song_id),
    )
    db.commit()


def save_user_chart_note(chart_id: int, user_id: int, note_text: str) -> None:
    ensure_charts_table()
    db = get_db()
    cur = db.cursor()
    text = (note_text or '').strip()
    if not text:
        cur.execute(
            "DELETE FROM worship_user_chart_notes WHERE chart_id = %s AND user_id = %s",
            (chart_id, user_id),
        )
    else:
        cur.execute(
            """
            INSERT INTO worship_user_chart_notes (chart_id, user_id, note_text)
            VALUES (%s,%s,%s)
            ON DUPLICATE KEY UPDATE note_text = VALUES(note_text)
            """,
            (chart_id, user_id, text),
        )
    db.commit()


def get_user_chart_note(chart_id: int, user_id: int) -> str:
    ensure_charts_table()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT note_text FROM worship_user_chart_notes WHERE chart_id = %s AND user_id = %s",
        (chart_id, user_id),
    )
    row = cur.fetchone()
    return (row or {}).get('note_text') or ''


def get_ccli_settings() -> dict:
    ensure_charts_table()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM worship_ccli_settings WHERE id = 1")
    row = cur.fetchone() or {}
    return {
        'ccli_license_number': (row.get('ccli_license_number') or '').strip(),
        'organization_name': (row.get('organization_name') or '').strip(),
        'notes': (row.get('notes') or '').strip(),
    }


def save_ccli_settings(data: dict, user_id: int) -> None:
    ensure_charts_table()
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO worship_ccli_settings (id, ccli_license_number, organization_name, notes, updated_by)
        VALUES (1, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            ccli_license_number = VALUES(ccli_license_number),
            organization_name = VALUES(organization_name),
            notes = VALUES(notes),
            updated_by = VALUES(updated_by)
        """,
        (
            (data.get('ccli_license_number') or '').strip() or None,
            (data.get('organization_name') or '').strip() or None,
            (data.get('notes') or '').strip() or None,
            user_id,
        ),
    )
    db.commit()


def songselect_search_url(title: str = '', artist: str = '', ccli: str = '') -> str:
    """
    Link-out only to official CCLI SongSelect — never scrape.
    User must have their own SongSelect/CCLI account.
    """
    from urllib.parse import quote_plus
    q = (ccli or title or '').strip()
    if artist and not ccli:
        q = f'{title} {artist}'.strip()
    if not q:
        return 'https://songselect.ccli.com/'
    return f'https://songselect.ccli.com/search/results?SearchTerm={quote_plus(q)}'
