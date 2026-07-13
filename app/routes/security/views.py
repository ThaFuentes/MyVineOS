# Security console views — attacks, bans, unlocks, access grants.

from flask import (
    render_template, request, session, flash, redirect, url_for, abort,
)
from functools import wraps

from app.utils.decorators import login_required
from app.models.log import log_change
from app.models.users import clear_account_login_lock
from poweredbytop.reputation.scorer import unban_ip, trust_ip, ban_ip

from . import security_bp
from .utils import (
    can_access_security_console,
    can_manage_security_access,
    ensure_security_grants_table,
)
from . import queries as q


def security_required(f):
    @wraps(f)
    @login_required
    def wrapped(*args, **kwargs):
        if not can_access_security_console():
            flash('You do not have access to the Security console.', 'error')
            abort(403)
        return f(*args, **kwargs)
    return wrapped


def _csrf_ok() -> bool:
    token = (
        request.form.get('csrf_token')
        or request.headers.get('X-CSRF-Token')
        or ''
    ).strip()
    if not token:
        return False
    try:
        from poweredbytop.core.security import validate_csrf
        return validate_csrf(token)
    except Exception:
        from flask import session as sess
        return token == (sess.get('csrf_token') or '')


@security_bp.route('/')
@security_required
def dashboard():
    ensure_security_grants_table()
    stats = q.summary_stats()
    recent_events, _ = q.list_security_events(limit=12, offset=0)
    bans = q.list_reputation_rows(filter_mode='bans', limit=12)
    locks = q.list_account_login_locks()
    attack_stats = q.list_attack_stats()[:12]
    return render_template(
        'security/dashboard.html',
        stats=stats,
        recent_events=recent_events,
        bans=bans,
        locks=locks,
        attack_stats=attack_stats,
        can_manage_access=can_manage_security_access(),
        page_title='Security',
    )


@security_bp.route('/events')
@security_required
def events():
    search = request.args.get('search', '').strip()
    event_type = request.args.get('type', '').strip()
    page = max(1, int(request.args.get('page', 1) or 1))
    page_size = 50
    rows, total = q.list_security_events(
        search=search,
        event_type=event_type,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    return render_template(
        'security/events.html',
        events=rows,
        total=total,
        page=page,
        total_pages=total_pages,
        search=search,
        event_type=event_type,
        event_types=q.list_event_types(),
        can_manage_access=can_manage_security_access(),
        page_title='Security Events',
    )


@security_bp.route('/bans', methods=['GET', 'POST'])
@security_required
def bans():
    if request.method == 'POST':
        if not _csrf_ok():
            flash('Security check failed. Reload and try again.', 'error')
            return redirect(url_for('security.bans'))
        action = (request.form.get('action') or '').strip()
        ip = (request.form.get('ip') or '').strip()
        actor = session['user_id']
        if not ip:
            flash('IP is required.', 'error')
            return redirect(url_for('security.bans'))
        try:
            if action == 'unban':
                ok = unban_ip(ip, restore_score=100)
                if ok:
                    log_change(actor, 'security_unban_ip', details=f'Unbanned IP {ip}; restored score')
                    flash(f'Removed ban for {ip}. They can use the site again.', 'success')
                else:
                    flash(f'No reputation row updated for {ip} (may already be clear).', 'error')
            elif action == 'trust':
                trust_ip(ip, score=250)
                log_change(actor, 'security_trust_ip', details=f'Trusted IP {ip}')
                flash(f'Marked {ip} as trusted (good standing).', 'success')
            elif action == 'temp_ban':
                hours = int(request.form.get('hours') or 1)
                reason = (request.form.get('reason') or 'Manual temp ban from Security console').strip()
                ban_ip(ip, reason=reason, permanent=False, hours=hours)
                log_change(actor, 'security_temp_ban_ip', details=f'Temp ban {ip} for {hours}h: {reason}')
                flash(f'Temp-banned {ip} for {hours} hour(s).', 'success')
            elif action == 'perm_ban':
                reason = (request.form.get('reason') or 'Manual permanent ban from Security console').strip()
                ban_ip(ip, reason=reason, permanent=True)
                log_change(actor, 'security_perm_ban_ip', details=f'Perm ban {ip}: {reason}')
                flash(f'Permanently banned {ip}.', 'success')
            else:
                flash('Unknown action.', 'error')
        except Exception as exc:
            flash(f'Could not update ban: {exc}', 'error')
        return redirect(url_for('security.bans', filter=request.args.get('filter', 'bans'), search=request.args.get('search', '')))

    filter_mode = request.args.get('filter', 'bans').strip() or 'bans'
    if filter_mode not in ('bans', 'low', 'all'):
        filter_mode = 'bans'
    search = request.args.get('search', '').strip()
    rows = q.list_reputation_rows(filter_mode=filter_mode, search=search, limit=200)
    return render_template(
        'security/bans.html',
        rows=rows,
        filter_mode=filter_mode,
        search=search,
        can_manage_access=can_manage_security_access(),
        page_title='IP Bans & Reputation',
    )


@security_bp.route('/account-locks', methods=['GET', 'POST'])
@security_required
def account_locks():
    if request.method == 'POST':
        if not _csrf_ok():
            flash('Security check failed. Reload and try again.', 'error')
            return redirect(url_for('security.account_locks'))
        action = (request.form.get('action') or '').strip()
        try:
            uid = int(request.form.get('user_id') or 0)
        except (TypeError, ValueError):
            uid = 0
        if action == 'unlock' and uid:
            try:
                clear_account_login_lock(uid, session['user_id'])
                flash('Account login lock cleared — they can sign in again.', 'success')
            except Exception as exc:
                flash(f'Could not unlock: {exc}', 'error')
        return redirect(url_for('security.account_locks'))

    locks = q.list_account_login_locks()
    return render_template(
        'security/account_locks.html',
        locks=locks,
        can_manage_access=can_manage_security_access(),
        page_title='Account Login Locks',
    )


@security_bp.route('/access', methods=['GET', 'POST'])
@security_required
def access():
    if not can_manage_security_access():
        flash('Only Owners and Admins can manage Security console access.', 'error')
        return redirect(url_for('security.dashboard'))

    if request.method == 'POST':
        if not _csrf_ok():
            flash('Security check failed. Reload and try again.', 'error')
            return redirect(url_for('security.access'))
        action = (request.form.get('action') or '').strip()
        actor = session['user_id']
        if action == 'grant':
            username = (request.form.get('username') or '').strip()
            notes = (request.form.get('notes') or '').strip()
            user = q.find_user_by_username(username)
            if not user:
                flash(f'No user named “{username}”.', 'error')
            elif user.get('role') in ('Owner', 'Admin', 'Staff'):
                flash(f'{username} already has console access via role.', 'error')
            else:
                q.grant_security_access(user['id'], actor, notes)
                log_change(
                    actor, 'security_grant_access',
                    target_id=user['id'], target_username=user['username'],
                    details=f'Granted Security console access to {user["username"]}',
                )
                flash(f'Granted Security console access to {user["username"]}.', 'success')
        elif action == 'revoke':
            try:
                uid = int(request.form.get('user_id') or 0)
            except (TypeError, ValueError):
                uid = 0
            if uid and q.revoke_security_access(uid):
                log_change(actor, 'security_revoke_access', target_id=uid, details=f'Revoked Security console grant for user {uid}')
                flash('Access grant removed.', 'success')
            else:
                flash('Could not revoke grant.', 'error')
        return redirect(url_for('security.access'))

    grants = q.list_security_grants()
    return render_template(
        'security/access.html',
        grants=grants,
        can_manage_access=True,
        page_title='Security Access',
    )
