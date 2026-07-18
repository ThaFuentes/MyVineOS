# Child Check-In routes — staff station, kiosk, pickup, rooms, parent portal.

from __future__ import annotations

from flask import (
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import app.models.child_checkin as cc
from app.models.log import log_change
from app.models.db import get_db
from app.utils.decorators import login_required, permission_required
from app.utils.time_utils import format_church
import pymysql

from . import child_checkin_bp


def _uid():
    return session.get('user_id')


def _can_manage():
    """Station managers: Admin/Owner full access, or manage_attendance / manage_child_checkin keys."""
    try:
        from app.utils.permissions import user_has_permission as _has_perm
        return bool(
            _has_perm('manage_attendance')
            or _has_perm('manage_child_checkin')
        )
    except Exception:
        # Defensive: never blow up parent portal if permission helper signature drifts
        return False


# ── Dashboard ───────────────────────────────────────────────────────────────

@child_checkin_bp.route('/')
@login_required
@permission_required('manage_attendance', 'manage_child_checkin')
def dashboard():
    stats = cc.dashboard_stats()
    rooms = cc.list_classrooms()
    counts = cc.room_live_counts()
    for r in rooms:
        r['live_count'] = counts.get(r['id'], 0)
    log_change(_uid(), 'view', change_details='Opened Child Check-In dashboard')
    return render_template(
        'child_checkin/dashboard.html',
        stats=stats,
        rooms=rooms,
        settings=cc.get_checkin_settings(),
    )


# ── Children directory ──────────────────────────────────────────────────────

@child_checkin_bp.route('/children')
@login_required
@permission_required('manage_attendance', 'manage_child_checkin')
def children_list():
    q = (request.args.get('q') or '').strip()
    kids = cc.list_children(search=q or None)
    return render_template(
        'child_checkin/children.html',
        children=kids,
        search_q=q,
        rooms=cc.list_classrooms(),
    )


@child_checkin_bp.route('/children/new', methods=['GET', 'POST'])
@login_required
@permission_required('manage_attendance', 'manage_child_checkin')
def child_new():
    if request.method == 'POST':
        try:
            cid = cc.save_child(_child_form(), created_by=_uid())
            # Optional primary guardian
            if request.form.get('guardian_user_id') or request.form.get('guardian_name'):
                cc.add_guardian(cid, {
                    'user_id': request.form.get('guardian_user_id') or None,
                    'full_name': request.form.get('guardian_name'),
                    'relationship': request.form.get('guardian_relationship') or 'parent',
                    'phone': request.form.get('guardian_phone'),
                    'email': request.form.get('guardian_email'),
                    'family_pin': request.form.get('family_pin'),
                    'is_primary': True,
                    'can_pickup': True,
                })
            flash('Child profile created.', 'success')
            log_change(_uid(), 'create', cid, change_details='Created child check-in profile')
            return redirect(url_for('child_checkin.child_detail', child_id=cid))
        except ValueError as e:
            flash(str(e), 'error')
    return render_template(
        'child_checkin/child_form.html',
        child=None,
        rooms=cc.list_classrooms(),
        members=_member_options(),
    )


@child_checkin_bp.route('/children/<int:child_id>', methods=['GET', 'POST'])
@login_required
@permission_required('manage_attendance', 'manage_child_checkin')
def child_detail(child_id):
    child = cc.get_child(child_id)
    if not child:
        flash('Child not found.', 'error')
        return redirect(url_for('child_checkin.children_list'))

    if request.method == 'POST':
        action = request.form.get('action') or 'save'
        try:
            if action == 'save':
                cc.save_child(_child_form(), child_id=child_id)
                flash('Child updated.', 'success')
            elif action == 'add_guardian':
                cc.add_guardian(child_id, {
                    'user_id': request.form.get('user_id') or None,
                    'full_name': request.form.get('full_name'),
                    'relationship': request.form.get('relationship') or 'parent',
                    'phone': request.form.get('phone'),
                    'email': request.form.get('email'),
                    'family_pin': request.form.get('family_pin'),
                    'is_primary': request.form.get('is_primary') == '1',
                    'can_pickup': request.form.get('can_pickup') != '0',
                    'notify_email': request.form.get('notify_email') == '1',
                    'notify_checkin': request.form.get('notify_checkin') == '1',
                    'notify_checkout': request.form.get('notify_checkout') == '1',
                })
                flash('Guardian linked.', 'success')
            elif action == 'remove_guardian':
                cc.remove_guardian(int(request.form.get('guardian_id') or 0))
                flash('Guardian removed.', 'success')
            elif action == 'deactivate':
                cc.delete_child(child_id)
                flash('Child deactivated.', 'success')
                return redirect(url_for('child_checkin.children_list'))
        except ValueError as e:
            flash(str(e), 'error')
        return redirect(url_for('child_checkin.child_detail', child_id=child_id))

    guardians = cc.list_guardians(child_id)
    active = cc.get_active_checkin(child_id)
    return render_template(
        'child_checkin/child_detail.html',
        child=child,
        guardians=guardians,
        rooms=cc.list_classrooms(),
        members=_member_options(),
        active_checkin=active,
    )


def _child_form() -> dict:
    return {
        'first_name': request.form.get('first_name'),
        'last_name': request.form.get('last_name'),
        'nickname': request.form.get('nickname'),
        'birthdate': request.form.get('birthdate'),
        'gender': request.form.get('gender'),
        'allergies': request.form.get('allergies'),
        'medical_notes': request.form.get('medical_notes'),
        'special_needs': request.form.get('special_needs'),
        'pin_code': request.form.get('pin_code'),
        'default_classroom_id': request.form.get('default_classroom_id') or None,
        'notes': request.form.get('notes'),
        'active': request.form.get('active') != '0',
    }


def _member_options(limit=400):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        """
        SELECT id, first_name, last_name, email, username
        FROM users
        WHERE COALESCE(needs_approval,0)=0 AND COALESCE(is_shadow_banned,0)=0
        ORDER BY last_name, first_name
        LIMIT %s
        """,
        (limit,),
    )
    return list(cur.fetchall() or [])


