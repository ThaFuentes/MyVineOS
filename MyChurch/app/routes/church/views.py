# Church page (official branch profile), Feed stays at /public/community,
# optional member pages at /church/u/<username>.

from flask import flash, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.utils import secure_filename

from app.models import church_community as cc
from app.models import social as social_model
from app.models.log import log_change
from app.utils.compose import available_compose_types
from app.utils.decorators import login_required
from app.utils.helpers import censor_text, contains_censored_word

from . import church_bp


@church_bp.route('/serve/<token>')
def serve_respond(token):
    """Email accept/decline for Sunday worship or pastoral roles."""
    from app.models.serving import get_ask_by_token, respond_ask
    action = (request.args.get('action') or '').lower()
    assignment = get_ask_by_token(token)
    error = None
    if not assignment:
        error = 'That serving link is not valid.'
    elif action in ('accept', 'decline') and (assignment.get('status') or 'pending') == 'pending':
        try:
            assignment = respond_ask(token, action == 'accept', session.get('user_id'))
        except Exception as exc:
            error = str(exc)
    return render_template(
        'volunteers/respond.html',
        error=error,
        assignment=assignment,
        action=action,
        respond_endpoint='church.serve_respond',
    )


@church_bp.route('/serve/reply', methods=['POST'])
@login_required
def serve_reply():
    from app.models.serving import respond_ask
    token = (request.form.get('token') or '').strip()
    accept = request.form.get('decision') == 'accept'
    nxt = (request.form.get('next') or '').strip()
    try:
        row = respond_ask(token, accept, session['user_id'])
        flash(
            'You’re on for this Sunday.' if accept else 'Marked as can’t make it.',
            'success',
        )
        if accept:
            try:
                from app.models.serving import _send_serving_email
                _send_serving_email(row, kind='accepted')
            except Exception:
                pass
    except Exception as exc:
        flash(str(exc) or 'Could not save that response.', 'error')
    if nxt.startswith('/') and not nxt.startswith('//'):
        return redirect(nxt)
    username = session.get('username') or ''
    if username:
        return redirect(url_for('church.member_page', username=username))
    return redirect(url_for('volunteers.my_schedule'))


def _birthday_iso(user: dict | None) -> str:
    if not user or not user.get('birthday'):
        return ''
    raw = user.get('birthday')
    try:
        if hasattr(raw, 'strftime'):
            return raw.strftime('%Y-%m-%d')
        return str(raw)[:10]
    except Exception:
        return ''


def _birthday_label(user: dict | None) -> str:
    iso = _birthday_iso(user)
    if not iso or not user or not user.get('show_birthday'):
        return ''
    try:
        from datetime import datetime
        return datetime.strptime(iso, '%Y-%m-%d').strftime('%B %d')
    except Exception:
        return iso


def _campus_from_request():
    raw = request.args.get('campus')
    if not raw and request.view_args:
        raw = request.view_args.get('campus_id')
    campus_id = None
    if raw not in (None, '', '0'):
        try:
            campus_id = int(raw)
        except (TypeError, ValueError):
            campus_id = None
    return cc.resolve_campus(campus_id=campus_id, user_id=session.get('user_id'))


def _church_scope_id(raw=None) -> int:
    if cc.single_church_install():
        return 0
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


