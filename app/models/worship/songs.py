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


def get_song(song_id: int, *, with_charts: bool = True):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM worship_songs WHERE id = %s", (song_id,))
    row = cur.fetchone()
    row = _attach_song_fields(row)
    if row and with_charts:
        try:
            from app.models.worship.charts import ensure_default_charts_for_song, list_charts
            ensure_default_charts_for_song(int(song_id), user_id=row.get('updated_by') or row.get('created_by'))
            row['charts'] = list_charts(int(song_id))
        except Exception:
            row['charts'] = []
    return row


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
            if not sections:
                try:
                    from app.models.worship.song_parse import parse_chart_to_sections
                    sections = parse_chart_to_sections(item['lyrics_raw'])
                except Exception:
                    pass
        for j, sec in enumerate(sections or []):
            if not sec.get('id'):
                sec['id'] = f's{j + 1}'
            sec['sort'] = j + 1
        sections_json = json.dumps(sections or [])
        play_order = parse_play_order(item.get('play_order'))
        if not play_order:
            play_order = default_play_order_from_sections(sections or [])
        play_order_json = json.dumps(play_order)
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
            play_order_json,
            (item.get('notes_permanent') or '').strip() or None,
        )
        if existing:
            cur2 = db.cursor()
            cur2.execute("""
                UPDATE worship_songs SET title=%s, artist=%s, ccli_song_number=%s, copyright_line=%s,
                    publisher=%s, copyright_year=%s, lyrics_raw=%s, sections_json=%s, play_order_json=%s,
                    notes_permanent=%s, updated_by=%s WHERE id=%s
            """, (*fields, user_id, existing['id']))
            updated += 1
        else:
            cur2 = db.cursor()
            cur2.execute("""
                INSERT INTO worship_songs (title, artist, ccli_song_number, copyright_line, publisher,
                    copyright_year, lyrics_raw, sections_json, play_order_json, notes_permanent, created_by, updated_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (*fields, user_id, user_id))
            created += 1
    db.commit()
    return {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors}


def save_song(data: dict, user_id: int, song_id: int = None):
    """
    Create or update a song.

    On update: never wipe existing sections / lyrics / chords / notes when the
    caller omits them or sends empty values (partial form posts).
    """
    existing = get_song(song_id, with_charts=False) if song_id else None

    sections_in = data.get('sections')
    lyrics_in = data.get('lyrics_raw')
    play_in = data.get('play_order')

    # If update and no section content was actually provided, keep existing
    sections_provided = sections_in is not None and (
        (isinstance(sections_in, list) and len(sections_in) > 0)
        or (isinstance(sections_in, str) and sections_in.strip())
    )
    lyrics_provided = lyrics_in is not None and str(lyrics_in).strip() != ''

    if song_id and existing and not sections_provided and not lyrics_provided:
        sections = existing.get('sections') or []
        lyrics_raw = existing.get('lyrics_raw')
        play_order = existing.get('play_order') or []
    else:
        sections = normalize_sections(sections_in or [], lyrics_in)
        if not sections and lyrics_in:
            sections = parse_lyrics_to_sections(lyrics_in)
        # On update with empty parse result, fall back to existing rather than wipe
        if song_id and existing and not sections:
            sections = existing.get('sections') or []
            lyrics_raw = existing.get('lyrics_raw')
            play_order = existing.get('play_order') or []
        else:
            # Preserve musical layers (chords/melody/TAB/drums) from Music Studio
            raw_sections = sections_in if isinstance(sections_in, list) else []
            layers_by_id = {}
            for rs in raw_sections:
                if isinstance(rs, dict) and rs.get('id') and rs.get('layers'):
                    layers_by_id[rs['id']] = rs['layers']
            # Also keep layers from existing sections when ids match
            if existing:
                for es in existing.get('sections') or []:
                    if es.get('id') and es.get('layers') and es['id'] not in layers_by_id:
                        layers_by_id[es['id']] = es['layers']
            for i, sec in enumerate(sections):
                if not sec.get('id'):
                    sec['id'] = f"s{uuid.uuid4().hex[:8]}"
                sec['sort'] = i + 1
                if sec['id'] in layers_by_id:
                    sec['layers'] = layers_by_id[sec['id']]
                elif isinstance(raw_sections, list) and i < len(raw_sections) and isinstance(raw_sections[i], dict):
                    if raw_sections[i].get('layers'):
                        sec['layers'] = raw_sections[i]['layers']
            lyrics_raw = lyrics_in
            if not lyrics_raw and sections:
                chunks = []
                for sec in sections:
                    label = sec.get('label') or sec.get('type') or 'Section'
                    chunks.append(f"[{label}]\n{(sec.get('content') or '').strip()}")
                lyrics_raw = '\n\n'.join(chunks)
            valid_ids = {s.get('id') for s in sections if s.get('id')}
            play_order = parse_play_order(play_in)
            play_order = [sid for sid in play_order if sid in valid_ids]
            if not play_order:
                play_order = default_play_order_from_sections(sections)

    sections_json = json.dumps(sections or [])
    play_order_json = json.dumps(play_order or [])

    # Merge metadata: keep existing values when new payload omits them
    title = data.get('title') or (existing.get('title') if existing else None)
    if not title:
        raise ValueError('Song title is required.')

    artist = data.get('artist') if 'artist' in data else (existing.get('artist') if existing else None)
    ccli = data.get('ccli_song_number') if 'ccli_song_number' in data else (existing.get('ccli_song_number') if existing else None)
    copyright_line = data.get('copyright_line') if 'copyright_line' in data else (existing.get('copyright_line') if existing else None)
    publisher = data.get('publisher') if 'publisher' in data else (existing.get('publisher') if existing else None)
    copyright_year = data.get('copyright_year') if 'copyright_year' in data else (existing.get('copyright_year') if existing else None)
    notes_permanent = data.get('notes_permanent') if 'notes_permanent' in data else (existing.get('notes_permanent') if existing else None)
    chords_filename = data.get('chords_filename') if data.get('chords_filename') else (
        existing.get('chords_filename') if existing else None
    )

    db = get_db()
    cur = db.cursor()
    if song_id:
        cur.execute("""
            UPDATE worship_songs SET title=%s, artist=%s, ccli_song_number=%s, copyright_line=%s,
                publisher=%s, copyright_year=%s, lyrics_raw=%s, sections_json=%s, play_order_json=%s,
                notes_permanent=%s, chords_filename=%s, updated_by=%s
            WHERE id=%s
        """, (
            title, artist, ccli, copyright_line, publisher, copyright_year,
            lyrics_raw, sections_json, play_order_json, notes_permanent,
            chords_filename, user_id, song_id,
        ))
        db.commit()
        return song_id
    cur.execute("""
        INSERT INTO worship_songs (title, artist, ccli_song_number, copyright_line, publisher,
            copyright_year, lyrics_raw, sections_json, play_order_json, notes_permanent,
            chords_filename, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        title, artist, ccli, copyright_line, publisher, copyright_year,
        lyrics_raw, sections_json, play_order_json, notes_permanent,
        chords_filename, user_id, user_id,
    ))
    db.commit()
    return cur.lastrowid


def delete_song(song_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM worship_songs WHERE id = %s", (song_id,))
    db.commit()
    return cur.rowcount > 0