# ── Classrooms ──────────────────────────────────────────────────────────────

@child_checkin_bp.route('/rooms', methods=['GET', 'POST'])
@login_required
@permission_required('manage_attendance', 'manage_child_checkin')
def rooms():
    if request.method == 'POST':
        rid = request.form.get('room_id')
        data = {
            'name': request.form.get('name'),
            'short_code': request.form.get('short_code'),
            'description': request.form.get('description'),
            'location': request.form.get('location'),
            'age_label': request.form.get('age_label'),
            'age_min_months': request.form.get('age_min_months'),
            'age_max_months': request.form.get('age_max_months'),
            'capacity': request.form.get('capacity'),
            'color': request.form.get('color') or '#22d3ee',
            'sort_order': request.form.get('sort_order') or 0,
            'active': request.form.get('active') == '1',
        }
        try:
            cc.save_classroom(data, int(rid) if rid else None)
            flash('Classroom saved.', 'success')
        except Exception as e:
            flash(str(e), 'error')
        return redirect(url_for('child_checkin.rooms'))

    rooms_list = cc.list_classrooms(active_only=False)
    counts = cc.room_live_counts()
    for r in rooms_list:
        r['live_count'] = counts.get(r['id'], 0)
    return render_template('child_checkin/rooms.html', rooms=rooms_list)


# ── Station kiosk (staff tablet) ────────────────────────────────────────────

@child_checkin_bp.route('/kiosk')
@login_required
@permission_required('manage_attendance', 'manage_child_checkin')
def kiosk():
    return render_template(
        'child_checkin/kiosk.html',
        rooms=cc.list_classrooms(),
        settings=cc.get_checkin_settings(),
        today=cc.church_today_str(),
    )


