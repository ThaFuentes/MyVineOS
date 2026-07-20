# app/models/pastoral/service_plans.py
# Full path: WebChurchMan/app/models/pastoral/service_plans.py
# File name: service_plans.py
# Brief, detailed purpose:
#   All database operations related to Service Planning module - FULL REBUILD for permanent recurring templates + forced notes + override count.
#   NEW SIMPLE & CLEAN STRUCTURE:
#     - service_templates: Central permanent recurring masters (Sunday Morning, Wednesday Night, etc.)
#       - One row per recurring service type
#       - No service_date - applies to all matching weekdays unless overridden
#       - Title, notes (regular Quill HTML), forced_notes (critical plain text lines), times, linked sermon, role assignments
#       - Change once -> instantly affects every future display of that weekday
#     - service_plans: Individual dated overrides/special events only (much fewer rows)
#     - get_plan_for_date(date_str): Returns dated override if exists, ELSE matching template
#       - For template plans: forced_notes prepended to notes (as highlighted HTML block)
#     - Templates matched by weekday (0-6) only - simple, no complex recurrence rules
#     - Global defaults still exist - pre-fill when creating new templates or dated overrides
#     - Removed old 52-week seeding - now seeds one default Sunday template if none exists
#     - get_upcoming_service(): Safe wrapper using get_plan_for_date for next date (plan or template)
#     - get_all_templates(): Now includes override_count (future dated plans on this weekday)
#   This gives true "central place - change once, updates all" for recurring services.
#   Overrides still possible via dated plans.
#   Delete template anytime.
#   Uses DictCursor for consistent dict results.
#   Parameterized queries for MariaDB / PyMySQL safety.

import re
import pymysql
from datetime import datetime, time, timedelta

from app.models.db import get_db

WEEKDAY_NAMES = [
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
]


def _normalize_time(value):
    """Normalize TIME values from DB (handles timedelta edge cases from PyMySQL)."""
    if value is None:
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, timedelta):
        total_seconds = value.days * 86400 + value.seconds
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return time(hours % 24, minutes)
    return value


# ----------------------------------------------------------------------
# Templates - Central permanent recurring masters (one canonical per weekday)
# ----------------------------------------------------------------------
def _hydrate_template_row(template: dict) -> dict:
    """Attach normalized times and role assignments to a template row."""
    template['start_time'] = _normalize_time(template.get('start_time'))
    template['worship_start_time'] = _normalize_time(template.get('worship_start_time'))
    template['assignments'] = get_template_assignments(template['id'])
    return template


