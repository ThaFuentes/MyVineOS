# Sunday serving: volunteer events + pastoral plans + worship setlists.
# Same accept/decline language everywhere; personal page is the home for "what I'm doing".

from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta

import pymysql

from app.models.db import get_db


def _cur():
    return get_db().cursor(pymysql.cursors.DictCursor)


def _today() -> date:
    try:
        from app.models.volunteers import church_today_str
        return datetime.strptime(church_today_str(), '%Y-%m-%d').date()
    except Exception:
        return date.today()


def _ymd(value) -> str:
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    return str(value)[:10]


def _clock(value) -> str:
    if value is None or value == '':
        return ''
    if hasattr(value, 'strftime'):
        try:
            return value.strftime('%-I:%M %p')
        except Exception:
            return value.strftime('%I:%M %p').lstrip('0')
    return str(value)[:8]


def ensure_serving_columns() -> None:
    db = get_db()
    cur = db.cursor()
    specs = (
        ('service_plan_assignments', [
            ('status', "VARCHAR(20) NOT NULL DEFAULT 'pending'"),
            ('response_token', 'VARCHAR(64) NULL'),
            ('notified_at', 'DATETIME NULL'),
            ('responded_at', 'DATETIME NULL'),
        ]),
        ('worship_setlist_assignments', [
            ('status', "VARCHAR(20) NOT NULL DEFAULT 'pending'"),
            ('response_token', 'VARCHAR(64) NULL'),
            ('notified_at', 'DATETIME NULL'),
            ('responded_at', 'DATETIME NULL'),
        ]),
    )
    for table, cols in specs:
        for name, coldef in cols:
            try:
                cur.execute(
                    """
                    SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
                    """,
                    (table, name),
                )
                if not cur.fetchone():
                    cur.execute(f'ALTER TABLE {table} ADD COLUMN {name} {coldef}')
                    db.commit()
            except Exception as exc:
                print(f'serving migrate {table}.{name}: {exc}')
                try:
                    db.rollback()
                except Exception:
                    pass
        try:
            cur.execute(f'CREATE UNIQUE INDEX idx_{table}_token ON {table} (response_token)')
            db.commit()
        except Exception:
            pass


def _snapshot(table: str, where_sql: str, where_args: tuple) -> dict:
    ensure_serving_columns()
    cur = _cur()
    try:
        cur.execute(
            f"""
            SELECT user_id, role_name, status, response_token, notified_at, responded_at
            FROM {table} WHERE {where_sql}
            """,
            where_args,
        )
        rows = list(cur.fetchall() or [])
    except Exception:
        return {}
    out = {}
    for row in rows:
        uid = row.get('user_id')
        if not uid:
            continue
        out[(int(uid), (row.get('role_name') or '').strip())] = row
    return out


def serving_fields_for_insert(prev: dict | None, user_id) -> tuple:
    """status, token, notified_at, responded_at for a (possibly new) person on a role."""
    if user_id and prev:
        return (
            prev.get('status') or 'pending',
            prev.get('response_token') or secrets.token_urlsafe(24),
            prev.get('notified_at'),
            prev.get('responded_at'),
        )
    if user_id:
        return ('pending', secrets.token_urlsafe(24), None, None)
    return ('pending', None, None, None)


def _send_serving_email(row: dict, *, kind: str = 'invite') -> bool:
    email = (row.get('email') or '').strip()
    token = row.get('response_token')
    if not email or not token:
        return False
    name = row.get('display_name') or row.get('first_name') or 'Friend'
    title = row.get('title') or 'This Sunday'
    role = row.get('role_name') or 'Serving'
    when = _ymd(row.get('serve_date'))
    clock = _clock(row.get('serve_time'))
    if clock:
        when = f'{when} · {clock}'
    kind_label = row.get('kind_label') or ''
    try:
        from app.utils.email_notifications import external_url
        from app.models.settings import get_settings
        church = (get_settings() or {}).get('church_name') or 'Church'
        accept_url = external_url('church.serve_respond', token=token, action='accept')
        decline_url = external_url('church.serve_respond', token=token, action='decline')
        page_url = external_url('church.member_page', username=row.get('username') or '')
    except Exception:
        church = 'Church'
        accept_url = decline_url = page_url = ''
    if kind == 'reminder':
        subject = f'Reminder: {role} — {title}'
        intro = f"Hi {name},\n\nFriendly reminder you're on for this service."
    elif kind == 'accepted':
        subject = f'Confirmed: {role} — {title}'
        intro = f"Hi {name},\n\nYou're confirmed. Thank you."
    else:
        subject = f'Can you serve as {role}? — {title}'
        intro = f"Hi {name},\n\nYou've been asked to serve this Sunday."
    body = (
        f"{intro}\n\n"
        f"{kind_label + ': ' if kind_label else ''}{title}\n"
        f"When: {when}\n"
        f"Role: {role}\n\n"
    )
    if kind != 'accepted':
        body += f"Accept:  {accept_url}\nDecline: {decline_url}\n\n"
    if page_url:
        body += f"Your page (sign in): {page_url}\n\n"
    body += f"— {church}"
    try:
        from app.utils.emailer import send_email
        send_email(email, subject, body)
        return True
    except Exception as exc:
        print(f'serving email: {exc}')
        return False