@child_checkin_bp.route('/api/search')
@login_required
@permission_required('manage_attendance', 'manage_child_checkin')
def api_search():
    q = (request.args.get('q') or '').strip()
    if len(q) < 1:
        return jsonify({'results': []})
    results = cc.kiosk_search(q)
    # Slim JSON for kiosk
    out = []
    for c in results:
        out.append({
            'id': c['id'],
            'display_name': c['display_name'],
            'first_name': c.get('first_name'),
            'last_name': c.get('last_name'),
            'age_label': c.get('age_label'),
            'allergies': c.get('allergies'),
            'special_needs': c.get('special_needs'),
            'default_classroom_id': c.get('default_classroom_id'),
            'pin_code': bool(c.get('pin_code')),
            'already_in': bool(c.get('active_checkin')),
            'active_checkin_id': (c.get('active_checkin') or {}).get('id'),
            'active_room': (c.get('active_checkin') or {}).get('classroom_name'),
            'active_code': (c.get('active_checkin') or {}).get('pickup_code'),
            'guardians': [
                {
                    'display': g.get('display'),
                    'relationship': g.get('relationship'),
                    'can_pickup': bool(g.get('can_pickup')),
                    'user_id': g.get('user_id'),
                }
                for g in (c.get('guardians') or [])
            ],
        })
    return jsonify({'results': out})


@child_checkin_bp.route('/api/checkin', methods=['POST'])
@login_required
@permission_required('manage_attendance', 'manage_child_checkin')
def api_checkin():
    data = request.get_json(silent=True) or request.form
    child_ids = data.get('child_ids') or data.getlist('child_ids') if hasattr(data, 'getlist') else data.get('child_ids')
    if isinstance(child_ids, str):
        child_ids = [x for x in child_ids.split(',') if x.strip()]
    if not child_ids:
        # single
        if data.get('child_id'):
            child_ids = [data.get('child_id')]
        else:
            return jsonify({'ok': False, 'error': 'Select at least one child.'}), 400

    rooms_map = data.get('classrooms') or {}
    if isinstance(rooms_map, str):
        rooms_map = {}
    event_label = data.get('event_label') or request.form.get('event_label')
    guardian_name = data.get('guardian_name')
    guardian_user_id = data.get('guardian_user_id') or None
    if guardian_user_id:
        try:
            guardian_user_id = int(guardian_user_id)
        except (TypeError, ValueError):
            guardian_user_id = None

    checked = []
    errors = []
    for cid in child_ids:
        try:
            cid = int(cid)
            room_id = rooms_map.get(str(cid)) or rooms_map.get(cid) or data.get(f'classroom_{cid}') or data.get('classroom_id')
            room_id = int(room_id) if room_id else None
            row = cc.check_in_child(
                child_id=cid,
                classroom_id=room_id,
                guardian_user_id=guardian_user_id,
                guardian_name=guardian_name,
                checked_in_by=_uid(),
                event_label=event_label,
            )
            # Notifications (best effort)
            try:
                cc.notify_guardians(row, 'checkin')
            except Exception:
                pass
            checked.append(_checkin_payload(row))
            log_change(_uid(), 'create', row['id'], change_details=f"Child check-in #{row['child_id']} code {row.get('pickup_code')}")
        except Exception as e:
            errors.append(str(e))

    return jsonify({'ok': not errors or bool(checked), 'checkins': checked, 'errors': errors})


def _checkin_payload(row: dict) -> dict:
    return {
        'id': row['id'],
        'child_id': row['child_id'],
        'display_name': row.get('display_name') or f"{row.get('first_name','')} {row.get('last_name','')}".strip(),
        'classroom_name': row.get('classroom_name'),
        'classroom_code': row.get('classroom_code'),
        'classroom_color': row.get('classroom_color') or '#22d3ee',
        'classroom_location': row.get('classroom_location'),
        'pickup_code': row.get('pickup_code'),
        'security_code': row.get('security_code'),
        'allergies': row.get('allergies'),
        'medical_notes': row.get('medical_notes'),
        'special_needs': row.get('special_needs'),
        'age_label': row.get('age_label'),
        'service_date': str(row.get('service_date') or ''),
        'check_in_at': format_church(row['check_in_at'], '%I:%M %p') if row.get('check_in_at') else '',
        'label_printed': bool(row.get('label_printed')),
    }


