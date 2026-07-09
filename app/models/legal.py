# app/models/legal.py
# Data access for legal categories and notices.

import re
import pymysql
from typing import Optional
from app.models.db import get_db


def slugify(text: str) -> str:
    text = (text or '').strip().lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-') or 'notice'


def get_all_categories(active_only: bool = False):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT id, slug, name, description, sort_order, is_system
        FROM legal_categories
        ORDER BY sort_order ASC, name ASC
    """)
    return cur.fetchall()


def get_category_by_slug(slug: str):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT id, slug, name, description, sort_order, is_system
        FROM legal_categories WHERE slug = %s
    """, (slug,))
    return cur.fetchone()


def get_category_by_id(category_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT id, slug, name, description, sort_order, is_system
        FROM legal_categories WHERE id = %s
    """, (category_id,))
    return cur.fetchone()


def get_active_notices_grouped(published_only: bool = False):
    """Return categories with their active notices.

    When published_only=True (public index), omit categories with no active notice.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT c.id AS category_id, c.slug AS category_slug, c.name AS category_name,
               c.description AS category_description, c.sort_order AS category_sort,
               n.id, n.title, n.slug, n.summary, n.content, n.is_active,
               n.updated_at,
               COALESCE(u.username, 'Staff') AS updated_by_name
        FROM legal_categories c
        LEFT JOIN legal_notices n ON n.category_id = c.id AND n.is_active = 1
        LEFT JOIN users u ON n.updated_by = u.id
        ORDER BY c.sort_order ASC, n.sort_order ASC, n.title ASC
    """)
    rows = cur.fetchall()
    grouped = []
    current = None
    for row in rows:
        if current is None or current['category_id'] != row['category_id']:
            current = {
                'category_id': row['category_id'],
                'category_slug': row['category_slug'],
                'category_name': row['category_name'],
                'category_description': row['category_description'],
                'notices': [],
            }
            grouped.append(current)
        if row['id']:
            current['notices'].append({
                'id': row['id'],
                'title': row['title'],
                'slug': row['slug'],
                'summary': row['summary'],
                'content': row['content'],
                'updated_at': row['updated_at'],
                'updated_by_name': row['updated_by_name'],
            })
    if published_only:
        grouped = [cat for cat in grouped if cat['notices']]
    return grouped


def _category_status(active_count: int, draft_count: int):
    if active_count > 0:
        return 'published', 'Published'
    if draft_count > 0:
        return 'draft', 'Draft — not public'
    return 'empty', 'No notice yet'


def get_categories_for_manage():
    """All categories with every notice listed — primary data for the manage screen."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT id, slug, name, description, sort_order, is_system
        FROM legal_categories
        ORDER BY sort_order ASC, name ASC
    """)
    categories = cur.fetchall()

    cur.execute("""
        SELECT n.id, n.category_id, n.title, n.slug, n.summary, n.is_active,
               n.sort_order, n.updated_at, n.created_at
        FROM legal_notices n
        ORDER BY n.is_active DESC, n.sort_order ASC, n.updated_at DESC, n.id DESC
    """)
    notices_by_category = {}
    for notice in cur.fetchall():
        notices_by_category.setdefault(notice['category_id'], []).append(notice)

    result = []
    for cat in categories:
        notices = notices_by_category.get(cat['id'], [])
        active_count = sum(1 for n in notices if n['is_active'])
        draft_count = len(notices) - active_count
        status, status_label = _category_status(active_count, draft_count)
        result.append({
            **cat,
            'notices': notices,
            'status': status,
            'status_label': status_label,
            'active_count': active_count,
            'draft_count': draft_count,
            'notice_count': len(notices),
        })
    return result


def get_category_publication_overview():
    """Lightweight admin summary used on the public legal index."""
    return [
        {
            'id': cat['id'],
            'slug': cat['slug'],
            'name': cat['name'],
            'description': cat['description'],
            'sort_order': cat['sort_order'],
            'status': cat['status'],
            'status_label': cat['status_label'],
            'active_count': cat['active_count'],
            'draft_count': cat['draft_count'],
            'notices': cat['notices'],
        }
        for cat in get_categories_for_manage()
    ]


def get_notice_by_slug(slug: str, active_only: bool = True):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    sql = """
        SELECT n.*, c.slug AS category_slug, c.name AS category_name,
               COALESCE(uc.username, 'Staff') AS created_by_name,
               COALESCE(uu.username, 'Staff') AS updated_by_name
        FROM legal_notices n
        JOIN legal_categories c ON c.id = n.category_id
        LEFT JOIN users uc ON n.created_by = uc.id
        LEFT JOIN users uu ON n.updated_by = uu.id
        WHERE n.slug = %s
    """
    if active_only:
        sql += " AND n.is_active = 1"
    cur.execute(sql, (slug,))
    return cur.fetchone()


def get_notice_by_id(notice_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT n.*, c.slug AS category_slug, c.name AS category_name
        FROM legal_notices n
        JOIN legal_categories c ON c.id = n.category_id
        WHERE n.id = %s
    """, (notice_id,))
    return cur.fetchone()


