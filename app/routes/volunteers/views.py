# Volunteer scheduling routes.

from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

from app.models import volunteers as vol
from app.models.log import log_change
from app.utils.decorators import login_required, permission_required

from . import volunteers_bp


def _uid():
    return session.get('user_id')


def _can_manage():
    from app.utils.permissions import user_has_permission
    if session.get('user_role') in ('Owner', 'Admin', 'Staff'):
        return user_has_permission('manage_volunteers') or user_has_permission('manage_attendance') or session.get('user_role') == 'Owner'
    return user_has_permission('manage_volunteers')


# ── Dashboard ───────────────────────────────────────────────────────────────

@volunteers_bp.route('/')
@login_required
@permission_required('manage_volunteers', 'manage_attendance')
def dashboard():
    stats = vol.dashboard_stats()
    upcoming = vol.list_events(from_date=vol.church_today_str(), limit=12)
    teams = vol.list_teams()
    log_change(_uid(), 'view', change_details='Opened Volunteer Scheduling')
    return render_template(
        'volunteers/dashboard.html',
        stats=stats,
        upcoming=upcoming,
        teams=teams,
        settings=vol.get_vol_settings(),
    )


# ── Teams ───────────────────────────────────────────────────────────────────

@volunteers_bp.route('/teams')
@login_required
@permission_required('manage_volunteers', 'manage_attendance')
def teams_list():
    return render_template('volunteers/teams.html', teams=vol.list_teams(active_only=False))


@volunteers_bp.route('/teams/new', methods=['GET', 'POST'])
@login_required
@permission_required('manage_volunteers', 'manage_attendance')
def team_new():
    if request.method == 'POST':
        tid = vol.save_team({
            'name': request.form.get('name'),
            'description': request.form.get('description'),
            'color': request.form.get('color') or '#22d3ee',
            'sort_order': request.form.get('sort_order') or 0,
            'active': True,
        })
        flash('Team created.', 'success')
        return redirect(url_for('volunteers.team_detail', team_id=tid))
    return render_template('volunteers/team_form.html', team=None)


@volunteers_bp.route('/teams/<int:team_id>', methods=['GET', 'POST'])
@login_required
@permission_required('manage_volunteers', 'manage_attendance')
def team_detail(team_id):
    team = vol.get_team(team_id)
    if not team:
        flash('Team not found.', 'error')
        return redirect(url_for('volunteers.teams_list'))

    if request.method == 'POST':
        action = request.form.get('action') or 'save_team'
        try:
            if action == 'save_team':
                vol.save_team({
                    'name': request.form.get('name'),
                    'description': request.form.get('description'),
                    'color': request.form.get('color'),
                    'sort_order': request.form.get('sort_order'),
                    'active': request.form.get('active') == '1',
                }, team_id)
                flash('Team saved.', 'success')
            elif action == 'add_role':
                vol.save_role(team_id, {
                    'name': request.form.get('name'),
                    'description': request.form.get('description'),
                    'slots': request.form.get('slots') or 1,
                    'required_skill_id': request.form.get('required_skill_id'),
                    'sort_order': request.form.get('sort_order') or 0,
                })
                flash('Role added.', 'success')
            elif action == 'update_role':
                vol.save_role(team_id, {
                    'name': request.form.get('name'),
                    'description': request.form.get('description'),
                    'slots': request.form.get('slots') or 1,
                    'required_skill_id': request.form.get('required_skill_id'),
                    'sort_order': request.form.get('sort_order') or 0,
                    'active': request.form.get('active') != '0',
                }, role_id=int(request.form.get('role_id') or 0))
                flash('Role updated.', 'success')
            elif action == 'add_member':
                vol.add_team_member(
                    team_id,
                    int(request.form.get('user_id') or 0),
                    preferred_role_id=request.form.get('preferred_role_id') or None,
                )
                flash('Member added to team.', 'success')
            elif action == 'remove_member':
                vol.remove_team_member(team_id, int(request.form.get('user_id') or 0))
                flash('Member removed.', 'success')
        except Exception as e:
            flash(str(e), 'error')
        return redirect(url_for('volunteers.team_detail', team_id=team_id))

    return render_template(
        'volunteers/team_detail.html',
        team=team,
        roles=vol.list_roles(team_id, active_only=False),
        members=vol.list_team_members(team_id),
        skills=vol.list_skills(),
        people=vol.list_members_picker(),
        rotations=vol.list_rotations(team_id),
    )


