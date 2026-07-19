# app/routes/pastoral/planning.py
# Full path: WebChurchMan/app/routes/pastoral/planning.py
# File name: planning.py
# Brief, detailed purpose:
#   Blueprint for Service Planning within the Pastoral Area - FULL REBUILD for template-based recurring system + forced notes + safe refresh.
#   Routes:
#     - /planning/ -> Overview with upcoming effective services (template fallback + overrides), calendar, links to templates & defaults
#     - /planning/edit/<date_str> -> Create/edit dated override/special event
#     - /planning/templates -> Centralized recurring templates console (list)
#     - /planning/templates/new -> Create new recurring template (weekday required, starts empty)
#     - /planning/templates/edit/<template_id> -> Edit recurring template (weekday fixed)
#     - /planning/templates/delete/<template_id> -> Delete recurring template
#     - /planning/templates/refresh/<template_id> -> Safe refresh: delete future identical overrides (manual edits preserved)
#     - /planning/defaults -> Manage global default role assignments (pre-fill NEW DATED OVERRIDES ONLY)
#     - /planning/assignments/<plan_id> -> AJAX for dated plan assignments
#     - /planning/delete/<date_str> -> Delete dated override
#   All routes protected by @pastoral_required().
#   NEW: Index shows upcoming effective services (next year) - master changes visible immediately for plain weeks.
#   NEW: New dated overrides copy from matching master template (roles, times, notes, sermon) - title blank for override.
#   NEW: forced_notes support - critical lines prepended for template plans.
#   NEW: template_refresh route - safe cleanup of legacy identical overrides (fixed _normalize_time import).
#   Global defaults pre-fill NEW DATED OVERRIDES ONLY if no template - master templates start empty for precise control.
#   Compatibility preserved for old planning_edit.html (dummy recurrence vars).
#   FIXED: plan always has 'service_date' (even for new) to avoid UndefinedError in template.

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime, timedelta
import calendar
import pymysql

from app.models.db import get_db
from app.models.pastoral.service_plans import (
    get_all_service_plans, get_service_plan_by_date, create_or_update_service_plan,
    get_service_plan_assignments, save_service_plan_assignments,
    get_all_templates, get_template_by_id, create_or_update_template,
    delete_template, get_template_assignments,
    get_default_assignments, save_default_assignments,
    get_plan_for_date, get_template_for_weekday,
    get_volunteer_team_role_names, cohesive_service_role_names,
    build_full_service_assignments,
    _normalize_time
)
from app.models.log import log_change
from . import pastoral_required

planning_bp = Blueprint('planning', __name__, url_prefix='/planning')


# ----------------------------------------------------------------------
# Overview - Upcoming Effective Services + Calendar
# ----------------------------------------------------------------------
@planning_bp.route('/')
@pastoral_required()
def index():
    today = datetime.today().date()

    # Generate upcoming effective plans (next 365 days)
    upcoming_plans = []
    override_dates = set()
    for days in range(365):
        check_date = today + timedelta(days=days)
        date_str = check_date.strftime('%Y-%m-%d')
        plan = get_plan_for_date(date_str)
        if plan:
            plan['source_badge'] = 'Override' if plan.get('source') == 'override' else 'Template'
            plan['source_class'] = 'bg-success' if plan.get('source') == 'override' else 'bg-primary'
            upcoming_plans.append(plan)
            if plan.get('source') == 'override':
                override_dates.add(date_str)

    # Calendar strip (12 months)
    calendar_months = []
    current = datetime(today.year, today.month, 1).date()
    for _ in range(12):
        year = current.year
        month_num = current.month
        month_name = calendar.month_name[month_num]
        cal = calendar.monthcalendar(year, month_num)
        days = []
        for week in cal:
            for day in week:
                if day == 0:
                    days.append({'date': None, 'day': None})
                else:
                    date_obj = datetime(year, month_num, day).date()
                    date_str = date_obj.strftime('%Y-%m-%d')
                    has_override = date_str in override_dates
                    days.append({'date': date_obj, 'day': day, 'has_override': has_override})
        calendar_months.append({'name': month_name, 'year': year, 'days': days})
        if month_num == 12:
            current = datetime(year + 1, 1, 1).date()
        else:
            current = datetime(year, month_num + 1, 1).date()

    return render_template(
        'pastoral/planning_list.html',
        upcoming_plans=upcoming_plans,
        calendar_months=calendar_months,
        today=today
    )