@church_bp.route('/')
@church_bp.route('/c/<int:campus_id>')
def church_home(campus_id=None):
    """Official church / campus social profile. This is Home — not the Feed, not Apps."""
    if campus_id and cc.single_church_install():
        return redirect(url_for('church.church_home'))
    is_org = campus_id in (None, 0) or cc.single_church_install()
    campus = None
    if is_org:
        campus = None if cc.single_church_install() else cc.main_campus()
        page = cc.get_canonical_church_page(0)
        branches = cc.branch_directory()
    else:
        campus = cc.resolve_campus(campus_id=campus_id)
        page = cc.get_canonical_church_page(campus.get('id') if campus else campus_id)
        branches = []

    gatherings = cc.upcoming_gatherings(campus, limit=2)
    gathering = gatherings[0] if gatherings else cc.empty_gathering()
    upcoming = gatherings[1] if len(gatherings) > 1 else None
    upcoming_service = cc.scheduler_upcoming()
    viewer_id = session.get('user_id')
    space = cc.get_member_space(viewer_id) if viewer_id else None
    about = page.get('about') or (campus.get('notes') if campus else '') or ''
    verse = page.get('verse') or ''
    branch = ''
    if not is_org and campus:
        branch = (campus.get('short_name') or campus.get('name') or '').strip()

    owner_type = 'church' if is_org else 'campus'
    owner_id = 0 if is_org else int((campus or {}).get('id') or 0)
    wall = cc.church_wall(
        include_members=bool(session.get('user_id')),
        limit=28,
        campus_id=0 if is_org else int((campus or {}).get('id') or 0),
    )
    serving = []
    if viewer_id:
        try:
            from app.models.serving import my_serving
            serving = my_serving(viewer_id, upcoming_only=True, limit=24)
        except Exception as exc:
            print(f'church serving: {exc}')
            serving = []
    serving_pending = [a for a in serving if (a.get('status') or '') == 'pending']
    serving_accepted = [a for a in serving if (a.get('status') or '') == 'accepted']
    return render_template(
        'church/church_page.html',
        is_org=is_org,
        campus=campus or {},
        page=page,
        gathering=gathering,
        upcoming=upcoming,
        upcoming_service=upcoming_service,
        contact=cc.profile_contact(campus),
        branches=branches,
        branch_count=len(branches),
        staff=cc.staff_on_page(campus),
        wall=wall,
        rail_updates=wall[:8],
        hero_url=cc.hero_for_profile(),
        church_name=cc.church_name(),
        branch_name=branch,
        about=censor_text(about) if about else '',
        verse=verse,
        can_edit=cc.can_edit_church_page(0 if is_org else int((campus or {}).get('id') or 0)),
        can_post=cc.can_post_church_updates(0 if is_org else int((campus or {}).get('id') or 0)),
        viewer_space=space,
        feed_url=url_for('public.public_dashboard.public_community'),
        apps_url=url_for('dashboard.dashboard'),
        bible_url=url_for('bible.member_study'),
        photos=social_model.list_photos(owner_type, owner_id, limit=4),
        photo_total=social_model.photo_count(owner_type, owner_id),
        photo_album_url=url_for('church.photo_album', owner_type=owner_type, owner_id=owner_id),
        books=social_model.list_links(owner_type, owner_id, 'book'),
        links=social_model.list_links(owner_type, owner_id),
        banner_url=social_model.church_banner_url((page or {}).get('hero_path')),
        avatar_url=social_model.church_avatar_url((page or {}).get('portrait_path')),
        banner_is_default=not bool((page or {}).get('hero_path')),
        avatar_is_default=not bool((page or {}).get('portrait_path')),
        worship=social_model.worship_lineup(owner_id or None, date_str=gathering.get('date_str')),
        palette_style=social_model.palette_style(page),
        banner_x=social_model.banner_focus(page)[0],
        banner_y=social_model.banner_focus(page)[1],
        compose_types=available_compose_types() if viewer_id else [],
        photo_limit=social_model.photo_limit(owner_type),
        owner_type=owner_type,
        owner_id=owner_id,
        serving=serving,
        serving_pending=serving_pending,
        serving_accepted=serving_accepted,
    )


@church_bp.route('/identity/<path:filename>')
def serve_identity(filename):
    from flask import current_app
    import os
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'identity')
    return send_from_directory(folder, secure_filename(filename.split('/')[-1]))


def _safe_next(default: str) -> str:
    nxt = (request.form.get('next') or '').strip()
    if nxt.startswith('/') and not nxt.startswith('//'):
        return nxt
    return default