# ── Skills ──────────────────────────────────────────────────────────────────

@volunteers_bp.route('/skills', methods=['GET', 'POST'])
@login_required
@permission_required('manage_volunteers', 'manage_attendance')
def skills():
    if request.method == 'POST':
        action = request.form.get('action') or 'add_skill'
        try:
            if action == 'add_skill':
                vol.save_skill(request.form.get('name'), request.form.get('description') or '')
                flash('Skill added.', 'success')
            elif action == 'set_user_skills':
                uid = int(request.form.get('user_id') or 0)
                ids = [int(x) for x in request.form.getlist('skill_ids')]
                vol.set_user_skills(uid, ids)
                flash('Skills updated for member.', 'success')
        except Exception as e:
            flash(str(e), 'error')
        return redirect(url_for('volunteers.skills'))

    selected_user = request.args.get('user_id', type=int)
    user_skills = vol.get_user_skill_ids(selected_user) if selected_user else []
    return render_template(
        'volunteers/skills.html',
        skills=vol.list_skills(active_only=False),
        people=vol.list_members_picker(),
        selected_user=selected_user,
        user_skills=user_skills,
    )


# ── Events / schedule ───────────────────────────────────────────────────────

@volunteers_bp.route('/schedule')
@login_required
@permission_required('manage_volunteers', 'manage_attendance')
def schedule():
    from_date = request.args.get('from') or vol.church_today_str()
    events = vol.list_events(from_date=from_date, limit=80)
    return render_template(
        'volunteers/schedule.html',
        events=events,
        from_date=from_date,
        teams=vol.list_teams(),
    )


@volunteers_bp.route('/events/new', methods=['GET', 'POST'])
@login_required
@permission_required('manage_volunteers', 'manage_attendance')
def event_new():
    if request.method == 'POST':
        try:
            eid = vol.save_event({
                'title': request.form.get('title'),
                'event_date': request.form.get('event_date'),
                'start_time': request.form.get('start_time') or None,
                'end_time': request.form.get('end_time') or None,
                'location': request.form.get('location'),
                'notes': request.form.get('notes'),
                'team_id': request.form.get('team_id') or None,
                'status': 'open',
            }, created_by=_uid())
            if request.form.get('fill_rotations') == '1' and request.form.get('team_id'):
                n = vol.fill_event_from_team_rotations(eid, int(request.form.get('team_id')), assigned_by=_uid())
                flash(f'Event created. Applied rotations ({n} assignments).', 'success')
            else:
                flash('Event created.', 'success')
            log_change(_uid(), 'create', eid, change_details='Created volunteer event')
            return redirect(url_for('volunteers.event_detail', event_id=eid))
        except Exception as e:
            flash(str(e), 'error')
    return render_template(
        'volunteers/event_form.html',
        event=None,
        teams=vol.list_teams(),
        default_date=vol.church_today_str(),
    )