def notify_if_new(row: dict, *, kind: str = 'invite') -> None:
    """Email once when someone is newly asked."""
    if not row or not row.get('user_id'):
        return
    if kind == 'invite' and row.get('notified_at'):
        return
    if (row.get('status') or 'pending') not in ('pending', '') and kind == 'invite':
        return
    if _send_serving_email(row, kind=kind):
        _mark_notified(row)


def _mark_notified(row: dict) -> None:
    table = row.get('_table')
    rid = row.get('_row_id')
    if not table or not rid:
        return
    db = get_db()
    cur = db.cursor()
    cur.execute(f'UPDATE {table} SET notified_at=NOW() WHERE id=%s', (int(rid),))
    db.commit()


def my_serving(user_id: int, *, upcoming_only: bool = True, limit: int = 24) -> list[dict]:
    """Everything this person is asked to do: volunteer, Sunday plan, worship."""
    uid = int(user_id)
    cache_key = (uid, bool(upcoming_only), int(limit))
    store = None
    try:
        from flask import g, has_request_context
        if has_request_context():
            store = getattr(g, '_my_serving_cache', None)
            if store is None:
                g._my_serving_cache = store = {}
            if cache_key in store:
                return store[cache_key]
    except Exception:
        store = None

    ensure_serving_columns()
    today = _today().isoformat()
    items: list[dict] = []

    try:
        from app.models import volunteers as vol
        for a in vol.my_assignments(uid, upcoming_only=upcoming_only, limit=limit) or []:
            items.append({
                'source': 'volunteer',
                'id': a.get('id'),
                'token': a.get('response_token'),
                'role_name': a.get('role_name') or 'Volunteer',
                'title': a.get('event_title') or 'Serving',
                'serve_date': _ymd(a.get('event_date')),
                'serve_time': _clock(a.get('start_time')),
                'location': a.get('event_location') or '',
                'status': a.get('status') or 'pending',
                'kind_label': a.get('team_name') or 'Serving',
                'respond_url': 'volunteers',
            })
    except Exception as exc:
        print(f'serving volunteer: {exc}')

    cur = _cur()
    date_clause = "AND p.service_date >= %s" if upcoming_only else ""
    params: list = [uid]
    if upcoming_only:
        params.append(today)
    try:
        cur.execute(
            f"""
            SELECT spa.id, spa.role_name, spa.status, spa.response_token,
                   p.service_date, p.title, p.start_time
            FROM service_plan_assignments spa
            JOIN service_plans p ON p.id = spa.service_plan_id
            WHERE spa.user_id = %s {date_clause}
            ORDER BY p.service_date ASC
            LIMIT %s
            """,
            (*params, int(limit)),
        )
        for row in cur.fetchall() or []:
            items.append({
                'source': 'pastoral',
                'id': row.get('id'),
                'token': row.get('response_token'),
                'role_name': row.get('role_name') or 'Role',
                'title': row.get('title') or 'Sunday service',
                'serve_date': _ymd(row.get('service_date')),
                'serve_time': _clock(row.get('start_time')),
                'location': '',
                'status': row.get('status') or 'pending',
                'kind_label': 'Sunday service',
                'respond_url': 'church',
            })
    except Exception as exc:
        print(f'serving pastoral: {exc}')

    date_clause_w = "AND s.service_date >= %s" if upcoming_only else ""
    wparams: list = [uid]
    if upcoming_only:
        wparams.append(today)
    try:
        cur.execute(
            f"""
            SELECT a.id, a.role_name, a.status, a.response_token,
                   s.service_date, s.title, s.service_time
            FROM worship_setlist_assignments a
            JOIN worship_setlists s ON s.id = a.setlist_id
            WHERE a.user_id = %s AND s.service_date IS NOT NULL {date_clause_w}
            ORDER BY s.service_date ASC
            LIMIT %s
            """,
            (*wparams, int(limit)),
        )
        for row in cur.fetchall() or []:
            items.append({
                'source': 'worship',
                'id': row.get('id'),
                'token': row.get('response_token'),
                'role_name': row.get('role_name') or 'Worship',
                'title': row.get('title') or 'Worship',
                'serve_date': _ymd(row.get('service_date')),
                'serve_time': _clock(row.get('service_time')),
                'location': '',
                'status': row.get('status') or 'pending',
                'kind_label': 'Worship',
                'respond_url': 'church',
            })
    except Exception as exc:
        print(f'serving worship: {exc}')

    items.sort(key=lambda r: (r.get('serve_date') or '9999', r.get('serve_time') or ''))
    items = items[:limit]
    if store is not None:
        store[cache_key] = items
    return items


