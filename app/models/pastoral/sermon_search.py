# Search + AI context for pastoral sermons — OWNER ONLY (never other users' content).

from __future__ import annotations

import re
from typing import Any

import pymysql

from app.models.db import get_db
from app.models.pastoral.sermons import get_sermon_sections
from app.utils.ai_format import plain_snippet


def _own_sql(user_id: int, alias: str = 'ps') -> tuple[str, list]:
    """Only sermons created by this user — not collaborators, not pastoral_group shares."""
    return f"{alias}.created_by = %s", [int(user_id)]


def _get_own_sermon(sermon_id: int, user_id: int) -> dict | None:
    """Load a sermon only if the current user is the creator (ignores Admin global access)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        """
        SELECT ps.*,
               CONCAT(IFNULL(u.first_name,''), ' ', IFNULL(u.last_name,'')) AS creator_name
        FROM pastoral_sermons ps
        LEFT JOIN users u ON ps.created_by = u.id
        WHERE ps.id = %s AND ps.created_by = %s
        """,
        (int(sermon_id), int(user_id)),
    )
    return cur.fetchone()


def list_own_sermons(user_id: int, *, limit: int = 80) -> list[dict]:
    """Sermons this user created (newest first)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    own_sql, own_params = _own_sql(user_id)
    cur.execute(
        f"""
        SELECT ps.id, ps.title, ps.primary_passage, ps.service_date,
               ps.series_tags, ps.created_at
        FROM pastoral_sermons ps
        WHERE {own_sql}
        ORDER BY ps.created_at DESC
        LIMIT %s
        """,
        (*own_params, int(limit)),
    )
    return list(cur.fetchall() or [])


def search_sermons_library(user_id: int, query: str, *, limit: int = 40) -> list[dict[str, Any]]:
    """
    Keyword search across YOUR sermons only (title, passage, tags, section body).
    Never returns another user's content.
    """
    q = (query or '').strip()
    if not q or len(q) < 2:
        return []

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    own_sql, own_params = _own_sql(user_id)
    like = f'%{q}%'

    cur.execute(
        f"""
        SELECT ps.id AS sermon_id, ps.title AS sermon_title, ps.primary_passage,
               ps.service_date, ps.created_at,
               ss.id AS section_id, ss.title AS section_title, ss.section_type,
               ss.content, ss.notes AS section_notes, ss.scripture_reference
        FROM pastoral_sermons ps
        INNER JOIN sermon_sections ss ON ss.sermon_id = ps.id
        WHERE {own_sql}
          AND (
                ss.content LIKE %s
             OR ss.title LIKE %s
             OR ss.notes LIKE %s
             OR ss.scripture_reference LIKE %s
          )
        ORDER BY ps.created_at DESC, ss.sort_order ASC
        LIMIT %s
        """,
        (*own_params, like, like, like, like, int(limit)),
    )
    section_rows = cur.fetchall() or []

    cur.execute(
        f"""
        SELECT ps.id AS sermon_id, ps.title AS sermon_title, ps.primary_passage,
               ps.service_date, ps.created_at, ps.series_tags,
               ps.header_text, ps.footer_text, NULL AS section_id
        FROM pastoral_sermons ps
        WHERE {own_sql}
          AND (
                ps.title LIKE %s
             OR ps.primary_passage LIKE %s
             OR COALESCE(ps.series_tags, '') LIKE %s
             OR COALESCE(ps.header_text, '') LIKE %s
             OR COALESCE(ps.footer_text, '') LIKE %s
          )
        ORDER BY ps.created_at DESC
        LIMIT %s
        """,
        (*own_params, like, like, like, like, like, int(limit)),
    )
    sermon_rows = cur.fetchall() or []

    hits: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    for row in section_rows:
        key = (int(row['sermon_id']), int(row['section_id']) if row.get('section_id') else 0)
        if key in seen:
            continue
        seen.add(key)
        body = row.get('content') or row.get('section_notes') or ''
        hits.append({
            'sermon_id': int(row['sermon_id']),
            'sermon_title': row.get('sermon_title') or 'Untitled',
            'primary_passage': row.get('primary_passage') or '',
            'service_date': row.get('service_date'),
            'section_id': row.get('section_id'),
            'section_title': row.get('section_title') or '',
            'section_type': row.get('section_type') or '',
            'match_field': 'section',
            'snippet': plain_snippet(body, q),
        })

    for row in sermon_rows:
        sid = int(row['sermon_id'])
        if any(h['sermon_id'] == sid for h in hits):
            title_hit = q.lower() in (row.get('sermon_title') or '').lower()
            passage_hit = q.lower() in (row.get('primary_passage') or '').lower()
            if not (title_hit or passage_hit):
                continue
        meta_key = (sid, -1)
        if meta_key in seen:
            continue
        seen.add(meta_key)
        field_bits = []
        for label, val in (
            ('title', row.get('sermon_title')),
            ('passage', row.get('primary_passage')),
            ('tags', row.get('series_tags')),
            ('header', row.get('header_text')),
            ('footer', row.get('footer_text')),
        ):
            if val and q.lower() in str(val).lower():
                field_bits.append(label)
        hits.append({
            'sermon_id': sid,
            'sermon_title': row.get('sermon_title') or 'Untitled',
            'primary_passage': row.get('primary_passage') or '',
            'service_date': row.get('service_date'),
            'section_id': None,
            'section_title': '',
            'section_type': '',
            'match_field': ', '.join(field_bits) or 'sermon',
            'snippet': plain_snippet(
                ' · '.join(
                    filter(None, [
                        row.get('sermon_title'),
                        row.get('primary_passage'),
                        row.get('series_tags'),
                    ])
                ),
                q,
            ),
        })

    return hits[:limit]