@church_bp.route('/manage/identity', methods=['POST'])
@login_required
def page_identity():
    slot = (request.form.get('slot') or 'avatar').strip()
    scope = (request.form.get('scope') or 'member').strip()
    campus_id = _church_scope_id(request.form.get('campus_id'))
    upload = request.files.get('photo')
    bx, by = request.form.get('banner_x'), request.form.get('banner_y')
    if scope == 'church':
        if not cc.can_edit_church_page(campus_id):
            flash('You cannot edit this church page.', 'error')
            return redirect(url_for('church.church_home'))
        back = _safe_next(
            url_for('church.church_edit', campus=campus_id) if campus_id else url_for('church.church_edit')
        )
        if bx not in (None, '') and by not in (None, ''):
            social_model.set_banner_focus('church', campus_id, int(float(bx)), int(float(by)))
            if request.headers.get('X-Requested-With') == 'fetch':
                return ('', 204)
            return redirect(back)
        ok, msg = social_model.set_church_identity(campus_id, slot, upload, session.get('user_id'))
        flash(msg, 'success' if ok else 'error')
        return redirect(back)
    back = _safe_next(url_for('church.member_page', username=session.get('username') or ''))
    if bx not in (None, '') and by not in (None, ''):
        social_model.set_banner_focus('member', session['user_id'], int(float(bx)), int(float(by)))
        if request.headers.get('X-Requested-With') == 'fetch':
            return ('', 204)
        return redirect(back)
    ok, msg = social_model.set_member_identity(session['user_id'], slot, upload)
    flash(msg, 'success' if ok else 'error')
    return redirect(back)


@church_bp.route('/messages')
@login_required
def messages():
    from app.models import social as social_mod
    from app.utils.note_notify import vapid_public
    uid = session['user_id']
    return render_template(
        'church/messages_inbox.html',
        threads=social_mod.list_inbox(uid),
        invites=social_mod.list_invites(uid),
        open_rooms=social_mod.list_open_rooms(uid),
        people=cc.find_people('', viewer_id=uid, limit=40),
        vapid_public=vapid_public(),
    )


@church_bp.route('/manage/item', methods=['POST'])
@login_required
def page_item_add():
    scope = (request.form.get('scope') or 'member').strip()
    item_type = (request.form.get('item_type') or 'website').strip()
    campus_id = _church_scope_id(request.form.get('campus_id'))
    uid = session.get('user_id')

    if scope == 'church':
        if not cc.can_edit_church_page(campus_id):
            flash('You cannot edit this church page.', 'error')
            return redirect(url_for('church.church_home'))
        owner_type = 'campus' if campus_id else 'church'
        owner_id = campus_id
        back = url_for('church.church_edit', campus=campus_id) if campus_id else url_for('church.church_edit')
        if item_type == 'photo':
            ok, msg = social_model.add_photo(
                owner_type, owner_id, request.files.get('photo'),
                request.form.get('caption') or request.form.get('note') or '', uid,
            )
            flash(msg, 'success' if ok else 'error')
            return redirect(back)
        kind = item_type if item_type in social_model.LINK_KINDS else 'website'
        added = social_model.add_link(
            owner_type, owner_id, kind,
            request.form.get('title') or '',
            request.form.get('url') or '',
            request.form.get('note') or '',
            uid,
        )
        flash('Added to the church page.' if added else 'Need a title (and a link for sermons/sites).', 'success' if added else 'error')
        return redirect(back)

    back = url_for('church.edit_my_page')
    if item_type == 'photo':
        ok, msg = social_model.add_photo(
            'member', uid, request.files.get('photo'),
            request.form.get('caption') or '', uid,
        )
        flash(msg, 'success' if ok else 'error')
        return redirect(back)
    kind = item_type if item_type in social_model.LINK_KINDS else 'website'
    added = social_model.add_link(
        'member', uid, kind,
        request.form.get('title') or '',
        request.form.get('url') or '',
        request.form.get('note') or '',
        uid,
    )
    flash('Added to your page.' if added else 'Need a title (and a link for sermons/sites).', 'success' if added else 'error')
    return redirect(back)


