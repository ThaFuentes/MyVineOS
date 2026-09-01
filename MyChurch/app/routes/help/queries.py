import re

from app.utils.permissions import user_has_permission


def _row_dict(row, keys):
    if isinstance(row, dict):
        return row
    return dict(zip(keys, row))


ARTICLE_KEYS = (
    'id', 'category_id', 'slug', 'title', 'summary', 'body_md',
    'permission_key', 'sort_order', 'is_published',
)
ARTICLE_KEYS_WITH_CAT = ARTICLE_KEYS + ('category_name', 'category_slug')
ARTICLE_KEYS_ADMIN = ARTICLE_KEYS + ('created_by', 'updated_by')

CATEGORY_KEYS = ('id', 'slug', 'name', 'description', 'sort_order', 'is_published')


def slugify(text: str) -> str:
    text = (text or '').strip().lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')[:80] or 'item'


def _article_visible(article: dict) -> bool:
    key = article.get('permission_key')
    if key and not user_has_permission(key):
        return False
    return True


# ---------------------------------------------------------------------------
# Categories - public
# ---------------------------------------------------------------------------

def list_published_categories(cur) -> list[dict]:
    cur.execute(
        """
        SELECT id, slug, name, description, sort_order, is_published
        FROM help_categories
        WHERE is_published = 1
        ORDER BY sort_order, name
        """
    )
    return [_row_dict(r, CATEGORY_KEYS) for r in cur.fetchall()]


def get_category_by_slug(cur, slug: str, *, published_only: bool = True) -> dict | None:
    sql = """
        SELECT id, slug, name, description, sort_order, is_published
        FROM help_categories WHERE slug = %s
    """
    if published_only:
        sql += " AND is_published = 1"
    sql += " LIMIT 1"
    cur.execute(sql, (slug,))
    row = cur.fetchone()
    return _row_dict(row, CATEGORY_KEYS) if row else None


# ---------------------------------------------------------------------------
# Categories - admin
# ---------------------------------------------------------------------------

def list_all_categories(cur) -> list[dict]:
    cur.execute(
        """
        SELECT c.id, c.slug, c.name, c.description, c.sort_order, c.is_published,
               (SELECT COUNT(*) FROM help_articles a WHERE a.category_id = c.id) AS article_count
        FROM help_categories c
        ORDER BY c.sort_order, c.name
        """
    )
    rows = []
    for r in cur.fetchall():
        if isinstance(r, dict):
            rows.append(r)
        else:
            rows.append({
                'id': r[0], 'slug': r[1], 'name': r[2], 'description': r[3],
                'sort_order': r[4], 'is_published': r[5], 'article_count': r[6],
            })
    return rows


def get_category_by_id(cur, category_id: int) -> dict | None:
    cur.execute(
        """
        SELECT id, slug, name, description, sort_order, is_published
        FROM help_categories WHERE id = %s LIMIT 1
        """,
        (category_id,),
    )
    row = cur.fetchone()
    return _row_dict(row, CATEGORY_KEYS) if row else None


