# Volunteer scheduling: teams, skills, events, assignments, rotations, reminders.

from __future__ import annotations

import json
import secrets
from datetime import date, datetime, timedelta
from typing import Any, Optional

import pymysql

from app.models.db import get_db
from app.utils.time_utils import now_church, utc_now


def _cur():
    return get_db().cursor(pymysql.cursors.DictCursor)


def _loads(raw, default=None):
    if raw is None or raw == '':
        return default if default is not None else []
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default if default is not None else []


def _dumps(val) -> str:
    return json.dumps(val if val is not None else [], ensure_ascii=False)


def church_today() -> date:
    return now_church().date()


def church_today_str() -> str:
    return church_today().strftime('%Y-%m-%d')


# ── Settings ────────────────────────────────────────────────────────────────

def get_vol_settings() -> dict:
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT vol_reminders_enabled, vol_reminder_days_before,
                   vol_auto_notify_on_assign, church_name
            FROM settings WHERE id = 1
            """
        )
        row = cur.fetchone() or {}
    except Exception:
        row = {}
    return {
        'reminders_enabled': bool(row.get('vol_reminders_enabled', 1)),
        'reminder_days': int(row.get('vol_reminder_days_before') or 3),
        'auto_notify': bool(row.get('vol_auto_notify_on_assign', 1)),
        'church_name': row.get('church_name') or 'Church',
    }


def save_vol_settings(data: dict) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE settings SET
            vol_reminders_enabled = %s,
            vol_reminder_days_before = %s,
            vol_auto_notify_on_assign = %s
        WHERE id = 1
        """,
        (
            1 if data.get('reminders_enabled') else 0,
            int(data.get('reminder_days') or 3),
            1 if data.get('auto_notify') else 0,
        ),
    )
    db.commit()


# ── Skills ──────────────────────────────────────────────────────────────────

def list_skills(active_only=True) -> list[dict]:
    cur = _cur()
    sql = "SELECT * FROM vol_skills"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY name"
    cur.execute(sql)
    return list(cur.fetchall() or [])


def save_skill(name: str, description: str = '', skill_id: int | None = None) -> int:
    db = get_db()
    cur = db.cursor()
    name = (name or '').strip()[:120]
    if not name:
        raise ValueError('Skill name required')
    if skill_id:
        cur.execute(
            "UPDATE vol_skills SET name=%s, description=%s WHERE id=%s",
            (name, (description or '').strip()[:500] or None, skill_id),
        )
        db.commit()
        return skill_id
    cur.execute(
        "INSERT INTO vol_skills (name, description) VALUES (%s,%s)",
        (name, (description or '').strip()[:500] or None),
    )
    db.commit()
    return cur.lastrowid


def set_user_skills(user_id: int, skill_ids: list[int]) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM vol_person_skills WHERE user_id=%s", (user_id,))
    for sid in skill_ids:
        cur.execute(
            "INSERT IGNORE INTO vol_person_skills (user_id, skill_id) VALUES (%s,%s)",
            (user_id, int(sid)),
        )
    db.commit()


def get_user_skill_ids(user_id: int) -> list[int]:
    cur = _cur()
    cur.execute("SELECT skill_id FROM vol_person_skills WHERE user_id=%s", (user_id,))
    return [int(r['skill_id']) for r in (cur.fetchall() or [])]