@church_bp.route('/manage/item/delete', methods=['POST'])
@login_required
def page_item_delete():
    scope = (request.form.get('scope') or 'member').strip()
    kind = (request.form.get('kind') or '').strip()
    item_id = int(request.form.get('item_id') or 0)
    campus_id = _church_scope_id(request.form.get('campus_id'))
    uid = session.get('user_id')
    if scope == 'church':
        if not cc.can_edit_church_page(campus_id):
            flash('You cannot edit this church page.', 'error')
            return redirect(url_for('church.church_home'))
        owner_type = 'campus' if campus_id else 'church'
        owner_id = campus_id
        back = url_for('church.church_edit', campus=campus_id) if campus_id else url_for('church.church_edit')
        if kind == 'photo':
            social_model.delete_photo(item_id, owner_type, owner_id)
        else:
            social_model.delete_link(item_id, owner_type, owner_id)
        flash('Removed.', 'success')
        return redirect(back)
    if kind == 'photo':
        social_model.delete_photo(item_id, 'member', uid)
    else:
        social_model.delete_link(item_id, 'member', uid)
    flash('Removed.', 'success')
    return redirect(url_for('church.edit_my_page'))


@church_bp.route('/edit', methods=['GET', 'POST'])
@login_required
def church_edit():
    raw = request.args.get('campus') or request.form.get('campus')
    campus = None
    campus_id = 0
    if not cc.single_church_install() and raw not in (None, '', '0'):
        campus = cc.resolve_campus(campus_id=int(raw))
        campus_id = campus.get('id') if campus else 0
    if not cc.can_edit_church_page(campus_id):
        flash('You cannot edit this church page.', 'error')
        return redirect(url_for('church.church_home', campus_id=campus_id) if campus_id else url_for('church.church_home'))
    page = cc.get_canonical_church_page(campus_id)
    owner_type = 'campus' if campus_id else 'church'
    edit_url = url_for('church.church_edit', campus=campus_id) if campus_id else url_for('church.church_edit')
    if request.method == 'POST':
        action = (request.form.get('action') or 'save').strip()
        if action == 'add_editor':
            if not cc.can_assign_page_editors(campus_id):
                flash('Only the Owner or a page admin can add editors.', 'error')
                return redirect(edit_url)
            user = None
            raw_id = (request.form.get('user_id') or '').strip()
            uname = (request.form.get('username') or '').strip()
            if raw_id.isdigit():
                from app.models.users import get_user_by_id
                user = get_user_by_id(int(raw_id))
            elif uname:
                user = cc.get_user_by_username(uname)
            if not user:
                flash('Pick a member from the list.', 'error')
                return redirect(edit_url + '#page-people')
            ok, msg = cc.add_page_editor(
                campus_id, user['id'], request.form.get('editor_role') or 'editor', session.get('user_id'),
            )
            flash(msg, 'success' if ok else 'error')
            return redirect(edit_url + '#page-people')
        if action == 'remove_editor':
            if not cc.can_assign_page_editors(campus_id):
                flash('Only the Owner or a page admin can remove editors.', 'error')
                return redirect(edit_url + '#page-people')
            try:
                cc.remove_page_editor(campus_id, int(request.form.get('user_id') or 0))
                flash('Removed from this page people list.', 'success')
            except Exception:
                flash('Could not remove that person.', 'error')
            return redirect(edit_url + '#page-people')
        about = (request.form.get('about') or '').strip()
        verse = (request.form.get('verse') or '').strip()
        if contains_censored_word(f'{about} {verse}'):
            flash('That text contains a prohibited word.', 'error')
            return redirect(edit_url)
        cc.save_church_page(
            campus_id, about, verse, session.get('user_id'),
            colors={
                'accent_color': social_model.hex_or_none(request.form.get('accent_color')),
                'bg_color': social_model.hex_or_none(request.form.get('bg_color')) or (page or {}).get('bg_color'),
                'text_color': social_model.hex_or_none(request.form.get('text_color')) or (page or {}).get('text_color'),
            },
        )
        log_change(
            session.get('user_id'),
            'edit_church_page',
            target_id=campus_id or None,
            change_details=f'Updated church page for campus {campus_id}',
        )
        flash('Saved.', 'success')
        return redirect(edit_url)
    editors = cc.list_page_editors(campus_id)
    taken = {int(e['user_id']) for e in editors}
    choices = []
    try:
        from app.models.users import get_all_users
        for row in get_all_users() or []:
            if (row.get('role') or '') == 'Owner':
                continue
            if int(row.get('id') or 0) in taken:
                continue
            name = f"{(row.get('first_name') or '').strip()} {(row.get('last_name') or '').strip()}".strip()
            choices.append({
                'id': row.get('id'),
                'username': row.get('username') or '',
                'display_name': name or row.get('username') or 'Member',
            })
    except Exception:
        choices = []
    return render_template(
        'church/church_edit.html',
        campus=campus,
        page=page,
        photos=social_model.list_photos(owner_type, campus_id),
        links=social_model.list_links(owner_type, campus_id),
        manage_scope='church',
        allow_photos=True,
        banner_url=social_model.church_banner_url((page or {}).get('hero_path')),
        avatar_url=social_model.church_avatar_url((page or {}).get('portrait_path')),
        banner_is_default=not bool((page or {}).get('hero_path')),
        avatar_is_default=not bool((page or {}).get('portrait_path')),
        banner_x=social_model.banner_focus(page)[0],
        banner_y=social_model.banner_focus(page)[1],
        church_name=cc.church_name(),
        page_editors=editors,
        can_assign_editors=cc.can_assign_page_editors(campus_id),
        campus_id=campus_id,
        member_choices=choices,
        ministry_posters=[] if campus_id else cc.list_automatic_church_posters(),
    )


