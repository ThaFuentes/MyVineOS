# Search + AI context for the Illustrations Library (text stories, analogies, vault sections).
# Packs only items the acting pastor can already see in the library UI.

from __future__ import annotations

import json
import re
from typing import Any

import pymysql

from app.models.db import get_db
from app.utils.ai_format import plain_snippet


def _parse_tags(tags_raw) -> list:
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


def _campus_frag(alias: str, user_id: int, owner_col: str) -> tuple[str, list]:
    try:
        from app.models.campuses import content_campus_filter_sql
        return content_campus_filter_sql(
            f'{alias}.campus_id', user_id=user_id, owner_column=f'{alias}.{owner_col}'
        )
    except Exception:
        return '', []


def _plain(text: str | None) -> str:
    if not text:
        return ''
    plain = re.sub(r'<[^>]+>', ' ', str(text))
    return re.sub(r'\s+', ' ', plain).strip()


def _item_key(kind: str, item_id: int) -> str:
    k = 'i' if kind in ('illustration', 'illus', 'i') else 's'
    return f'{k}-{int(item_id)}'


def parse_item_key(raw: str) -> tuple[str, int] | None:
    """Parse UI key 'i-12' / 's-34' or bare int (illustration)."""
    s = (raw or '').strip().lower()
    if not s:
        return None
    m = re.match(r'^(i|s|illustration|section|illus|vault)[-_:]?(\d+)$', s)
    if m:
        kind = 'illustration' if m.group(1) in ('i', 'illustration', 'illus') else 'section'
        return kind, int(m.group(2))
    try:
        return 'illustration', int(s)
    except (TypeError, ValueError):
        return None


