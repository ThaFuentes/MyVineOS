# Report button queue + word-list hits (content_flags).
# Members report; moderators Hide / Dismiss / Restore. Every decision goes to
# the reversible moderation ledger (moderation_actions) and the audit log.

from __future__ import annotations

import pymysql
from flask import has_request_context, request, session

from app.models.db import get_db

REPORT_CATEGORIES = (
    ('spam', 'Spam or scam'),
    ('harassment', 'Harassment or bullying'),
    ('abuse', 'Hateful or abusive'),
    ('sexual', 'Sexual or inappropriate'),
    ('crisis', 'Someone may be in danger'),
    ('pii', 'Shares private information'),
    ('other', 'Something else'),
)
CATEGORY_KEYS = {k for k, _l in REPORT_CATEGORIES}
CATEGORY_SEVERITY = {'crisis': 5, 'abuse': 3, 'harassment': 3, 'sexual': 3, 'pii': 3, 'spam': 2, 'other': 1}
REPORTS_PER_DAY = 20


def _cur():
    return get_db().cursor(pymysql.cursors.DictCursor)


def _masked(text: str | None, limit: int = 480) -> str:
    from app.utils.helpers import censor_text
    try:
        return censor_text(text or '')[:limit]
    except Exception:
        return ''


def resolve_target(kind: str, content_id: int, comment_type: str | None = None) -> dict | None:
    """Look up a reportable thing. kind is a CONTENT_SPECS kind or 'comment'."""
    from app.models import moderation as mod
    kind = (kind or '').strip()
    try:
        content_id = int(content_id)
    except (TypeError, ValueError):
        return None
    if content_id <= 0:
        return None
    if kind == 'comment':
        from app.utils.comment_moderation import COMMENT_TYPES
        cfg = COMMENT_TYPES.get((comment_type or '').strip())
        if not cfg:
            return None
        row = mod.get_comment(cfg['table'], content_id)
        if not row:
            return None
        return {
            'kind': 'comment',
            'id': content_id,
            'table': cfg['table'],
            'comment_type': comment_type,
            'author_id': row.get('user_id'),
            'text': row.get('body') or '',
            'hidden': bool(row.get('removed')),
        }
    spec = mod.CONTENT_SPECS.get(kind)
    if not spec:
        return None
    try:
        row = mod._fetch_content_row(spec, content_id)
    except Exception:
        row = None
    if not row:
        return None
    title = row.get(spec.get('title') or 'title') or ''
    body = row.get(spec.get('body') or 'body') or ''
    return {
        'kind': kind,
        'id': content_id,
        'table': spec['table'],
        'author_id': mod.content_author_id(kind, content_id),
        'text': f'{title}\n{body}'.strip(),
        'hidden': mod.content_is_hidden(kind, row),
    }