def users_with_skill(skill_id: int) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT u.id, u.first_name, u.last_name, u.email, u.phone
        FROM vol_person_skills ps
        JOIN users u ON u.id = ps.user_id
        WHERE ps.skill_id = %s
          AND COALESCE(u.needs_approval,0)=0
          AND COALESCE(u.is_shadow_banned,0)=0
        ORDER BY u.last_name, u.first_name
        """,
        (skill_id,),
    )
    return list(cur.fetchall() or [])


# ── Teams & roles ───────────────────────────────────────────────────────────

def list_teams(active_only=True) -> list[dict]:
    cur = _cur()
    sql = """
        SELECT t.*,
               (SELECT COUNT(*) FROM vol_roles r WHERE r.team_id = t.id AND r.active=1) AS role_count,
               (SELECT COUNT(*) FROM vol_team_members m WHERE m.team_id = t.id AND m.active=1) AS member_count
        FROM vol_teams t
    """
    if active_only:
        sql += " WHERE t.active = 1"
    sql += " ORDER BY t.sort_order, t.name"
    cur.execute(sql)
    return list(cur.fetchall() or [])


def get_team(team_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute("SELECT * FROM vol_teams WHERE id=%s", (team_id,))
    return cur.fetchone()


def save_team(data: dict, team_id: int | None = None) -> int:
    db = get_db()
    cur = db.cursor()
    fields = (
        (data.get('name') or 'Team').strip()[:160],
        (data.get('description') or '').strip() or None,
        (data.get('color') or '#22d3ee')[:24],
        int(data.get('sort_order') or 0),
        1 if data.get('active', True) else 0,
    )
    if team_id:
        cur.execute(
            """
            UPDATE vol_teams SET name=%s, description=%s, color=%s, sort_order=%s, active=%s
            WHERE id=%s
            """,
            (*fields, team_id),
        )
        db.commit()
        return team_id
    cur.execute(
        """
        INSERT INTO vol_teams (name, description, color, sort_order, active)
        VALUES (%s,%s,%s,%s,%s)
        """,
        fields,
    )
    db.commit()
    return cur.lastrowid


def list_roles(team_id: int, active_only=True) -> list[dict]:
    cur = _cur()
    sql = """
        SELECT r.*, s.name AS skill_name
        FROM vol_roles r
        LEFT JOIN vol_skills s ON s.id = r.required_skill_id
        WHERE r.team_id = %s
    """
    params: list[Any] = [team_id]
    if active_only:
        sql += " AND r.active = 1"
    sql += " ORDER BY r.sort_order, r.name"
    cur.execute(sql, params)
    return list(cur.fetchall() or [])


def save_role(team_id: int, data: dict, role_id: int | None = None) -> int:
    db = get_db()
    cur = db.cursor()
    skill = data.get('required_skill_id')
    skill = int(skill) if skill not in (None, '', 0, '0') else None
    fields = (
        team_id,
        (data.get('name') or 'Role').strip()[:160],
        (data.get('description') or '').strip()[:500] or None,
        max(1, int(data.get('slots') or 1)),
        skill,
        int(data.get('sort_order') or 0),
        1 if data.get('active', True) else 0,
    )
    if role_id:
        cur.execute(
            """
            UPDATE vol_roles SET team_id=%s, name=%s, description=%s, slots=%s,
                required_skill_id=%s, sort_order=%s, active=%s
            WHERE id=%s
            """,
            (*fields, role_id),
        )
        db.commit()
        return role_id
    cur.execute(
        """
        INSERT INTO vol_roles
            (team_id, name, description, slots, required_skill_id, sort_order, active)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,
        fields,
    )
    db.commit()
    return cur.lastrowid


