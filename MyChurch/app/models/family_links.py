# Family links from member pages: request, display, parent privacy override.

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import pymysql
from flask import url_for

from app.models.db import get_db
from app.models.log import log_change

CHOICES = (
    ('spouse|wife', 'Wife'),
    ('spouse|husband', 'Husband'),
    ('spouse|spouse', 'Spouse'),
    ('parent|mother', 'Mother'),
    ('parent|father', 'Father'),
    ('parent|parent', 'Parent'),
    ('child|daughter', 'Daughter'),
    ('child|son', 'Son'),
    ('child|child', 'Child'),
    ('sibling|sister', 'Sister'),
    ('sibling|brother', 'Brother'),
    ('sibling|sibling', 'Sibling'),
)
CANON = {'spouse', 'parent', 'child', 'sibling'}
INVERSE = {'spouse': 'spouse', 'parent': 'child', 'child': 'parent', 'sibling': 'sibling'}
INVERSE_LABEL = {
    'wife': 'Husband',
    'husband': 'Wife',
    'spouse': 'Spouse',
    'mother': 'Child',
    'father': 'Child',
    'parent': 'Child',
    'daughter': 'Parent',
    'son': 'Parent',
    'child': 'Parent',
    'sister': 'Sibling',
    'brother': 'Sibling',
    'sibling': 'Sibling',
}


def _cur():
    return get_db().cursor(pymysql.cursors.DictCursor)


def parse_choice(raw: str) -> tuple[str, str]:
    text = (raw or '').strip().lower()
    if '|' in text:
        typ, lab = text.split('|', 1)
    else:
        typ, lab = text, text
    if typ not in CANON:
        raise ValueError('Pick how they are family to you.')
    label = (lab or typ).strip()[:24] or typ
    return typ, label


def display_label(relation_type: str, label: str | None, *, inverse: bool = False) -> str:
    lab = (label or relation_type or '').strip().lower()
    if inverse:
        pretty = INVERSE_LABEL.get(lab) or INVERSE.get(relation_type, relation_type)
        return str(pretty).title()
    for key, title in CHOICES:
        if key.endswith('|' + lab) or key == f'{relation_type}|{lab}':
            return title
    return (label or relation_type or 'Family').title()


def _age_years(user: dict | None) -> Optional[int]:
    raw = (user or {}).get('birthday')
    if not raw:
        return None
    try:
        if hasattr(raw, 'year'):
            born = raw if isinstance(raw, date) and not isinstance(raw, datetime) else raw.date()
        else:
            born = datetime.strptime(str(raw)[:10], '%Y-%m-%d').date()
    except Exception:
        return None
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def is_adult(user: dict | None) -> bool:
    age = _age_years(user)
    return age is not None and age >= 18


def is_minor(user: dict | None) -> bool:
    return not is_adult(user)


def _name(row: dict) -> str:
    n = f"{(row.get('first_name') or '').strip()} {(row.get('last_name') or '').strip()}".strip()
    return n or (row.get('username') or 'Member')


