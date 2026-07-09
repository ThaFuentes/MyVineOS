# MYVINECHURCH.ONLINE/app/routes/public/public_dashboard/queries.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/public_dashboard/queries.py
# File name: queries.py
# Brief, detailed purpose: Reusable database query functions for the Public Dashboard (rich social-media style feed on homepage).
# - Reuses ALL existing public queries safely.
# - Smart priority ordering + recent comment previews on every card.
# - FIXED: Prophecies now use correct column 'date_added' (matches prophecy_comments table used in views.py).
# - All other types unchanged and working.
# - Production-clean version.

from app.models.db import get_db
import pymysql.cursors

# Reuse our existing public modular queries
from app.routes.public.events.queries import get_public_events
from app.routes.public.sermons.queries import get_public_sermons
from app.routes.public.announcements.queries import get_public_announcements
from app.routes.public.dreams.queries import get_public_dreams
from app.routes.public.prophecies.queries import get_public_prophecies


def get_public_dashboard_feed(limit=30):
    """Build the rich homepage feed with smart priority ordering and recent comment previews on every item."""
    feed = []
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    try:
        # 1. Upcoming Events (highest priority)
        events = get_public_events()
        for e in events[:8]:
            e['type'] = 'event'
            e['title'] = e.get('event_name')
            e['body'] = e.get('description') or f"Event on {e.get('event_date')}"
            e['datetime'] = e.get('event_date') or e.get('created_at')
            e['comments'] = get_recent_comments('event', e['id'])
            feed.append(e)

        # 2. Newest Sermons
        sermons = get_public_sermons()
        for s in sermons[:6]:
            s['type'] = 'sermon'
            s['body'] = None
            s['datetime'] = s.get('uploaded_at') or s.get('created_at')
            s['comments'] = get_recent_comments('sermon', s['id'])
            feed.append(s)

        # 3. Recent Announcements
        announcements = get_public_announcements()
        for a in announcements[:6]:
            a['type'] = 'announcement'
            a['body'] = a.get('content')
            a['datetime'] = a.get('created_at')
            a['comments'] = get_recent_comments('announcement', a['id'])
            feed.append(a)

        # 4. Latest Dreams
        dreams = get_public_dreams()
        for d in dreams[:5]:
            d['type'] = 'dream'
            d['body'] = d.get('description')
            d['datetime'] = d.get('date_posted')
            d['comments'] = get_recent_comments('dream', d['id'])
            feed.append(d)

        # 5. Latest Prophecies
        prophecies = get_public_prophecies()
        for p in prophecies[:5]:
            p['type'] = 'prophecy'
            p['body'] = p.get('description')
            p['datetime'] = p.get('created_at')
            p['comments'] = get_recent_comments('prophecy', p['id'])
            feed.append(p)

        # Sort newest/upcoming first
        feed.sort(key=lambda x: str(x.get('datetime') or '0000-00-00'), reverse=True)

    except Exception:
        pass  # Silent fail – feed will still render

    cur.close()
    return feed[:limit]


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
        'prophecy': {                                      # ← THIS WAS THE LAST BUG
            'table': 'prophecy_comments',
            'name_col': 'contributor_name',
            'comment_col': 'comment',
            'date_col': 'date_added'                       # ← Fixed to match views.py
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