def list_team_members(team_id: int) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT m.*, u.first_name, u.last_name, u.email, u.phone,
               r.name AS preferred_role_name
        FROM vol_team_members m
        JOIN users u ON u.id = m.user_id
        LEFT JOIN vol_roles r ON r.id = m.preferred_role_id
        WHERE m.team_id = %s AND m.active = 1
        ORDER BY u.last_name, u.first_name
        """,
        (team_id,),
    )
    return list(cur.fetchall() or [])


def add_team_member(team_id: int, user_id: int, preferred_role_id=None, notes=None) -> int:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO vol_team_members (team_id, user_id, preferred_role_id, notes, active)
        VALUES (%s,%s,%s,%s,1)
        ON DUPLICATE KEY UPDATE active=1, preferred_role_id=VALUES(preferred_role_id), notes=VALUES(notes)
        """,
        (
            team_id,
            user_id,
            int(preferred_role_id) if preferred_role_id else None,
            (notes or '').strip()[:500] or None,
        ),
    )
    db.commit()
    rid = cur.lastrowid

    # Automation: volunteer onboarding workflows
    try:
        from app.models import communications as comm
        team_name = ''
        try:
            c2 = db.cursor(pymysql.cursors.DictCursor)
            c2.execute("SELECT name FROM vol_teams WHERE id=%s", (team_id,))
            row = c2.fetchone() or {}
            team_name = row.get('name') or 'Volunteer team'
        except Exception:
            team_name = 'Volunteer team'
        comm.fire_trigger('volunteer_onboarding', int(user_id), context={
            'source': 'team_join',
            'team_id': team_id,
            'team_name': team_name,
        })
    except Exception as auto_err:
        print(f"Automation volunteer hook: {auto_err}")

    return rid


def remove_team_member(team_id: int, user_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE vol_team_members SET active=0 WHERE team_id=%s AND user_id=%s",
        (team_id, user_id),
    )
    db.commit()


def list_members_picker(limit=500) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT id, first_name, last_name, email
        FROM users
        WHERE COALESCE(needs_approval,0)=0 AND COALESCE(is_shadow_banned,0)=0
        ORDER BY last_name, first_name
        LIMIT %s
        """,
        (limit,),
    )
    return list(cur.fetchall() or [])


# ── Events & assignments ────────────────────────────────────────────────────

def list_events(*, from_date: str | None = None, to_date: str | None = None, team_id=None, limit=60) -> list[dict]:
    cur = _cur()
    sql = """
        SELECT e.*, t.name AS team_name, t.color AS team_color,
               (SELECT COUNT(*) FROM vol_assignments a WHERE a.event_id=e.id) AS assign_count,
               (SELECT COUNT(*) FROM vol_assignments a WHERE a.event_id=e.id AND a.status='accepted') AS accepted_count,
               (SELECT COUNT(*) FROM vol_assignments a WHERE a.event_id=e.id AND a.status='pending') AS pending_count,
               (SELECT COUNT(*) FROM vol_assignments a WHERE a.event_id=e.id AND a.status='declined') AS declined_count
        FROM vol_events e
        LEFT JOIN vol_teams t ON t.id = e.team_id
        WHERE 1=1
    """
    params: list[Any] = []
    try:
        from app.models.campuses import campus_scope_sql
        frag, p = campus_scope_sql('e.campus_id')
        sql += frag
        params.extend(p)
    except Exception:
        pass
    if from_date:
        sql += " AND e.event_date >= %s"
        params.append(from_date)
    if to_date:
        sql += " AND e.event_date <= %s"
        params.append(to_date)
    if team_id:
        sql += " AND e.team_id = %s"
        params.append(int(team_id))
    sql += " ORDER BY e.event_date ASC, e.start_time ASC LIMIT %s"
    params.append(int(limit))
    cur.execute(sql, params)
    return list(cur.fetchall() or [])


def get_event(event_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT e.*, t.name AS team_name, t.color AS team_color
        FROM vol_events e
        LEFT JOIN vol_teams t ON t.id = e.team_id
        WHERE e.id = %s
        """,
        (event_id,),
    )
    return cur.fetchone()