@volunteers_bp.route('/events/<int:event_id>', methods=['GET', 'POST'])
@login_required
@permission_required('manage_volunteers', 'manage_attendance')
def event_detail(event_id):
    event = vol.get_event(event_id)
    if not event:
        flash('Event not found.', 'error')
        return redirect(url_for('volunteers.schedule'))

    if request.method == 'POST':
        action = request.form.get('action') or 'save'
        try:
            if action == 'save':
                vol.save_event({
                    'title': request.form.get('title'),
                    'event_date': request.form.get('event_date'),
                    'start_time': request.form.get('start_time') or None,
                    'end_time': request.form.get('end_time') or None,
                    'location': request.form.get('location'),
                    'notes': request.form.get('notes'),
                    'team_id': request.form.get('team_id') or None,
                    'status': request.form.get('status') or 'open',
                }, event_id)
                flash('Event saved.', 'success')
            elif action == 'assign':
                a = vol.assign_volunteer(
                    event_id,
                    int(request.form.get('user_id') or 0),
                    request.form.get('role_name') or 'Volunteer',
                    role_id=int(request.form.get('role_id')) if request.form.get('role_id') else None,
                    assigned_by=_uid(),
                    notify=request.form.get('notify') == '1',
                )
                flash(f"Assigned {a.get('display_name')} as {a.get('role_name')} (pending).", 'success')
            elif action == 'remove_assignment':
                vol.remove_assignment(int(request.form.get('assignment_id') or 0))
                flash('Assignment removed.', 'success')
            elif action == 'apply_rotation':
                created = vol.apply_rotation_to_event(
                    int(request.form.get('rotation_id') or 0),
                    event_id,
                    assigned_by=_uid(),
                    slots=int(request.form.get('slots') or 1),
                )
                flash(f'Rotation applied ({len(created)} people).', 'success')
            elif action == 'fill_rotations':
                if not event.get('team_id'):
                    flash('Set a team on this event first.', 'error')
                else:
                    n = vol.fill_event_from_team_rotations(event_id, event['team_id'], assigned_by=_uid())
                    flash(f'Filled from rotations: {n} assignments.', 'success')
            elif action == 'resend':
                a = vol.get_assignment(int(request.form.get('assignment_id') or 0))
                if a and vol.notify_assignment(a, kind='invite'):
                    flash('Invite re-sent.', 'success')
                else:
                    flash('Could not send (no email?).', 'error')
            elif action == 'delete':
                vol.delete_event(event_id)
                flash('Event deleted.', 'success')
                return redirect(url_for('volunteers.schedule'))
        except Exception as e:
            flash(str(e), 'error')
        return redirect(url_for('volunteers.event_detail', event_id=event_id))

    assignments = vol.list_assignments(event_id)
    roles = vol.list_roles(event['team_id']) if event.get('team_id') else []
    members = vol.list_team_members(event['team_id']) if event.get('team_id') else vol.list_members_picker()
    # Normalize picker shape
    if event.get('team_id'):
        picker = [{'id': m['user_id'], 'first_name': m['first_name'], 'last_name': m['last_name']} for m in members]
    else:
        picker = members
    rotations = vol.list_rotations(event['team_id']) if event.get('team_id') else []
    suggestions = {}
    for r in roles:
        suggestions[r['id']] = vol.suggest_for_role(event['team_id'], r)[:8] if event.get('team_id') else []

    return render_template(
        'volunteers/event_detail.html',
        event=event,
        assignments=assignments,
        roles=roles,
        picker=picker,
        rotations=rotations,
        teams=vol.list_teams(),
        suggestions=suggestions,
    )


# ── Rotations ───────────────────────────────────────────────────────────────

@volunteers_bp.route('/rotations', methods=['GET', 'POST'])
@login_required
@permission_required('manage_volunteers', 'manage_attendance')
def rotations():
    if request.method == 'POST':
        action = request.form.get('action') or 'create'
        try:
            if action == 'create':
                rid = vol.save_rotation({
                    'team_id': request.form.get('team_id'),
                    'role_id': request.form.get('role_id') or None,
                    'role_name': request.form.get('role_name'),
                    'name': request.form.get('name'),
                    'frequency': request.form.get('frequency') or 'weekly',
                    'member_ids': request.form.getlist('member_ids'),
                    'notes': request.form.get('notes'),
                    'active': True,
                })
                flash('Rotation created.', 'success')
                log_change(_uid(), 'create', rid, change_details='Created volunteer rotation')
            elif action == 'delete':
                vol.delete_rotation(int(request.form.get('rotation_id') or 0))
                flash('Rotation deleted.', 'success')
            elif action == 'save':
                vol.save_rotation({
                    'team_id': request.form.get('team_id'),
                    'role_id': request.form.get('role_id') or None,
                    'role_name': request.form.get('role_name'),
                    'name': request.form.get('name'),
                    'frequency': request.form.get('frequency') or 'weekly',
                    'member_ids': request.form.getlist('member_ids'),
                    'cursor_index': request.form.get('cursor_index') or 0,
                    'notes': request.form.get('notes'),
                    'active': request.form.get('active') == '1',
                }, rotation_id=int(request.form.get('rotation_id') or 0))
                flash('Rotation saved.', 'success')
        except Exception as e:
            flash(str(e), 'error')
        return redirect(url_for('volunteers.rotations'))

    teams = vol.list_teams()
    team_roles = {t['id']: vol.list_roles(t['id']) for t in teams}
    team_members = {t['id']: vol.list_team_members(t['id']) for t in teams}
    return render_template(
        'volunteers/rotations.html',
        rotations=vol.list_rotations(),
        teams=teams,
        team_roles=team_roles,
        team_members=team_members,
    )