def get_template_for_weekday(weekday: int, exclude_id: int | None = None):
    """
    Return the canonical master template for a weekday.
    When duplicates exist, the oldest row (lowest id) wins.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    sql = """
        SELECT st.*,
               CONCAT(u.first_name, ' ', u.last_name) AS creator_name,
               ps.title AS linked_sermon_title
        FROM service_templates st
        LEFT JOIN users u ON st.created_by = u.id
        LEFT JOIN pastoral_sermons ps ON st.pastoral_sermon_id = ps.id
        WHERE st.weekday = %s
    """
    params: list = [weekday]
    if exclude_id:
        sql += " AND st.id != %s"
        params.append(exclude_id)
    sql += " ORDER BY st.id ASC LIMIT 1"
    cur.execute(sql, params)
    row = cur.fetchone()
    return _hydrate_template_row(row) if row else None


def dedupe_service_templates():
    """
    Remove duplicate master templates for the same weekday.
    Keeps the oldest template (lowest id) per weekday.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT weekday, GROUP_CONCAT(id ORDER BY id) AS id_list, COUNT(*) AS cnt
        FROM service_templates
        GROUP BY weekday
        HAVING cnt > 1
    """)
    removed = 0
    for row in cur.fetchall():
        ids = [int(x) for x in (row['id_list'] or '').split(',') if x]
        for dup_id in ids[1:]:
            delete_template(dup_id)
            removed += 1
    if removed:
        print(f"Removed {removed} duplicate service template(s) - one master per weekday.")
    return removed


def _assignment_display_name(assignment: dict) -> str | None:
    """Prefer member name; fall back to free-text guest_name for guest speakers."""
    name = (assignment.get('user_full_name') or '').strip()
    if name:
        return name
    guest = (assignment.get('guest_name') or '').strip()
    return guest or None


def _extract_preacher(plan: dict):
    """Return the assigned preacher/pastor/speaker name from a plan or template.
    Supports guest speakers via guest_name when no member user is selected.
    """
    for a in plan.get('assignments', []) or []:
        role = (a.get('role_name') or '').lower().strip()
        if role in ('preacher', 'pastor', 'speaker', 'guest speaker', 'guest preacher'):
            name = _assignment_display_name(a)
            if name:
                return name
    return None


def _public_notes_html(plan: dict) -> str:
    """Order-of-service notes for guest pages (HTML from Quill). Empty if none."""
    raw = (plan.get('notes') or '').strip()
    if not raw:
        return ''
    # Drop empty Quill shells
    plain = re.sub(r'<[^>]+>', '', raw).replace('\xa0', ' ').strip()
    if not plain:
        return ''
    return raw


def _effective_service_title(plan: dict) -> str:
    """Display title: dated override label, else master template title for that weekday."""
    custom = (plan.get('title') or '').strip()
    if custom:
        return custom
    service_date = plan.get('service_date')
    if service_date is not None:
        weekday = service_date.weekday() if hasattr(service_date, 'weekday') else None
        if weekday is not None:
            template = get_template_for_weekday(weekday)
            if template and template.get('title'):
                return template['title']
    return plan.get('title') or 'Service'


def _plan_to_public_service(plan: dict, *, is_recurring: bool = False) -> dict:
    """Normalize a plan dict for guest-facing schedule cards."""
    service_date = plan.get('service_date')
    weekday = service_date.weekday() if service_date is not None and hasattr(service_date, 'weekday') else plan.get('weekday')
    # Role list for public (Preacher + other filled roles)
    public_roles = []
    for a in plan.get('assignments', []) or []:
        name = _assignment_display_name(a)
        role = (a.get('role_name') or '').strip()
        if name and role:
            public_roles.append({'role_name': role, 'name': name})
    return {
        'weekday': weekday,
        'title': _effective_service_title(plan),
        'weekday_name': WEEKDAY_NAMES[weekday] if weekday is not None else None,
        'start_time': _format_display_time(plan.get('start_time')),
        'worship_start_time': _format_display_time(plan.get('worship_start_time')),
        'preacher': _extract_preacher(plan),
        'notes': _public_notes_html(plan),
        'roles': public_roles,
        'is_recurring': is_recurring,
        'is_override': plan.get('source') == 'override' or (
            plan.get('id') is not None and plan.get('source') != 'template'
        ),
        'service_date': service_date,
    }


def get_weekly_schedule_display():
    """
    Public-facing recurring schedule: exactly one entry per weekday that has a template.
    Sorted with Sunday first, then Monday-Saturday.
    """
    display_order = [6, 0, 1, 2, 3, 4, 5]
    schedule = []
    for weekday in display_order:
        template = get_template_for_weekday(weekday)
        if not template:
            continue
        entry = _plan_to_public_service(template, is_recurring=True)
        entry['weekday'] = weekday
        entry['weekday_name'] = WEEKDAY_NAMES[weekday]
        schedule.append(entry)
    return schedule


def get_upcoming_services_display(limit: int = 2, days_ahead: int = 90):
    """
    Guest-facing upcoming service dates using effective plans (override + template fallback).
    Includes filled roles (members + guests) and order-of-service notes — same as homepage.

    Weekly overrides (Edit Plan) are authoritative: only people saved on that week show.
    Non-override weeks soft-fill from overall defaults / worship.
    """
    today = datetime.today().date()
    services = []
    for offset in range(days_ahead):
        check_date = today + timedelta(days=offset)
        date_str = check_date.strftime('%Y-%m-%d')
        plan = get_plan_for_date(date_str)
        if not plan:
            continue
        plan = dict(plan)
        # Strict: only people on this plan (override or recurring template) — never overall defaults
        try:
            plan['assignments'] = build_full_service_assignments(
                plan.get('assignments') or [],
                date_str=date_str,
                apply_fallbacks=False,
            )
        except Exception as exc:
            print(f'get_upcoming_services_display enrich: {exc}')
        entry = _plan_to_public_service(plan)
        entry['date_label'] = check_date.strftime('%A, %B %d, %Y')
        entry['date_str'] = date_str
        services.append(entry)
        if len(services) >= limit:
            break
    return services


def _format_display_time(value):
    if value is None:
        return None
    if hasattr(value, 'strftime'):
        return value.strftime('%I:%M %p').lstrip('0')
    return str(value)


def get_all_templates():
    """Fetch all permanent recurring templates with override_count (future dated overrides on weekday)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    today_str = datetime.today().strftime('%Y-%m-%d')
    cur.execute("""
        SELECT st.*,
               CONCAT(u.first_name, ' ', u.last_name) AS creator_name,
               COUNT(sp.service_date) AS override_count
        FROM service_templates st
        INNER JOIN (
            SELECT weekday, MIN(id) AS canon_id
            FROM service_templates
            GROUP BY weekday
        ) canon ON st.id = canon.canon_id
        LEFT JOIN users u ON st.created_by = u.id
        LEFT JOIN service_plans sp
               ON sp.service_date >= %s
               AND WEEKDAY(sp.service_date) = st.weekday
        GROUP BY st.id
        ORDER BY FIELD(st.weekday, 6, 0, 1, 2, 3, 4, 5), st.start_time
    """, (today_str,))
    templates = cur.fetchall()
    for t in templates:
        t['start_time'] = _normalize_time(t['start_time'])
        t['worship_start_time'] = _normalize_time(t['worship_start_time'])
        t['assignments'] = get_template_assignments(t['id'])
        t['override_count'] = t.get('override_count', 0)  # safety
    return templates


def get_template_by_id(template_id: int):
    """Fetch a single template with assignments."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT st.*,
               CONCAT(u.first_name, ' ', u.last_name) AS creator_name
        FROM service_templates st
        LEFT JOIN users u ON st.created_by = u.id
        WHERE st.id = %s
    """, (template_id,))
    template = cur.fetchone()
    if template:
        template['start_time'] = _normalize_time(template['start_time'])
        template['worship_start_time'] = _normalize_time(template['worship_start_time'])
        template['assignments'] = get_template_assignments(template_id)
    return template