# ----------------------------------------------------------------------
# Dated Override / Special Event Edit
# ----------------------------------------------------------------------
def _assignable_users_for_planning(cur):
    """Pastoral + Worship Team + Owner/Admin/Staff so plan editors can pick anyone serving."""
    try:
        cur.execute("""
            SELECT DISTINCT u.id,
                   CONCAT(u.first_name, ' ', u.last_name) AS full_name,
                   u.username
            FROM users u
            LEFT JOIN user_groups ug ON u.id = ug.user_id
            LEFT JOIN groups g ON ug.group_id = g.id
            WHERE COALESCE(u.role, '') NOT IN ('banned', 'pending')
              AND (
                    g.name IN ('Pastoral Group', 'Worship Team')
                 OR g.system_key IN ('pastoral', 'worship_team')
                 OR u.role IN ('Owner', 'Admin', 'Staff')
              )
            ORDER BY u.first_name, u.last_name
        """)
        rows = cur.fetchall() or []
        if rows:
            return rows
    except Exception as exc:
        print(f'_assignable_users_for_planning: {exc}')
    try:
        cur.execute("""
            SELECT id, CONCAT(first_name, ' ', last_name) AS full_name, username
            FROM users
            WHERE COALESCE(role, '') NOT IN ('banned', 'pending')
            ORDER BY first_name, last_name
            LIMIT 500
        """)
        return cur.fetchall() or []
    except Exception:
        return []


@planning_bp.route('/edit/<date_str>', methods=['GET', 'POST'])
@pastoral_required()
def edit(date_str):
    try:
        service_date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'error')
        return redirect(url_for('pastoral.planning.index'))

    plan = get_service_plan_by_date(date_str)

    # Common data
    today = datetime.today().date()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    # Sermons
    try:
        cur.execute("""
            SELECT id, title, service_date
            FROM pastoral_sermons
            ORDER BY COALESCE(service_date, created_at) DESC
        """)
        linkable_sermons = cur.fetchall()
    except Exception:
        linkable_sermons = []

    assignable_users = _assignable_users_for_planning(cur)

    # Base plan shell for this date (override, template copy, or empty)
    if not plan:
        template_plan = get_plan_for_date(date_str)
        if template_plan and template_plan.get('source') == 'template':
            plan = {
                'id': None,
                'service_date': service_date_obj,
                'title': '',
                'notes': template_plan.get('notes') or '',
                'start_time': template_plan.get('start_time'),
                'worship_start_time': template_plan.get('worship_start_time'),
                'pastoral_sermon_id': template_plan.get('pastoral_sermon_id'),
                # Start from template rows; full roster merge below fills missing roles
                'assignments': [dict(a) for a in (template_plan.get('assignments') or [])],
            }
        else:
            plan = {
                'id': None,
                'service_date': service_date_obj,
                'title': '',
                'notes': '',
                'start_time': None,
                'worship_start_time': None,
                'pastoral_sermon_id': None,
                'assignments': [],
            }

    # ALWAYS expand to full Sunday roster:
    # all volunteer teams + worship/band roles; fill from plan → worship defaults → pastoral defaults
    # Unassigned roles stay listed empty — user does not re-add them every time.
    try:
        plan['assignments'] = build_full_service_assignments(plan.get('assignments') or [])
    except Exception as exc:
        print(f'planning.edit build_full_service_assignments: {exc}')
        plan['assignments'] = plan.get('assignments') or []

    assignments = plan['assignments']

    # Dummy recurrence vars for old template
    future_count = 0
    last_future_date = None

    if request.method == 'POST':
        data = {
            'service_date': date_str,
            'title': request.form.get('title', '').strip(),
            'notes': request.form.get('notes'),
            'pastoral_sermon_id': request.form.get('sermon_id') or None,
            'start_time': request.form.get('start_time') or None,
            'worship_start_time': request.form.get('worship_start_time') or None,
            'assignments': []
        }

        role_names = request.form.getlist('role_name')
        user_ids = request.form.getlist('user_id')
        guest_names = request.form.getlist('guest_name')
        while len(guest_names) < len(role_names):
            guest_names.append('')
        while len(user_ids) < len(role_names):
            user_ids.append('')
        for role, uid, guest in zip(role_names, user_ids, guest_names):
            if role and role.strip():
                data['assignments'].append({
                    'role_name': role.strip(),
                    'user_id': uid or None,
                    'guest_name': (guest or '').strip() or None,
                })

        # Persist every role row shown (including empty people) so next open keeps the full list
        create_or_update_service_plan(data, session['user_id'])
        log_change(session['user_id'], 'plan_save', None, data['title'], f'Saved override plan for {date_str}')
        flash('Plan saved with full role roster (worship + volunteers).', 'success')
        return redirect(url_for('pastoral.planning.edit', date_str=date_str))

    # GET - compatibility
    if not plan:
        plan = {'service_date': service_date_obj, 'assignments': []}

    # Ensure service_date always present for template
    plan.setdefault('service_date', service_date_obj)

    service_date = service_date_obj

    return render_template(
        'pastoral/planning_edit.html',
        plan=plan,
        service_date=service_date,
        today=today,
        linkable_sermons=linkable_sermons,
        assignments=assignments,
        assignable_users=assignable_users,
        future_count=future_count,
        last_future_date=last_future_date
    )


