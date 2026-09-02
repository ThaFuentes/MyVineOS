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


def _plain_html(text: str) -> str:
    body = re.sub(r'<[^>]+>', ' ', text or '')
    return re.sub(r'\s+', ' ', body).strip()


def sermon_blob_for_ai(sermon: dict, sections: list[dict] | None = None) -> str:
    """Full plain-text sermon for an AI prompt (title, passage, every section)."""
    sid = sermon.get('id')
    parts = [
        f"=== Sermon #{sid}: {sermon.get('title') or 'Untitled'} ===",
        f"Passage: {sermon.get('primary_passage') or '(none)'}",
        f"Date: {str(sermon.get('service_date') or '')[:10] or '(none)'}",
    ]
    if sermon.get('series_tags'):
        parts.append(f"Series/tags: {sermon.get('series_tags')}")
    for sec in sections or []:
        st = (sec.get('title') or sec.get('section_type') or 'Section').strip()
        body = _plain_html(sec.get('content') or '')
        notes = _plain_html(sec.get('notes') or '')
        scripture = (sec.get('scripture_reference') or '').strip()
        if not body and not st and not notes:
            continue
        line = f"[{st}]"
        if scripture:
            line += f" ({scripture})"
        if body:
            line += f" {body}"
        parts.append(line)
        if notes:
            parts.append(f"  Notes: {notes}")
    return '\n'.join(parts)


def pack_sermons_for_ai(
    user_id: int,
    question: str,
    *,
    sermon_ids: list[int] | None = None,
    max_sermons: int = 10,
    max_chars_each: int = 400000,
    max_total_chars: int = 350000,
) -> tuple[str, list[dict], dict]:
    """
    Build AI context from THIS user's sermons only.
    Never includes collaborator-only or pastoral-group sermons owned by others.

    If sermon_ids is provided (user-selected), only those sermons are packed
    (still ownership-checked). Otherwise auto-picks by keyword relevance.
    """
    q = (question or '').strip()
    ordered_ids: list[int] = []

    # Explicit selection from the research UI (preferred)
    if sermon_ids is not None:
        seen: set[int] = set()
        for raw in sermon_ids:
            try:
                sid = int(raw)
            except (TypeError, ValueError):
                continue
            if sid <= 0 or sid in seen:
                continue
            # Ownership gate — skip anything not created by this user
            if not _get_own_sermon(sid, user_id):
                continue
            seen.add(sid)
            ordered_ids.append(sid)
        # Use all selected; expand budget for larger libraries
        max_sermons = max(1, len(ordered_ids))
        # Prefer complete sermons over many stubs. ~350k chars ≈ a long manuscript.
        max_total_chars = max(max_total_chars, min(400_000, 12_000 + max_sermons * 80_000))
        max_chars_each = max(max_chars_each, 400_000)
    else:
        hits = search_sermons_library(user_id, q, limit=30) if len(q) >= 2 else []
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
    omitted: list[str] = []
    truncated = False
    total = 0
    catalog = sermon_catalog(user_id, limit=120)
    # Catalog in header: if user selected, list only those; else full library index
    if sermon_ids is not None and ordered_ids:
        sel_set = set(ordered_ids)
        catalog_for_header = [c for c in catalog if int(c['id']) in sel_set]
        if not catalog_for_header:
            catalog_for_header = [
                {'id': sid, 'title': f'Sermon #{sid}', 'passage': '', 'service_date': ''}
                for sid in ordered_ids
            ]
    else:
        catalog_for_header = catalog
    catalog_lines = [
        f"- #{c['id']}: {c['title']}"
        + (f" ({c['passage']})" if c.get('passage') else '')
        + (f" · {c['service_date']}" if c.get('service_date') else '')
        for c in catalog_for_header
    ]
    header = (
        f"MY SERMON LIBRARY ONLY ({len(catalog_for_header)} sermons selected for this question — never other pastors):\n"
        + '\n'.join(catalog_lines[:120])
        + "\n\nDETAILED CONTENT:\n"
    )
    total += len(header)

    empty_meta = {
        'chars': total,
        'truncated': False,
        'omitted': [],
        'included_full': 0,
    }
    if not ordered_ids:
        return header + "\n(No sermons selected or available.)\n", used, empty_meta

    for sid in ordered_ids:
        if len(used) >= max_sermons:
            sermon = _get_own_sermon(sid, user_id)
            omitted.append((sermon or {}).get('title') or f'Sermon #{sid}')
            continue
        sermon = _get_own_sermon(sid, user_id)
        if not sermon:
            continue
        title = sermon.get('title') or 'Untitled'
        blob = sermon_blob_for_ai(sermon, get_sermon_sections(sid) or [])
        if len(blob) > max_chars_each:
            blob = blob[:max_chars_each] + (
                '\n[…this sermon was longer than the per-item size ceiling.]'
            )
            truncated = True
        if total + len(blob) + 2 <= max_total_chars:
            chunks.append(blob)
            total += len(blob) + 2
            used.append({
                'id': sid,
                'title': title,
                'passage': sermon.get('primary_passage') or '',
            })
            continue
        remain = max_total_chars - total
        if not used and remain >= 2500:
            chunks.append(
                blob[:remain] +
                '\n[…this sermon was shortened to fit the AI provider size limit.]'
            )
            total = max_total_chars
            truncated = True
            used.append({
                'id': sid,
                'title': title,
                'passage': sermon.get('primary_passage') or '',
            })
            continue
        omitted.append(title)

    if omitted:
        header += (
            f"\n({len(omitted)} additional sermon(s) not packed due to size: "
            + ', '.join(omitted[:12])
            + (', …' if len(omitted) > 12 else '')
            + ")\n"
        )

    context = header + '\n\n'.join(chunks)
    meta = {
        'chars': len(context),
        'truncated': truncated,
        'omitted': omitted,
        'included_full': max(0, len(used) - (1 if truncated else 0)),
    }
    return context, used, meta