def create_or_update_template(data: dict, user_id: int):
    """Upsert a permanent recurring template (including forced_notes)."""
    db = get_db()
    cur = db.cursor()
    template_id = data.get('id')

    forced_notes = data.get('forced_notes', '').strip()

    weekday = data.get('weekday')
    if weekday is not None and template_id is None:
        existing = get_template_for_weekday(int(weekday))
        if existing:
            raise ValueError(
                f"A master template already exists for {WEEKDAY_NAMES[int(weekday)]}. "
                "Edit the existing template or create a dated override for a specific week."
            )

    if template_id:
        cur.execute("""
            UPDATE service_templates
            SET title = %s, notes = %s, forced_notes = %s,
                start_time = %s, worship_start_time = %s,
                pastoral_sermon_id = %s, weekday = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (data['title'], data.get('notes'), forced_notes,
              data.get('start_time'), data.get('worship_start_time'),
              data.get('pastoral_sermon_id'), data['weekday'], template_id))
    else:
        cur.execute("""
            INSERT INTO service_templates
            (title, notes, forced_notes, start_time, worship_start_time,
             pastoral_sermon_id, weekday, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (data['title'], data.get('notes'), forced_notes,
              data.get('start_time'), data.get('worship_start_time'),
              data.get('pastoral_sermon_id'), data['weekday'], user_id))
        template_id = cur.lastrowid

    # Only replace assignments when explicitly provided (never wipe on partial update)
    if 'assignments' in data:
        save_template_assignments(template_id, data.get('assignments') or [])
    db.commit()
    return template_id


def delete_template(template_id: int):
    """Delete a permanent recurring template and its assignments."""
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM service_template_assignments WHERE template_id = %s", (template_id,))
    cur.execute("DELETE FROM service_templates WHERE id = %s", (template_id,))
    db.commit()


def get_template_assignments(template_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT sta.role_name, sta.user_id, sta.guest_name,
               CONCAT(u.first_name, ' ', u.last_name) AS user_full_name
        FROM service_template_assignments sta
        LEFT JOIN users u ON sta.user_id = u.id
        WHERE sta.template_id = %s
        ORDER BY sta.role_name
    """, (template_id,))
    return cur.fetchall()


def save_template_assignments(template_id: int, assignments: list):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM service_template_assignments WHERE template_id = %s", (template_id,))
    for a in assignments:
        if a['role_name'].strip():
            uid = a.get('user_id') or None
            if uid in ('', 'None'):
                uid = None
            guest = (a.get('guest_name') or '').strip() or None
            if uid:
                guest = None
            cur.execute("""
                INSERT INTO service_template_assignments (template_id, role_name, user_id, guest_name)
                VALUES (%s, %s, %s, %s)
            """, (template_id, a['role_name'], uid, guest))
    db.commit()


# ----------------------------------------------------------------------
# Dated Plans - Overrides / special events only
# ----------------------------------------------------------------------
def get_all_service_plans():
    """Fetch all dated override/special plans (for list view)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT sp.*, CONCAT(u.first_name, ' ', u.last_name) AS creator_name,
               ps.title AS linked_sermon_title
        FROM service_plans sp
        JOIN users u ON sp.created_by = u.id
        LEFT JOIN pastoral_sermons ps ON sp.pastoral_sermon_id = ps.id
        ORDER BY sp.service_date DESC
    """)
    plans = cur.fetchall()
    for p in plans:
        p['start_time'] = _normalize_time(p['start_time'])
        p['worship_start_time'] = _normalize_time(p['worship_start_time'])
        p['assignments'] = get_service_plan_assignments(p['id'])
    return plans


def get_service_plan_by_date(service_date: str):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT sp.*, 'override' AS source,
               CONCAT(u.first_name, ' ', u.last_name) AS creator_name,
               ps.title AS linked_sermon_title
        FROM service_plans sp
        JOIN users u ON sp.created_by = u.id
        LEFT JOIN pastoral_sermons ps ON sp.pastoral_sermon_id = ps.id
        WHERE sp.service_date = %s
    """, (service_date,))
    plan = cur.fetchone()
    if plan:
        plan['start_time'] = _normalize_time(plan['start_time'])
        plan['worship_start_time'] = _normalize_time(plan['worship_start_time'])
        plan['assignments'] = get_service_plan_assignments(plan['id'])
    return plan


def create_or_update_service_plan(data: dict, user_id: int):
    db = get_db()
    cur = db.cursor()
    service_date = data['service_date']

    existing = get_service_plan_by_date(service_date)
    if existing:
        cur.execute("""
            UPDATE service_plans
            SET title = %s, notes = %s, pastoral_sermon_id = %s,
                start_time = %s, worship_start_time = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE service_date = %s
        """, (data.get('title'), data.get('notes'), data.get('pastoral_sermon_id'),
              data.get('start_time'), data.get('worship_start_time'), service_date))
        plan_id = existing['id']
    else:
        cur.execute("""
            INSERT INTO service_plans
            (service_date, title, notes, pastoral_sermon_id, created_by,
             start_time, worship_start_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (service_date, data.get('title'), data.get('notes'),
              data.get('pastoral_sermon_id'), user_id,
              data.get('start_time'), data.get('worship_start_time')))
        plan_id = cur.lastrowid

    # Only replace assignments when explicitly provided (never wipe on partial update)
    if 'assignments' in data:
        save_service_plan_assignments(plan_id, data.get('assignments') or [])
    db.commit()
    return plan_id


def get_service_plan_assignments(plan_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT spa.role_name, spa.user_id, spa.guest_name,
               CONCAT(u.first_name, ' ', u.last_name) AS user_full_name
        FROM service_plan_assignments spa
        LEFT JOIN users u ON spa.user_id = u.id
        WHERE spa.service_plan_id = %s
        ORDER BY spa.role_name
    """, (plan_id,))
    return cur.fetchall()


def save_service_plan_assignments(plan_id: int, assignments: list):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM service_plan_assignments WHERE service_plan_id = %s", (plan_id,))
    for a in assignments:
        if a['role_name'].strip():
            uid = a.get('user_id') or None
            if uid in ('', 'None'):
                uid = None
            guest = (a.get('guest_name') or '').strip() or None
            # If a member is selected, clear guest name (member takes precedence)
            if uid:
                guest = None
            cur.execute("""
                INSERT INTO service_plan_assignments (service_plan_id, role_name, user_id, guest_name)
                VALUES (%s, %s, %s, %s)
            """, (plan_id, a['role_name'], uid, guest))
    db.commit()


# ----------------------------------------------------------------------
# Unified Plan Retrieval - Prepend forced_notes for template plans
# ----------------------------------------------------------------------
def get_plan_for_date(date_str: str):
    """
    Return the effective plan for a date.

    Hierarchy (strict):
      1. Dated week override — full authority for that date
      2. Recurring weekday template — people + times + notes for that day
         (template people only; overall defaults never auto-fill)
      3. None — no service that day (service days = templates only)
    """
    # 1. Dated override
    plan = get_service_plan_by_date(date_str)
    if plan:
        return plan

    # 2. Only days that have a weekday template (e.g. Sunday only)
    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    weekday = date_obj.weekday()  # 0=Monday ... 6=Sunday

    template = get_template_for_weekday(weekday)
    if not template:
        return None

    template = dict(template)
    template['source'] = 'template'
    template['service_date'] = date_obj
    # Keep template['assignments'] as loaded by get_template_for_weekday /
    # get_template_by_id — overall defaults must NOT replace them.

    forced = template.get('forced_notes', '').strip()
    regular = template.get('notes') or ''
    if forced:
        forced_html = '<div class="forced-notes bg-danger text-white p-3 mb-4 rounded"><strong>CRITICAL NOTES:</strong><br>' + \
                      forced.replace('\n', '<br>') + '</div>'
        template['notes'] = forced_html + regular
    else:
        template['notes'] = regular

    return template


# ----------------------------------------------------------------------
# get_upcoming_service - Safe for migration
# ----------------------------------------------------------------------
def get_upcoming_service():
    """Return the next upcoming service (plan or template fallback). Safe during schema migration.
    Includes filled_roles (role_name + name) for dashboard display.
    """
    today = datetime.today().date()
    plan = None
    date_str = None

    # First: next dated plan >= today
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute("""
            SELECT service_date
            FROM service_plans
            WHERE service_date >= %s
            ORDER BY service_date ASC
            LIMIT 1
        """, (today,))
        row = cur.fetchone()
        if row:
            sd = row['service_date']
            date_str = sd.strftime('%Y-%m-%d') if hasattr(sd, 'strftime') else str(sd)[:10]
            plan = get_plan_for_date(date_str)
    except pymysql.err.ProgrammingError as e:
        if "doesn't exist" in str(e):
            print("service_plans table not created yet - using template fallback only.")
        else:
            raise

    # No dated plan - find next date with template
    if not plan:
        for days_ahead in range(0, 30):
            check_date = today + timedelta(days=days_ahead)
            date_str = check_date.strftime('%Y-%m-%d')
            plan = get_plan_for_date(date_str)
            if plan:
                break

    if not plan:
        # Ultimate fallback (no templates yet)
        plan = {
            'service_date': today + timedelta(days=((6 - today.weekday()) % 7) or 7),  # next Sunday
            'title': 'Regular Service',
            'notes': '',
            'start_time': time(10, 0),
            'worship_start_time': time(10, 15),
            'assignments': [],
            'source': 'fallback',
            'filled_roles': [],
            'date_str': (today + timedelta(days=((6 - today.weekday()) % 7) or 7)).strftime('%Y-%m-%d'),
        }
        return plan

    plan = dict(plan)
    if not date_str:
        sd = plan.get('service_date')
        date_str = sd.strftime('%Y-%m-%d') if hasattr(sd, 'strftime') else str(sd or '')[:10]
    plan['date_str'] = date_str
    # Strict: only people on this plan (override or recurring template)
    try:
        plan['assignments'] = build_full_service_assignments(
            plan.get('assignments') or [],
            date_str=date_str,
            apply_fallbacks=False,
        )
    except Exception as exc:
        print(f'get_upcoming_service enrich: {exc}')
    filled = []
    for a in plan.get('assignments') or []:
        name = _assignment_display_name(a)
        role = (a.get('role_name') or '').strip()
        if name and role:
            filled.append({'role_name': role, 'name': name})
    plan['filled_roles'] = filled
    return plan


# Cohesive service roles: pastoral + volunteer Teams + worship defaults
SERVICE_VOLUNTEER_TEAM_ROLES = [
    'Greeters',
    'Ushers',
    'Parking',
    'Kids Check-In',
    'Hospitality',
    'Tech / Media',
    'Prayer Team',
]

# Worship module default role names (app/routes/worship/utils.py DEFAULT_ROLES)
SERVICE_WORSHIP_ROLES = [
    'Worship Leader', 'Vocals', 'Guitar', 'Bass', 'Keys', 'Drums', 'Sound', 'Slides',
]

SERVICE_CORE_ROLES = [
    'Preacher',
]


def ensure_default_assignment_schema():
    """
    Make sure default_service_plan_assignments exists and has guest_name.
    Prevents 500s on older DBs that never ran the guest_name migration.
    """
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS default_service_plan_assignments (
                id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                role_name VARCHAR(191) NOT NULL,
                user_id INT UNSIGNED NULL,
                guest_name VARCHAR(191) NULL,
                UNIQUE KEY uniq_default_role (role_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        db.commit()
    except Exception as exc:
        print(f'default_service_plan_assignments create: {exc}')
        try:
            db.rollback()
        except Exception:
            pass
    try:
        cur.execute("""
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'default_service_plan_assignments'
              AND COLUMN_NAME = 'guest_name'
        """)
        if not cur.fetchone():
            cur.execute(
                "ALTER TABLE default_service_plan_assignments "
                "ADD COLUMN guest_name VARCHAR(191) NULL AFTER user_id"
            )
            db.commit()
    except Exception as exc:
        print(f'default_service_plan_assignments guest_name: {exc}')
        try:
            db.rollback()
        except Exception:
            pass


def get_volunteer_team_role_names() -> list[str]:
    """Live team names from Volunteers module when available; else static defaults."""
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute("""
            SELECT name FROM vol_teams
            WHERE COALESCE(active, 1) = 1
            ORDER BY sort_order, name
        """)
        rows = cur.fetchall() or []
        names = [(r.get('name') or '').strip() for r in rows if (r.get('name') or '').strip()]
        if names:
            return names
    except Exception:
        pass
    return list(SERVICE_VOLUNTEER_TEAM_ROLES)


def get_worship_default_assignments() -> list[dict]:
    """
    Role assignments from Worship Team → Default Roles
    (worship_default_assignments). Used so pastoral planning mirrors worship.
    """
    try:
        from app.models.worship import setlists as worship_setlists
        rows = worship_setlists.get_default_assignments() or []
        out = []
        for r in rows:
            role = (r.get('role_name') or '').strip()
            if not role:
                continue
            uid = r.get('user_id')
            try:
                uid = int(uid) if uid not in (None, '', 'None') else None
            except (TypeError, ValueError):
                uid = None
            guest = (r.get('guest_name') or '').strip() or None
            full = r.get('user_full_name') or guest
            out.append({
                'role_name': role,
                'user_id': uid,
                'guest_name': guest if not uid else None,
                'user_full_name': full,
                'source': 'worship',
            })
        return out
    except Exception as exc:
        print(f'get_worship_default_assignments: {exc}')
        return []


def get_primary_worship_leader_user_id() -> int | None:
    """Prefer Worship Team group leader; fall back to first worship default WL."""
    try:
        from app.models.worship.shared import get_worship_leaders
        leaders = get_worship_leaders() or []
        for L in leaders:
            if (L.get('role_in_group') or '') == 'leader' and L.get('id'):
                return int(L['id'])
        if leaders and leaders[0].get('id'):
            return int(leaders[0]['id'])
    except Exception as exc:
        print(f'get_primary_worship_leader_user_id: {exc}')
    for w in get_worship_default_assignments():
        if (w.get('role_name') or '').strip().lower() == 'worship leader' and w.get('user_id'):
            return int(w['user_id'])
    return None


def cohesive_service_role_names() -> list[str]:
    """
    Full Sunday roster role list, always in a stable order:
      Preacher → Worship Leader + band → Volunteer teams → any extra custom roles later
    Every volunteer team and every worship default role is included even if unassigned.
    """
    core = list(SERVICE_CORE_ROLES)
    seen = {r.lower() for r in core}

    # Always include ALL standard worship roles (even if worship has no defaults yet)
    for t in SERVICE_WORSHIP_ROLES:
        if t.lower() not in seen:
            core.append(t)
            seen.add(t.lower())
    # Plus any extra custom roles saved in worship defaults
    for w in get_worship_default_assignments():
        t = (w.get('role_name') or '').strip()
        if t and t.lower() not in seen:
            core.append(t)
            seen.add(t.lower())

    # Always include ALL volunteer teams
    for t in get_volunteer_team_role_names():
        if t and t.lower() not in seen:
            core.append(t)
            seen.add(t.lower())
    return core


def _assignment_lookup(rows) -> dict:
    """role_name lower -> assignment dict (first wins)."""
    out = {}
    for a in rows or []:
        if not isinstance(a, dict):
            continue
        role = (a.get('role_name') or '').strip()
        if not role:
            continue
        key = role.lower()
        if key not in out:
            out[key] = a
    return out


def _uid_ok(uid) -> int | None:
    if uid in (None, '', 0, '0', 'None'):
        return None
    try:
        return int(uid)
    except (TypeError, ValueError):
        return None


def volunteer_people_for_date(date_str: str) -> dict[str, dict]:
    """
    Map team_name_lower -> {user_id, user_full_name, source} from volunteer
    events scheduled that day (accepted/pending preferred).
    """
    out = {}
    if not date_str:
        return out
    try:
        from app.models import volunteers as vol
        events = vol.list_events(from_date=date_str, to_date=date_str, limit=50) or []
        for ev in events:
            team_name = (ev.get('team_name') or '').strip()
            if not team_name:
                continue
            key = team_name.lower()
            assigns = vol.list_assignments(int(ev['id'])) or []
            # Prefer accepted, then pending, then anything with a user
            ordered = sorted(
                assigns,
                key=lambda a: (
                    0 if (a.get('status') or '') == 'accepted' else
                    1 if (a.get('status') or '') == 'pending' else 2
                ),
            )
            for a in ordered:
                uid = _uid_ok(a.get('user_id'))
                if not uid:
                    continue
                name = ' '.join(filter(None, [
                    (a.get('first_name') or '').strip(),
                    (a.get('last_name') or '').strip(),
                ])).strip() or a.get('user_full_name')
                out[key] = {
                    'user_id': uid,
                    'user_full_name': name or None,
                    'source': 'volunteer',
                    'status': a.get('status'),
                }
                break
    except Exception as exc:
        print(f'volunteer_people_for_date: {exc}')
    return out


def _picker_options_for_role(kind: str, team_id: int | None = None) -> list[dict]:
    """People you can pick for this role — never free-type the team name."""
    options = []
    seen = set()

    def _add(uid, label, note=''):
        uid = _uid_ok(uid)
        if not uid or uid in seen:
            return
        seen.add(uid)
        options.append({'id': uid, 'label': label, 'note': note})

    try:
        if kind == 'volunteer' and team_id:
            from app.models import volunteers as vol
            for m in vol.list_team_members(int(team_id)) or []:
                name = f"{m.get('first_name') or ''} {m.get('last_name') or ''}".strip()
                pref = (m.get('preferred_role_name') or '').strip()
                _add(m.get('user_id'), name or f"User #{m.get('user_id')}", pref)
        elif kind == 'worship':
            from app.models.worship.shared import get_worship_team_members
            for m in get_worship_team_members() or []:
                name = f"{m.get('first_name') or ''} {m.get('last_name') or ''}".strip()
                _add(m.get('id'), name or m.get('username') or f"User #{m.get('id')}",
                     'Leader' if (m.get('role_in_group') or '') == 'leader' else '')
        else:
            # Preacher / pastoral — pastoral group + staff
            db = get_db()
            cur = db.cursor(pymysql.cursors.DictCursor)
            cur.execute("""
                SELECT DISTINCT u.id, u.first_name, u.last_name, u.username
                FROM users u
                LEFT JOIN user_groups ug ON ug.user_id = u.id
                LEFT JOIN groups g ON g.id = ug.group_id
                WHERE COALESCE(u.role,'') NOT IN ('banned','pending')
                  AND (
                        g.name = 'Pastoral Group' OR g.system_key = 'pastoral'
                     OR u.role IN ('Owner','Admin','Staff')
                  )
                ORDER BY u.last_name, u.first_name
            """)
            for u in cur.fetchall() or []:
                name = f"{u.get('first_name') or ''} {u.get('last_name') or ''}".strip()
                _add(u['id'], name or u.get('username') or f"User #{u['id']}")
    except Exception as exc:
        print(f'_picker_options_for_role {kind}: {exc}')
    return options


def build_full_service_assignments(existing=None, date_str: str | None = None, *, apply_fallbacks: bool = True) -> list[dict]:
    """
    Live roster from the app — not free-text roles.

    Sources (locked role labels, never typed):
      - Preacher
      - Worship → Default Roles + Worship Team members as pickers
      - Volunteers → Teams (Greeters, Ushers, …) as locked team rows + team-member pickers
      - Volunteer schedule for that date fills people when already assigned

    Role names are ALWAYS from teams/worship — you only pick a person.

    apply_fallbacks=False: use only `existing` people — no soft-fill from overall
    defaults, worship defaults, or volunteer schedule. Required for:
      - Overall Defaults form (cleared slots stay empty)
      - Weekly Edit Plan overrides (that week's save fully replaces defaults)
    apply_fallbacks=True: only for weeks with NO dated override (standing roster).
    """
    try:
        ensure_default_assignment_schema()
        sync_worship_defaults_into_pastoral()
    except Exception as exc:
        print(f'build_full_service_assignments prep: {exc}')

    existing = existing or []
    existing_by = _assignment_lookup(existing)
    try:
        pastoral_by = _assignment_lookup(get_default_assignments()) if apply_fallbacks else {}
    except Exception:
        pastoral_by = {}
    worship_by = _assignment_lookup(get_worship_default_assignments()) if apply_fallbacks else {}
    # Never force a person into empty roles (esp. Worship Leader).
    vol_day = volunteer_people_for_date(date_str) if (date_str and apply_fallbacks) else {}

    # Live volunteer teams (the real list from /volunteers/)
    vol_teams = []
    try:
        from app.models import volunteers as vol
        vol_teams = vol.list_teams(active_only=True) or []
    except Exception as exc:
        print(f'build_full list_teams: {exc}')
        for name in get_volunteer_team_role_names():
            vol_teams.append({'id': None, 'name': name, 'color': '#60a5fa', 'member_count': 0})

    # Worship roles from defaults + standard band list
    worship_role_names = list(SERVICE_WORSHIP_ROLES)
    for w in worship_by.values():
        rn = (w.get('role_name') or '').strip()
        if rn and rn not in worship_role_names:
            worship_role_names.append(rn)

    worship_pickers = _picker_options_for_role('worship')
    pastoral_pickers = _picker_options_for_role('pastoral')

    def _resolve(role: str, kind: str, team_id=None, color=None, pickers=None) -> dict:
        key = role.lower()
        uid = None
        guest = None
        full = None
        source = 'empty'

        ex = existing_by.get(key)
        if ex:
            uid = _uid_ok(ex.get('user_id'))
            guest = (ex.get('guest_name') or '').strip() or None
            full = ex.get('user_full_name')
            if uid or guest:
                source = ex.get('source') or 'plan'

        if not uid and kind == 'volunteer' and key in vol_day:
            uid = vol_day[key]['user_id']
            full = vol_day[key].get('user_full_name')
            source = 'volunteer'

        if not uid and not guest and kind == 'worship':
            w = worship_by.get(key)
            if w and w.get('user_id'):
                uid = _uid_ok(w['user_id'])
                full = w.get('user_full_name')
                source = 'worship'
            elif w and (w.get('guest_name') or '').strip():
                guest = (w.get('guest_name') or '').strip()
                full = w.get('user_full_name') or guest
                source = 'worship'
            # Do not auto-fill Worship Leader (or any role) from group membership.

        if not uid:
            p = pastoral_by.get(key)
            if p:
                uid = _uid_ok(p.get('user_id'))
                guest = guest or ((p.get('guest_name') or '').strip() or None)
                full = full or p.get('user_full_name')
                if uid or guest:
                    source = p.get('source') or 'pastoral'

        pickers = pickers if pickers is not None else []
        # Ensure selected person appears in picker even if not on team list
        if uid and not any(int(o['id']) == int(uid) for o in pickers):
            pickers = list(pickers) + [{'id': uid, 'label': full or f'User #{uid}', 'note': 'assigned'}]

        return {
            'role_name': role,
            'user_id': uid,
            'guest_name': guest if not uid else None,
            'user_full_name': full,
            'source': source,
            'kind': kind,
            'team_id': team_id,
            'team_color': color or ('#00e5ff' if kind == 'worship' else '#a78bfa' if kind == 'pastoral' else '#34d399'),
            'locked': True,  # role label is not free-text
            'picker_options': pickers,
            'is_filled': bool(uid or guest),
        }

    built = []
    # 1) Preacher
    built.append(_resolve('Preacher', 'pastoral', pickers=pastoral_pickers))
    # 2) Worship band roles
    for role in worship_role_names:
        built.append(_resolve(role, 'worship', pickers=worship_pickers))
    # 3) Every volunteer team from /volunteers/ — never typed by hand
    for t in vol_teams:
        name = (t.get('name') or '').strip()
        if not name:
            continue
        tid = t.get('id')
        pickers = _picker_options_for_role('volunteer', team_id=tid) if tid else pastoral_pickers
        built.append(_resolve(
            name, 'volunteer',
            team_id=tid,
            color=t.get('color') or '#34d399',
            pickers=pickers,
        ))

    # 4) Custom / one-off roles already saved on this plan (not a standard team/worship slot)
    standard_keys = {(b.get('role_name') or '').strip().lower() for b in built}
    # Broad picker for custom rows: pastoral + worship + all team members
    custom_pickers = list(pastoral_pickers)
    seen_custom = {p['id'] for p in custom_pickers}
    for p in worship_pickers:
        if p['id'] not in seen_custom:
            custom_pickers.append(p)
            seen_custom.add(p['id'])
    for t in vol_teams:
        tid = t.get('id')
        if not tid:
            continue
        for p in _picker_options_for_role('volunteer', team_id=tid):
            if p['id'] not in seen_custom:
                custom_pickers.append(p)
                seen_custom.add(p['id'])

    for a in existing:
        role = (a.get('role_name') or '').strip()
        if not role:
            continue
        key = role.lower()
        if key in standard_keys:
            continue
        standard_keys.add(key)
        uid = _uid_ok(a.get('user_id'))
        guest = (a.get('guest_name') or '').strip() or None
        full = a.get('user_full_name')
        pickers = list(custom_pickers)
        if uid and not any(int(o['id']) == int(uid) for o in pickers):
            pickers.append({'id': uid, 'label': full or f'User #{uid}', 'note': 'assigned'})
        built.append({
            'role_name': role,
            'user_id': uid,
            'guest_name': guest if not uid else None,
            'user_full_name': full,
            'source': a.get('source') or 'plan',
            'kind': 'custom',
            'team_id': None,
            'team_color': '#fbbf24',
            'locked': False,  # custom rows can rename / remove
            'picker_options': pickers,
            'is_filled': bool(uid or guest),
        })

    # Names for any missing labels
    need_ids = [b['user_id'] for b in built if b.get('user_id') and not (b.get('user_full_name') or '').strip()]
    if need_ids:
        try:
            db = get_db()
            cur = db.cursor(pymysql.cursors.DictCursor)
            placeholders = ','.join(['%s'] * len(need_ids))
            cur.execute(
                f"SELECT id, CONCAT(first_name, ' ', last_name) AS full_name FROM users WHERE id IN ({placeholders})",
                need_ids,
            )
            names = {int(r['id']): r['full_name'] for r in (cur.fetchall() or [])}
            for b in built:
                if b.get('user_id') and not b.get('user_full_name'):
                    b['user_full_name'] = names.get(int(b['user_id']))
        except Exception as exc:
            print(f'build_full_service_assignments names: {exc}')

    return built


def assignments_for_display(assignments: list, *, only_filled: bool = False) -> list[dict]:
    """Filter for list cards: hide empty roles when only_filled=True."""
    rows = assignments or []
    if only_filled:
        return [a for a in rows if a.get('is_filled') or a.get('user_id') or (a.get('guest_name') or '').strip()]
    return rows


def _upsert_default_role(role_name: str, user_id=None, guest_name=None, *, overwrite_user: bool = False):
    """Insert role if missing; optionally fill empty user_id from worship."""
    role_name = (role_name or '').strip()
    if not role_name:
        return
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT id, user_id FROM default_service_plan_assignments WHERE role_name = %s LIMIT 1",
        (role_name,),
    )
    row = cur.fetchone()
    if not row:
        cur2 = db.cursor()
        try:
            cur2.execute(
                """
                INSERT INTO default_service_plan_assignments (role_name, user_id, guest_name)
                VALUES (%s, %s, %s)
                """,
                (role_name, user_id, guest_name),
            )
            db.commit()
        except Exception:
            # Fallback without guest_name for ancient schemas
            try:
                db.rollback()
                cur2.execute(
                    """
                    INSERT INTO default_service_plan_assignments (role_name, user_id)
                    VALUES (%s, %s)
                    """,
                    (role_name, user_id),
                )
                db.commit()
            except Exception as exc:
                print(f'_upsert_default_role insert {role_name}: {exc}')
                try:
                    db.rollback()
                except Exception:
                    pass
        return

    if user_id and (overwrite_user or not row.get('user_id')):
        cur2 = db.cursor()
        try:
            cur2.execute(
                "UPDATE default_service_plan_assignments SET user_id = %s WHERE id = %s",
                (user_id, row['id']),
            )
            db.commit()
        except Exception as exc:
            print(f'_upsert_default_role update {role_name}: {exc}')
            try:
                db.rollback()
            except Exception:
                pass


def sync_worship_defaults_into_pastoral():
    """
    Ensure pastoral default role SLOTS exist for worship + volunteer teams.

    Never forces a person into any role (including Worship Leader).
    Only creates empty rows when a slot is missing — does not overwrite
    user_id if the pastor cleared an assignment.
    """
    ensure_default_assignment_schema()
    try:
        # Empty slots only — never assign people automatically
        for role in SERVICE_WORSHIP_ROLES:
            _upsert_default_role(role, None, overwrite_user=False)

        # Extra role names that exist in worship defaults (slots only)
        for w in get_worship_default_assignments():
            role = (w.get('role_name') or '').strip()
            if role and role not in SERVICE_WORSHIP_ROLES:
                _upsert_default_role(role, None, overwrite_user=False)

        for role in get_volunteer_team_role_names():
            _upsert_default_role(role, None, overwrite_user=False)

        _upsert_default_role('Preacher', None, overwrite_user=False)
    except Exception as exc:
        print(f'sync_worship_defaults_into_pastoral: {exc}')


def seed_default_assignments_with_volunteer_teams():
    """Backward-compatible name: sync worship + volunteer + preacher slots safely."""
    try:
        ensure_default_assignment_schema()
        sync_worship_defaults_into_pastoral()
    except Exception as exc:
        print(f'seed_default_assignments_with_volunteer_teams: {exc}')


# ----------------------------------------------------------------------
# Global Default Role Assignments - pre-fill new templates & overrides
# ----------------------------------------------------------------------
def get_default_assignments():
    """
    Global default roles for new plans.

    Pulls Worship Team defaults (band roles + Worship Leader) and volunteer
    team slots into pastoral defaults. Safe on older schemas (no 500).
    """
    try:
        ensure_default_assignment_schema()
        sync_worship_defaults_into_pastoral()
    except Exception as exc:
        print(f'get_default_assignments prep: {exc}')

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    rows = []
    try:
        # Prefer selecting guest_name; fall back if column still missing
        try:
            cur.execute("""
                SELECT d.role_name, d.user_id, d.guest_name,
                       CONCAT(u.first_name, ' ', u.last_name) AS user_full_name
                FROM default_service_plan_assignments d
                LEFT JOIN users u ON d.user_id = u.id
                ORDER BY
                  CASE
                    WHEN d.role_name = 'Preacher' THEN 0
                    WHEN d.role_name = 'Worship Leader' THEN 1
                    ELSE 10
                  END,
                  d.role_name
            """)
        except Exception:
            cur.execute("""
                SELECT d.role_name, d.user_id, NULL AS guest_name,
                       CONCAT(u.first_name, ' ', u.last_name) AS user_full_name
                FROM default_service_plan_assignments d
                LEFT JOIN users u ON d.user_id = u.id
                ORDER BY d.role_name
            """)
        rows = cur.fetchall() or []
    except Exception as exc:
        print(f'get_default_assignments query: {exc}')
        rows = []

    # Tag worship-sourced roles for UI
    worship_roles = {w['role_name'] for w in get_worship_default_assignments()}
    worship_roles.update(SERVICE_WORSHIP_ROLES)
    for r in rows:
        r['source'] = 'worship' if (r.get('role_name') or '') in worship_roles else 'pastoral'

    if not rows:
        rows = [{'role_name': '', 'user_id': None, 'guest_name': None, 'user_full_name': None, 'source': 'pastoral'}]
    return rows


def save_default_assignments(assignments: list):
    """
    Replace pastoral defaults from form save.
    Dedupes by role_name (table has UNIQUE). Safe without guest_name column.
    """
    ensure_default_assignment_schema()
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM default_service_plan_assignments")

    # Dedupe: last non-empty row for a role wins (avoids UNIQUE 500)
    by_role = {}
    for a in assignments or []:
        role = (a.get('role_name') or '').strip()
        if not role:
            continue
        uid = a.get('user_id')
        if uid in ('', 'None', None):
            uid = None
        else:
            try:
                uid = int(uid)
            except (TypeError, ValueError):
                uid = None
        guest = (a.get('guest_name') or '').strip() or None
        if uid:
            guest = None
        by_role[role] = {'role_name': role, 'user_id': uid, 'guest_name': guest}

    for role, a in by_role.items():
        try:
            cur.execute(
                """
                INSERT INTO default_service_plan_assignments (role_name, user_id, guest_name)
                VALUES (%s, %s, %s)
                """,
                (a['role_name'], a['user_id'], a['guest_name']),
            )
        except Exception:
            try:
                cur.execute(
                    """
                    INSERT INTO default_service_plan_assignments (role_name, user_id)
                    VALUES (%s, %s)
                    """,
                    (a['role_name'], a['user_id']),
                )
            except Exception as exc:
                print(f'save_default_assignments skip {role}: {exc}')
    db.commit()


# ----------------------------------------------------------------------
# Initial Setup - Seed default Sunday template if none exists
# ----------------------------------------------------------------------
def seed_default_sunday_template():
    """Seed a basic Sunday template if no Sunday master exists yet."""
    dedupe_service_templates()
    try:
        seed_default_assignments_with_volunteer_teams()
    except Exception as exc:
        print(f'seed_default_sunday_template defaults: {exc}')
    if get_template_for_weekday(6):
        return

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT id FROM users WHERE role = 'Owner' LIMIT 1")
    owner = cur.fetchone()
    if not owner:
        return
    creator_id = owner['id']

    # Seed empty slots only — do not force Worship Leader or anyone else
    assignments = [{'role_name': 'Preacher', 'user_id': creator_id, 'guest_name': None}]
    for role in cohesive_service_role_names():
        if role == 'Preacher':
            continue
        assignments.append({'role_name': role, 'user_id': None, 'guest_name': None})

    create_or_update_template({
        'title': 'Sunday Morning Worship',
        'notes': None,
        'forced_notes': '',
        'start_time': '10:00',
        'worship_start_time': '10:15',
        'pastoral_sermon_id': None,
        'weekday': 6,  # Sunday
        'assignments': assignments,
    }, creator_id)
    print("Seeded default Sunday Morning template with Preacher + worship/volunteer roles.")