def _media_denied(reason: str):
    if reason == 'login':
        flash('That page is for church members.', 'info')
        return redirect(url_for('auth.login'))
    if reason == 'private':
        flash('That page is private.', 'info')
        return redirect(url_for('church.church_home'))
    flash('That page does not exist.', 'error')
    return redirect(url_for('church.church_home'))


@church_bp.route('/album/<owner_type>/<int:owner_id>')
def photo_album(owner_type, owner_id):
    kind = (owner_type or '').strip()
    if kind not in ('member', 'church', 'campus'):
        flash('That album does not exist.', 'error')
        return redirect(url_for('church.church_home'))
    denied = cc.media_access(kind, owner_id, session.get('user_id'))
    if denied:
        return _media_denied(denied)
    photos = social_model.list_photos(kind, owner_id)
    if kind == 'member':
        user = cc.get_user_public(owner_id) or {}
        name = f"{(user.get('first_name') or '').strip()} {(user.get('last_name') or '').strip()}".strip()
        title = f"{name or user.get('username') or 'Member'}'s photos"
        back = url_for('church.member_page', username=user.get('username') or '')
    else:
        title = f"{cc.church_name()} photos"
        back = url_for('church.church_home', campus_id=owner_id) if kind == 'campus' and owner_id else url_for('church.church_home')
    return render_template(
        'church/photo_album.html',
        photos=photos,
        album_title=title,
        back_url=back,
    )


@church_bp.route('/pic/<int:photo_id>')
def photo_view(photo_id):
    from app.utils.comment_moderation import fetch_public_comments

    row = social_model.get_photo(photo_id)
    if not row:
        flash('That photo does not exist.', 'error')
        return redirect(url_for('church.church_home'))
    kind = row.get('owner_type') or 'church'
    owner_id = int(row.get('owner_id') or 0)
    denied = cc.media_access(kind, owner_id, session.get('user_id'))
    if denied:
        return _media_denied(denied)
    row['url'] = url_for('church.serve_photo', photo_id=row['id'])
    comments = fetch_public_comments(
        'photo', row['id'],
        viewer_ip=request.remote_addr,
        viewer_user_id=session.get('user_id'),
    )
    for c in comments:
        c['comment'] = c.get('comment') or c.get('comment_text') or ''
    album = url_for('church.photo_album', owner_type=kind, owner_id=owner_id)
    return render_template(
        'church/photo_view.html',
        photo=row,
        comments=comments,
        album_url=album,
        photo_surface='member' if kind == 'member' else 'church',
    )


@church_bp.route('/people')
def people():
    """Find people. Guests only see public pages; members see the church directory."""
    viewer_id = session.get('user_id')
    q = (request.args.get('q') or '').strip()
    return render_template(
        'church/people.html',
        people=cc.find_people(q, viewer_id=viewer_id),
        query=q,
    )


