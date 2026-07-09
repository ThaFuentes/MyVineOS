# app/utils/comment_moderation.py
# Shared comment moderation: visibility, stats, manager queries, and actions.

from flask import flash
from app.models.db import get_db
from app.models.log import log_change
import pymysql.cursors


COMMENT_TYPES = {
    'event': {
        'table': 'event_comments',
        'parent_col': 'event_id',
        'text_col': 'comment',
        'name_col': 'name',
        'ip_col': 'ip',
        'user_col': 'user_id',
        'date_col': 'created_at',
        'label': 'Event comment',
        'manager_section': 'events',
    },
    'prayer': {
        'table': 'prayers_added',
        'parent_col': 'prayer_request_id',
        'text_col': 'prayer',
        'name_col': 'contributor_name',
        'ip_col': 'ip_address',
        'user_col': 'user_id',
        'date_col': 'date_added',
        'label': 'Prayer response',
        'manager_section': 'prayers',
    },
    'sermon': {
        'table': 'sermon_comments',
        'parent_col': 'sermon_id',
        'text_col': 'comment',
        'name_col': 'contributor_name',
        'ip_col': 'ip_address',
        'user_col': 'user_id',
        'date_col': 'date_added',
        'label': 'Sermon comment',
        'manager_section': 'sermons',
    },
    'dream': {
        'table': 'dream_comments',
        'parent_col': 'dream_id',
        'text_col': 'comment',
        'name_col': 'contributor_name',
        'ip_col': 'ip_address',
        'user_col': 'user_id',
        'date_col': 'date_posted',
        'label': 'Dream comment',
        'manager_section': 'dreams',
    },
    'prophecy': {
        'table': 'prophecy_comments',
        'parent_col': 'prophecy_id',
        'text_col': 'comment',
        'name_col': 'contributor_name',
        'ip_col': 'ip_address',
        'user_col': 'user_id',
        'date_col': 'date_added',
        'label': 'Prophecy comment',
        'manager_section': 'prophecies',
    },
    'announcement': {
        'table': 'announcement_comments',
        'parent_col': 'announcement_id',
        'text_col': 'comment',
        'name_col': 'contributor_name',
        'ip_col': 'ip_address',
        'user_col': 'user_id',
        'date_col': 'date_added',
        'label': 'Announcement comment',
        'manager_section': 'announcements',
    },
}

PARENT_JOINS = {
    'event': ('events e', 'e.id = c.event_id', 'e.event_name'),
    'prayer': ('prayers p', 'p.id = c.prayer_request_id', 'p.title'),
    'sermon': ('sermons s', 's.id = c.sermon_id', 's.title'),
    'dream': ('dreams d', 'd.id = c.dream_id', 'd.title'),
    'prophecy': ('prophecies pr', 'pr.id = c.prophecy_id', 'pr.title'),
    'announcement': ('announcements a', 'a.id = c.announcement_id', 'a.title'),
}


def fetch_moderation_comments_queue(limit=300, status_filter='all', search=None):
    """All comments for the unified moderation hub with full text and status."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    queue = []

    for ctype, cfg in COMMENT_TYPES.items():
        join = PARENT_JOINS.get(ctype)
        if not join:
            continue
        parent_table, join_on, parent_title_col = join
        extra = []
        params = []
        if status_filter == 'shadowed':
            extra.append('COALESCE(c.shadowed, 0) = 1')
        elif status_filter == 'visible':
            extra.append('COALESCE(c.shadowed, 0) = 0')
        elif status_filter == 'edited':
            extra.append('COALESCE(c.edited_by_moderator, 0) = 1')
        if search:
            extra.append(f'(c.{cfg["name_col"]} LIKE %s OR c.{cfg["text_col"]} LIKE %s OR {parent_title_col} LIKE %s)')
            params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
        where_extra = (' AND ' + ' AND '.join(extra)) if extra else ''
        try:
            cur.execute(f"""
                SELECT %s AS content_type, c.id, c.{cfg['parent_col']} AS parent_id,
                       {parent_title_col} AS parent_title,
                       COALESCE(c.{cfg['name_col']}, 'Guest') AS name,
                       c.{cfg['text_col']} AS body,
                       c.{cfg['date_col']} AS posted_at,
                       COALESCE(c.shadowed, 0) AS shadowed,
                       COALESCE(c.edited_by_moderator, 0) AS edited_by_moderator
                FROM {cfg['table']} c
                JOIN {parent_table} ON {join_on}
                WHERE 1=1{where_extra}
            """, [ctype, *params])
            queue.extend(cur.fetchall())
        except Exception:
            continue

    cur.close()
    queue.sort(key=lambda r: r.get('posted_at') or '', reverse=True)
    return queue[:limit]


def public_comments_enabled():
    """Return True when public-facing comments are allowed."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("SELECT public_comments_enabled FROM settings WHERE id = 1")
        row = cur.fetchone()
        cur.close()
        if row is None:
            return True
        return bool(row[0])
    except Exception:
        cur.close()
        return True