def sermon_catalog(user_id: int, *, limit: int = 80) -> list[dict]:
    """Lightweight list of THIS user's sermons only (for AI catalog / UI)."""
    rows = list_own_sermons(user_id, limit=limit)
    out = []
    for r in rows:
        out.append({
            'id': r.get('id'),
            'title': r.get('title') or 'Untitled',
            'passage': r.get('primary_passage') or '',
            'service_date': str(r.get('service_date') or '')[:10],
            'series': r.get('series_tags') or '',
        })
    return out


def pack_sermons_for_ai(
    user_id: int,
    question: str,
    *,
    max_sermons: int = 10,
    max_chars_each: int = 2200,
    max_total_chars: int = 24000,
) -> tuple[str, list[dict]]:
    """
    Build AI context from THIS user's sermons only.
    Never includes collaborator-only or pastoral-group sermons owned by others.
    """
    q = (question or '').strip()
    hits = search_sermons_library(user_id, q, limit=30) if len(q) >= 2 else []
    ordered_ids: list[int] = []
    for h in hits:
        sid = int(h['sermon_id'])
        if sid not in ordered_ids:
            ordered_ids.append(sid)

    for r in list_own_sermons(user_id, limit=40):
        sid = int(r['id'])
        if sid not in ordered_ids:
            ordered_ids.append(sid)
        if len(ordered_ids) >= max_sermons * 2:
            break

    used: list[dict] = []
    chunks: list[str] = []
    total = 0
    catalog = sermon_catalog(user_id, limit=60)
    catalog_lines = [
        f"- #{c['id']}: {c['title']}"
        + (f" ({c['passage']})" if c.get('passage') else '')
        + (f" · {c['service_date']}" if c.get('service_date') else '')
        for c in catalog
    ]
    header = (
        f"MY SERMON LIBRARY ONLY ({len(catalog)} sermons I created — never other pastors):\n"
        + '\n'.join(catalog_lines[:60])
        + "\n\nDETAILED CONTENT (most relevant first):\n"
    )
    total += len(header)

    for sid in ordered_ids:
        if len(used) >= max_sermons or total >= max_total_chars:
            break
        # Owner-only load — do not use get_sermon_by_id (Admin can open any sermon)
        sermon = _get_own_sermon(sid, user_id)
        if not sermon:
            continue
        sections = get_sermon_sections(sid) or []
        parts = [
            f"=== Sermon #{sid}: {sermon.get('title') or 'Untitled'} ===",
            f"Passage: {sermon.get('primary_passage') or '(none)'}",
            f"Date: {str(sermon.get('service_date') or '')[:10] or '(none)'}",
        ]
        if sermon.get('series_tags'):
            parts.append(f"Series/tags: {sermon.get('series_tags')}")
        for sec in sections:
            st = (sec.get('title') or sec.get('section_type') or 'Section').strip()
            body = re.sub(r'<[^>]+>', ' ', sec.get('content') or '')
            body = re.sub(r'\s+', ' ', body).strip()
            if not body and not st:
                continue
            parts.append(f"[{st}] {body}")
        blob = '\n'.join(parts)
        if len(blob) > max_chars_each:
            blob = blob[:max_chars_each] + '\n[…truncated]'
        if total + len(blob) > max_total_chars:
            remain = max_total_chars - total
            if remain < 400:
                break
            blob = blob[:remain] + '\n[…truncated]'
        chunks.append(blob)
        total += len(blob) + 2
        used.append({
            'id': sid,
            'title': sermon.get('title') or 'Untitled',
            'passage': sermon.get('primary_passage') or '',
        })

    context = header + '\n\n'.join(chunks)
    return context, used