# ----------------------------------------------------------------------
# Recurring Templates Console - List
# ----------------------------------------------------------------------
@planning_bp.route('/templates')
@pastoral_required()
def templates_list():
    templates = get_all_templates()
    weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    return render_template(
        'pastoral/planning_templates_list.html',
        templates=templates,
        weekday_names=weekday_names
    )


# ----------------------------------------------------------------------
# Recurring Template - Create / Edit (with forced_notes)
# ----------------------------------------------------------------------
@planning_bp.route('/templates/new', methods=['GET', 'POST'])
@planning_bp.route('/templates/edit/<int:template_id>', methods=['GET', 'POST'])
@pastoral_required()
def template_edit(template_id=None):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    # Sermons dropdown
    cur.execute("""
        SELECT id, title, service_date
        FROM pastoral_sermons
        ORDER BY COALESCE(service_date, created_at) DESC
    """)
    sermons = cur.fetchall()

    # Assignable users
    cur.execute("""
        SELECT u.id, CONCAT(u.first_name, ' ', u.last_name) AS full_name, u.username
        FROM users u
        JOIN user_groups ug ON u.id = ug.user_id
        JOIN groups g ON ug.group_id = g.id
        WHERE g.name = 'Pastoral Group'
        ORDER BY u.first_name, u.last_name
    """)
    assignable_users = cur.fetchall()

    is_new = template_id is None

    if not is_new:
        template = get_template_by_id(template_id)
        if not template:
            flash('Template not found.', 'error')
            return redirect(url_for('pastoral.planning.templates_list'))
        assignments = template.get('assignments', [])
    else:
        template = {
            'id': None,
            'title': '',
            'notes': '',
            'forced_notes': '',
            'start_time': None,
            'worship_start_time': None,
            'pastoral_sermon_id': None,
            'weekday': None
        }
        assignments = []  # Start empty - precise control

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        forced_notes = request.form.get('forced_notes', '').strip()

        if not title:
            flash('Title is required.', 'error')
        else:
            data = {
                'id': template_id,
                'title': title,
                'notes': request.form.get('notes'),
                'forced_notes': forced_notes,
                'start_time': request.form.get('start_time') or None,
                'worship_start_time': request.form.get('worship_start_time') or None,
                'pastoral_sermon_id': request.form.get('sermon_id') or None,
                'weekday': template['weekday'] if not is_new else int(request.form['weekday']),
                'assignments': []
            }

            if is_new and data['weekday'] is None:
                flash('Weekday is required for new templates.', 'error')
            else:
                role_names = request.form.getlist('role_name')
                user_ids = request.form.getlist('user_id')
                guest_names = request.form.getlist('guest_name')
                while len(guest_names) < len(role_names):
                    guest_names.append('')
                for role, uid, guest in zip(role_names, user_ids, guest_names):
                    if role.strip():
                        data['assignments'].append({
                            'role_name': role.strip(),
                            'user_id': int(uid) if uid else None,
                            'guest_name': (guest or '').strip() or None,
                        })

                try:
                    new_id = create_or_update_template(data, session['user_id'])
                except ValueError as exc:
                    flash(str(exc), 'warning')
                    existing = get_template_for_weekday(data['weekday'])
                    if existing:
                        return redirect(url_for(
                            'pastoral.planning.template_edit', template_id=existing['id']
                        ))
                    return redirect(url_for('pastoral.planning.templates_list'))

                log_change(session['user_id'], 'template_save', template_id or new_id, title, 'Saved master recurring template')
                flash('Master template saved - affects all future weeks.', 'success')
                return redirect(url_for('pastoral.planning.templates_list'))

    weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    return render_template(
        'pastoral/planning_template_edit.html',
        template=template,
        assignments=assignments,
        sermons=sermons,
        assignable_users=assignable_users,
        is_new=is_new,
        weekday_names=weekday_names
    )