@church_bp.route('/u/<username>')
def member_page(username):
    """Optional member space. Church strip = THIS person's campus, not the viewer's."""
    user = cc.get_user_by_username((username or '').strip())
    if not user:
        flash('That page does not exist.', 'error')
        return redirect(url_for('church.church_home'))
    space = cc.get_member_space(user['id']) or {}
    viewer_id = session.get('user_id')
    is_owner = bool(viewer_id and int(viewer_id) == int(user['id']))
    if not space and is_owner:
        return redirect(url_for('church.create_page'))
    if space and space.get('page_private') and not is_owner:
        flash('That page is private.', 'info')
        return redirect(url_for('church.church_home') if viewer_id else url_for('auth.login'))
    if space and not space.get('show_to_visitors') and not viewer_id and not is_owner:
        flash('That page is for church members.', 'info')
        return redirect(url_for('auth.login'))
    if not space and not viewer_id:
        flash('That page is for church members.', 'info')
        return redirect(url_for('auth.login'))

    context = cc.church_context_for_user(user['id'])
    display = (
        f"{(user.get('first_name') or '').strip()} {(user.get('last_name') or '').strip()}"
    ).strip() or user.get('username')
    if viewer_id and social_model.blocked_either_way(viewer_id, user['id']):
        flash('That page does not exist.', 'error')
        return redirect(url_for('church.church_home'))
    wall = cc.member_wall(user['id'], username=user.get('username') or '', space=space)
    wall_q = (request.args.get('q') or '').strip()
    wall = cc.visible_items(
        wall,
        viewer_id,
        owner_id=user['id'],
        surface='wall',
        query=wall_q,
    )
    sermons = [item for item in wall if item.get('type') == 'sermon']
    serving = []
    if is_owner:
        try:
            from app.models.serving import my_serving
            serving = my_serving(user['id'], upcoming_only=True, limit=24)
        except Exception as exc:
            print(f'member serving: {exc}')
            serving = []
    serving_pending = [a for a in serving if (a.get('status') or '') == 'pending']
    serving_accepted = [a for a in serving if (a.get('status') or '') == 'accepted']
    warnings = []
    if is_owner:
        try:
            from app.models.moderation import active_warnings_for
            warnings = active_warnings_for(user['id'])
        except Exception:
            warnings = []
    return render_template(
        'church/member_page.html',
        owner=user,
        space=space,
        display_name=display,
        is_owner=is_owner,
        church_context=context,
        upcoming_service=context.get('upcoming_service') or cc.scheduler_upcoming(),
        contact=cc.profile_contact(cc.resolve_campus(user_id=user['id'])),
        wall=wall,
        about=censor_text(space.get('about') or '') if space.get('about') else '',
        verse=space.get('favorite_verse') or '',
        banner_url=social_model.identity_url(space.get('banner_path')),
        avatar_url=social_model.identity_url(space.get('photo_path')),
        feed_url=url_for('public.public_dashboard.public_community'),
        photos=social_model.list_photos('member', user['id'], limit=4),
        photo_total=social_model.photo_count('member', user['id']),
        photo_album_url=url_for('church.photo_album', owner_type='member', owner_id=user['id']),
        books=social_model.list_links('member', user['id'], 'book'),
        links=social_model.list_links('member', user['id']),
        badges=social_model.list_badges(user['id']),
        stats=social_model.follow_counts(user['id']) if space.get('show_stats') else None,
        is_following=bool(viewer_id and social_model.is_following(viewer_id, user['id'])),
        allow_messages=bool(space.get('allow_messages')),
        palette_style=social_model.palette_style(space),
        compose_types=available_compose_types() if is_owner else [],
        photo_limit=social_model.photo_limit('member'),
        sermons=sermons,
        banner_x=social_model.banner_focus(space)[0],
        banner_y=social_model.banner_focus(space)[1],
        birthday_label=_birthday_label(user),
        following=social_model.following_preview(user['id'], viewer_id=viewer_id, limit=10),
        wall_q=wall_q,
        wall_searchable=True,
        serving=serving,
        serving_pending=serving_pending,
        serving_accepted=serving_accepted,
        warnings=warnings,
    )


