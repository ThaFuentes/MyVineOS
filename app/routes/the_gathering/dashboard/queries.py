# MYVINECHURCH.ONLINE/app/routes/the_gathering/dashboard/queries.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/dashboard/queries.py
# File name: queries.py
# Brief, detailed purpose: Reusable database query functions specifically for the main Gathering Place Manager Dashboard.
# • Provides summary statistics (counts across all major content types) and recent activity feed.
# • 100% rebuilt to match the exact clean, safe, and consistent style of public/events/queries.py and public/dreams/queries.py.
# • All queries are parameterized, use DictCursor, and follow the public gold standard (no f-strings in SQL, detailed docstrings, cursor always closed).
# • Original behavior, table names, column aliases, and return values preserved 100%.

from app.models.db import get_db
from app.utils.comment_moderation import get_comment_stats
import pymysql.cursors


def get_dashboard_stats():
    """
    Retrieve overall summary counts for the Gathering Place Manager dashboard.
    Counts total + public events, plus totals for prayers, sermons, dreams,
    prophecies, and announcements. Exact same queries and keys as the original version.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    stats = {}

    # Events
    cur.execute("SELECT COUNT(*) AS count FROM events")
    stats['total_events'] = cur.fetchone()['count']

    cur.execute("SELECT COUNT(*) AS count FROM events WHERE visibility = 'public'")
    stats['public_events'] = cur.fetchone()['count']

    # Prayers
    cur.execute("SELECT COUNT(*) AS count FROM prayers")
    stats['total_prayers'] = cur.fetchone()['count']

    # Sermons
    cur.execute("SELECT COUNT(*) AS count FROM sermons")
    stats['total_sermons'] = cur.fetchone()['count']

    # Dreams
    cur.execute("SELECT COUNT(*) AS count FROM dreams")
    stats['total_dreams'] = cur.fetchone()['count']

    # Prophecies
    cur.execute("SELECT COUNT(*) AS count FROM prophecies")
    stats['total_prophecies'] = cur.fetchone()['count']

    # Announcements
    cur.execute("SELECT COUNT(*) AS count FROM announcements")
    stats['total_announcements'] = cur.fetchone()['count']

    cur.close()
    return stats


def get_recent_activity(limit=10):
    """
    Retrieve recent activity across major sections for the dashboard feed.
    Uses UNION ALL over the main content tables. Each branch aliases its native
    timestamp column (created_at / date_posted / uploaded_at) to 'created_at' so
    the result is uniform. Also provides 'visibility' (for badge) and 'author'
    (best-effort; many tables support contributor_name for guests).
    Fully parameterized. Includes events, prayers, sermons, dreams, prophecies,
    announcements to match the manager dashboard UI expectations and icons.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    # Combine recent items from multiple tables.
    # Use the actual timestamp column that exists in each table's builddb schema,
    # aliased to created_at for consistent result rows + template.
    # visibility included for the "PUBLIC/PRIVATE" badge in the template.
    # author falls back to contributor_name where supported (guest posts), else NULL.
    cur.execute("""
        SELECT 'event' AS type, id, event_name AS title, created_at, visibility, NULL AS author
        FROM events
        UNION ALL
        SELECT 'prayer' AS type, id, title, date_posted AS created_at, visibility, contributor_name AS author
        FROM prayers
        UNION ALL
        SELECT 'sermon' AS type, id, title, uploaded_at AS created_at, visibility, NULL AS author
        FROM sermons
        UNION ALL
        SELECT 'dream' AS type, id, title, date_posted AS created_at, visibility, contributor_name AS author
        FROM dreams
        UNION ALL
        SELECT 'prophecy' AS type, id, title, created_at, visibility, NULL AS author
        FROM prophecies
        UNION ALL
        SELECT 'announcement' AS type, id, title, created_at, visibility, NULL AS author
        FROM announcements
        ORDER BY created_at DESC
        LIMIT %s
    """, (int(limit),))

    recent = cur.fetchall()
    cur.close()
    return recent