# ----------------------------------------------------------------------
# Recurring Template - Delete
# ----------------------------------------------------------------------
@planning_bp.route('/templates/delete/<int:template_id>', methods=['POST'])
@pastoral_required()
def template_delete(template_id):
    template = get_template_by_id(template_id)
    if template:
        delete_template(template_id)
        log_change(session['user_id'], 'template_delete', template_id, template['title'], 'Deleted master recurring template')
        flash('Master template deleted.', 'success')
    else:
        flash('Template not found.', 'error')
    return redirect(url_for('pastoral.planning.templates_list'))


# ----------------------------------------------------------------------
# Recurring Template - Refresh plain weeks (safe cleanup of legacy identical overrides)
# ----------------------------------------------------------------------
@planning_bp.route('/templates/refresh/<int:template_id>', methods=['POST'])
@pastoral_required()
def template_refresh(template_id):
    template = get_template_by_id(template_id)
    if not template:
        flash('Template not found.', 'error')
        return redirect(url_for('pastoral.planning.templates_list'))

    db = get_db()
    cur = db.cursor()

    # Get current template data for comparison
    template_roles = {a['role_name']: a['user_id'] for a in template['assignments']}

    # Find future dated plans on this weekday
    today_str = datetime.today().strftime('%Y-%m-%d')
    cur.execute("""
        SELECT sp.id, sp.title, sp.notes, sp.start_time, sp.worship_start_time, sp.pastoral_sermon_id
        FROM service_plans sp
        WHERE sp.service_date >= %s AND WEEKDAY(sp.service_date) = %s
    """, (today_str, template['weekday']))
    future_plans = cur.fetchall()

    deleted_count = 0
    for p in future_plans:
        # Get roles for this plan
        cur.execute("SELECT role_name, user_id FROM service_plan_assignments WHERE service_plan_id = %s", (p['id'],))
        plan_roles = {r['role_name']: r['user_id'] for r in cur.fetchall()}

        # Normalize times
        p_start = _normalize_time(p['start_time'])
        p_worship = _normalize_time(p['worship_start_time'])
        t_start = _normalize_time(template['start_time'])
        t_worship = _normalize_time(template['worship_start_time'])

        # Compare
        if (p['title'] == template['title'] or p['title'] is None or p['title'] == '' and
            p['notes'] == template['notes'] and
            p_start == t_start and
            p_worship == t_worship and
            p['pastoral_sermon_id'] == template['pastoral_sermon_id'] and
            plan_roles == template_roles):
            # Identical or title blank - safe to delete
            cur.execute("DELETE FROM service_plan_assignments WHERE service_plan_id = %s", (p['id'],))
            cur.execute("DELETE FROM service_plans WHERE id = %s", (p['id'],))
            deleted_count += 1

    db.commit()

    log_change(session['user_id'], 'template_refresh', template_id, template['title'], f'Refreshed {deleted_count} future plain weeks')
    flash(f'Successfully refreshed {deleted_count} future plain weeks to use latest template.', 'success')
    return redirect(url_for('pastoral.planning.templates_list'))