def _shadow_visibility_sql(alias=''):
    prefix = f"{alias}." if alias else ""
    return f"""(
        COALESCE({prefix}shadowed, 0) = 0
        OR ({prefix}shadow_ip IS NOT NULL AND {prefix}shadow_ip = %s)
        OR ({prefix}shadow_user_id IS NOT NULL AND {prefix}shadow_user_id = %s)
    )"""


def get_comment_stats():
    """Total and shadowed comment counts per content type for the manager dashboard."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    stats = {
        'event_comments': {'total': 0, 'shadowed': 0},
        'prayer_comments': {'total': 0, 'shadowed': 0},
        'sermon_comments': {'total': 0, 'shadowed': 0},
        'dream_comments': {'total': 0, 'shadowed': 0},
        'prophecy_comments': {'total': 0, 'shadowed': 0},
        'announcement_comments': {'total': 0, 'shadowed': 0},
        'all_total': 0,
        'all_shadowed': 0,
    }
    key_map = {
        'event': 'event_comments',
        'prayer': 'prayer_comments',
        'sermon': 'sermon_comments',
        'dream': 'dream_comments',
        'prophecy': 'prophecy_comments',
        'announcement': 'announcement_comments',
    }
    for ctype, cfg in COMMENT_TYPES.items():
        key = key_map[ctype]
        try:
            cur.execute(f"""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN COALESCE(shadowed, 0) = 1 THEN 1 ELSE 0 END) AS shadowed
                FROM {cfg['table']}
            """)
            row = cur.fetchone() or {}
            total = int(row.get('total') or 0)
            shadowed = int(row.get('shadowed') or 0)
            stats[key] = {'total': total, 'shadowed': shadowed}
            stats['all_total'] += total
            stats['all_shadowed'] += shadowed
        except Exception:
            pass
    cur.close()
    return stats


def fetch_public_comments(content_type, parent_id, viewer_ip=None, viewer_user_id=None):
    """Comments visible to a public viewer (hides shadowed unless they are the author)."""
    from app.utils.account_moderation import content_author_clause

    cfg = COMMENT_TYPES.get(content_type)
    if not cfg:
        return []

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    visibility = _shadow_visibility_sql()
    account_shadow_sql, account_shadow_params = content_author_clause(
        cfg['user_col'],
        viewer_id=viewer_user_id,
    )
    try:
        cur.execute(f"""
            SELECT
                id,
                COALESCE({cfg['name_col']}, 'Guest') AS name,
                {cfg['text_col']} AS comment_text,
                parent_id,
                DATE_FORMAT({cfg['date_col']}, '%%b %%e, %%Y %%h:%%i %%p') AS created_at_nice,
                COALESCE(edited_by_moderator, 0) AS edited_by_moderator
            FROM {cfg['table']}
            WHERE {cfg['parent_col']} = %s AND {visibility}{account_shadow_sql}
            ORDER BY {cfg['date_col']} ASC
        """, (parent_id, viewer_ip, viewer_user_id, *account_shadow_params))
        rows = cur.fetchall()
    except Exception:
        rows = []
    cur.close()
    return rows


def fetch_manager_comments(content_type, parent_id, search=None, status_filter='all'):
    """All comments for manager moderation UI."""
    cfg = COMMENT_TYPES.get(content_type)
    if not cfg:
        return []

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    clauses = [f"{cfg['parent_col']} = %s"]
    params = [parent_id]

    if search:
        clauses.append(f"({cfg['name_col']} LIKE %s OR {cfg['text_col']} LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    if status_filter == 'shadowed':
        clauses.append("COALESCE(shadowed, 0) = 1")
    elif status_filter == 'edited':
        clauses.append("COALESCE(edited_by_moderator, 0) = 1")
    elif status_filter == 'visible':
        clauses.append("COALESCE(shadowed, 0) = 0")

    where_sql = " AND ".join(clauses)
    try:
        cur.execute(f"""
            SELECT
                id,
                COALESCE({cfg['name_col']}, 'Guest') AS name,
                {cfg['text_col']} AS comment_text,
                parent_id,
                {cfg['ip_col']} AS ip_address,
                {cfg['user_col']} AS user_id,
                DATE_FORMAT({cfg['date_col']}, '%%b %%e, %%Y %%h:%%i %%p') AS created_at_nice,
                COALESCE(shadowed, 0) AS shadowed,
                COALESCE(edited_by_moderator, 0) AS edited_by_moderator,
                moderator_edited_at,
                moderated_by,
                moderated_at
            FROM {cfg['table']}
            WHERE {where_sql}
            ORDER BY {cfg['date_col']} ASC
        """, params)
        rows = cur.fetchall()
    except Exception:
        rows = []
    cur.close()
    return rows


def validate_comment_moderation_form(form_data):
    """Validate manager moderation POST."""
    action = (form_data.get('action') or '').strip()
    comment_id = (form_data.get('comment_id') or '').strip()
    new_text = (form_data.get('new_text') or '').strip()

    if not action or not comment_id or not comment_id.isdigit():
        flash('Invalid moderation request.', 'error')
        return None

    if action not in ('delete', 'edit', 'shadow', 'unshadow'):
        flash('Unknown moderation action.', 'error')
        return None

    if action == 'edit' and not new_text:
        flash('Edited comment text cannot be empty.', 'error')
        return None

    return {
        'action': action,
        'comment_id': int(comment_id),
        'new_text': new_text,
    }


def apply_moderation_action(content_type, parent_id, moderator_id, moderator_username, form_data):
    """Execute delete / edit / shadow / unshadow and write audit log."""
    clean = validate_comment_moderation_form(form_data)
    if not clean:
        return False

    cfg = COMMENT_TYPES.get(content_type)
    if not cfg:
        flash('Unknown content type.', 'error')
        return False

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    comment_id = clean['comment_id']

    try:
        cur.execute(f"""
            SELECT id, {cfg['text_col']} AS body, {cfg['ip_col']} AS ip_val,
                   {cfg['user_col']} AS uid, COALESCE(shadowed, 0) AS shadowed
            FROM {cfg['table']}
            WHERE id = %s AND {cfg['parent_col']} = %s
        """, (comment_id, parent_id))
        comment = cur.fetchone()
    except Exception:
        cur.close()
        flash('Comment not found.', 'error')
        return False

    if not comment:
        cur.close()
        flash('Comment not found.', 'error')
        return False

    action = clean['action']
    label = cfg['label']
    detail_prefix = f"{label} #{comment_id} on {content_type} #{parent_id}"

    try:
        if action == 'delete':
            cur.execute(f"DELETE FROM {cfg['table']} WHERE id = %s", (comment_id,))
            log_change(
                moderator_id, 'moderate_comment_delete',
                item_id=comment_id,
                item_title=f"{content_type}:{parent_id}",
                details=f"{detail_prefix} deleted by {moderator_username}. Original: {(comment['body'] or '')[:200]}",
            )
            flash('Comment deleted.', 'success')

        elif action == 'edit':
            cur.execute(f"""
                UPDATE {cfg['table']}
                SET {cfg['text_col']} = %s,
                    edited_by_moderator = 1,
                    moderator_edited_at = NOW(),
                    moderated_by = %s,
                    moderated_at = NOW()
                WHERE id = %s
            """, (clean['new_text'], moderator_id, comment_id))
            log_change(
                moderator_id, 'moderate_comment_edit',
                item_id=comment_id,
                item_title=f"{content_type}:{parent_id}",
                details=f"{detail_prefix} edited by {moderator_username}. Was: {(comment['body'] or '')[:120]}",
            )
            flash('Comment updated.', 'success')

        elif action == 'shadow':
            cur.execute(f"""
                UPDATE {cfg['table']}
                SET shadowed = 1,
                    shadow_ip = %s,
                    shadow_user_id = %s,
                    moderated_by = %s,
                    moderated_at = NOW()
                WHERE id = %s
            """, (comment['ip_val'], comment['uid'], moderator_id, comment_id))
            log_change(
                moderator_id, 'moderate_comment_shadow',
                item_id=comment_id,
                item_title=f"{content_type}:{parent_id}",
                details=f"{detail_prefix} shadowed by {moderator_username} (visible only to poster).",
            )
            flash('Comment shadowed — only the original poster can see it.', 'success')

        elif action == 'unshadow':
            cur.execute(f"""
                UPDATE {cfg['table']}
                SET shadowed = 0,
                    shadow_ip = NULL,
                    shadow_user_id = NULL,
                    moderated_by = %s,
                    moderated_at = NOW()
                WHERE id = %s
            """, (moderator_id, comment_id))
            log_change(
                moderator_id, 'moderate_comment_unshadow',
                item_id=comment_id,
                item_title=f"{content_type}:{parent_id}",
                details=f"{detail_prefix} unshadowed by {moderator_username}.",
            )
            flash('Comment is visible to everyone again.', 'success')

        db.commit()
        cur.close()
        return True
    except Exception:
        db.rollback()
        cur.close()
        flash('Failed to moderate comment.', 'error')
        return False


def handle_manager_comments_post(content_type, parent_id, moderator_id, form_data):
    """Resolve moderator username and apply moderation action."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute("SELECT username FROM users WHERE id = %s", (moderator_id,))
        mod = cur.fetchone()
    except Exception:
        mod = None
    cur.close()
    mod_name = (mod or {}).get('username') or f"user#{moderator_id}"
    return apply_moderation_action(content_type, parent_id, moderator_id, mod_name, form_data)


