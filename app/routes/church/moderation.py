# Site-mod desk and reviewer reversals. Mods only get this — not office tools.

from flask import flash, redirect, render_template, request, session, url_for

from app.models import moderation as mod
from app.models.users import get_user_by_username
from app.utils.comment_moderation import fetch_moderation_comments_queue, handle_manager_comments_post
from app.utils.decorators import login_required, permission_required

from . import church_bp


def _can_touch_account(target: dict | None) -> bool:
    if not target:
        return False
    role = (target.get('role') or '').strip()
    if role in ('Owner', 'Admin'):
        return session.get('user_role') == 'Owner'
    if int(target.get('id') or 0) == int(session.get('user_id') or 0):
        return False
    return True


@church_bp.route('/moderation', methods=['GET', 'POST'])
@login_required
@permission_required('moderate_site', 'moderate_content')
def moderation_desk():
    mod.ensure_tables()
    site_mod = mod.can_moderate_site()
    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()
        actor = session['user_id']
        try:
            # Moderators (moderate_content) work posts, prayers and comments only.
            # People tools (warn / shadow an account) stay with site mods.
            if not site_mod:
                kind = (request.form.get('kind') or '').strip()
                if action in ('warn', 'shadow_user') or (
                    action == 'hide_content' and kind not in mod.CONTENT_MOD_KINDS
                ):
                    flash('That tool is for site moderators.', 'error')
                    return redirect(url_for('church.moderation_desk'))
            if action in ('delete', 'shadow', 'unshadow', 'restore', 'edit'):
                content_type = (request.form.get('content_type') or '').strip()
                parent_id = (request.form.get('parent_id') or '').strip()
                if content_type and parent_id.isdigit():
                    handle_manager_comments_post(content_type, int(parent_id), actor, request.form)
            elif action == 'hide_post':
                post_id = int(request.form.get('post_id') or 0)
                reason = (request.form.get('reason') or '').strip()
                ok, msg = mod.hide_post(post_id, actor, reason)
                flash(msg, 'success' if ok else 'error')
            elif action == 'hide_content':
                kind = (request.form.get('kind') or '').strip()
                item_id = int(request.form.get('item_id') or 0)
                reason = (request.form.get('reason') or '').strip()
                ok, msg = mod.hide_content(kind, item_id, actor, reason)
                flash(msg, 'success' if ok else 'error')
            elif action == 'warn':
                username = (request.form.get('username') or '').strip().lstrip('@')
                message = (request.form.get('message') or '').strip()
                user = get_user_by_username(username) if username else None
                if not user:
                    flash('Could not find that member.', 'error')
                elif not _can_touch_account(user):
                    flash('You cannot warn that account.', 'error')
                else:
                    mod.warn_user(user['id'], actor, message)
                    flash(f'Warning noted for @{user.get("username")}. They will see it on their page.', 'success')
            elif action == 'shadow_user':
                username = (request.form.get('username') or '').strip().lstrip('@')
                user = get_user_by_username(username) if username else None
                if not user:
                    flash('Could not find that member.', 'error')
                elif not _can_touch_account(user):
                    flash('You cannot shadow that account.', 'error')
                else:
                    from app.models.users import set_shadow_ban
                    set_shadow_ban(user['id'], True, actor)
                    flash(f'@{user.get("username")} is shadowed. A reviewer can reverse this.', 'success')
            else:
                flash('Unknown moderation action.', 'error')
        except ValueError as exc:
            flash(str(exc), 'error')
        except Exception as exc:
            flash(f'Could not complete that action: {exc}', 'error')
        return redirect(url_for('church.moderation_desk'))

    comments = fetch_moderation_comments_queue(limit=80, status_filter='all')
    from app.models.social import list_recent_wall_posts
    posts = list_recent_wall_posts(session.get('user_id'), limit=24)
    prayers = []
    try:
        from app.models.db import get_db
        import pymysql
        cur = get_db().cursor(pymysql.cursors.DictCursor)
        cur.execute(
            """
            SELECT p.id, p.title, p.description AS body, p.date_posted,
                   COALESCE(u.username, p.contributor_name, '') AS username
            FROM prayers p
            LEFT JOIN users u ON COALESCE(p.user_id, p.created_by) = u.id
            WHERE COALESCE(p.status, 'approved') NOT IN
                  ('rejected', 'deleted', 'removed', 'spam', 'hidden')
              AND COALESCE(p.moderation_hidden, 0) = 0
            ORDER BY p.date_posted DESC
            LIMIT 16
            """
        )
        prayers = list(cur.fetchall() or [])
    except Exception:
        prayers = []
    my_actions = mod.list_actions(status='active', actor_id=session['user_id'], limit=20)
    from app.models.flags import open_count
    return render_template(
        'church/moderation_desk.html',
        comments=comments,
        posts=posts,
        prayers=prayers,
        my_actions=my_actions,
        can_review=mod.can_review_moderation(),
        site_mod=site_mod,
        open_flags=open_count(),
    )


