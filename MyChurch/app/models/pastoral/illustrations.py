# app/models/pastoral/illustrations.py
# Full path: WebChurchMan/app/models/pastoral/illustrations.py
# File name: illustrations.py
# Brief, detailed purpose:
#   Pure database layer for the Illustration Library.
#   Handles fetching, CRUD, search, and tag parsing.
#   Visibility: 'private' (user_id = owner), 'pastoral_group' (user_id IS NULL).
#   Personal notes stored in notes column (creator-only display in UI).
#   NO Flask imports - models must remain independent of routes.

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


def _normalize_tags_for_storage(tags) -> str:
    """Store tags consistently as JSON array string."""
    if not tags:
        return json.dumps([])
    if isinstance(tags, list):
        return json.dumps(tags)
    if isinstance(tags, str):
        try:
            parsed = json.loads(tags)
            return json.dumps(parsed if isinstance(parsed, list) else [tags])
        except json.JSONDecodeError:
            return json.dumps([t.strip() for t in tags.split(',') if t.strip()])
    return json.dumps([])


def _resolve_owner(data: dict, acting_user_id: int):
    """Private → owner user_id; shared/pastoral_group → NULL (visible to pastoral group)."""
    vis = data.get('visibility') or 'private'
    if isinstance(vis, str):
        vis = vis.strip().lower()
    if vis in ('private', 'only_me', 'me'):
        return acting_user_id
    return None


def get_visible_illustrations(user_id: int, search: str | None = None) -> list[dict]:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    sql = """
        SELECT il.*,
               u.username AS creator_name,
               CASE WHEN il.user_id IS NOT NULL THEN 'private' ELSE 'pastoral_group' END AS visibility
        FROM illustration_library il
        LEFT JOIN users u ON il.user_id = u.id
        WHERE il.user_id = %s OR il.user_id IS NULL
    """
    params = [user_id]

    try:
        from app.models.campuses import content_campus_filter_sql
        frag, cparams = content_campus_filter_sql(
            'il.campus_id', user_id=user_id, owner_column='il.user_id'
        )
        sql += frag
        params.extend(cparams)
    except Exception:
        pass

    if search:
        like = f"%{search}%"
        sql += (
            " AND (il.title LIKE %s OR il.content LIKE %s OR il.source LIKE %s"
            " OR il.tags LIKE %s OR IFNULL(il.notes, '') LIKE %s)"
        )
        params.extend([like] * 5)

    sql += " ORDER BY il.created_at DESC"

    cur.execute(sql, params)
    results = cur.fetchall()

    for r in results:
        r['tags'] = _parse_tags(r.get('tags'))

    return results


def get_illustration_by_id(illus_id: int, user_id: int) -> dict | None:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    sql = """
        SELECT il.*,
               u.username AS creator_name,
               CASE WHEN il.user_id IS NOT NULL THEN 'private' ELSE 'pastoral_group' END AS visibility
        FROM illustration_library il
        LEFT JOIN users u ON il.user_id = u.id
        WHERE il.id = %s
          AND (il.user_id = %s OR il.user_id IS NULL)
    """
    params = [illus_id, user_id]
    try:
        from app.models.campuses import content_campus_filter_sql
        frag, cparams = content_campus_filter_sql(
            'il.campus_id', user_id=user_id, owner_column='il.user_id'
        )
        sql += frag
        params.extend(cparams)
    except Exception:
        pass
    cur.execute(sql, params)

    result = cur.fetchone()
    if result:
        result['tags'] = _parse_tags(result.get('tags'))
    return result


def create_illustration(data: dict, user_id: int) -> int:
    """Create illustration. user_id is the acting user; visibility in data controls owner."""
    db = get_db()
    cur = db.cursor()

    owner = _resolve_owner(data, user_id)
    campus_id = data.get('campus_id')
    if campus_id in (None, '', 0, '0'):
        try:
            from app.models.campuses import resolve_campus_id_for_write
            campus_id = resolve_campus_id_for_write(data.get('campus_id'))
        except Exception:
            campus_id = None

    notes = data.get('notes')
    if notes is not None:
        notes = str(notes).strip() or None

    cur.execute("""
        INSERT INTO illustration_library (user_id, title, content, source, tags, notes, campus_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        owner,
        data['title'],
        data['content'],
        data.get('source'),
        _normalize_tags_for_storage(data.get('tags')),
        notes,
        campus_id,
    ))

    db.commit()
    return cur.lastrowid


def update_illustration(illus_id: int, data: dict, user_id: int) -> None:
    """Update illustration. user_id is the acting user (for ownership check + private owner)."""
    db = get_db()
    cur = db.cursor()

    owner = _resolve_owner(data, user_id)
    notes = data.get('notes')
    if notes is not None:
        notes = str(notes).strip() or None

    cur.execute("""
        UPDATE illustration_library
        SET user_id = %s, title = %s, content = %s, source = %s, tags = %s, notes = %s
        WHERE id = %s AND (user_id = %s OR user_id IS NULL)
    """, (
        owner,
        data['title'],
        data['content'],
        data.get('source'),
        _normalize_tags_for_storage(data.get('tags')),
        notes,
        illus_id,
        user_id,
    ))

    db.commit()


def delete_illustration(illus_id: int, user_id: int) -> bool:
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        DELETE FROM illustration_library
        WHERE id = %s AND (user_id = %s OR user_id IS NULL)
    """, (illus_id, user_id))

    db.commit()
    return cur.rowcount > 0