def map_comments_legacy(comments):
    """Normalize fetch_public_comments rows for sermon/dream/prophecy/announcement templates."""
    return [
        {
            'id': c['id'],
            'name': c['name'],
            'comment': c['comment_text'],
            'date': c['created_at_nice'],
            'parent_id': c['parent_id'],
            'edited_by_moderator': c.get('edited_by_moderator'),
        }
        for c in comments
    ]


def insert_public_comment(content_type, parent_id, name, text, parent_comment_id=None,
                          ip=None, user_id=None):
    """Insert a new public comment with IP/user for shadow moderation support."""
    cfg = COMMENT_TYPES.get(content_type)
    if not cfg:
        return False

    db = get_db()
    cur = db.cursor()
    cols = [cfg['parent_col'], cfg['name_col'], cfg['text_col'], cfg['ip_col'], cfg['user_col']]
    vals = [parent_id, name, text, ip, user_id]
    if parent_comment_id is not None:
        cols.append('parent_id')
        vals.append(parent_comment_id)
    placeholders = ', '.join(['%s'] * len(vals))
    col_sql = ', '.join(cols)
    try:
        cur.execute(f"INSERT INTO {cfg['table']} ({col_sql}) VALUES ({placeholders})", vals)
        db.commit()
        cur.close()
        return True
    except Exception:
        db.rollback()
        cur.close()
        return False


def comment_count_subquery(content_type, parent_alias, parent_id_col='id'):
    """SQL fragment for listing pages: (SELECT COUNT(*) ... ) AS comment_count."""
    cfg = COMMENT_TYPES.get(content_type)
    if not cfg:
        return "0 AS comment_count"
    return f"""(
        SELECT COUNT(*) FROM {cfg['table']} c
        WHERE c.{cfg['parent_col']} = {parent_alias}.{parent_id_col}
    ) AS comment_count"""