@church_bp.route('/moderation/flags', methods=['GET', 'POST'])
@login_required
@permission_required('moderate_site', 'moderate_content')
def moderation_flags():
    """Report queue: Hide / Dismiss / Restore. Every decision is in the ledger + audit log."""
    from app.models import flags
    mod.ensure_tables()
    if request.method == 'POST':
        actor = session['user_id']
        kind = (request.form.get('content_kind') or '').strip()
        decision = (request.form.get('decision') or '').strip()
        note = (request.form.get('note') or '').strip()[:400]
        try:
            content_id = int(request.form.get('content_id') or 0)
        except (TypeError, ValueError):
            content_id = 0
        if not mod.can_moderate_site() and kind not in mod.CONTENT_MOD_KINDS and kind != 'comment':
            flash('That item needs a site moderator.', 'error')
        elif not content_id:
            flash('Missing item.', 'error')
        else:
            try:
                ok, msg = flags.resolve(
                    kind, content_id, decision, actor,
                    table=(request.form.get('content_table') or '').strip() or None,
                    comment_type=(request.form.get('comment_type') or '').strip() or None,
                    note=note,
                )
                flash(msg, 'success' if ok else 'error')
            except Exception as exc:
                flash(f'Could not complete that: {exc}', 'error')
        return redirect(url_for('church.moderation_flags', status=request.args.get('status') or 'open'))

    status = (request.args.get('status') or 'open').strip()
    if status not in ('open', 'hidden', 'dismissed', 'restored'):
        status = 'open'
    return render_template(
        'church/moderation_flags.html',
        targets=flags.list_targets(status=status),
        status_filter=status,
        removed=mod.list_removed(limit=40),
        wordlist_hits=flags.list_wordlist_hits(limit=25),
        categories=flags.REPORT_CATEGORIES,
        site_mod=mod.can_moderate_site(),
        can_review=mod.can_review_moderation(),
    )


@church_bp.route('/moderation/restore', methods=['POST'])
@login_required
@permission_required('moderate_site', 'moderate_content')
def moderation_restore():
    """Undo a hide or soft delete straight from the ledger row."""
    action_id = int(request.form.get('action_id') or 0)
    row = mod.get_action(action_id) if action_id else None
    if not row or row.get('status') != 'active' or row.get('action_type') not in mod.HIDE_ACTIONS:
        flash('Nothing to restore there.', 'error')
        return redirect(url_for('church.moderation_flags'))
    kind = row.get('target_kind') or ''
    if not mod.can_moderate_site() and kind not in mod.CONTENT_MOD_KINDS and kind != 'comment':
        flash('That item needs a site moderator.', 'error')
        return redirect(url_for('church.moderation_flags'))
    try:
        ok, msg = mod.restore_target(
            kind, int(row.get('target_id') or 0), session['user_id'],
            (request.form.get('note') or 'Restored').strip()[:400],
            table=row.get('target_table'),
        )
        if ok:
            from app.models.flags import _set_status
            try:
                _set_status(kind, int(row.get('target_id') or 0), row.get('target_table'), 'restored',
                            session['user_id'], from_status=('open', 'hidden'))
            except Exception:
                pass
            from app.models.log import log_change
            log_change(session['user_id'], 'moderation_restore', target_id=int(row.get('target_id') or 0),
                       change_details=f"Restored {kind} #{row.get('target_id')} (ledger #{action_id})")
        flash(msg, 'success' if ok else 'error')
    except Exception as exc:
        flash(f'Could not restore that: {exc}', 'error')
    return redirect(url_for('church.moderation_flags'))


@church_bp.route('/moderation/review', methods=['GET', 'POST'])
@login_required
@permission_required('review_moderation')
def moderation_review():
    mod.ensure_tables()
    if request.method == 'POST':
        action_id = int(request.form.get('action_id') or 0)
        decision = (request.form.get('decision') or '').strip()
        note = (request.form.get('note') or '').strip()
        try:
            if decision == 'reverse':
                flash(mod.reverse_action(action_id, session['user_id'], note), 'success')
            elif decision == 'uphold':
                flash(mod.uphold_action(action_id, session['user_id']), 'success')
            else:
                flash('Pick reverse or looks good.', 'error')
        except ValueError as exc:
            flash(str(exc), 'error')
        except Exception as exc:
            flash(f'Could not review that: {exc}', 'error')
        return redirect(url_for('church.moderation_review', status=request.args.get('status') or 'active'))

    status = (request.args.get('status') or 'active').strip()
    if status not in ('active', 'reversed', 'upheld', 'all'):
        status = 'active'
    rows = mod.list_actions(status=status, limit=120)
    return render_template(
        'church/moderation_review.html',
        rows=rows,
        status_filter=status,
        can_moderate=mod.can_moderate_site(),
    )