def serving_counts(user_id: int | None) -> tuple[int, int]:
    """(unanswered, volunteered) for upcoming asks."""
    if not user_id:
        return (0, 0)
    pending = accepted = 0
    for row in my_serving(int(user_id), upcoming_only=True, limit=24):
        status = (row.get('status') or '').strip()
        if status == 'pending':
            pending += 1
        elif status == 'accepted':
            accepted += 1
    return (pending, accepted)


def get_ask_by_token(token: str) -> dict | None:
    if not token:
        return None
    ensure_serving_columns()
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT spa.id, spa.user_id, spa.role_name, spa.status, spa.response_token,
                   p.service_date AS serve_date, p.title, p.start_time AS serve_time,
                   'pastoral' AS source, 'service_plan_assignments' AS _table
            FROM service_plan_assignments spa
            JOIN service_plans p ON p.id = spa.service_plan_id
            WHERE spa.response_token = %s
            LIMIT 1
            """,
            (token,),
        )
        row = cur.fetchone()
        if row:
            return _decorate_ask(row)
    except Exception:
        pass
    try:
        cur.execute(
            """
            SELECT a.id, a.user_id, a.role_name, a.status, a.response_token,
                   s.service_date AS serve_date, s.title, s.service_time AS serve_time,
                   'worship' AS source, 'worship_setlist_assignments' AS _table
            FROM worship_setlist_assignments a
            JOIN worship_setlists s ON s.id = a.setlist_id
            WHERE a.response_token = %s
            LIMIT 1
            """,
            (token,),
        )
        row = cur.fetchone()
        if row:
            return _decorate_ask(row)
    except Exception:
        pass
    return None


def _decorate_ask(row: dict) -> dict:
    row['event_title'] = row.get('title')
    row['event_date'] = _ymd(row.get('serve_date'))
    row['start_time'] = _clock(row.get('serve_time'))
    row['serve_date'] = _ymd(row.get('serve_date'))
    return row


def respond_ask(token: str, accept: bool, actor_id: int | None = None) -> dict:
    row = get_ask_by_token(token)
    if not row:
        raise ValueError('That serving link is not valid.')
    if actor_id and int(row.get('user_id') or 0) != int(actor_id):
        raise ValueError('That serving request is for someone else.')
    if (row.get('status') or '') in ('accepted', 'declined') and row.get('responded_at'):
        return row
    status = 'accepted' if accept else 'declined'
    table = row.get('_table')
    db = get_db()
    cur = db.cursor()
    cur.execute(
        f"UPDATE {table} SET status=%s, responded_at=NOW() WHERE id=%s",
        (status, int(row['id'])),
    )
    db.commit()
    updated = get_ask_by_token(token) or row
    updated['status'] = status
    return updated


def after_plan_saved(plan_id: int) -> None:
    """Issue tokens + first invite for people just put on a dated Sunday plan."""
    ensure_serving_columns()
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT spa.id, spa.user_id, spa.role_name, spa.status, spa.response_token,
                   spa.notified_at, p.service_date, p.title, p.start_time,
                   u.email, u.first_name, u.last_name, u.username
            FROM service_plan_assignments spa
            JOIN service_plans p ON p.id = spa.service_plan_id
            JOIN users u ON u.id = spa.user_id
            WHERE spa.service_plan_id = %s AND spa.user_id IS NOT NULL
            """,
            (int(plan_id),),
        )
        rows = list(cur.fetchall() or [])
    except Exception as exc:
        print(f'serving after plan: {exc}')
        return
    db = get_db()
    wcur = db.cursor()
    for row in rows:
        token = row.get('response_token') or secrets.token_urlsafe(24)
        if not row.get('response_token'):
            wcur.execute(
                "UPDATE service_plan_assignments SET response_token=%s, status=COALESCE(NULLIF(status,''),'pending') WHERE id=%s",
                (token, row['id']),
            )
            row['response_token'] = token
        row['_table'] = 'service_plan_assignments'
        row['_row_id'] = row['id']
        row['title'] = row.get('title') or 'Sunday service'
        row['serve_date'] = row.get('service_date')
        row['serve_time'] = row.get('start_time')
        row['kind_label'] = 'Sunday service'
        row['display_name'] = f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip()
        notify_if_new(row, kind='invite')
    db.commit()


