# app/models/pastoral/vault.py
# Full path: WebChurchMan/app/models/pastoral/vault.py
# File name: vault.py
# Brief, detailed purpose: Database operations for the Pastoral Vault (personal + shared).
# Fully aligned with the updated pastoral_vault schema (title required, section_type, scripture_reference, source_url).

import pymysql
import json
from app.models.db import get_db


def _parse_tags(tags_raw) -> list:
    """Parse tags from JSON array or legacy comma-separated text."""
    if not tags_raw:
        return []
    if isinstance(tags_raw, list):
        return tags_raw
    if isinstance(tags_raw, str):
        try:
            parsed = json.loads(tags_raw)
            return parsed if isinstance(parsed, list) else [str(parsed)]
        except json.JSONDecodeError:
            return [t.strip() for t in tags_raw.split(',') if t.strip()]
    return []


def get_my_vault(user_id: int):
    """Private items owned by the user (visibility='private' AND user_id = current user)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT * FROM pastoral_vault
        WHERE user_id = %s AND visibility = 'private'
        ORDER BY created_at DESC
    """, (user_id,))
    items = cur.fetchall()
    for i in items:
        i['tags'] = _parse_tags(i.get('tags'))
    return items


def get_shared_vault():
    """Items shared with the entire pastoral group (user_id IS NULL AND visibility='pastoral_group')."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT * FROM pastoral_vault
        WHERE user_id IS NULL AND visibility = 'pastoral_group'
        ORDER BY created_at DESC
    """)
    items = cur.fetchall()
    for i in items:
        i['tags'] = _parse_tags(i.get('tags'))
    return items


def add_vault_item(data: dict, owner_id: int | None):
    """Insert a new vault item. owner_id = user_id for private, None for shared."""
    db = get_db()
    cur = db.cursor()

    tags_json = json.dumps(data.get('tags', [])) if isinstance(data.get('tags'), list) else data.get('tags', '[]')
    campus_id = data.get('campus_id')
    if campus_id in (None, '', 0, '0'):
        try:
            from app.models.campuses import resolve_campus_id_for_write
            campus_id = resolve_campus_id_for_write(data.get('campus_id'))
        except Exception:
            campus_id = None

    cur.execute("""
        INSERT INTO pastoral_vault
        (user_id, title, content, reference, notes, tags,
         section_type, scripture_reference, source_url, visibility, campus_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        owner_id,
        data['title'],
        data['content'],
        data.get('reference'),
        data.get('notes'),
        tags_json,
        data.get('section_type', 'point'),
        data.get('scripture_reference'),
        data.get('source_url'),
        data['visibility'],
        campus_id,
    ))
    db.commit()
    return cur.lastrowid


def update_vault_item(item_id: int, data: dict, current_user_id: int):
    """Update an existing vault item - allows edit of both private and shared items."""
    db = get_db()
    cur = db.cursor()

    visibility = data['visibility']
    owner_id = current_user_id if visibility == 'private' else None

    tags_json = json.dumps(data.get('tags', [])) if isinstance(data.get('tags'), list) else data.get('tags', '[]')

    cur.execute("""
        UPDATE pastoral_vault
        SET user_id = %s,
            title = %s,
            content = %s,
            reference = %s,
            notes = %s,
            tags = %s,
            section_type = %s,
            scripture_reference = %s,
            source_url = %s,
            visibility = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s AND (user_id = %s OR user_id IS NULL)
    """, (
        owner_id,
        data['title'],
        data['content'],
        data.get('reference'),
        data.get('notes'),
        tags_json,
        data.get('section_type', 'point'),
        data.get('scripture_reference'),
        data.get('source_url'),
        visibility,
        item_id,
        current_user_id
    ))
    db.commit()


def delete_vault_item(item_id: int, current_user_id: int):
    """Delete a vault item - allowed for owned private items or any shared item."""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        DELETE FROM pastoral_vault
        WHERE id = %s AND (user_id = %s OR user_id IS NULL)
    """, (item_id, current_user_id))
    db.commit()


def search_vault_and_sermons(user_id: int, query: str, visibility: str = 'all', limit: int = 50):
    """Unified search used by both full-page search and Insert-from-Vault modal."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    like = f"%{query}%"

    # Visibility filtering for vault items
    if visibility == 'private':
        vault_condition = "user_id = %s AND visibility = 'private'"
        vault_params = [user_id]
    elif visibility == 'pastoral_group':
        vault_condition = "user_id IS NULL AND visibility = 'pastoral_group'"
        vault_params = []
    else:  # all
        vault_condition = "1=1"
        vault_params = []

    sql = f"""
        SELECT 'vault' AS source_type, id, visibility AS subtype,
               title, content, scripture_reference AS reference,
               notes, tags, created_at, section_type
        FROM pastoral_vault
        WHERE {vault_condition}
          AND (title LIKE %s OR content LIKE %s OR scripture_reference LIKE %s
               OR source_url LIKE %s OR notes LIKE %s OR tags LIKE %s)

        UNION ALL

        SELECT 'sermon' AS source_type, id, visibility AS subtype,
               title, '' AS content, primary_passage AS reference,
               notes, series_tags AS tags, created_at, NULL AS section_type
        FROM pastoral_sermons
        WHERE (created_by = %s
               OR visibility = 'collaborators' AND EXISTS (
                   SELECT 1 FROM sermon_collaborators
                   WHERE sermon_id = pastoral_sermons.id AND user_id = %s)
               OR visibility = 'pastoral_group')
          AND (title LIKE %s OR primary_passage LIKE %s OR notes LIKE %s OR series_tags LIKE %s)

        ORDER BY created_at DESC
        LIMIT %s
    """
    params = vault_params + [like] * 6 + [user_id, user_id] + [like] * 4 + [limit]

    cur.execute(sql, params)
    results = cur.fetchall()
    for r in results:
        r['tags'] = _parse_tags(r.get('tags'))
    return results