@child_checkin_bp.route('/labels')
@login_required
@permission_required('manage_attendance', 'manage_child_checkin')
def labels():
    """Print labels for one or more check-in IDs (?ids=1,2,3)."""
    raw = request.args.get('ids') or ''
    ids = [int(x) for x in raw.split(',') if x.strip().isdigit()]
    checkins = []
    for i in ids:
        row = cc.get_checkin(i)
        if row:
            checkins.append(row)
            cc.mark_label_printed(i)
    if not checkins:
        flash('No check-ins to print.', 'error')
        return redirect(url_for('child_checkin.kiosk'))
    return render_template(
        'child_checkin/labels.html',
        checkins=checkins,
        settings=cc.get_checkin_settings(),
    )


# ── Secure pickup ───────────────────────────────────────────────────────────

@child_checkin_bp.route('/pickup', methods=['GET', 'POST'])
@login_required
@permission_required('manage_attendance', 'manage_child_checkin')
def pickup():
    result = None
    if request.method == 'POST':
        code = (request.form.get('code') or '').strip()
        confirm_id = request.form.get('confirm_id')
        try:
            if confirm_id:
                row = cc.check_out(int(confirm_id), checked_out_by=_uid(), method='staff_confirm')
                try:
                    cc.notify_guardians(row, 'checkout')
                except Exception:
                    pass
                flash(f"Checked out {row.get('display_name')} — thank you!", 'success')
                log_change(_uid(), 'update', row['id'], change_details='Child secure checkout')
                return redirect(url_for('child_checkin.pickup'))
            # Lookup only (preview)
            d = cc.church_today_str()
            db = get_db()
            cur = db.cursor(pymysql.cursors.DictCursor)
            cur.execute(
                """
                SELECT id FROM child_checkins
                WHERE service_date=%s AND status='checked_in'
                  AND (pickup_code=%s OR security_code=%s)
                LIMIT 1
                """,
                (d, code, code),
            )
            found = cur.fetchone()
            if not found:
                flash('No match for that code today. Double-check the label.', 'error')
            else:
                result = cc.get_checkin(int(found['id']))
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash(str(e), 'error')

    return render_template('child_checkin/pickup.html', result=result)


@child_checkin_bp.route('/api/pickup', methods=['POST'])
@login_required
@permission_required('manage_attendance', 'manage_child_checkin')
def api_pickup():
    data = request.get_json(silent=True) or {}
    code = data.get('code') or ''
    try:
        row = cc.check_out_by_code(code, checked_out_by=_uid(), method='code')
        try:
            cc.notify_guardians(row, 'checkout')
        except Exception:
            pass
        return jsonify({'ok': True, 'checkin': _checkin_payload(row)})
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


# ── Room board ──────────────────────────────────────────────────────────────

@child_checkin_bp.route('/board')
@login_required
@permission_required('manage_attendance', 'manage_child_checkin')
def room_board():
    room_id = request.args.get('room', type=int)
    rooms = cc.list_classrooms()
    kids = cc.list_checked_in(classroom_id=room_id)
    counts = cc.room_live_counts()
    for r in rooms:
        r['live_count'] = counts.get(r['id'], 0)
    return render_template(
        'child_checkin/board.html',
        rooms=rooms,
        kids=kids,
        filter_room=room_id,
        today=cc.church_today_str(),
        auto_refresh=True,
    )


@child_checkin_bp.route('/api/board')
@login_required
@permission_required('manage_attendance', 'manage_child_checkin')
def api_board():
    room_id = request.args.get('room', type=int)
    kids = cc.list_checked_in(classroom_id=room_id)
    return jsonify({
        'kids': [_checkin_payload(k) | {
            'check_in_at': format_church(k['check_in_at'], '%I:%M %p') if k.get('check_in_at') else '',
            'allergies': k.get('allergies'),
            'special_needs': k.get('special_needs'),
        } for k in kids],
        'counts': cc.room_live_counts(),
    })


# ── Reports ─────────────────────────────────────────────────────────────────