# ── Settings ────────────────────────────────────────────────────────────────

@volunteers_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@permission_required('manage_volunteers', 'manage_attendance')
def settings():
    if request.method == 'POST':
        vol.save_vol_settings({
            'reminders_enabled': request.form.get('reminders_enabled') == '1',
            'reminder_days': request.form.get('reminder_days') or 3,
            'auto_notify': request.form.get('auto_notify') == '1',
        })
        flash('Volunteer settings saved.', 'success')
        return redirect(url_for('volunteers.settings'))
    return render_template('volunteers/settings.html', settings=vol.get_vol_settings())


# ── My schedule (all members) ───────────────────────────────────────────────

@volunteers_bp.route('/my-schedule')
@login_required
def my_schedule():
    upcoming = vol.my_assignments(_uid(), upcoming_only=True)
    all_rows = vol.my_assignments(_uid(), upcoming_only=False, limit=40)
    today = vol.church_today_str()
    past = []
    for a in all_rows:
        d = a.get('event_date')
        ds = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10]
        if ds < today:
            past.append(a)
    past = past[:15]

    # Tickets assigned to this person (answer / update from My Serving)
    assigned_tickets = []
    try:
        from app.routes.tickets.queries import get_tickets_assigned_to
        assigned_tickets = get_tickets_assigned_to(_uid(), open_only=True)
    except Exception as e:
        print(f"my_schedule tickets: {e}")

    return render_template(
        'volunteers/my_schedule.html',
        upcoming=upcoming,
        past=past,
        assigned_tickets=assigned_tickets,
        can_manage=_can_manage(),
    )


@volunteers_bp.route('/my-schedule/<int:assignment_id>/respond', methods=['POST'])
@login_required
def my_respond(assignment_id):
    a = vol.get_assignment(assignment_id)
    if not a or a['user_id'] != _uid():
        flash('Assignment not found.', 'error')
        return redirect(url_for('volunteers.my_schedule'))
    accept = request.form.get('decision') == 'accept'
    vol.respond_assignment(a['response_token'], accept, request.form.get('note') or '')
    flash('Thanks — response recorded as ' + ('accepted' if accept else 'declined') + '.', 'success')
    if accept:
        try:
            vol.notify_assignment(vol.get_assignment(assignment_id), kind='accepted')
        except Exception:
            pass
    return redirect(url_for('volunteers.my_schedule'))


# ── Public token accept/decline (from email links) ──────────────────────────

@volunteers_bp.route('/respond/<token>')
def respond(token):
    """Landing page for email accept/decline links (login optional)."""
    action = (request.args.get('action') or '').lower()
    assignment = vol.get_assignment_by_token(token)
    if not assignment:
        return render_template('volunteers/respond.html', error='This link is invalid or has expired.', assignment=None)

    if action in ('accept', 'decline') and assignment['status'] == 'pending':
        try:
            assignment = vol.respond_assignment(token, action == 'accept')
            if action == 'accept':
                try:
                    vol.notify_assignment(assignment, kind='accepted')
                except Exception:
                    pass
        except Exception as e:
            return render_template('volunteers/respond.html', error=str(e), assignment=assignment)

    return render_template('volunteers/respond.html', error=None, assignment=assignment, action=action)