@church_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_page():
    uid = session.get('user_id')
    existing = cc.get_member_space(uid)
    if existing and request.method == 'GET':
        user = cc.get_user_public(uid)
        return redirect(url_for('church.member_page', username=user['username']))
    if request.method == 'POST':
        if request.form.get('not_now'):
            flash('You can create a page later from Home.', 'info')
            return redirect(url_for('church.church_home'))
        about = (request.form.get('about') or '').strip()
        verse = (request.form.get('favorite_verse') or '').strip()
        cc.create_member_space(uid, about=about, favorite_verse=verse)
        cc.update_member_space(uid, {
            'about': about,
            'favorite_verse': verse,
            'show_to_visitors': request.form.get('show_to_visitors') == '1',
            'show_training': request.form.get('show_training') == '1',
            'show_replies': request.form.get('show_replies') == '1',
            'show_follows': request.form.get('show_follows') == '1',
            'show_in_directory': request.form.get('show_in_directory') == '1',
            'page_private': request.form.get('page_private') == '1',
            'allow_messages': request.form.get('allow_messages') == '1',
            'show_stats': request.form.get('show_stats') == '1',
            'accent_color': social_model.hex_or_none(request.form.get('accent_color')),
            'bg_color': social_model.hex_or_none(request.form.get('bg_color')),
            'text_color': social_model.hex_or_none(request.form.get('text_color')),
        })
        log_change(uid, 'create_member_space', target_id=uid, change_details='Created member page')
        user = cc.get_user_public(uid)
        flash('Your page is ready.', 'success')
        return redirect(url_for('church.member_page', username=user['username']))
    me = cc.get_user_public(uid)
    return render_template(
        'church/create_page.html',
        user=me,
        birthday_iso=_birthday_iso(me),
    )


@church_bp.route('/me/edit', methods=['GET', 'POST'])
@login_required
def edit_my_page():
    uid = session.get('user_id')
    space = cc.get_member_space(uid)
    if not space:
        return redirect(url_for('church.create_page'))
    user = cc.get_user_public(uid)
    if request.method == 'POST':
        about = (request.form.get('about') or '').strip()
        verse = (request.form.get('favorite_verse') or '').strip()
        if contains_censored_word(f'{about} {verse}'):
            flash('That text contains a prohibited word.', 'error')
            return redirect(url_for('church.edit_my_page'))
        cc.update_member_space(uid, {
            'about': about,
            'favorite_verse': verse,
            'show_to_visitors': request.form.get('show_to_visitors') == '1',
            'show_training': request.form.get('show_training') == '1',
            'show_replies': request.form.get('show_replies') == '1',
            'show_follows': request.form.get('show_follows') == '1',
            'show_in_directory': request.form.get('show_in_directory') == '1',
            'page_private': request.form.get('page_private') == '1',
            'allow_messages': request.form.get('allow_messages') == '1',
            'show_stats': request.form.get('show_stats') == '1',
            'accent_color': social_model.hex_or_none(request.form.get('accent_color')),
            'bg_color': social_model.hex_or_none(request.form.get('bg_color')) or space.get('bg_color'),
            'text_color': social_model.hex_or_none(request.form.get('text_color')) or space.get('text_color'),
            'hometown': (request.form.get('hometown') or '').strip(),
            'occupation': (request.form.get('occupation') or '').strip(),
            'interests': (request.form.get('interests') or '').strip(),
        })
        from app.models.users import update_user_profile
        bday = (request.form.get('birthday') or '').strip() or None
        update_user_profile(
            uid,
            birthday=bday,
            show_birthday=1 if request.form.get('show_birthday') == '1' else 0,
            updated_by=uid,
        )
        flash('Saved.', 'success')
        return redirect(url_for('church.edit_my_page'))
    return render_template(
        'church/create_page.html',
        space=space,
        editing=True,
        photos=social_model.list_photos('member', uid),
        links=social_model.list_links('member', uid),
        manage_scope='member',
        allow_photos=True,
        banner_url=social_model.identity_url((space or {}).get('banner_path')),
        avatar_url=social_model.identity_url((space or {}).get('photo_path')),
        banner_x=social_model.banner_focus(space)[0],
        banner_y=social_model.banner_focus(space)[1],
        user=user,
        birthday_iso=_birthday_iso(user),
    )