def get_all_notices_for_manage():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT n.id, n.title, n.slug, n.is_active, n.sort_order, n.updated_at,
               c.name AS category_name, c.slug AS category_slug
        FROM legal_notices n
        JOIN legal_categories c ON c.id = n.category_id
        ORDER BY c.sort_order ASC, n.sort_order ASC, n.title ASC
    """)
    return cur.fetchall()


def get_active_notice_for_category(category_slug: str):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT n.id, n.title, n.slug, n.summary
        FROM legal_notices n
        JOIN legal_categories c ON c.id = n.category_id
        WHERE c.slug = %s AND n.is_active = 1
        ORDER BY n.sort_order ASC, n.updated_at DESC
        LIMIT 1
    """, (category_slug,))
    return cur.fetchone()


def unique_notice_slug(base_slug: str, exclude_id: Optional[int] = None) -> str:
    db = get_db()
    cur = db.cursor()
    slug = slugify(base_slug)
    candidate = slug
    suffix = 2
    while True:
        if exclude_id:
            cur.execute(
                "SELECT id FROM legal_notices WHERE slug = %s AND id != %s",
                (candidate, exclude_id),
            )
        else:
            cur.execute("SELECT id FROM legal_notices WHERE slug = %s", (candidate,))
        if not cur.fetchone():
            return candidate
        candidate = f"{slug}-{suffix}"
        suffix += 1


def create_notice(category_id: int, title: str, content: str, summary: str = '',
                  is_active: bool = True, sort_order: int = 0,
                  created_by: Optional[int] = None) -> int:
    db = get_db()
    slug = unique_notice_slug(title)
    cur = db.cursor()
    cur.execute("""
        INSERT INTO legal_notices
            (category_id, title, slug, summary, content, is_active, sort_order, created_by, updated_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (category_id, title.strip(), slug, summary.strip() or None, content.strip(),
          1 if is_active else 0, sort_order, created_by, created_by))
    db.commit()
    return cur.lastrowid


def update_notice(notice_id: int, category_id: int, title: str, content: str,
                  summary: str = '', is_active: bool = True, sort_order: int = 0,
                  updated_by: Optional[int] = None) -> bool:
    db = get_db()
    slug = unique_notice_slug(title, exclude_id=notice_id)
    cur = db.cursor()
    cur.execute("""
        UPDATE legal_notices
        SET category_id = %s, title = %s, slug = %s, summary = %s, content = %s,
            is_active = %s, sort_order = %s, updated_by = %s
        WHERE id = %s
    """, (category_id, title.strip(), slug, summary.strip() or None, content.strip(),
          1 if is_active else 0, sort_order, updated_by, notice_id))
    db.commit()
    return cur.rowcount > 0


def delete_notice(notice_id: int) -> bool:
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM legal_notices WHERE id = %s", (notice_id,))
    db.commit()
    return cur.rowcount > 0


def set_notice_active(notice_id: int, is_active: bool, updated_by: Optional[int] = None) -> bool:
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE legal_notices
        SET is_active = %s, updated_by = %s
        WHERE id = %s
    """, (1 if is_active else 0, updated_by, notice_id))
    db.commit()
    return cur.rowcount > 0