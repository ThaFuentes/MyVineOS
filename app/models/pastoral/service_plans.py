# app/models/pastoral/service_plans.py
# Full path: WebChurchMan/app/models/pastoral/service_plans.py
# File name: service_plans.py
# Brief, detailed purpose:
#   All database operations related to Service Planning module – FULL REBUILD for permanent recurring templates + forced notes + override count.
#   NEW SIMPLE & CLEAN STRUCTURE:
#     - service_templates: Central permanent recurring masters (Sunday Morning, Wednesday Night, etc.)
#       - One row per recurring service type
#       - No service_date – applies to all matching weekdays unless overridden
#       - Title, notes (regular Quill HTML), forced_notes (critical plain text lines), times, linked sermon, role assignments
#       - Change once → instantly affects every future display of that weekday
#     - service_plans: Individual dated overrides/special events only (much fewer rows)
#     - get_plan_for_date(date_str): Returns dated override if exists, ELSE matching template
#       - For template plans: forced_notes prepended to notes (as highlighted HTML block)
#     - Templates matched by weekday (0-6) only – simple, no complex recurrence rules
#     - Global defaults still exist – pre-fill when creating new templates or dated overrides
#     - Removed old 52-week seeding – now seeds one default Sunday template if none exists
#     - get_upcoming_service(): Safe wrapper using get_plan_for_date for next date (plan or template)
#     - get_all_templates(): Now includes override_count (future dated plans on this weekday)
#   This gives true "central place – change once, updates all" for recurring services.
#   Overrides still possible via dated plans.
#   Delete template anytime.
#   Uses DictCursor for consistent dict results.
#   Parameterized queries for MariaDB / PyMySQL safety.

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
# Templates – Central permanent recurring masters (one canonical per weekday)
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
        print(f"Removed {removed} duplicate service template(s) — one master per weekday.")
    return removed


def _extract_preacher(plan: dict):
    """Return the assigned preacher/pastor/speaker name from a plan or template."""
    return next(
        (
            a['user_full_name']
            for a in plan.get('assignments', [])
            if a.get('role_name', '').lower() in ('preacher', 'pastor', 'speaker')
            and a.get('user_full_name')
        ),
        None,
    )


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
    return {
        'weekday': weekday,
        'title': _effective_service_title(plan),
        'weekday_name': WEEKDAY_NAMES[weekday] if weekday is not None else None,
        'start_time': _format_display_time(plan.get('start_time')),
        'worship_start_time': _format_display_time(plan.get('worship_start_time')),
        'preacher': _extract_preacher(plan),
        'is_recurring': is_recurring,
        'is_override': plan.get('source') == 'override',
        'service_date': service_date,
    }


def get_weekly_schedule_display():
    """
    Public-facing recurring schedule: exactly one entry per weekday that has a template.
    Sorted with Sunday first, then Monday–Saturday.
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
    """
    today = datetime.today().date()
    services = []
    for offset in range(days_ahead):
        check_date = today + timedelta(days=offset)
        plan = get_plan_for_date(check_date.strftime('%Y-%m-%d'))
        if not plan:
            continue
        entry = _plan_to_public_service(plan)
        entry['date_label'] = check_date.strftime('%A, %B %d, %Y')
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

    save_template_assignments(template_id, data.get('assignments', []))
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
        SELECT sta.role_name, sta.user_id,
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
            cur.execute("""
                INSERT INTO service_template_assignments (template_id, role_name, user_id)
                VALUES (%s, %s, %s)
            """, (template_id, a['role_name'], a.get('user_id')))
    db.commit()


# ----------------------------------------------------------------------
# Dated Plans – Overrides / special events only
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

    save_service_plan_assignments(plan_id, data.get('assignments', []))
    db.commit()


