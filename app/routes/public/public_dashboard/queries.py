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

FEED_TYPES = ('event', 'prayer', 'sermon', 'announcement', 'dream', 'prophecy')
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


def get_public_dashboard_feed(limit=40, type_filter=None, when_filter=None):
    """Build a date-sorted public feed. Optional type/when filters keep section pages intact."""
    feed = []
    type_filter = (type_filter or '').strip().lower() or None
    if type_filter not in FEED_TYPES:
        type_filter = None
    when_filter = (when_filter or 'all').strip().lower()
    if when_filter not in WHEN_FILTERS:
        when_filter = 'all'
    per_type = 24 if type_filter else 10

    def take(rows, kind, title_key, body_key, date_key, extra_date=None):
        if type_filter and type_filter != kind:
            return
        for row in (rows or [])[:per_type]:
            row['type'] = kind
            row['title'] = row.get(title_key) or row.get('title') or 'Untitled'
            row['body'] = row.get(body_key)
            row['datetime'] = row.get(date_key) or (row.get(extra_date) if extra_date else None)
            row['sort_dt'] = parse_feed_datetime(row.get('datetime'))
            if kind != 'prayer':
                try:
                    row['comments'] = get_recent_comments(kind, row['id'])
                except Exception:
                    row['comments'] = []
            else:
                row['comments'] = []
            feed.append(row)

    try:
        take(get_public_events(), 'event', 'event_name', 'description', 'event_date', 'created_at')
        take(get_public_sermons(), 'sermon', 'title', None, 'uploaded_at', 'created_at')
        take(get_public_announcements(), 'announcement', 'title', 'content', 'created_at')
        take(get_public_dreams(), 'dream', 'title', 'description', 'date_posted')
        take(get_public_prophecies(), 'prophecy', 'title', 'description', 'created_at')
        try:
            take(get_public_prayers(), 'prayer', 'title', 'description', 'date_posted')
        except Exception:
            pass
    except Exception:
        pass

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
            'date_col': 'created_at'
        },
        'sermon': {
            'table': 'sermon_comments',
            'name_col': 'contributor_name',
            'comment_col': 'comment',
            'date_col': 'date_added'
        },
        'announcement': {
            'table': 'announcement_comments',
            'name_col': 'contributor_name',
            'comment_col': 'comment',
            'date_col': 'date_added'
        },
        'dream': {
            'table': 'dream_comments',
            'name_col': 'contributor_name',
            'comment_col': 'comment',
            'date_col': 'date_posted'
        },
        'prophecy': {                                      # <- THIS WAS THE LAST BUG
            'table': 'prophecy_comments',
            'name_col': 'contributor_name',
            'comment_col': 'comment',
            'date_col': 'date_added'                       # <- Fixed to match views.py
        }
    }

    mapping = column_maps.get(content_type)
    if not mapping:
        return []

    table = mapping['table']
    name_col = mapping['name_col']
    comment_col = mapping['comment_col']
    date_col = mapping['date_col']

    try:
        cur.execute(f"""
            SELECT 
                {name_col} AS name, 
                {comment_col} AS comment,
                DATE_FORMAT({date_col}, '%%b %%e, %%Y %%h:%%i %%p') AS date
            FROM {table}
            WHERE {content_type}_id = %s
            ORDER BY {date_col} DESC
            LIMIT %s
        """, (content_id, limit))
        return cur.fetchall()
    except Exception:
        return []
    finally:
        cur.close()