@child_checkin_bp.route('/report')
@login_required
@permission_required('manage_attendance', 'manage_child_checkin')
def report():
    date = request.args.get('date') or cc.church_today_str()
    data = cc.day_report(date)
    for r in data['rows']:
        if r.get('check_in_at'):
            r['check_in_fmt'] = format_church(r['check_in_at'], '%I:%M %p')
        if r.get('check_out_at'):
            r['check_out_fmt'] = format_church(r['check_out_at'], '%I:%M %p')
    return render_template('child_checkin/report.html', report=data)


# ── Parent portal ───────────────────────────────────────────────────────────

@child_checkin_bp.route('/my-kids', methods=['GET', 'POST'])
@login_required
def my_kids():
    """Parents add kids, set family/child PINs, and see today's check-in status."""
    uid = _uid()
    kids = cc.children_for_user(uid)

    if request.method == 'POST':
        action = request.form.get('action') or ''
        try:
            if action == 'add_child':
                # Any logged-in member can register their own child + PIN
                cid = cc.parent_create_child(uid, {
                    'first_name': request.form.get('first_name'),
                    'last_name': request.form.get('last_name'),
                    'nickname': request.form.get('nickname'),
                    'birthdate': request.form.get('birthdate'),
                    'gender': request.form.get('gender'),
                    'allergies': request.form.get('allergies'),
                    'medical_notes': request.form.get('medical_notes'),
                    'pin_code': request.form.get('pin_code'),
                    'family_pin': request.form.get('family_pin') or request.form.get('pin_code'),
                    'relationship': request.form.get('relationship') or 'parent',
                    'default_classroom_id': request.form.get('default_classroom_id') or None,
                    'notify_email': request.form.get('notify_email') == '1',
                    'notify_checkin': request.form.get('notify_checkin') != '0',
                    'notify_checkout': request.form.get('notify_checkout') != '0',
                })
                flash(
                    'Child added to your profile. Use the family/child PIN at the check-in kiosk.',
                    'success',
                )
                log_change(uid, 'create', cid, change_details='Parent added child via My Kids')
            elif action == 'update_child':
                cid = int(request.form.get('child_id') or 0)
                pin = (request.form.get('pin_code') or '').strip()
                data = {
                    'first_name': request.form.get('first_name'),
                    'last_name': request.form.get('last_name'),
                    'nickname': request.form.get('nickname'),
                    'birthdate': request.form.get('birthdate'),
                    'allergies': request.form.get('allergies'),
                    'medical_notes': request.form.get('medical_notes'),
                }
                if pin:
                    data['pin_code'] = pin
                cc.parent_update_child(uid, cid, data)
                # Family PIN / notify on guardian link
                cc.update_guardian_for_user(uid, cid, {
                    'family_pin': request.form.get('family_pin'),
                    'relationship': request.form.get('relationship'),
                    'notify_email': request.form.get('notify_email') == '1',
                    'notify_checkin': request.form.get('notify_checkin') == '1',
                    'notify_checkout': request.form.get('notify_checkout') == '1',
                })
                flash('Child / PIN settings updated.', 'success')
                log_change(uid, 'update', cid, change_details='Parent updated child via My Kids')
            elif action == 'link_self' and _can_manage():
                cid = int(request.form.get('child_id') or 0)
                cc.add_guardian(cid, {
                    'user_id': uid,
                    'relationship': request.form.get('relationship') or 'parent',
                    'family_pin': request.form.get('family_pin'),
                    'is_primary': True,
                    'can_pickup': True,
                    'notify_email': True,
                    'notify_checkin': True,
                    'notify_checkout': True,
                })
                flash('Child linked to your account.', 'success')
            else:
                flash('Unknown action.', 'error')
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash(str(e), 'error')
        return redirect(url_for('child_checkin.my_kids'))

    today_status = []
    for k in kids:
        active = cc.get_active_checkin(k['id'])
        today_status.append({'child': k, 'checkin': active})

    return render_template(
        'child_checkin/my_kids.html',
        kids=kids,
        today_status=today_status,
        can_manage=_can_manage(),
        all_children=cc.list_children() if _can_manage() else [],
        rooms=cc.list_classrooms(active_only=True),
        settings=cc.get_checkin_settings(),
    )