def after_setlist_saved(setlist_id: int) -> None:
    ensure_serving_columns()
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT a.id, a.user_id, a.role_name, a.status, a.response_token,
                   a.notified_at, s.service_date, s.title, s.service_time,
                   u.email, u.first_name, u.last_name, u.username
            FROM worship_setlist_assignments a
            JOIN worship_setlists s ON s.id = a.setlist_id
            JOIN users u ON u.id = a.user_id
            WHERE a.setlist_id = %s AND a.user_id IS NOT NULL AND s.service_date IS NOT NULL
            """,
            (int(setlist_id),),
        )
        rows = list(cur.fetchall() or [])
    except Exception as exc:
        print(f'serving after setlist: {exc}')
        return
    db = get_db()
    wcur = db.cursor()
    for row in rows:
        token = row.get('response_token') or secrets.token_urlsafe(24)
        if not row.get('response_token'):
            wcur.execute(
                "UPDATE worship_setlist_assignments SET response_token=%s, status=COALESCE(NULLIF(status,''),'pending') WHERE id=%s",
                (token, row['id']),
            )
            row['response_token'] = token
        row['_table'] = 'worship_setlist_assignments'
        row['_row_id'] = row['id']
        row['title'] = row.get('title') or 'Worship'
        row['serve_date'] = row.get('service_date')
        row['serve_time'] = row.get('service_time')
        row['kind_label'] = 'Worship'
        row['display_name'] = f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip()
        notify_if_new(row, kind='invite')
    db.commit()


def send_pending_reminders() -> int:
    """Remind pastoral/worship pending asks in the volunteer reminder window."""
    ensure_serving_columns()
    try:
        from app.models.volunteers import get_vol_settings
        settings = get_vol_settings()
        if not settings.get('reminders_enabled'):
            return 0
        days = int(settings.get('reminder_days') or 3)
    except Exception:
        days = 3
    today = _today()
    until = (today + timedelta(days=days)).isoformat()
    sent = 0
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT spa.id, spa.user_id, spa.role_name, spa.status, spa.response_token,
                   spa.notified_at, p.service_date, p.title, p.start_time,
                   u.email, u.first_name, u.last_name
            FROM service_plan_assignments spa
            JOIN service_plans p ON p.id = spa.service_plan_id
            JOIN users u ON u.id = spa.user_id
            WHERE spa.status='pending' AND spa.response_token IS NOT NULL
              AND p.service_date BETWEEN %s AND %s
            """,
            (today.isoformat(), until),
        )
        for row in cur.fetchall() or []:
            payload = {
                '_table': 'service_plan_assignments',
                '_row_id': row['id'],
                'user_id': row['user_id'],
                'email': row.get('email'),
                'display_name': f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip(),
                'title': row.get('title') or 'Sunday service',
                'serve_date': row.get('service_date'),
                'serve_time': row.get('start_time'),
                'role_name': row.get('role_name'),
                'response_token': row.get('response_token'),
                'status': 'pending',
                'kind_label': 'Sunday service',
                'notified_at': None,
            }
            notify_if_new(payload, kind='reminder')
            sent += 1
    except Exception as exc:
        print(f'serving pastoral reminders: {exc}')
    try:
        cur.execute(
            """
            SELECT a.id, a.user_id, a.role_name, a.status, a.response_token,
                   s.service_date, s.title, s.service_time,
                   u.email, u.first_name, u.last_name
            FROM worship_setlist_assignments a
            JOIN worship_setlists s ON s.id = a.setlist_id
            JOIN users u ON u.id = a.user_id
            WHERE a.status='pending' AND a.response_token IS NOT NULL
              AND s.service_date BETWEEN %s AND %s
            """,
            (today.isoformat(), until),
        )
        for row in cur.fetchall() or []:
            payload = {
                '_table': 'worship_setlist_assignments',
                '_row_id': row['id'],
                'user_id': row['user_id'],
                'email': row.get('email'),
                'display_name': f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip(),
                'title': row.get('title') or 'Worship',
                'serve_date': row.get('service_date'),
                'serve_time': row.get('service_time'),
                'role_name': row.get('role_name'),
                'response_token': row.get('response_token'),
                'status': 'pending',
                'kind_label': 'Worship',
                'notified_at': None,
            }
            notify_if_new(payload, kind='reminder')
            sent += 1
    except Exception as exc:
        print(f'serving worship reminders: {exc}')
    return sent
