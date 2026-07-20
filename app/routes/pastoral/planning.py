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
    build_full_service_assignments, assignments_for_display,
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

    # Generate upcoming effective plans (next 90 days for speed; full roster enrichment)
    upcoming_plans = []
    override_dates = set()
    # Live volunteer teams for the overview chips
    try:
        from app.models.volunteers import list_teams
        volunteer_teams = list_teams(active_only=True) or []
    except Exception:
        volunteer_teams = []

    for days in range(90):
        check_date = today + timedelta(days=days)
        date_str = check_date.strftime('%Y-%m-%d')
        plan = get_plan_for_date(date_str)
        if plan:
            plan = dict(plan)
            plan['source_badge'] = 'Override' if plan.get('source') == 'override' else 'Template'
            plan['source_class'] = 'bg-success' if plan.get('source') == 'override' else 'bg-primary'
            # Strict: only people on override or recurring template (no overall-defaults soft-fill)
            is_override = plan.get('source') == 'override'
            try:
                full = build_full_service_assignments(
                    plan.get('assignments') or [],
                    date_str=date_str,
                    apply_fallbacks=False,
                )
                plan['assignments'] = full
                plan['roster_filled'] = assignments_for_display(full, only_filled=True)
            except Exception as exc:
                print(f'planning.index roster: {exc}')
                plan['roster_filled'] = []
            upcoming_plans.append(plan)
            if is_override:
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
        today=today,
        volunteer_teams=volunteer_teams,
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

    # Sermons (service_date may be date or str depending on driver/config — template handles both)
    try:
        cur.execute("""
            SELECT id, title, service_date
            FROM pastoral_sermons
            ORDER BY COALESCE(service_date, created_at) DESC
        """)
        linkable_sermons = list(cur.fetchall() or [])
    except Exception:
        linkable_sermons = []

    assignable_users = _assignable_users_for_planning(cur)

    # Base plan shell for this date (override, or overall defaults + template times)
    if not plan:
        base = get_plan_for_date(date_str)  # no override → overall default people
        if base:
            plan = {
                'id': None,
                'service_date': service_date_obj,
                'title': base.get('title') or '',
                'notes': base.get('notes') or '',
                'start_time': base.get('start_time'),
                'worship_start_time': base.get('worship_start_time'),
                'pastoral_sermon_id': base.get('pastoral_sermon_id'),
                # Overall default plan roster (guest Tim, etc.) — not stale template users
                'assignments': [dict(a) for a in (base.get('assignments') or [])],
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

    # Hierarchy: dated override people OR recurring template people only (strict — no overall defaults).
    is_override = bool(plan.get('id')) or plan.get('source') == 'override'
    try:
        plan['assignments'] = build_full_service_assignments(
            plan.get('assignments') or [],
            date_str=date_str,
            apply_fallbacks=False,
        )
    except Exception as exc:
        print(f'planning.edit build_full_service_assignments: {exc}')
        plan['assignments'] = plan.get('assignments') or []

    assignments = plan['assignments']
    roster_by_kind = {
        'pastoral': [a for a in assignments if (a.get('kind') or '') == 'pastoral'],
        'worship': [a for a in assignments if (a.get('kind') or '') == 'worship'],
        'volunteer': [a for a in assignments if (a.get('kind') or '') == 'volunteer'],
        'custom': [a for a in assignments if (a.get('kind') or '') == 'custom'],
    }
    # Fallback if kind missing (older rows)
    if not any(roster_by_kind.values()):
        roster_by_kind = {'pastoral': [], 'worship': [], 'volunteer': assignments, 'custom': []}
    try:
        from app.models.volunteers import list_teams
        volunteer_teams = list_teams(active_only=True) or []
    except Exception:
        volunteer_teams = []

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

        # Save exactly what was posted — this week fully overrides the recurring plan
        create_or_update_service_plan(data, session['user_id'])
        log_change(session['user_id'], 'plan_save', None, data['title'], f'Saved override plan for {date_str}')
        flash(
            "This week's plan saved. It fully overrides the recurring plan for this date only.",
            'success',
        )
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
        roster_by_kind=roster_by_kind,
        assignable_users=assignable_users,
        volunteer_teams=volunteer_teams,
        future_count=future_count,
        last_future_date=last_future_date,
        is_override=bool(plan.get('id')) or plan.get('source') == 'override',
        date_str=date_str,
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
def _roster_by_kind_from_assignments(assignments):
    """Split built roster rows into kind buckets for _roster_panel.html."""
    roster_by_kind = {
        'pastoral': [a for a in assignments if (a.get('kind') or '') == 'pastoral'],
        'worship': [a for a in assignments if (a.get('kind') or '') == 'worship'],
        'volunteer': [a for a in assignments if (a.get('kind') or '') == 'volunteer'],
        'custom': [a for a in assignments if (a.get('kind') or '') == 'custom'],
    }
    if not any(roster_by_kind.values()):
        roster_by_kind = {'pastoral': [], 'worship': [], 'volunteer': assignments or [], 'custom': []}
    return roster_by_kind


def _assignments_from_form():
    """Parse role_name / user_id / guest_name lists from the roster form."""
    assignments = []
    role_names = request.form.getlist('role_name')
    user_ids = request.form.getlist('user_id')
    guest_names = request.form.getlist('guest_name')
    while len(guest_names) < len(role_names):
        guest_names.append('')
    while len(user_ids) < len(role_names):
        user_ids.append('')
    for role, uid, guest in zip(role_names, user_ids, guest_names):
        if role and str(role).strip():
            raw_uid = uid or None
            if raw_uid in ('', 'None'):
                raw_uid = None
            try:
                raw_uid = int(raw_uid) if raw_uid is not None else None
            except (TypeError, ValueError):
                raw_uid = None
            assignments.append({
                'role_name': str(role).strip(),
                'user_id': raw_uid,
                'guest_name': (guest or '').strip() or None,
            })
    return assignments


@planning_bp.route('/templates/new', methods=['GET', 'POST'])
@planning_bp.route('/templates/edit/<int:template_id>', methods=['GET', 'POST'])
@pastoral_required()
def template_edit(template_id=None):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    try:
        cur.execute("""
            SELECT id, title, service_date
            FROM pastoral_sermons
            ORDER BY COALESCE(service_date, created_at) DESC
        """)
        sermons = list(cur.fetchall() or [])
    except Exception:
        sermons = []

    assignable_users = _assignable_users_for_planning(cur)
    is_new = template_id is None
    weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    if not is_new:
        template = get_template_by_id(template_id)
        if not template:
            flash('Template not found.', 'error')
            return redirect(url_for('pastoral.planning.templates_list'))
        stored_assignments = template.get('assignments') or []
    else:
        template = {
            'id': None,
            'title': '',
            'notes': '',
            'forced_notes': '',
            'start_time': None,
            'worship_start_time': None,
            'pastoral_sermon_id': None,
            'weekday': None,
        }
        stored_assignments = []

    # Explicit copy of overall defaults into this recurring plan (never automatic)
    if request.method == 'POST' and request.form.get('action') == 'copy_overall_defaults':
        if is_new:
            flash('Save the recurring plan first, then copy overall defaults into it.', 'error')
            return redirect(url_for('pastoral.planning.template_edit'))
        try:
            overall = get_default_assignments() or []
            people = [
                {
                    'role_name': (a.get('role_name') or '').strip(),
                    'user_id': a.get('user_id'),
                    'guest_name': (a.get('guest_name') or '').strip() or None,
                }
                for a in overall
                if (a.get('role_name') or '').strip()
            ]
            data = {
                'id': template_id,
                'title': template.get('title') or 'Service',
                'notes': template.get('notes'),
                'forced_notes': template.get('forced_notes') or '',
                'start_time': template.get('start_time'),
                'worship_start_time': template.get('worship_start_time'),
                'pastoral_sermon_id': template.get('pastoral_sermon_id'),
                'weekday': template.get('weekday'),
                'assignments': people,
            }
            create_or_update_template(data, session['user_id'])
            log_change(
                session['user_id'], 'template_copy_defaults', template_id,
                template.get('title'), 'Copied overall defaults into recurring plan',
            )
            flash('Overall defaults copied into this recurring plan. Review and save if you need further edits.', 'success')
        except Exception as exc:
            print(f'template_edit copy_overall_defaults: {exc}')
            flash(f'Could not copy overall defaults: {exc}', 'error')
        return redirect(url_for('pastoral.planning.template_edit', template_id=template_id))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        forced_notes = request.form.get('forced_notes', '').strip()

        if not title:
            flash('Title is required.', 'error')
        else:
            try:
                weekday_val = template['weekday'] if not is_new else int(request.form.get('weekday'))
            except (TypeError, ValueError):
                weekday_val = None

            if is_new and weekday_val is None:
                flash('Weekday is required for a new recurring plan.', 'error')
            else:
                data = {
                    'id': template_id,
                    'title': title,
                    'notes': request.form.get('notes'),
                    'forced_notes': forced_notes,
                    'start_time': request.form.get('start_time') or None,
                    'worship_start_time': request.form.get('worship_start_time') or None,
                    'pastoral_sermon_id': request.form.get('sermon_id') or None,
                    'weekday': weekday_val,
                    'assignments': _assignments_from_form(),
                }
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

                log_change(
                    session['user_id'], 'template_save', template_id or new_id,
                    title, 'Saved recurring service plan',
                )
                flash(
                    'Recurring plan saved — applies to every future week of that day '
                    '(unless a single week is customized).',
                    'success',
                )
                return redirect(url_for(
                    'pastoral.planning.template_edit',
                    template_id=template_id or new_id,
                ))

        # Reload after validation error
        if not is_new:
            template = get_template_by_id(template_id) or template
            stored_assignments = (template or {}).get('assignments') or stored_assignments

    try:
        built = build_full_service_assignments(
            stored_assignments, date_str=None, apply_fallbacks=False,
        )
    except Exception as exc:
        print(f'template_edit build_full: {exc}')
        built = stored_assignments or []

    roster_by_kind = _roster_by_kind_from_assignments(built)

    return render_template(
        'pastoral/planning_template_edit.html',
        template=template,
        assignments=built,
        roster_by_kind=roster_by_kind,
        sermons=sermons,
        assignable_users=assignable_users,
        is_new=is_new,
        weekday_names=weekday_names,
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
    Overall default plan (standing roster).

    Same Who is serving form as /planning/edit/<date>.
    Used when a week has no dated override. Per-week changes stay on edit/<date>.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    assignable_users = _assignable_users_for_planning(cur)

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
                if role and str(role).strip():
                    assignments.append({
                        'role_name': str(role).strip(),
                        'user_id': uid or None,
                        'guest_name': (guest or '').strip() or None,
                    })
            save_default_assignments(assignments)
            log_change(session['user_id'], 'defaults_save', None, None, 'Saved overall default plan roster')
            flash(
                'Starter defaults saved. Recurring service plans were not changed — '
                'edit those under Recurring plans if you want Sundays (etc.) updated.',
                'success',
            )
        except Exception as exc:
            print(f'planning.defaults POST: {exc}')
            flash(f'Could not save defaults: {exc}', 'error')
        return redirect(url_for('pastoral.planning.defaults'))

    try:
        stored = get_default_assignments()
    except Exception as exc:
        print(f'planning.defaults GET stored: {exc}')
        stored = []
    try:
        defaults = build_full_service_assignments(stored, date_str=None, apply_fallbacks=False)
    except Exception as exc:
        print(f'planning.defaults build_full: {exc}')
        defaults = stored or []

    roster_by_kind = _roster_by_kind_from_assignments(defaults)
    weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    try:
        recurring_plans = get_all_templates() or []
    except Exception:
        recurring_plans = []

    return render_template(
        'pastoral/planning_defaults.html',
        defaults=defaults,
        roster_by_kind=roster_by_kind,
        assignable_users=assignable_users,
        recurring_plans=recurring_plans,
        weekday_names=weekday_names,
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
    """Remove this week's override so the date falls back to the recurring weekday plan."""
    plan = get_service_plan_by_date(date_str)
    if plan:
        save_service_plan_assignments(plan['id'], [])  # clear assignments first
        db = get_db()
        cur = db.cursor()
        cur.execute("DELETE FROM service_plans WHERE service_date = %s", (date_str,))
        db.commit()
        log_change(
            session['user_id'],
            'plan_delete',
            None,
            plan.get('title') or 'Service Plan',
            f'Reverted override for {date_str} to recurring plan',
        )
        flash(
            "This week's custom plan was removed. It now uses the recurring plan for that day again.",
            'success',
        )
    else:
        flash('No custom plan for this date — already using the recurring plan.', 'info')
    return redirect(url_for('pastoral.planning.edit', date_str=date_str))