def reports_today(reporter_id: int) -> int:
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT COUNT(*) AS n FROM content_flags
            WHERE reporter_id=%s AND source='report' AND created_at >= (NOW() - INTERVAL 1 DAY)
            """,
            (int(reporter_id),),
        )
        return int((cur.fetchone() or {}).get('n') or 0)
    except Exception:
        return 0


def raise_flag(*, kind: str, content_id: int | None, table: str | None, author_id: int | None,
               source: str = 'report', category: str = 'other', severity: int | None = None,
               reporter_id: int | None = None, note: str = '', excerpt: str = '',
               context: str = '', status: str = 'open', ai_score=None, ai_reason: str = '') -> int | None:
    """Insert one flag row. Returns its id, or None (duplicate report or DB problem)."""
    category = category if category in CATEGORY_KEYS else 'other'
    sev = int(severity if severity is not None else CATEGORY_SEVERITY.get(category, 1))
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO content_flags
              (content_kind, content_id, content_table, author_id, source, category, severity,
               ai_score, ai_reason, reporter_id, reporter_note, excerpt, context, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                (kind or 'unknown')[:32],
                int(content_id) if content_id else None,
                (table or None),
                int(author_id) if author_id else None,
                source[:16],
                category,
                max(1, min(5, sev)),
                ai_score,
                (ai_reason or '')[:500] or None,
                int(reporter_id) if reporter_id else None,
                (note or '')[:500] or None,
                _masked(excerpt) or None,
                (context or '')[:160] or None,
                status[:16],
            ),
        )
        db.commit()
        return int(cur.lastrowid)
    except pymysql.err.IntegrityError:
        db.rollback()
        return None
    except Exception as exc:
        print(f'raise_flag: {exc}')
        try:
            db.rollback()
        except Exception:
            pass
        return None


def report(reporter_id: int, kind: str, content_id, category: str, note: str = '',
           comment_type: str | None = None) -> tuple[bool, str]:
    """Member pressed Report."""
    from app.utils.html_sanitize import sanitize_plain_text
    target = resolve_target(kind, content_id, comment_type)
    if not target:
        return False, 'We could not find that post.'
    if target.get('author_id') and int(target['author_id']) == int(reporter_id):
        return False, 'That one is yours. You can delete it instead.'
    if reports_today(reporter_id) >= REPORTS_PER_DAY:
        return False, 'You have sent a lot of reports today. Our moderators are on it. Try again tomorrow.'
    category = (category or 'other').strip()
    flag_id = raise_flag(
        kind=target['kind'],
        content_id=target['id'],
        table=target['table'],
        author_id=target.get('author_id'),
        source='report',
        category=category,
        reporter_id=reporter_id,
        note=sanitize_plain_text(note or '')[:500],
        excerpt=target.get('text') or '',
    )
    if not flag_id:
        return False, 'You already reported this. Thanks, a moderator will look at it.'
    try:
        from app.models.log import log_change
        log_change(reporter_id, 'report_content', target_id=target['id'],
                   change_details=f"Reported {target['kind']} #{target['id']} ({category})")
    except Exception:
        pass
    return True, 'Thanks for telling us. A moderator will take a look.'


def record_wordlist_hit(text: str, context: str = '') -> None:
    """Censored-word hook: a save was blocked. Keep a masked row for the mods."""
    uid = None
    ip = ''
    if has_request_context():
        uid = session.get('user_id')
        ip = (request.remote_addr or '')[:45]
        context = context or f'{request.method} {request.path}'[:160]
    raise_flag(
        kind='wordlist',
        content_id=None,
        table=None,
        author_id=uid,
        source='wordlist',
        category='other',
        severity=1,
        note=f'ip {ip}' if (ip and not uid) else '',
        excerpt=text or '',
        context=context,
        status='blocked',
    )


def open_count() -> int:
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT COUNT(DISTINCT content_kind, content_id, content_table) AS n
            FROM content_flags WHERE status='open' AND content_id IS NOT NULL
            """
        )
        return int((cur.fetchone() or {}).get('n') or 0)
    except Exception:
        return 0


def list_targets(status: str = 'open', limit: int = 80) -> list[dict]:
    """One row per reported item, worst first."""
    if status not in ('open', 'hidden', 'dismissed', 'restored'):
        status = 'open'
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT content_kind, content_id, content_table,
                   MAX(author_id) AS author_id,
                   COUNT(*) AS reports,
                   MAX(severity) AS severity,
                   MIN(created_at) AS first_at,
                   MAX(created_at) AS last_at,
                   GROUP_CONCAT(DISTINCT category ORDER BY category SEPARATOR ', ') AS categories,
                   GROUP_CONCAT(DISTINCT source ORDER BY source SEPARATOR ', ') AS sources,
                   SUBSTRING(GROUP_CONCAT(reporter_note ORDER BY id DESC SEPARATOR ' | '), 1, 600) AS notes,
                   MAX(excerpt) AS excerpt
            FROM content_flags
            WHERE status=%s AND content_id IS NOT NULL
            GROUP BY content_kind, content_id, content_table
            ORDER BY MAX(severity) DESC, COUNT(*) DESC, MIN(created_at) ASC
            LIMIT %s
            """,
            (status, int(limit)),
        )
        rows = list(cur.fetchall() or [])
    except Exception as exc:
        print(f'list_targets: {exc}')
        return []
    from app.utils.comment_moderation import COMMENT_TYPES
    table_to_type = {}
    for key, cfg in COMMENT_TYPES.items():
        table_to_type.setdefault(cfg['table'], key)
    authors = _usernames([r.get('author_id') for r in rows])
    for row in rows:
        kind = row.get('content_kind')
        ctype = table_to_type.get(row.get('content_table') or '') if kind == 'comment' else None
        target = resolve_target(kind, row.get('content_id'), ctype)
        row['comment_type'] = ctype or ''
        row['missing'] = target is None
        row['hidden'] = bool(target and target.get('hidden'))
        row['preview'] = _masked((target or {}).get('text') or row.get('excerpt') or '', 400)
        row['author_username'] = authors.get(int(row.get('author_id') or 0), '')
        row['notes'] = _masked(row.get('notes') or '', 600)
    return rows


def list_wordlist_hits(limit: int = 40) -> list[dict]:
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT f.*, u.username FROM content_flags f
            LEFT JOIN users u ON u.id = f.author_id
            WHERE f.source='wordlist'
            ORDER BY f.created_at DESC LIMIT %s
            """,
            (int(limit),),
        )
        return list(cur.fetchall() or [])
    except Exception:
        return []


