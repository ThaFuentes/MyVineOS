# MYVINECHURCH.ONLINE/app/routes/public/public_dashboard/queries.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/public_dashboard/queries.py
# File name: queries.py
# Brief, detailed purpose: Reusable database query functions for the Public Dashboard (rich social-media style feed on homepage).
# - Reuses ALL existing public queries safely.
# - Smart priority ordering + recent comment previews on every card.
# - FIXED: Prophecies now use correct column 'date_added' (matches prophecy_comments table used in views.py).
# - All other types unchanged and working.
# - Production-clean version.

from datetime import date, datetime, timedelta

from app.models.db import get_db
import pymysql.cursors

# Reuse our existing public modular queries
from app.routes.public.events.queries import get_public_events
from app.routes.public.sermons.queries import get_public_sermons
from app.routes.public.announcements.queries import get_public_announcements
from app.routes.public.dreams.queries import get_public_dreams
from app.routes.public.prophecies.queries import get_public_prophecies
from app.routes.public.prayers.queries import get_public_prayers

FEED_TYPES = ('event', 'prayer', 'sermon', 'announcement', 'dream', 'prophecy', 'post')
WHEN_FILTERS = ('all', 'upcoming', 'week', 'month')


def parse_feed_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        raw = value.strip()
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                return datetime.strptime(raw[:19] if ' ' in raw else raw[:10], fmt)
            except ValueError:
                continue
    return None


def _matches_when(item, when_filter, today):
    if not when_filter or when_filter == 'all':
        return True
    dt = item.get('sort_dt')
    if not dt:
        return when_filter == 'all'
    day = dt.date()
    if when_filter == 'upcoming':
        return day >= today
    if when_filter == 'week':
        return (today - timedelta(days=7)) <= day <= (today + timedelta(days=7))
    if when_filter == 'month':
        return (today - timedelta(days=30)) <= day <= (today + timedelta(days=30))
    return True


def _safe_rows(loader):
    try:
        return loader() or []
    except Exception:
        return []


def _vis_sql(include_members):
    return "IN ('public', 'private')" if include_members else "= 'public'"


def _feed_rows(sql):
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute(sql)
        rows = list(cur.fetchall() or [])
        cur.close()
        return rows
    except Exception:
        return []


def _feed_prayers(include_members=False):
    """Public prayers for guests; members also see private church prayer requests."""
    if not include_members:
        return _safe_rows(get_public_prayers)
    rows = _feed_rows(f"""
        SELECT
            p.id,
            p.title,
            p.description,
            p.date_posted,
            p.visibility,
            COALESCE(u.username, p.contributor_name, 'Anonymous') AS creator_name
        FROM prayers p
        LEFT JOIN users u ON COALESCE(p.user_id, p.created_by) = u.id
        WHERE p.visibility {_vis_sql(True)}
          AND COALESCE(p.status, 'approved') NOT IN ('rejected', 'deleted', 'removed', 'spam', 'hidden')
        ORDER BY p.date_posted DESC
    """)
    return rows or _safe_rows(get_public_prayers)


def _feed_announcements(include_members=False):
    if not include_members:
        return _safe_rows(get_public_announcements)
    return _feed_rows(f"""
        SELECT a.*,
               COALESCE(CONCAT(u.first_name, ' ', u.last_name), u.username, 'Anonymous') AS creator_name
        FROM announcements a
        LEFT JOIN users u ON COALESCE(a.created_by, a.user_id) = u.id
        WHERE a.visibility {_vis_sql(True)}
          AND COALESCE(a.is_active, 1) = 1
        ORDER BY a.created_at DESC
    """) or _safe_rows(get_public_announcements)


def _feed_events(include_members=False):
    if not include_members:
        return _safe_rows(get_public_events)
    return _feed_rows(f"""
        SELECT e.*, COALESCE(u.username, 'Anonymous') AS creator_name
        FROM events e
        LEFT JOIN users u ON e.created_by = u.id
        WHERE e.visibility {_vis_sql(True)}
        ORDER BY e.event_date DESC, e.event_time DESC
    """) or _safe_rows(get_public_events)


def _feed_sermons(include_members=False):
    if not include_members:
        return _safe_rows(get_public_sermons)
    return _feed_rows(f"""
        SELECT s.id, s.title, s.notes, s.details, s.uploaded_at, s.visibility,
               COALESCE(u.username, 'Anonymous') AS creator_name
        FROM sermons s
        LEFT JOIN users u ON COALESCE(s.uploaded_by, s.created_by) = u.id
        WHERE s.visibility {_vis_sql(True)}
        ORDER BY s.uploaded_at DESC
    """) or _safe_rows(get_public_sermons)


def _feed_dreams(include_members=False):
    if not include_members:
        return _safe_rows(get_public_dreams)
    return _feed_rows(f"""
        SELECT d.*, COALESCE(u.username, 'Anonymous') AS creator_name
        FROM dreams d
        LEFT JOIN users u ON COALESCE(d.user_id, d.created_by) = u.id
        WHERE d.visibility {_vis_sql(True)}
        ORDER BY d.date_posted DESC
    """) or _safe_rows(get_public_dreams)