def create_category(cur, data: dict) -> int:
    cur.execute(
        """
        INSERT INTO help_categories (slug, name, description, sort_order, is_published)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            data['slug'], data['name'], data.get('description'),
            data.get('sort_order', 0), 1 if data.get('is_published', True) else 0,
        ),
    )
    return cur.lastrowid


def update_category(cur, category_id: int, data: dict) -> None:
    cur.execute(
        """
        UPDATE help_categories
        SET slug = %s, name = %s, description = %s,
            sort_order = %s, is_published = %s
        WHERE id = %s
        """,
        (
            data['slug'], data['name'], data.get('description'),
            data.get('sort_order', 0), 1 if data.get('is_published', True) else 0,
            category_id,
        ),
    )


def delete_category(cur, category_id: int) -> None:
    cur.execute("UPDATE help_articles SET category_id = NULL WHERE category_id = %s", (category_id,))
    cur.execute("DELETE FROM help_categories WHERE id = %s", (category_id,))


def category_slug_exists(cur, slug: str, exclude_id: int | None = None) -> bool:
    if exclude_id:
        cur.execute(
            "SELECT 1 FROM help_categories WHERE slug = %s AND id != %s LIMIT 1",
            (slug, exclude_id),
        )
    else:
        cur.execute("SELECT 1 FROM help_categories WHERE slug = %s LIMIT 1", (slug,))
    return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Articles - public
# ---------------------------------------------------------------------------

def _fetch_articles(cur, where_sql: str, params: tuple) -> list[dict]:
    cur.execute(
        f"""
        SELECT a.id, a.category_id, a.slug, a.title, a.summary, a.body_md,
               a.permission_key, a.sort_order, a.is_published,
               c.name AS category_name, c.slug AS category_slug
        FROM help_articles a
        LEFT JOIN help_categories c ON c.id = a.category_id
        WHERE {where_sql}
        ORDER BY c.sort_order, a.sort_order, a.title
        """,
        params,
    )
    articles = [_row_dict(r, ARTICLE_KEYS_WITH_CAT) for r in cur.fetchall()]
    return [a for a in articles if _article_visible(a)]


def list_published_articles(cur, category_id: int | None = None) -> list[dict]:
    if category_id:
        return _fetch_articles(cur, "a.is_published = 1 AND a.category_id = %s", (category_id,))
    return _fetch_articles(cur, "a.is_published = 1", ())


def group_articles_by_category(cur, articles: list[dict]) -> list[dict]:
    """Return categories with nested articles for browse UI."""
    categories = list_published_categories(cur)
    by_cat = {}
    uncategorized = []
    for article in articles:
        cid = article.get('category_id')
        if cid:
            by_cat.setdefault(cid, []).append(article)
        else:
            uncategorized.append(article)

    result = []
    for cat in categories:
        items = by_cat.get(cat['id'], [])
        if items:
            result.append({**cat, 'articles': items})
    if uncategorized:
        result.append({
            'id': None,
            'slug': 'general',
            'name': 'General',
            'description': 'Guides not assigned to a category yet.',
            'articles': uncategorized,
        })
    return result


def search_articles(cur, query: str) -> list[dict]:
    q = (query or '').strip()
    if not q:
        return []
    like = f'%{q}%'
    return _fetch_articles(
        cur,
        "a.is_published = 1 AND (a.title LIKE %s OR a.summary LIKE %s OR a.body_md LIKE %s)",
        (like, like, like),
    )


def get_article_by_slug(cur, slug: str) -> dict | None:
    cur.execute(
        """
        SELECT a.id, a.category_id, a.slug, a.title, a.summary, a.body_md,
               a.permission_key, a.sort_order, a.is_published,
               c.name AS category_name, c.slug AS category_slug
        FROM help_articles a
        LEFT JOIN help_categories c ON c.id = a.category_id
        WHERE a.slug = %s AND a.is_published = 1
        LIMIT 1
        """,
        (slug,),
    )
    row = cur.fetchone()
    if not row:
        return None
    article = _row_dict(row, ARTICLE_KEYS_WITH_CAT)
    if not _article_visible(article):
        return None
    return article


def get_related_articles(cur, article: dict, limit: int = 4) -> list[dict]:
    cur.execute(
        """
        SELECT a.id, a.category_id, a.slug, a.title, a.summary, a.body_md,
               a.permission_key, a.sort_order, a.is_published,
               c.name AS category_name, c.slug AS category_slug
        FROM help_articles a
        LEFT JOIN help_categories c ON c.id = a.category_id
        WHERE a.is_published = 1 AND a.id != %s
          AND (a.category_id = %s OR a.category_id IS NOT NULL)
        ORDER BY CASE WHEN a.category_id = %s THEN 0 ELSE 1 END, a.sort_order, a.title
        LIMIT 12
        """,
        (article['id'], article.get('category_id'), article.get('category_id')),
    )
    related = []
    for r in cur.fetchall():
        item = _row_dict(r, ARTICLE_KEYS_WITH_CAT)
        if _article_visible(item):
            related.append(item)
        if len(related) >= limit:
            break
    return related


# ---------------------------------------------------------------------------
# Articles - admin
# ---------------------------------------------------------------------------

def list_all_articles(cur, category_id: int | None = None) -> list[dict]:
    if category_id:
        cur.execute(
            """
            SELECT a.id, a.category_id, a.slug, a.title, a.summary, a.body_md,
                   a.permission_key, a.sort_order, a.is_published,
                   c.name AS category_name
            FROM help_articles a
            LEFT JOIN help_categories c ON c.id = a.category_id
            WHERE a.category_id = %s
            ORDER BY a.sort_order, a.title
            """,
            (category_id,),
        )
    else:
        cur.execute(
            """
            SELECT a.id, a.category_id, a.slug, a.title, a.summary, a.body_md,
                   a.permission_key, a.sort_order, a.is_published,
                   c.name AS category_name
            FROM help_articles a
            LEFT JOIN help_categories c ON c.id = a.category_id
            ORDER BY c.sort_order, a.sort_order, a.title
            """
        )
    rows = []
    for r in cur.fetchall():
        if isinstance(r, dict):
            rows.append(r)
        else:
            rows.append({
                'id': r[0], 'category_id': r[1], 'slug': r[2], 'title': r[3],
                'summary': r[4], 'body_md': r[5], 'permission_key': r[6],
                'sort_order': r[7], 'is_published': r[8], 'category_name': r[9],
            })
    return rows


def get_article_by_id(cur, article_id: int) -> dict | None:
    cur.execute(
        """
        SELECT id, category_id, slug, title, summary, body_md,
               permission_key, sort_order, is_published
        FROM help_articles WHERE id = %s LIMIT 1
        """,
        (article_id,),
    )
    row = cur.fetchone()
    return _row_dict(row, ARTICLE_KEYS) if row else None


def create_article(cur, data: dict, user_id: int) -> int:
    cur.execute(
        """
        INSERT INTO help_articles
            (category_id, slug, title, summary, body_md, permission_key,
             sort_order, is_published, created_by, updated_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            data.get('category_id'), data['slug'], data['title'],
            data.get('summary'), data['body_md'],
            data.get('permission_key') or None,
            data.get('sort_order', 0),
            1 if data.get('is_published', True) else 0,
            user_id, user_id,
        ),
    )
    return cur.lastrowid


