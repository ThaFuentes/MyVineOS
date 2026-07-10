import json
import uuid
import pymysql
from app.models.db import get_db
from app.models.worship.sections import (
    default_play_order_from_sections,
    normalize_sections,
    parse_lyrics_to_sections,
    parse_play_order,
)

UPLOAD_SUBDIR = 'worship/chords'


def _parse_sections(raw):
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw or '[]')
    except (json.JSONDecodeError, TypeError):
        return []


def _attach_song_fields(row):
    if not row:
        return row
    row['sections'] = normalize_sections(
        _parse_sections(row.get('sections_json')),
        row.get('lyrics_raw'),
    )
    po = parse_play_order(row.get('play_order_json'))
    if not po:
        po = default_play_order_from_sections(row['sections'])
    row['play_order'] = po
    return row


def list_songs():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM worship_songs ORDER BY title")
    rows = cur.fetchall()
    for row in rows:
        _attach_song_fields(row)
    return rows


def get_song(song_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM worship_songs WHERE id = %s", (song_id,))
    row = cur.fetchone()
    return _attach_song_fields(row)


def bulk_import_songs(items: list, user_id: int) -> dict:
    created = updated = skipped = 0
    errors = []
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"Row {i + 1}: not an object")
            skipped += 1
            continue
        title = (item.get('title') or '').strip()
        if not title:
            errors.append(f"Row {i + 1}: missing title")
            skipped += 1
            continue
        sections = normalize_sections(item.get('sections'), item.get('lyrics_raw'))
        if not sections and item.get('lyrics_raw'):
            sections = parse_lyrics_to_sections(item['lyrics_raw'])
        sections_json = json.dumps(sections or [])
        cur.execute("SELECT id FROM worship_songs WHERE title = %s AND IFNULL(artist,'') = IFNULL(%s,'') LIMIT 1", (
            title, (item.get('artist') or '').strip() or None,
        ))
        existing = cur.fetchone()
        fields = (
            title,
            (item.get('artist') or '').strip() or None,
            (item.get('ccli_song_number') or '').strip() or None,
            (item.get('copyright_line') or '').strip() or None,
            (item.get('publisher') or '').strip() or None,
            item.get('copyright_year'),
            (item.get('lyrics_raw') or '').strip() or None,
            sections_json,
            (item.get('notes_permanent') or '').strip() or None,
        )
        if existing:
            cur2 = db.cursor()
            cur2.execute("""
                UPDATE worship_songs SET title=%s, artist=%s, ccli_song_number=%s, copyright_line=%s,
                    publisher=%s, copyright_year=%s, lyrics_raw=%s, sections_json=%s,
                    notes_permanent=%s, updated_by=%s WHERE id=%s
            """, (*fields, user_id, existing['id']))
            updated += 1
        else:
            cur2 = db.cursor()
            cur2.execute("""
                INSERT INTO worship_songs (title, artist, ccli_song_number, copyright_line, publisher,
                    copyright_year, lyrics_raw, sections_json, notes_permanent, created_by, updated_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (*fields, user_id, user_id))
            created += 1
    db.commit()
    return {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors}


def save_song(data: dict, user_id: int, song_id: int = None):
    sections = normalize_sections(data.get('sections') or [], data.get('lyrics_raw'))
    if not sections and data.get('lyrics_raw'):
        sections = parse_lyrics_to_sections(data['lyrics_raw'])
    for i, sec in enumerate(sections):
        if not sec.get('id'):
            sec['id'] = f"s{uuid.uuid4().hex[:8]}"
        sec['sort'] = i + 1
    sections_json = json.dumps(sections)

    valid_ids = {s.get('id') for s in sections if s.get('id')}
    play_order = parse_play_order(data.get('play_order'))
    play_order = [sid for sid in play_order if sid in valid_ids]
    if not play_order:
        play_order = default_play_order_from_sections(sections)
    play_order_json = json.dumps(play_order)

    # Keep lyrics_raw in sync for export/search when built from sections
    lyrics_raw = data.get('lyrics_raw')
    if not lyrics_raw and sections:
        chunks = []
        for sec in sections:
            label = sec.get('label') or sec.get('type') or 'Section'
            chunks.append(f"[{label}]\n{(sec.get('content') or '').strip()}")
        lyrics_raw = '\n\n'.join(chunks)

    db = get_db()
    cur = db.cursor()
    if song_id:
        cur.execute("""
            UPDATE worship_songs SET title=%s, artist=%s, ccli_song_number=%s, copyright_line=%s,
                publisher=%s, copyright_year=%s, lyrics_raw=%s, sections_json=%s, play_order_json=%s,
                notes_permanent=%s, chords_filename=%s, updated_by=%s
            WHERE id=%s
        """, (
            data['title'], data.get('artist'), data.get('ccli_song_number'),
            data.get('copyright_line'), data.get('publisher'), data.get('copyright_year'),
            lyrics_raw, sections_json, play_order_json, data.get('notes_permanent'),
            data.get('chords_filename'), user_id, song_id,
        ))
        db.commit()
        return song_id
    cur.execute("""
        INSERT INTO worship_songs (title, artist, ccli_song_number, copyright_line, publisher,
            copyright_year, lyrics_raw, sections_json, play_order_json, notes_permanent,
            chords_filename, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        data['title'], data.get('artist'), data.get('ccli_song_number'),
        data.get('copyright_line'), data.get('publisher'), data.get('copyright_year'),
        lyrics_raw, sections_json, play_order_json, data.get('notes_permanent'),
        data.get('chords_filename'), user_id, user_id,
    ))
    db.commit()
    return cur.lastrowid


def delete_song(song_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM worship_songs WHERE id = %s", (song_id,))
    db.commit()
    return cur.rowcount > 0