def _feed_prophecies(include_members=False):
    if not include_members:
        return _safe_rows(get_public_prophecies)
    return _feed_rows(f"""
        SELECT p.*, COALESCE(u.username, 'Anonymous') AS creator_name
        FROM prophecies p
        LEFT JOIN users u ON COALESCE(p.user_id, p.created_by) = u.id
        WHERE p.visibility {_vis_sql(True)}
        ORDER BY p.created_at DESC
    """) or _safe_rows(get_public_prophecies)


def get_public_dashboard_feed(limit=40, type_filter=None, when_filter=None, include_members=False):
    """Build a date-sorted feed. One source failing must not empty the rest."""
    feed = []
    type_filter = (type_filter or '').strip().lower() or None
    if type_filter not in FEED_TYPES:
        type_filter = None
    when_filter = (when_filter or 'all').strip().lower()
    if when_filter not in WHEN_FILTERS:
        when_filter = 'all'
    per_type = 24 if type_filter else 12

    def take(rows, kind, title_key, body_key, date_key, extra_date=None):
        if type_filter and type_filter != kind:
            return
        for row in (rows or [])[:per_type]:
            item = dict(row)
            item['type'] = kind
            item['title'] = item.get(title_key) or item.get('title') or 'Untitled'
            item['body'] = item.get(body_key)
            item['datetime'] = item.get(date_key) or (item.get(extra_date) if extra_date else None)
            item['sort_dt'] = parse_feed_datetime(item.get('datetime'))
            try:
                item['comments'] = get_recent_comments(kind, item.get('id'))
            except Exception:
                item['comments'] = []
            feed.append(item)

    take(_feed_events(include_members), 'event', 'event_name', 'description', 'event_date', 'created_at')
    take(_feed_sermons(include_members), 'sermon', 'title', None, 'uploaded_at', 'created_at')
    take(_feed_announcements(include_members), 'announcement', 'title', 'content', 'created_at')
    take(_feed_dreams(include_members), 'dream', 'title', 'description', 'date_posted')
    take(_feed_prophecies(include_members), 'prophecy', 'title', 'description', 'created_at')
    take(_feed_prayers(include_members), 'prayer', 'title', 'description', 'date_posted')

    today = date.today()
    filtered = [item for item in feed if _matches_when(item, when_filter, today)]
    filtered.sort(key=lambda x: x.get('sort_dt') or datetime.min, reverse=True)
    return filtered[:limit]


def get_recent_comments(content_type, content_id, limit=3):
    """Helper to get recent comments for any content type (for homepage preview)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    # Column mapping based on the actual schema used in each public module
    column_maps = {
        'event': {
            'table': 'event_comments',
            'name_col': 'name',
            'comment_col': 'comment',
            'date_col': 'created_at',
            'parent_col': 'event_id',
        },
        'sermon': {
            'table': 'sermon_comments',
            'name_col': 'contributor_name',
            'comment_col': 'comment',
            'date_col': 'date_added',
            'parent_col': 'sermon_id',
        },
        'announcement': {
            'table': 'announcement_comments',
            'name_col': 'contributor_name',
            'comment_col': 'comment',
            'date_col': 'date_added',
            'parent_col': 'announcement_id',
        },
        'dream': {
            'table': 'dream_comments',
            'name_col': 'contributor_name',
            'comment_col': 'comment',
            'date_col': 'date_posted',
            'parent_col': 'dream_id',
        },
        'prophecy': {
            'table': 'prophecy_comments',
            'name_col': 'contributor_name',
            'comment_col': 'comment',
            'date_col': 'date_added',
            'parent_col': 'prophecy_id',
        },
        'prayer': {
            'table': 'prayers_added',
            'name_col': 'contributor_name',
            'comment_col': 'prayer',
            'date_col': 'date_added',
            'parent_col': 'prayer_request_id',
        },
        'photo': {
            'table': 'page_photo_comments',
            'name_col': 'contributor_name',
            'comment_col': 'comment',
            'date_col': 'date_added',
            'parent_col': 'photo_id',
        },
    }

    mapping = column_maps.get(content_type)
    if not mapping:
        return []

    table = mapping['table']
    name_col = mapping['name_col']
    comment_col = mapping['comment_col']
    date_col = mapping['date_col']
    parent_col = mapping.get('parent_col') or (content_type + '_id')
    if not content_id:
        return []

    try:
        cur.execute(f"""
            SELECT 
                {name_col} AS name, 
                {comment_col} AS comment,
                DATE_FORMAT({date_col}, '%%b %%e, %%Y %%h:%%i %%p') AS date
            FROM {table}
            WHERE {parent_col} = %s
            ORDER BY {date_col} DESC
            LIMIT %s
        """, (content_id, limit))
        return cur.fetchall()
    except Exception:
        return []
    finally:
        cur.close()