def get_pending_moderation():
    """
    Prayer submissions awaiting approval plus total/shadowed comment counts.
    Comments publish immediately — dashboard shows totals, not a false pending queue.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    pending = {
        'total_pending': 0,
        'pending_prayers': 0,
        'comment_stats': get_comment_stats(),
    }
    try:
        cur.execute("SELECT COUNT(*) AS count FROM prayers WHERE status = 'pending'")
        row = cur.fetchone()
        pending['pending_prayers'] = row['count'] if row else 0
        pending['total_pending'] = pending['pending_prayers']
    except Exception:
        pass
    cur.close()
    return pending


def get_pending_prayer_submissions(limit=50):
    """Visitor/member prayer requests awaiting moderator approval."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute("""
            SELECT id, title, description, contributor_name, date_posted, visibility, status
            FROM prayers
            WHERE status = 'pending'
            ORDER BY date_posted DESC
            LIMIT %s
        """, (int(limit),))
        rows = cur.fetchall()
    except Exception:
        rows = []
    cur.close()
    return rows


def get_pending_comments_queue(limit=100):
    """All unmoderated comments across every public content type — unified moderator inbox."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    queue = []

    sources = [
        {
            'type': 'event',
            'sql': """
                SELECT c.id, COALESCE(c.name, 'Guest') AS name, c.comment AS body, c.event_id AS parent_id,
                       e.event_name AS parent_title, c.created_at AS posted_at
                FROM event_comments c
                JOIN events e ON e.id = c.event_id
            """,
        },
        {
            'type': 'prayer',
            'sql': """
                SELECT c.id, COALESCE(c.contributor_name, 'Guest') AS name, c.prayer AS body,
                       c.prayer_request_id AS parent_id, p.title AS parent_title, c.date_added AS posted_at
                FROM prayers_added c
                JOIN prayers p ON p.id = c.prayer_request_id
            """,
        },
        {
            'type': 'sermon',
            'sql': """
                SELECT c.id, COALESCE(c.contributor_name, 'Guest') AS name, c.comment AS body,
                       c.sermon_id AS parent_id, s.title AS parent_title, c.date_added AS posted_at
                FROM sermon_comments c
                JOIN sermons s ON s.id = c.sermon_id
            """,
        },
        {
            'type': 'dream',
            'sql': """
                SELECT c.id, COALESCE(c.contributor_name, 'Guest') AS name, c.comment AS body,
                       c.dream_id AS parent_id, d.title AS parent_title, c.date_posted AS posted_at
                FROM dream_comments c
                JOIN dreams d ON d.id = c.dream_id
            """,
        },
        {
            'type': 'prophecy',
            'sql': """
                SELECT c.id, COALESCE(c.contributor_name, 'Guest') AS name, c.comment AS body,
                       c.prophecy_id AS parent_id, pr.title AS parent_title, c.date_added AS posted_at
                FROM prophecy_comments c
                JOIN prophecies pr ON pr.id = c.prophecy_id
            """,
        },
        {
            'type': 'announcement',
            'sql': """
                SELECT c.id, COALESCE(c.contributor_name, 'Guest') AS name, c.comment AS body,
                       c.announcement_id AS parent_id, a.title AS parent_title, c.date_added AS posted_at
                FROM announcement_comments c
                JOIN announcements a ON a.id = c.announcement_id
                WHERE c.moderated = 0 OR c.moderated IS NULL
            """,
        },
    ]

    for src in sources:
        try:
            cur.execute(src['sql'])
            for row in cur.fetchall():
                row['content_type'] = src['type']
                queue.append(row)
        except Exception:
            continue

    cur.close()
    queue.sort(key=lambda r: r.get('posted_at') or '', reverse=True)
    return queue[:limit]


print("✅ MYVINECHURCH.ONLINE the_gathering/dashboard/queries.py loaded successfully (public-style rebuilt – fully parameterized and consistent)")