def get_service_plan_assignments(plan_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT spa.role_name, spa.user_id,
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
            cur.execute("""
                INSERT INTO service_plan_assignments (service_plan_id, role_name, user_id)
                VALUES (%s, %s, %s)
            """, (plan_id, a['role_name'], a.get('user_id')))
    db.commit()


# ----------------------------------------------------------------------
# Unified Plan Retrieval – Prepend forced_notes for template plans
# ----------------------------------------------------------------------
def get_plan_for_date(date_str: str):
    """
    Return the effective plan for a date.
    1. Dated override if exists
    2. Matching weekday template (forced_notes prepended to notes)
    3. None
    """
    # 1. Dated override
    plan = get_service_plan_by_date(date_str)
    if plan:
        return plan

    # 2. Template fallback
    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    weekday = date_obj.weekday()  # 0=Monday ... 6=Sunday

    template = get_template_for_weekday(weekday)
    if template:
        template = dict(template)
        template['source'] = 'template'
        template['service_date'] = date_obj

        # Prepend forced_notes as highlighted block
        forced = template.get('forced_notes', '').strip()
        regular = template.get('notes') or ''
        if forced:
            forced_html = '<div class="forced-notes bg-danger text-white p-3 mb-4 rounded"><strong>CRITICAL NOTES:</strong><br>' + \
                          forced.replace('\n', '<br>') + '</div>'
            template['notes'] = forced_html + regular
        else:
            template['notes'] = regular

        return template

    return None


# ----------------------------------------------------------------------
# get_upcoming_service – Safe for migration
# ----------------------------------------------------------------------
def get_upcoming_service():
    """Return the next upcoming service (plan or template fallback). Safe during schema migration."""
    today = datetime.today().date()

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
            return get_plan_for_date(row['service_date'].strftime('%Y-%m-%d'))
    except pymysql.err.ProgrammingError as e:
        if "doesn't exist" in str(e):
            print("service_plans table not created yet – using template fallback only.")
        else:
            raise

    # No dated plan – find next date with template
    for days_ahead in range(0, 30):
        check_date = today + timedelta(days=days_ahead)
        plan = get_plan_for_date(check_date.strftime('%Y-%m-%d'))
        if plan:
            return plan

    # Ultimate fallback (no templates yet)
    return {
        'service_date': today + timedelta(days=((6 - today.weekday()) % 7) or 7),  # next Sunday
        'title': 'Regular Service',
        'notes': '',
        'start_time': time(10, 0),
        'worship_start_time': time(10, 15),
        'assignments': [],
        'source': 'fallback'
    }


# ----------------------------------------------------------------------
# Global Default Role Assignments – pre-fill new templates & overrides
# ----------------------------------------------------------------------
def get_default_assignments():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT role_name, user_id,
               CONCAT(u.first_name, ' ', u.last_name) AS user_full_name
        FROM default_service_plan_assignments d
        LEFT JOIN users u ON d.user_id = u.id
        ORDER BY role_name
    """)
    rows = cur.fetchall()
    if not rows:
        rows = [{'role_name': '', 'user_id': None, 'user_full_name': None}]
    return rows


def save_default_assignments(assignments: list):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM default_service_plan_assignments")
    for a in assignments:
        if a['role_name'].strip():
            cur.execute("""
                INSERT INTO default_service_plan_assignments (role_name, user_id)
                VALUES (%s, %s)
            """, (a['role_name'], a['user_id']))
    db.commit()


# ----------------------------------------------------------------------
# Initial Setup – Seed default Sunday template if none exists
# ----------------------------------------------------------------------
def seed_default_sunday_template():
    """Seed a basic Sunday template if no Sunday master exists yet."""
    dedupe_service_templates()
    if get_template_for_weekday(6):
        return

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT id FROM users WHERE role = 'Owner' LIMIT 1")
    owner = cur.fetchone()
    if not owner:
#        print("Warning: No Owner – cannot seed default template.")
        return
    creator_id = owner['id']

    create_or_update_template({
        'title': 'Sunday Morning Worship',
        'notes': None,
        'forced_notes': '',
        'start_time': '10:00',
        'worship_start_time': '10:15',
        'pastoral_sermon_id': None,
        'weekday': 6,  # Sunday
        'assignments': [{'role_name': 'Preacher', 'user_id': creator_id}]
    }, creator_id)
    print("Seeded default Sunday Morning template with Preacher = Owner.")