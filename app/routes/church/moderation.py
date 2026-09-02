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
@permission_required('moderate_site')
def moderation_desk():
    mod.ensure_tables()
    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()
        actor = session['user_id']
        try:
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
    my_actions = mod.list_actions(status='active', actor_id=session['user_id'], limit=20)
    return render_template(
        'church/moderation_desk.html',
        comments=comments,
        posts=posts,
        my_actions=my_actions,
        can_review=mod.can_review_moderation(),
    )


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