def save_event(data: dict, event_id: int | None = None, created_by: int | None = None) -> int:
    db = get_db()
    cur = db.cursor()
    try:
        from app.models.campuses import resolve_campus_id_for_write
        campus_id = resolve_campus_id_for_write(data.get('campus_id'))
    except Exception:
        campus_id = None
    fields = (
        (data.get('title') or 'Volunteer event').strip()[:255],
        data.get('event_date') or church_today_str(),
        data.get('start_time') or None,
        data.get('end_time') or None,
        (data.get('location') or '').strip()[:255] or None,
        (data.get('notes') or '').strip() or None,
        int(data['team_id']) if data.get('team_id') else None,
        data.get('status') or 'open',
    )
    if event_id:
        try:
            cur.execute(
                """
                UPDATE vol_events SET
                    title=%s, event_date=%s, start_time=%s, end_time=%s,
                    location=%s, notes=%s, team_id=%s, status=%s, campus_id=COALESCE(%s, campus_id)
                WHERE id=%s
                """,
                (*fields, campus_id, event_id),
            )
        except Exception:
            cur.execute(
                """
                UPDATE vol_events SET
                    title=%s, event_date=%s, start_time=%s, end_time=%s,
                    location=%s, notes=%s, team_id=%s, status=%s
                WHERE id=%s
                """,
                (*fields, event_id),
            )
        db.commit()
        return event_id
    try:
        cur.execute(
            """
            INSERT INTO vol_events
                (title, event_date, start_time, end_time, location, notes, team_id, status, created_by, campus_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (*fields, created_by, campus_id),
        )
    except Exception:
        cur.execute(
            """
            INSERT INTO vol_events
                (title, event_date, start_time, end_time, location, notes, team_id, status, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (*fields, created_by),
        )
    db.commit()
    return cur.lastrowid

def delete_event(event_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM vol_events WHERE id=%s", (event_id,))
    db.commit()


def list_assignments(event_id: int) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT a.*, u.first_name, u.last_name, u.email, u.phone
        FROM vol_assignments a
        JOIN users u ON u.id = a.user_id
        WHERE a.event_id = %s
        ORDER BY a.role_name, u.last_name, u.first_name
        """,
        (event_id,),
    )
    rows = list(cur.fetchall() or [])
    for r in rows:
        r['display_name'] = f"{r.get('first_name') or ''} {r.get('last_name') or ''}".strip()
    return rows


def assign_volunteer(
    event_id: int,
    user_id: int,
    role_name: str,
    *,
    role_id: int | None = None,
    assigned_by: int | None = None,
    notify: bool | None = None,
) -> dict:
    """Create pending assignment; optionally email invite."""
    event = get_event(event_id)
    if not event:
        raise ValueError('Event not found')
    role_name = (role_name or 'Volunteer').strip()[:160]
    token = secrets.token_urlsafe(24)
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO vol_assignments
                (event_id, role_id, role_name, user_id, status, response_token, assigned_by)
            VALUES (%s,%s,%s,%s,'pending',%s,%s)
            """,
            (event_id, role_id, role_name, user_id, token, assigned_by),
        )
        db.commit()
        aid = cur.lastrowid
    except Exception as e:
        db.rollback()
        # Already assigned same role?
        cur.execute(
            """
            SELECT id FROM vol_assignments
            WHERE event_id=%s AND user_id=%s AND role_name=%s
            """,
            (event_id, user_id, role_name),
        )
        existing = cur.fetchone()
        if existing:
            return get_assignment(existing[0] if not isinstance(existing, dict) else existing['id'])
        raise ValueError(str(e)[:200])

    assignment = get_assignment(aid)
    settings = get_vol_settings()
    should_notify = settings['auto_notify'] if notify is None else notify
    if should_notify:
        try:
            notify_assignment(assignment, kind='invite')
        except Exception as e:
            print(f"Volunteer notify failed: {e}")
    return assignment


def get_assignment(assignment_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT a.*, u.first_name, u.last_name, u.email, u.phone,
               e.title AS event_title, e.event_date, e.start_time, e.end_time,
               e.location AS event_location, e.team_id,
               t.name AS team_name
        FROM vol_assignments a
        JOIN users u ON u.id = a.user_id
        JOIN vol_events e ON e.id = a.event_id
        LEFT JOIN vol_teams t ON t.id = e.team_id
        WHERE a.id = %s
        """,
        (assignment_id,),
    )
    row = cur.fetchone()
    if row:
        row['display_name'] = f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip()
    return row


def get_assignment_by_token(token: str) -> Optional[dict]:
    if not token:
        return None
    cur = _cur()
    cur.execute("SELECT id FROM vol_assignments WHERE response_token=%s", (token,))
    row = cur.fetchone()
    if not row:
        return None
    return get_assignment(int(row['id']))


def respond_assignment(token: str, accept: bool, note: str = '') -> dict:
    a = get_assignment_by_token(token)
    if not a:
        raise ValueError('Invalid or expired response link.')
    if a['status'] in ('accepted', 'declined') and a.get('responded_at'):
        return a  # already responded
    status = 'accepted' if accept else 'declined'
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE vol_assignments
        SET status=%s, response_note=%s, responded_at=%s
        WHERE id=%s
        """,
        (status, (note or '').strip()[:500] or None, utc_now(), a['id']),
    )
    db.commit()
    return get_assignment(a['id'])


def remove_assignment(assignment_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM vol_assignments WHERE id=%s", (assignment_id,))
    db.commit()


def suggest_for_role(team_id: int, role: dict) -> list[dict]:
    """Suggest team members, preferring those with required skill."""
    members = list_team_members(team_id)
    skill_id = role.get('required_skill_id')
    if not skill_id:
        return members
    skilled = {u['id'] for u in users_with_skill(int(skill_id))}
    preferred = [m for m in members if m['user_id'] in skilled]
    others = [m for m in members if m['user_id'] not in skilled]
    for m in preferred:
        m['skill_match'] = True
    for m in others:
        m['skill_match'] = False
    return preferred + others


# ── Rotations ───────────────────────────────────────────────────────────────

def list_rotations(team_id: int | None = None) -> list[dict]:
    cur = _cur()
    sql = """
        SELECT r.*, t.name AS team_name
        FROM vol_rotations r
        JOIN vol_teams t ON t.id = r.team_id
        WHERE 1=1
    """
    params: list[Any] = []
    if team_id:
        sql += " AND r.team_id = %s"
        params.append(int(team_id))
    sql += " ORDER BY t.name, r.name"
    cur.execute(sql, params)
    rows = list(cur.fetchall() or [])
    for r in rows:
        r['member_ids'] = _loads(r.get('member_ids_json'), [])
    return rows


def get_rotation(rotation_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT r.*, t.name AS team_name
        FROM vol_rotations r
        JOIN vol_teams t ON t.id = r.team_id
        WHERE r.id = %s
        """,
        (rotation_id,),
    )
    row = cur.fetchone()
    if row:
        row['member_ids'] = _loads(row.get('member_ids_json'), [])
    return row


def save_rotation(data: dict, rotation_id: int | None = None) -> int:
    db = get_db()
    cur = db.cursor()
    member_ids = data.get('member_ids') or []
    member_ids = [int(x) for x in member_ids]
    fields = (
        int(data['team_id']),
        int(data['role_id']) if data.get('role_id') else None,
        (data.get('role_name') or 'Volunteer').strip()[:160],
        (data.get('name') or 'Rotation').strip()[:160],
        data.get('frequency') or 'weekly',
        _dumps(member_ids),
        int(data.get('cursor_index') or 0),
        1 if data.get('active', True) else 0,
        (data.get('notes') or '').strip()[:500] or None,
    )
    if not member_ids:
        raise ValueError('Add at least one person to the rotation.')
    if rotation_id:
        cur.execute(
            """
            UPDATE vol_rotations SET
                team_id=%s, role_id=%s, role_name=%s, name=%s, frequency=%s,
                member_ids_json=%s, cursor_index=%s, active=%s, notes=%s
            WHERE id=%s
            """,
            (*fields, rotation_id),
        )
        db.commit()
        return rotation_id
    cur.execute(
        """
        INSERT INTO vol_rotations
            (team_id, role_id, role_name, name, frequency, member_ids_json, cursor_index, active, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        fields,
    )
    db.commit()
    return cur.lastrowid


def delete_rotation(rotation_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM vol_rotations WHERE id=%s", (rotation_id,))
    db.commit()


def apply_rotation_to_event(rotation_id: int, event_id: int, *, assigned_by=None, slots: int | None = None) -> list[dict]:
    """
    Assign next N people from rotation (round-robin), advance cursor.
    """
    rot = get_rotation(rotation_id)
    if not rot or not rot.get('active'):
        raise ValueError('Rotation not found or inactive')
    members = rot['member_ids']
    if not members:
        raise ValueError('Rotation has no members')
    n = slots if slots is not None else 1
    n = max(1, int(n))
    cursor = int(rot.get('cursor_index') or 0) % len(members)
    created = []
    for i in range(n):
        uid = members[(cursor + i) % len(members)]
        try:
            a = assign_volunteer(
                event_id,
                uid,
                rot['role_name'],
                role_id=rot.get('role_id'),
                assigned_by=assigned_by,
            )
            created.append(a)
        except Exception as e:
            print(f"Rotation assign skip {uid}: {e}")
    new_cursor = (cursor + n) % len(members)
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE vol_rotations SET cursor_index=%s WHERE id=%s", (new_cursor, rotation_id))
    db.commit()
    return created


def fill_event_from_team_rotations(event_id: int, team_id: int, assigned_by=None) -> int:
    """Apply all active rotations for a team to an event (1 slot each, or role slots)."""
    roles = {r['id']: r for r in list_roles(team_id)}
    rots = list_rotations(team_id)
    count = 0
    for rot in rots:
        if not rot.get('active'):
            continue
        slots = 1
        if rot.get('role_id') and rot['role_id'] in roles:
            slots = int(roles[rot['role_id']].get('slots') or 1)
        created = apply_rotation_to_event(rot['id'], event_id, assigned_by=assigned_by, slots=slots)
        count += len(created)
    return count


# ── Notifications & reminders ───────────────────────────────────────────────

def _format_event_when(event: dict) -> str:
    d = event.get('event_date')
    if hasattr(d, 'strftime'):
        ds = d.strftime('%A, %B %d, %Y')
    else:
        ds = str(d)
    t = event.get('start_time')
    if t:
        if hasattr(t, 'strftime'):
            ts = t.strftime('%I:%M %p')
        else:
            ts = str(t)[:5]
        return f"{ds} at {ts}"
    return ds


def notify_assignment(assignment: dict, kind: str = 'invite') -> bool:
    """Email volunteer invite / reminder / confirmation."""
    email = (assignment.get('email') or '').strip()
    if not email:
        return False
    settings = get_vol_settings()
    church = settings['church_name']
    name = assignment.get('display_name') or assignment.get('first_name') or 'Friend'
    when = _format_event_when(assignment)
    role = assignment.get('role_name') or 'Volunteer'
    title = assignment.get('event_title') or 'Serving opportunity'
    location = assignment.get('event_location') or ''
    token = assignment.get('response_token')

    try:
        from app.utils.email_notifications import external_url
        accept_url = external_url('volunteers.respond', token=token, action='accept')
        decline_url = external_url('volunteers.respond', token=token, action='decline')
        my_url = external_url('volunteers.my_schedule')
    except Exception:
        accept_url = decline_url = my_url = ''

    if kind == 'reminder':
        subject = f"Reminder: serving as {role} — {title}"
        intro = f"Hi {name},\n\nThis is a friendly reminder that you're scheduled to serve."
    elif kind == 'accepted':
        subject = f"Confirmed: {role} — {title}"
        intro = f"Hi {name},\n\nThank you for accepting! You're confirmed to serve."
    else:
        subject = f"Can you serve as {role}? — {title}"
        intro = f"Hi {name},\n\nYou've been asked to serve with {church}."

    body = (
        f"{intro}\n\n"
        f"Event: {title}\n"
        f"When: {when}\n"
        f"Role: {role}\n"
        f"{('Location: ' + location + chr(10)) if location else ''}"
        f"{('Team: ' + (assignment.get('team_name') or '') + chr(10)) if assignment.get('team_name') else ''}\n"
    )
    if kind != 'accepted' and assignment.get('status') == 'pending':
        body += (
            f"Please respond:\n"
            f"  Accept:  {accept_url}\n"
            f"  Decline: {decline_url}\n\n"
        )
    body += f"View your schedule: {my_url}\n\n— {church}"

    try:
        from app.utils.emailer import send_email
        send_email(email, subject, body)
        return True
    except Exception as e:
        print(f"Volunteer email failed to {email}: {e}")
        return False


def send_pending_reminders() -> int:
    """Email reminders for pending/accepted assignments within reminder window."""
    settings = get_vol_settings()
    if not settings['reminders_enabled']:
        return 0
    days = settings['reminder_days']
    today = church_today()
    target = today + timedelta(days=days)
    cur = _cur()
    cur.execute(
        """
        SELECT a.id
        FROM vol_assignments a
        JOIN vol_events e ON e.id = a.event_id
        WHERE e.event_date = %s
          AND a.status IN ('pending', 'accepted')
          AND a.reminded_at IS NULL
        """,
        (target.strftime('%Y-%m-%d'),),
    )
    rows = cur.fetchall() or []
    sent = 0
    db = get_db()
    for r in rows:
        a = get_assignment(int(r['id']))
        if not a:
            continue
        if notify_assignment(a, kind='reminder'):
            c2 = db.cursor()
            c2.execute("UPDATE vol_assignments SET reminded_at=%s WHERE id=%s", (utc_now(), a['id']))
            db.commit()
            sent += 1
    return sent


# ── My schedule & dashboard ─────────────────────────────────────────────────

def my_assignments(user_id: int, *, upcoming_only=True, limit=50) -> list[dict]:
    cur = _cur()
    sql = """
        SELECT a.*, e.title AS event_title, e.event_date, e.start_time, e.end_time,
               e.location AS event_location, t.name AS team_name, t.color AS team_color
        FROM vol_assignments a
        JOIN vol_events e ON e.id = a.event_id
        LEFT JOIN vol_teams t ON t.id = e.team_id
        WHERE a.user_id = %s
    """
    params: list[Any] = [user_id]
    if upcoming_only:
        sql += " AND e.event_date >= %s"
        params.append(church_today_str())
    sql += " ORDER BY e.event_date ASC, e.start_time ASC LIMIT %s"
    params.append(int(limit))
    cur.execute(sql, params)
    rows = list(cur.fetchall() or [])
    for r in rows:
        r['display_name'] = f"{r.get('first_name') or ''}"
    return rows


def dashboard_stats() -> dict:
    cur = _cur()
    today = church_today_str()
    stats = {'date': today}
    queries = {
        'teams': "SELECT COUNT(*) AS n FROM vol_teams WHERE active=1",
        'upcoming_events': f"SELECT COUNT(*) AS n FROM vol_events WHERE event_date >= '{today}' AND status='open'",
        'pending': "SELECT COUNT(*) AS n FROM vol_assignments a JOIN vol_events e ON e.id=a.event_id WHERE a.status='pending' AND e.event_date >= CURDATE()",
        'accepted_week': """
            SELECT COUNT(*) AS n FROM vol_assignments a
            JOIN vol_events e ON e.id=a.event_id
            WHERE a.status='accepted'
              AND e.event_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)
        """,
        'rotations': "SELECT COUNT(*) AS n FROM vol_rotations WHERE active=1",
    }
    for k, sql in queries.items():
        try:
            cur.execute(sql)
            stats[k] = int((cur.fetchone() or {}).get('n') or 0)
        except Exception:
            stats[k] = 0
    return stats