def link_between(a: int, b: int) -> Optional[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT * FROM family_relations
        WHERE (user_id = %s AND relative_id = %s) OR (user_id = %s AND relative_id = %s)
        ORDER BY id DESC LIMIT 1
        """,
        (int(a), int(b), int(b), int(a)),
    )
    return cur.fetchone()


def request_link(sender_id: int, receiver_id: int, choice: str, show_on_page: bool = True) -> tuple[bool, str]:
    if int(sender_id) == int(receiver_id):
        return False, 'That is your own page.'
    typ, label = parse_choice(choice)
    existing = link_between(sender_id, receiver_id)
    if existing and (existing.get('status') or '') == 'approved':
        return False, 'You are already family.'
    if existing and (existing.get('status') or '') == 'pending' and int(existing.get('user_id') or 0) == int(sender_id):
        return False, 'That request is already waiting.'
    from app.models.users import get_user_by_id
    other = get_user_by_id(int(receiver_id)) or {}
    auto = typ == 'child' and is_minor(other)
    status = 'approved' if auto else 'pending'
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        DELETE FROM family_relations
        WHERE (user_id = %s AND relative_id = %s) OR (user_id = %s AND relative_id = %s)
        """,
        (int(sender_id), int(receiver_id), int(receiver_id), int(sender_id)),
    )
    try:
        cur.execute(
            """
            INSERT INTO family_relations
                (user_id, relative_id, relation_type, status, label, show_user, show_relative)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (int(sender_id), int(receiver_id), typ, status, label, 1 if show_on_page else 0, 1),
        )
    except Exception:
        cur.execute(
            """
            INSERT INTO family_relations (user_id, relative_id, relation_type, status)
            VALUES (%s, %s, %s, %s)
            """,
            (int(sender_id), int(receiver_id), typ, status),
        )
    db.commit()
    log_change(sender_id, 'send_family_request', target_id=int(receiver_id), change_details=f'{typ}:{label}')
    if auto:
        return True, f"Added as your {display_label(typ, label).lower()}. Because they are a child, you can set their page privacy."
    return True, f"Asked them to confirm you as family ({display_label(typ, label).lower()})."


def respond_link(relation_id: int, user_id: int, accept: bool, show_on_page: bool = True) -> tuple[bool, str]:
    cur = _cur()
    cur.execute("SELECT * FROM family_relations WHERE id = %s", (int(relation_id),))
    row = cur.fetchone()
    if not row or (row.get('status') or '') != 'pending':
        return False, 'That request is gone.'
    if int(row.get('relative_id') or 0) != int(user_id):
        return False, 'That request was not sent to you.'
    db = get_db()
    c = db.cursor()
    if not accept:
        c.execute(
            "UPDATE family_relations SET status='rejected', responded_at=CURRENT_TIMESTAMP WHERE id=%s",
            (int(relation_id),),
        )
        db.commit()
        return True, 'Declined.'
    try:
        c.execute(
            """
            UPDATE family_relations
            SET status='approved', responded_at=CURRENT_TIMESTAMP, show_relative=%s
            WHERE id=%s
            """,
            (1 if show_on_page else 0, int(relation_id)),
        )
    except Exception:
        c.execute(
            "UPDATE family_relations SET status='approved', responded_at=CURRENT_TIMESTAMP WHERE id=%s",
            (int(relation_id),),
        )
    db.commit()
    return True, 'You are family now.'


def remove_link(relation_id: int, user_id: int) -> tuple[bool, str]:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        DELETE FROM family_relations
        WHERE id = %s AND (user_id = %s OR relative_id = %s)
        """,
        (int(relation_id), int(user_id), int(user_id)),
    )
    db.commit()
    if cur.rowcount == 0:
        return False, 'Could not remove that.'
    return True, 'Removed from family.'


def set_show_on_my_page(relation_id: int, user_id: int, show: bool) -> None:
    cur = _cur()
    cur.execute("SELECT * FROM family_relations WHERE id = %s", (int(relation_id),))
    row = cur.fetchone() or {}
    db = get_db()
    c = db.cursor()
    if int(row.get('user_id') or 0) == int(user_id):
        c.execute("UPDATE family_relations SET show_user = %s WHERE id = %s", (1 if show else 0, int(relation_id)))
    elif int(row.get('relative_id') or 0) == int(user_id):
        c.execute("UPDATE family_relations SET show_relative = %s WHERE id = %s", (1 if show else 0, int(relation_id)))
    db.commit()