# ----------------------------------------------------------------------
# Global Default Role Assignments
# ----------------------------------------------------------------------
@planning_bp.route('/defaults', methods=['GET', 'POST'])
@pastoral_required()
def defaults():
    """
    Pastoral service default roles.
    Merges Worship Team defaults (Worship Leader, band roles) so they stay in sync.
    Hardened against schema/migration issues so this page does not 500.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    # Assignable people: Pastoral Group + Worship Team + Owner/Admin
    try:
        cur.execute("""
            SELECT DISTINCT u.id,
                   CONCAT(u.first_name, ' ', u.last_name) AS full_name,
                   u.username
            FROM users u
            LEFT JOIN user_groups ug ON u.id = ug.user_id
            LEFT JOIN groups g ON ug.group_id = g.id
            WHERE u.role IN ('Owner', 'Admin', 'Staff', 'Member')
              AND (
                    g.name = 'Pastoral Group'
                 OR g.system_key = 'pastoral'
                 OR g.name = 'Worship Team'
                 OR g.system_key = 'worship_team'
                 OR u.role IN ('Owner', 'Admin')
              )
            ORDER BY u.first_name, u.last_name
        """)
        assignable_users = cur.fetchall() or []
    except Exception as exc:
        print(f'planning.defaults assignable_users: {exc}')
        assignable_users = []

    if request.method == 'POST':
        try:
            assignments = []
            role_names = request.form.getlist('role_name')
            user_ids = request.form.getlist('user_id')
            guest_names = request.form.getlist('guest_name')
            while len(guest_names) < len(role_names):
                guest_names.append('')
            while len(user_ids) < len(role_names):
                user_ids.append('')
            for role, uid, guest in zip(role_names, user_ids, guest_names):
                if role and role.strip():
                    assignments.append({
                        'role_name': role.strip(),
                        'user_id': uid or None,
                        'guest_name': (guest or '').strip() or None,
                    })
            save_default_assignments(assignments)
            log_change(session['user_id'], 'defaults_save', None, None, 'Saved global default role assignments')
            flash('Global defaults saved. Worship Leader and band roles stay aligned with Worship Team defaults when you reopen this page.', 'success')
        except Exception as exc:
            print(f'planning.defaults POST: {exc}')
            flash(f'Could not save defaults: {exc}', 'error')
        return redirect(url_for('pastoral.planning.defaults'))

    try:
        defaults = get_default_assignments()
    except Exception as exc:
        print(f'planning.defaults GET: {exc}')
        flash('Defaults loaded with limited data (see server log).', 'warning')
        defaults = [{'role_name': '', 'user_id': None, 'guest_name': None, 'user_full_name': None}]

    try:
        volunteer_team_roles = get_volunteer_team_role_names()
    except Exception:
        volunteer_team_roles = []
    try:
        from app.models.pastoral.service_plans import get_worship_default_assignments, SERVICE_WORSHIP_ROLES
        worship_defaults = get_worship_default_assignments()
        worship_role_names = list({*(SERVICE_WORSHIP_ROLES or []), *[w.get('role_name') for w in worship_defaults if w.get('role_name')]})
    except Exception:
        worship_defaults = []
        worship_role_names = []

    return render_template(
        'pastoral/planning_defaults.html',
        defaults=defaults,
        assignable_users=assignable_users,
        volunteer_team_roles=volunteer_team_roles,
        worship_defaults=worship_defaults,
        worship_role_names=worship_role_names,
        cohesive_roles=(cohesive_service_role_names() or []),
    )


# ----------------------------------------------------------------------
# Existing AJAX & Delete (preserved)
# ----------------------------------------------------------------------
@planning_bp.route('/assignments/<int:plan_id>', methods=['GET', 'POST'])
@pastoral_required()
def assignments(plan_id: int):
    if request.method == 'POST':
        assignments = request.get_json() or []
        save_service_plan_assignments(plan_id, assignments)
        return jsonify({'status': 'success'})
    return jsonify(get_service_plan_assignments(plan_id))


@planning_bp.route('/delete/<date_str>', methods=['POST'])
@pastoral_required()
def delete(date_str):
    plan = get_service_plan_by_date(date_str)
    if plan:
        save_service_plan_assignments(plan['id'], [])  # clear assignments first
        db = get_db()
        cur = db.cursor()
        cur.execute("DELETE FROM service_plans WHERE service_date = %s", (date_str,))
        db.commit()
        log_change(session['user_id'], 'plan_delete', None, plan.get('title') or 'Service Plan', f'Deleted override plan for {date_str}')
        flash('Override plan deleted.', 'success')
    else:
        flash('Plan not found.', 'error')
    return redirect(url_for('pastoral.planning.index'))