def list_visible_library_items(user_id: int, *, limit: int = 120) -> list[dict]:
    """Illustrations + vault sections visible to this pastor (newest first)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    items: list[dict] = []

    illus_frag, illus_params = _campus_frag('il', user_id, 'user_id')
    cur.execute(
        f"""
        SELECT il.id, il.title, il.content, il.source, il.tags, il.notes,
               il.created_at, il.user_id,
               'illustration' AS kind,
               CASE WHEN il.user_id IS NOT NULL THEN 'private' ELSE 'pastoral_group' END AS visibility
        FROM illustration_library il
        WHERE (il.user_id = %s OR il.user_id IS NULL)
        {illus_frag}
        ORDER BY il.created_at DESC
        LIMIT %s
        """,
        (int(user_id), *list(illus_params), int(limit)),
    )
    for r in cur.fetchall() or []:
        tags = _parse_tags(r.get('tags'))
        items.append({
            'id': int(r['id']),
            'kind': 'illustration',
            'key': _item_key('illustration', r['id']),
            'title': r.get('title') or 'Untitled',
            'source': r.get('source') or '',
            'tags': tags,
            'tag_str': ', '.join(tags) if tags else '',
            'visibility': r.get('visibility') or 'private',
            'created_at': str(r.get('created_at') or '')[:10],
            'snippet': plain_snippet(r.get('content') or '', '')[:140],
            'content': r.get('content') or '',
            'notes': r.get('notes') or '',
            'scripture_reference': '',
        })

    vault_frag, vault_params = _campus_frag('pv', user_id, 'user_id')
    cur.execute(
        f"""
        SELECT pv.id, pv.title, pv.content, pv.source_url, pv.tags, pv.notes,
               pv.created_at, pv.user_id, pv.scripture_reference, pv.section_type,
               'section' AS kind,
               CASE
                   WHEN pv.visibility = 'private' OR (pv.visibility IS NULL AND pv.user_id IS NOT NULL)
                   THEN 'private'
                   ELSE 'pastoral_group'
               END AS visibility
        FROM pastoral_vault pv
        WHERE (pv.user_id = %s OR pv.user_id IS NULL)
        {vault_frag}
        ORDER BY pv.created_at DESC
        LIMIT %s
        """,
        (int(user_id), *list(vault_params), int(limit)),
    )
    for r in cur.fetchall() or []:
        tags = _parse_tags(r.get('tags'))
        items.append({
            'id': int(r['id']),
            'kind': 'section',
            'key': _item_key('section', r['id']),
            'title': r.get('title') or 'Untitled',
            'source': r.get('source_url') or '',
            'tags': tags,
            'tag_str': ', '.join(tags) if tags else '',
            'visibility': r.get('visibility') or 'private',
            'created_at': str(r.get('created_at') or '')[:10],
            'snippet': plain_snippet(r.get('content') or '', '')[:140],
            'content': r.get('content') or '',
            'notes': r.get('notes') or '',
            'scripture_reference': r.get('scripture_reference') or '',
            'section_type': r.get('section_type') or '',
        })

    items.sort(key=lambda x: x.get('created_at') or '', reverse=True)
    return items[:limit]


def illustration_catalog(user_id: int, *, limit: int = 100) -> list[dict]:
    """Lightweight list for AI pick UI."""
    rows = list_visible_library_items(user_id, limit=limit)
    out = []
    for r in rows:
        out.append({
            'id': r['id'],
            'kind': r['kind'],
            'key': r['key'],
            'title': r['title'],
            'source': r.get('source') or '',
            'tags': r.get('tag_str') or '',
            'created_at': r.get('created_at') or '',
            'visibility': r.get('visibility') or '',
            'label': (
                ('Illustration' if r['kind'] == 'illustration' else 'Section')
                + f" · {r['title']}"
            ),
        })
    return out


def search_illustrations_library(
    user_id: int, query: str, *, limit: int = 50
) -> list[dict[str, Any]]:
    """Keyword search across visible illustrations + vault sections."""
    q = (query or '').strip()
    if not q or len(q) < 2:
        return []

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    like = f'%{q}%'
    hits: list[dict[str, Any]] = []

    illus_frag, illus_params = _campus_frag('il', user_id, 'user_id')
    cur.execute(
        f"""
        SELECT il.id, il.title, il.content, il.source, il.tags, il.notes, il.created_at
        FROM illustration_library il
        WHERE (il.user_id = %s OR il.user_id IS NULL)
        {illus_frag}
          AND (
                il.title LIKE %s OR il.content LIKE %s OR IFNULL(il.source, '') LIKE %s
             OR IFNULL(il.tags, '') LIKE %s OR IFNULL(il.notes, '') LIKE %s
          )
        ORDER BY il.created_at DESC
        LIMIT %s
        """,
        (int(user_id), *list(illus_params), like, like, like, like, like, int(limit)),
    )
    for row in cur.fetchall() or []:
        field_bits = []
        for label, val in (
            ('title', row.get('title')),
            ('content', row.get('content')),
            ('source', row.get('source')),
            ('tags', row.get('tags')),
            ('notes', row.get('notes')),
        ):
            if val and q.lower() in str(val).lower():
                field_bits.append(label)
        hits.append({
            'id': int(row['id']),
            'kind': 'illustration',
            'key': _item_key('illustration', row['id']),
            'title': row.get('title') or 'Untitled',
            'source': row.get('source') or '',
            'match_field': ', '.join(field_bits) or 'illustration',
            'snippet': plain_snippet(row.get('content') or row.get('title') or '', q),
            'created_at': str(row.get('created_at') or '')[:10],
        })

    vault_frag, vault_params = _campus_frag('pv', user_id, 'user_id')
    cur.execute(
        f"""
        SELECT pv.id, pv.title, pv.content, pv.source_url, pv.tags, pv.notes,
               pv.scripture_reference, pv.created_at
        FROM pastoral_vault pv
        WHERE (pv.user_id = %s OR pv.user_id IS NULL)
        {vault_frag}
          AND (
                pv.title LIKE %s OR pv.content LIKE %s
             OR IFNULL(pv.scripture_reference, '') LIKE %s
             OR IFNULL(pv.source_url, '') LIKE %s
             OR IFNULL(pv.notes, '') LIKE %s
             OR IFNULL(pv.tags, '') LIKE %s
          )
        ORDER BY pv.created_at DESC
        LIMIT %s
        """,
        (int(user_id), *list(vault_params), like, like, like, like, like, like, int(limit)),
    )
    for row in cur.fetchall() or []:
        field_bits = []
        for label, val in (
            ('title', row.get('title')),
            ('content', row.get('content')),
            ('scripture', row.get('scripture_reference')),
            ('source', row.get('source_url')),
            ('notes', row.get('notes')),
            ('tags', row.get('tags')),
        ):
            if val and q.lower() in str(val).lower():
                field_bits.append(label)
        hits.append({
            'id': int(row['id']),
            'kind': 'section',
            'key': _item_key('section', row['id']),
            'title': row.get('title') or 'Untitled',
            'source': row.get('source_url') or '',
            'match_field': ', '.join(field_bits) or 'section',
            'snippet': plain_snippet(row.get('content') or row.get('title') or '', q),
            'created_at': str(row.get('created_at') or '')[:10],
            'scripture_reference': row.get('scripture_reference') or '',
        })

    hits.sort(key=lambda h: h.get('created_at') or '', reverse=True)
    return hits[:limit]


def _load_visible_item(kind: str, item_id: int, user_id: int) -> dict | None:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    if kind == 'illustration':
        frag, params = _campus_frag('il', user_id, 'user_id')
        cur.execute(
            f"""
            SELECT il.*, 'illustration' AS kind,
                   il.source AS source_url,
                   CASE WHEN il.user_id IS NOT NULL THEN 'private' ELSE 'pastoral_group' END AS visibility
            FROM illustration_library il
            WHERE il.id = %s AND (il.user_id = %s OR il.user_id IS NULL)
            {frag}
            """,
            (int(item_id), int(user_id), *list(params)),
        )
        row = cur.fetchone()
        if row:
            row['tags'] = _parse_tags(row.get('tags'))
        return row

    frag, params = _campus_frag('pv', user_id, 'user_id')
    cur.execute(
        f"""
        SELECT pv.*, 'section' AS kind, pv.source_url,
               CASE
                   WHEN pv.visibility = 'private' OR (pv.visibility IS NULL AND pv.user_id IS NOT NULL)
                   THEN 'private'
                   ELSE 'pastoral_group'
               END AS visibility
        FROM pastoral_vault pv
        WHERE pv.id = %s AND (pv.user_id = %s OR pv.user_id IS NULL)
        {frag}
        """,
        (int(item_id), int(user_id), *list(params)),
    )
    row = cur.fetchone()
    if row:
        row['tags'] = _parse_tags(row.get('tags'))
    return row


def pack_illustrations_for_ai(
    user_id: int,
    question: str,
    *,
    item_keys: list[str] | None = None,
    max_items: int = 20,
    max_chars_each: int = 1800,
    max_total_chars: int = 28000,
) -> tuple[str, list[dict]]:
    """
    Build AI context from library items the pastor can see.
    item_keys: list of 'i-12' / 's-34' from the research UI.
    """
    ordered: list[tuple[str, int]] = []
    seen: set[str] = set()

    if item_keys is not None:
        for raw in item_keys:
            parsed = parse_item_key(str(raw))
            if not parsed:
                continue
            kind, iid = parsed
            key = _item_key(kind, iid)
            if key in seen:
                continue
            if not _load_visible_item(kind, iid, user_id):
                continue
            seen.add(key)
            ordered.append((kind, iid))
        max_items = max(1, len(ordered))
        max_total_chars = max(max_total_chars, min(100_000, max_items * 1600 + 4000))
        if max_items > 16:
            max_chars_each = min(max_chars_each, max(700, 26000 // max(1, max_items)))
    else:
        q = (question or '').strip()
        hits = search_illustrations_library(user_id, q, limit=40) if len(q) >= 2 else []
        for h in hits:
            key = h['key']
            if key in seen:
                continue
            seen.add(key)
            ordered.append((h['kind'], h['id']))
        for r in list_visible_library_items(user_id, limit=60):
            key = r['key']
            if key in seen:
                continue
            seen.add(key)
            ordered.append((r['kind'], r['id']))
            if len(ordered) >= max_items * 2:
                break

    catalog = illustration_catalog(user_id, limit=120)
    if item_keys is not None and ordered:
        sel = {_item_key(k, i) for k, i in ordered}
        catalog_for_header = [c for c in catalog if c['key'] in sel]
        if not catalog_for_header:
            catalog_for_header = [
                {
                    'key': _item_key(k, i),
                    'title': f'{k} #{i}',
                    'kind': k,
                    'source': '',
                    'created_at': '',
                }
                for k, i in ordered
            ]
    else:
        catalog_for_header = catalog

    catalog_lines = [
        f"- [{c.get('kind', '?')}] {c['key']}: {c['title']}"
        + (f" · {c['source']}" if c.get('source') else '')
        + (f" · {c['created_at']}" if c.get('created_at') else '')
        for c in catalog_for_header
    ]
    header = (
        f"MY ILLUSTRATIONS LIBRARY ONLY ({len(catalog_for_header)} items selected — "
        "stories, analogies, and saved sermon sections I can access):\n"
        + '\n'.join(catalog_lines[:120])
        + "\n\nDETAILED CONTENT:\n"
    )

    used: list[dict] = []
    chunks: list[str] = []
    total = len(header)

    if not ordered:
        return header + "\n(No library items selected or available.)\n", used

    for kind, iid in ordered:
        if len(used) >= max_items or total >= max_total_chars:
            break
        item = _load_visible_item(kind, iid, user_id)
        if not item:
            continue
        title = item.get('title') or 'Untitled'
        tags = item.get('tags') or []
        if isinstance(tags, list):
            tag_str = ', '.join(str(t) for t in tags)
        else:
            tag_str = str(tags)
        body = _plain(item.get('content'))
        notes = _plain(item.get('notes'))
        source = (item.get('source') or item.get('source_url') or '').strip()
        scripture = (item.get('scripture_reference') or '').strip()
        kind_label = 'Illustration' if kind == 'illustration' else 'Saved section'
        parts = [
            f"=== {kind_label} { _item_key(kind, iid) }: {title} ===",
            f"Visibility: {item.get('visibility') or 'private'}",
        ]
        if source:
            parts.append(f"Source: {source}")
        if scripture:
            parts.append(f"Scripture: {scripture}")
        if tag_str:
            parts.append(f"Tags: {tag_str}")
        if body:
            parts.append(f"Content: {body}")
        if notes:
            parts.append(f"Notes: {notes}")
        blob = '\n'.join(parts)
        if len(blob) > max_chars_each:
            blob = blob[:max_chars_each] + '\n[…truncated]'
        if total + len(blob) > max_total_chars:
            remain = max_total_chars - total
            if remain < 300:
                break
            blob = blob[:remain] + '\n[…truncated]'
        chunks.append(blob)
        total += len(blob) + 2
        used.append({
            'id': iid,
            'kind': kind,
            'key': _item_key(kind, iid),
            'title': title,
            'source': source,
        })

    return header + '\n\n'.join(chunks), used