def _usernames(ids) -> dict[int, str]:
    clean = sorted({int(i) for i in ids if i})
    if not clean:
        return {}
    cur = _cur()
    try:
        cur.execute(
            f"SELECT id, username FROM users WHERE id IN ({','.join(['%s'] * len(clean))})",
            clean,
        )
        return {int(r['id']): (r.get('username') or '') for r in cur.fetchall() or []}
    except Exception:
        return {}


def _set_status(kind: str, content_id: int, table: str | None, status: str, actor_id: int,
                action_id=None, from_status: tuple = ('open',)) -> None:
    db = get_db()
    cur = db.cursor()
    ph = ','.join(['%s'] * len(from_status))
    cur.execute(
        f"""
        UPDATE content_flags
        SET status=%s, resolved_by=%s, resolved_at=NOW(),
            moderation_action_id=COALESCE(%s, moderation_action_id)
        WHERE content_kind=%s AND content_id=%s AND (content_table <=> %s) AND status IN ({ph})
        """,
        (status, int(actor_id), action_id, kind, int(content_id), table, *from_status),
    )
    db.commit()


def resolve(kind: str, content_id: int, decision: str, actor_id: int, *, table: str | None = None,
            comment_type: str | None = None, note: str = '') -> tuple[bool, str]:
    """Hide / Dismiss / Restore one reported item. All of it lands in the ledger + audit log."""
    from app.models import moderation as mod
    from app.models.log import log_change
    kind = (kind or '').strip()
    decision = (decision or '').strip()
    if kind == 'comment' and not table:
        from app.utils.comment_moderation import COMMENT_TYPES
        table = (COMMENT_TYPES.get(comment_type or '') or {}).get('table')
    if kind != 'comment':
        spec = mod.CONTENT_SPECS.get(kind)
        if not spec:
            return False, 'Unknown item.'
        table = spec['table']
    if not table:
        return False, 'Unknown item.'
    if decision == 'hide':
        if kind == 'comment':
            ok = mod.soft_delete_comment(table, int(content_id), actor_id, note or 'Hidden from a report')
            msg = 'Comment hidden. You can restore it here.' if ok else 'Could not hide that comment.'
        else:
            ok, msg = mod.hide_content(kind, int(content_id), actor_id, note or 'Hidden from a report', warn=False)
        if ok or 'already hidden' in (msg or ''):
            _set_status(kind, int(content_id), table, 'hidden', actor_id, mod.last_action_id())
            ok = True
        log_change(actor_id, 'flag_hide', target_id=int(content_id),
                   change_details=f'Hid reported {kind} #{content_id}')
        return ok, msg
    if decision == 'dismiss':
        action_id = mod.record_action(
            actor_id=actor_id,
            action_type='flag_dismiss',
            target_kind=kind,
            target_table=table,
            target_id=int(content_id),
            reason=note or 'Reports dismissed',
        )
        _set_status(kind, int(content_id), table, 'dismissed', actor_id, action_id)
        log_change(actor_id, 'flag_dismiss', target_id=int(content_id),
                   change_details=f'Dismissed reports on {kind} #{content_id}')
        return True, 'Dismissed. It stays up.'
    if decision == 'restore':
        ok, msg = mod.restore_target(kind, int(content_id), actor_id, note or 'Restored from the report queue',
                                     table=table)
        if ok:
            _set_status(kind, int(content_id), table, 'restored', actor_id,
                        from_status=('open', 'hidden'))
        log_change(actor_id, 'flag_restore', target_id=int(content_id),
                   change_details=f'Restored {kind} #{content_id}')
        return ok, msg
    return False, 'Pick Hide, Dismiss, or Restore.'