def update_article(cur, article_id: int, data: dict, user_id: int) -> None:
    cur.execute(
        """
        UPDATE help_articles
        SET category_id = %s, slug = %s, title = %s, summary = %s, body_md = %s,
            permission_key = %s, sort_order = %s, is_published = %s, updated_by = %s
        WHERE id = %s
        """,
        (
            data.get('category_id'), data['slug'], data['title'],
            data.get('summary'), data['body_md'],
            data.get('permission_key') or None,
            data.get('sort_order', 0),
            1 if data.get('is_published', True) else 0,
            user_id, article_id,
        ),
    )


def delete_article(cur, article_id: int) -> None:
    cur.execute("DELETE FROM user_help_pins WHERE article_id = %s", (article_id,))
    cur.execute("DELETE FROM help_articles WHERE id = %s", (article_id,))


def article_slug_exists(cur, slug: str, exclude_id: int | None = None) -> bool:
    if exclude_id:
        cur.execute(
            "SELECT 1 FROM help_articles WHERE slug = %s AND id != %s LIMIT 1",
            (slug, exclude_id),
        )
    else:
        cur.execute("SELECT 1 FROM help_articles WHERE slug = %s LIMIT 1", (slug,))
    return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Pins
# ---------------------------------------------------------------------------

def get_user_pinned_ids(cur, user_id: int) -> set[int]:
    cur.execute(
        "SELECT article_id FROM user_help_pins WHERE user_id = %s ORDER BY pinned_at DESC",
        (user_id,),
    )
    return {row['article_id'] if isinstance(row, dict) else row[0] for row in cur.fetchall()}


def list_pinned_articles(cur, user_id: int) -> list[dict]:
    cur.execute(
        """
        SELECT a.id, a.category_id, a.slug, a.title, a.summary, a.body_md,
               a.permission_key, a.sort_order, a.is_published,
               c.name AS category_name, c.slug AS category_slug, p.pinned_at
        FROM user_help_pins p
        JOIN help_articles a ON a.id = p.article_id
        LEFT JOIN help_categories c ON c.id = a.category_id
        WHERE p.user_id = %s AND a.is_published = 1
        ORDER BY p.pinned_at DESC
        """,
        (user_id,),
    )
    articles = []
    for r in cur.fetchall():
        if isinstance(r, dict):
            articles.append(r)
        else:
            articles.append({
                'id': r[0], 'category_id': r[1], 'slug': r[2], 'title': r[3],
                'summary': r[4], 'body_md': r[5], 'permission_key': r[6],
                'sort_order': r[7], 'is_published': r[8],
                'category_name': r[9], 'category_slug': r[10], 'pinned_at': r[11],
            })
    return [a for a in articles if _article_visible(a)]


def pin_article(cur, user_id: int, article_id: int) -> bool:
    cur.execute("SELECT id FROM help_articles WHERE id = %s AND is_published = 1", (article_id,))
    if not cur.fetchone():
        return False
    cur.execute(
        """
        INSERT INTO user_help_pins (user_id, article_id)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE pinned_at = CURRENT_TIMESTAMP
        """,
        (user_id, article_id),
    )
    return True


def unpin_article(cur, user_id: int, article_id: int) -> None:
    cur.execute(
        "DELETE FROM user_help_pins WHERE user_id = %s AND article_id = %s",
        (user_id, article_id),
    )


def is_article_pinned(cur, user_id: int, article_id: int) -> bool:
    cur.execute(
        "SELECT 1 FROM user_help_pins WHERE user_id = %s AND article_id = %s LIMIT 1",
        (user_id, article_id),
    )
    return cur.fetchone() is not None