def pending_incoming(user_id: int) -> list[dict]:
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT fr.*, u.username, u.first_name, u.last_name
            FROM family_relations fr
            JOIN users u ON u.id = fr.user_id
            WHERE fr.relative_id = %s AND fr.status = 'pending'
            ORDER BY fr.requested_at DESC
            """,
            (int(user_id),),
        )
        rows = list(cur.fetchall() or [])
    except Exception:
        cur.execute(
            """
            SELECT fr.*, u.username, u.first_name, u.last_name
            FROM family_relations fr
            JOIN users u ON u.id = fr.user_id
            WHERE fr.relative_id = %s AND fr.status = 'pending'
            ORDER BY fr.id DESC
            """,
            (int(user_id),),
        )
        rows = list(cur.fetchall() or [])
    out = []
    for row in rows:
        typ = row.get('relation_type') or 'spouse'
        out.append({
            **row,
            'name': _name(row),
            'page_url': url_for('church.member_page', username=row['username']) if row.get('username') else '',
            'label': display_label(typ, row.get('label'), inverse=True),
        })
    return out


def family_for_page(owner_id: int, viewer_id: int | None = None) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT fr.*,
               CASE WHEN fr.user_id = %s THEN ru.username ELSE su.username END AS username,
               CASE WHEN fr.user_id = %s THEN ru.first_name ELSE su.first_name END AS first_name,
               CASE WHEN fr.user_id = %s THEN ru.last_name ELSE su.last_name END AS last_name,
               CASE WHEN fr.user_id = %s THEN ru.id ELSE su.id END AS person_id
        FROM family_relations fr
        JOIN users su ON su.id = fr.user_id
        JOIN users ru ON ru.id = fr.relative_id
        WHERE fr.status = 'approved' AND (fr.user_id = %s OR fr.relative_id = %s)
        ORDER BY fr.id DESC
        """,
        (int(owner_id), int(owner_id), int(owner_id), int(owner_id), int(owner_id), int(owner_id)),
    )
    out = []
    for row in cur.fetchall() or []:
        requester = int(row.get('user_id') or 0) == int(owner_id)
        show = row.get('show_user' if requester else 'show_relative')
        if show is None:
            show = 1
        if not show and (not viewer_id or int(viewer_id) != int(owner_id)):
            continue
        typ = row.get('relation_type') or 'spouse'
        out.append({
            'id': row.get('id'),
            'person_id': row.get('person_id'),
            'username': row.get('username'),
            'name': _name(row),
            'label': display_label(typ, row.get('label'), inverse=not requester),
            'page_url': url_for('church.member_page', username=row['username']) if row.get('username') else '',
            'show_on_my_page': bool(show),
        })
    return out


def is_parent_of(parent_id: int, child_id: int) -> bool:
    if not parent_id or not child_id or int(parent_id) == int(child_id):
        return False
    cur = _cur()
    cur.execute(
        """
        SELECT 1 FROM family_relations
        WHERE status = 'approved' AND (
            (user_id = %s AND relative_id = %s AND relation_type = 'child')
            OR (user_id = %s AND relative_id = %s AND relation_type = 'parent')
        )
        LIMIT 1
        """,
        (int(parent_id), int(child_id), int(child_id), int(parent_id)),
    )
    return bool(cur.fetchone())


def can_manage_child_privacy(parent_id: int, child_user: dict | None) -> bool:
    if not parent_id or not child_user:
        return False
    if is_adult(child_user):
        return False
    return is_parent_of(int(parent_id), int(child_user.get('id') or 0))


def privacy_is_locked(child_id: int) -> bool:
    from app.models.church_community import get_member_space
    from app.models.users import get_user_by_id
    space = get_member_space(int(child_id)) or {}
    locker = space.get('privacy_locked_by')
    if not locker:
        return False
    child = get_user_by_id(int(child_id)) or {}
    if is_adult(child):
        return False
    return True


def set_child_privacy(parent_id: int, child_id: int, data: dict) -> tuple[bool, str]:
    from app.models.users import get_user_by_id
    from app.models.church_community import get_member_space, create_member_space, update_member_space
    child = get_user_by_id(int(child_id))
    if not can_manage_child_privacy(parent_id, child):
        return False, 'Only a parent can set privacy for a child page.'
    if not get_member_space(int(child_id)):
        create_member_space(int(child_id))
    update_member_space(int(child_id), {
        'page_private': bool(data.get('page_private')),
        'show_to_visitors': bool(data.get('show_to_visitors')),
        'show_in_directory': bool(data.get('show_in_directory')),
        'show_family': bool(data.get('show_family')),
        'allow_messages': bool(data.get('allow_messages')),
    })
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            UPDATE member_spaces
            SET privacy_locked_by = %s, privacy_locked_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
            """,
            (int(parent_id), int(child_id)),
        )
        db.commit()
    except Exception as exc:
        print(f'privacy lock column: {exc}')
    return True, 'Saved their privacy. They cannot change it until they are 18.'
