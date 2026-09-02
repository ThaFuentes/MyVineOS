# Follow, block, messages, photos, links on church/member pages.

from flask import flash, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.utils import secure_filename

from app.models import church_community as cc
from app.models import social as social_model
from app.models.log import log_change
from app.utils.decorators import login_required
from app.utils.helpers import contains_censored_word

from . import church_bp


def _unknown():
    flash('That page isn’t here.', 'error')
    return redirect(url_for('church.church_home'))


@church_bp.route('/post/<int:post_id>/moderate', methods=['POST'])
@login_required
def moderate_wall_post(post_id):
    from app.models import moderation as mod
    from flask import abort
    if not mod.can_moderate_walls():
        abort(403)
    action = (request.form.get('action') or '').strip()
    reason = (request.form.get('reason') or '').strip()
    actor = session['user_id']
    try:
        if action == 'shadow':
            ok, msg = mod.shadow_post(post_id, actor, reason)
        elif action == 'unshadow':
            ok, msg = mod.unshadow_post(post_id, actor)
        elif action == 'hide':
            ok, msg = mod.hide_post(post_id, actor, reason)
        else:
            ok, msg = False, 'Unknown moderation action.'
    except Exception as exc:
        ok, msg = False, str(exc)
    flash(msg, 'success' if ok else 'error')
    nxt = (request.form.get('next') or '').strip()
    if nxt.startswith('/') and not nxt.startswith('//'):
        return redirect(nxt)
    return redirect(url_for('church.church_home'))


@church_bp.route('/u/<username>/family', methods=['POST'])
@login_required
def family_request(username):
    from app.models import family_links as fam
    user = cc.get_user_by_username(username)
    if not user:
        return _unknown()
    try:
        ok, msg = fam.request_link(
            session['user_id'], user['id'],
            request.form.get('relation') or '',
            show_on_page=request.form.get('show_on_page') != '0',
        )
    except ValueError as exc:
        ok, msg = False, str(exc)
    flash(msg, 'success' if ok else 'error')
    return redirect(url_for('church.member_page', username=username))


@church_bp.route('/family/<int:relation_id>/respond', methods=['POST'])
@login_required
def family_respond(relation_id):
    from app.models import family_links as fam
    accept = request.form.get('accept') != '0'
    ok, msg = fam.respond_link(
        relation_id, session['user_id'], accept,
        show_on_page=request.form.get('show_on_page') != '0',
    )
    flash(msg, 'success' if ok else 'error')
    nxt = (request.form.get('next') or '').strip()
    if nxt.startswith('/') and not nxt.startswith('//'):
        return redirect(nxt)
    return redirect(url_for('church.member_page', username=session.get('username') or ''))


@church_bp.route('/family/<int:relation_id>/remove', methods=['POST'])
@login_required
def family_remove(relation_id):
    from app.models import family_links as fam
    ok, msg = fam.remove_link(relation_id, session['user_id'])
    flash(msg, 'success' if ok else 'error')
    nxt = (request.form.get('next') or '').strip()
    if nxt.startswith('/') and not nxt.startswith('//'):
        return redirect(nxt)
    return redirect(url_for('church.member_page', username=session.get('username') or ''))


@church_bp.route('/u/<username>/child-privacy', methods=['POST'])
@login_required
def child_privacy(username):
    from app.models import family_links as fam
    user = cc.get_user_by_username(username)
    if not user:
        return _unknown()
    ok, msg = fam.set_child_privacy(session['user_id'], user['id'], {
        'page_private': request.form.get('page_private') == '1',
        'show_to_visitors': request.form.get('show_to_visitors') == '1',
        'show_in_directory': request.form.get('show_in_directory') == '1',
        'show_family': request.form.get('show_family') == '1',
        'allow_messages': request.form.get('allow_messages') == '1',
    })
    flash(msg, 'success' if ok else 'error')
    return redirect(url_for('church.member_page', username=username))


@church_bp.route('/notices/seen', methods=['POST'])
@login_required
def notices_seen():
    from app.models.notices import mark_notices_seen
    mark_notices_seen(session['user_id'])
    nxt = (request.form.get('next') or '').strip()
    if nxt.startswith('/') and not nxt.startswith('//'):
        return redirect(nxt)
    return redirect(url_for('public.public_dashboard.public_community'))


@church_bp.route('/pin', methods=['POST'])
@login_required
def pin_wall_item():
    owner_type = (request.form.get('owner_type') or '').strip()
    item_type = (request.form.get('item_type') or '').strip()
    try:
        owner_id = int(request.form.get('owner_id') or 0)
        item_id = int(request.form.get('item_id') or 0)
    except (TypeError, ValueError):
        owner_id, item_id = 0, 0
    pinned = request.form.get('pinned') != '0'
    uid = session['user_id']
    allowed = False
    if owner_type == 'member' and owner_id == int(uid):
        allowed = True
    elif owner_type in ('church', 'campus') and cc.can_edit_church_page(owner_id if owner_type == 'campus' else 0):
        allowed = True
    if not allowed:
        flash('You can only pin posts on your own page.', 'error')
    else:
        ok, msg = cc.set_pin(owner_type, owner_id, item_type, item_id, pinned, uid)
        flash(msg, 'success' if ok else 'error')
    nxt = (request.form.get('next') or '').strip()
    if nxt.startswith('/') and not nxt.startswith('//'):
        return redirect(nxt)
    if owner_type == 'member':
        user = cc.get_user_public(uid) or {}
        if user.get('username'):
            return redirect(url_for('church.member_page', username=user['username']))
    if owner_type == 'campus' and owner_id:
        return redirect(url_for('church.church_home', campus_id=owner_id))
    return redirect(url_for('church.church_home'))


@church_bp.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_wall_post(post_id):
    ok, msg = social_model.delete_post(post_id, session['user_id'])
    if ok:
        log_change(session['user_id'], 'delete_community_post', target_id=post_id, change_details='Removed a wall post')
    flash(msg, 'success' if ok else 'error')
    nxt = (request.form.get('next') or '').strip()
    if nxt.startswith('/') and not nxt.startswith('//'):
        return redirect(nxt)
    username = session.get('username') or ''
    if username:
        return redirect(url_for('church.member_page', username=username))
    return redirect(url_for('church.church_home'))


@church_bp.route('/u/<username>/follow', methods=['POST'])
@login_required
def follow_user(username):
    user = cc.get_user_by_username(username)
    if not user or social_model.blocked_either_way(session['user_id'], user['id']):
        return _unknown()
    follow = request.form.get('follow') != '0'
    social_model.set_follow(session['user_id'], user['id'], follow)
    log_change(session['user_id'], 'follow_user' if follow else 'unfollow_user', target_id=user['id'])
    return redirect(url_for('church.member_page', username=username))


@church_bp.route('/u/<username>/block', methods=['POST'])
@login_required
def block_user(username):
    user = cc.get_user_by_username(username)
    if not user:
        return _unknown()
    block = request.form.get('block') != '0'
    social_model.set_block(session['user_id'], user['id'], block)
    log_change(session['user_id'], 'block_user' if block else 'unblock_user', target_id=user['id'])
    return redirect(url_for('church.church_home') if block else url_for('church.member_page', username=username))


@church_bp.route('/message', methods=['POST'])
@login_required
def message_church():
    from app.models import church_community as cc_mod
    uid = session['user_id']
    campus_id = 0 if cc_mod.single_church_install() else int(request.form.get('campus_id') or 0)
    thread_id = social_model.get_or_start_church_thread(uid, campus_id)
    if not thread_id:
        flash('Couldn’t open a note to the church. Try again in a moment.', 'error')
        return redirect(url_for('church.church_home'))
    log_change(uid, 'start_church_dm', target_id=thread_id, change_details='Opened a church page message')
    return redirect(url_for('church.messages_thread', thread_id=thread_id))


@church_bp.route('/u/<username>/message', methods=['POST'])
@login_required
def start_message(username):
    user = cc.get_user_by_username(username)
    me = session['user_id']
    if not user or int(user['id']) == int(me):
        return _unknown()
    space = cc.get_member_space(user['id']) or {}
    if not space.get('allow_messages'):
        flash('They’re not receiving notes right now.', 'info')
        return redirect(url_for('church.member_page', username=username))
    if social_model.blocked_either_way(me, user['id']):
        return _unknown()
    thread_id = social_model.get_or_start_thread(me, user['id'])
    log_change(me, 'start_dm', target_id=thread_id, change_details='Opened a message thread')
    return redirect(url_for('church.messages_thread', thread_id=thread_id))


@church_bp.route('/messages/<int:thread_id>', methods=['GET', 'POST'])
@login_required
def messages_thread(thread_id):
    me = session['user_id']
    thread = social_model.get_thread(thread_id, me)
    if not thread:
        return _unknown()
    if request.method == 'POST':
        ok, msg = social_model.send_message(thread_id, me, request.form.get('body') or '')
        if not ok:
            flash(msg, 'error')
        return redirect(url_for('church.messages_thread', thread_id=thread_id))
    social_model.mark_thread_read(thread_id, me)
    church_thread = social_model.is_church_thread(thread)
    room_thread = social_model.is_room_thread(thread)
    other = {}
    thread_title = 'Note'
    thread_kicker = ''
    other_page_url = ''
    pic_url = ''
    compose_hint = 'Write a note…'
    church = ''
    members = []
    mine = {}
    people = []
    if room_thread:
        thread_title = (thread.get('title') or '').strip() or ('Open note' if thread.get('thread_kind') == 'open' else 'Group note')
        thread_kicker = 'Open note — anyone in this church can join' if thread.get('thread_kind') == 'open' else 'Group note — invite only'
        compose_hint = 'Write the group…'
        members = social_model.list_room_members(thread_id)
        mine = social_model.membership(thread_id, me) or {}
        people = cc.find_people('', viewer_id=me, limit=40)
    elif church_thread:
        from app.models import church_community as cc_mod
        church = cc_mod.church_name()
        starter = int(thread.get('starter_id') or thread.get('user_low') or 0)
        if int(me) == starter:
            thread_title = church
            thread_kicker = 'Church office'
            other_page_url = url_for('church.church_home')
            pic_url = social_model.church_portrait_url(int(thread.get('campus_id') or 0))
            compose_hint = f'A note for {church}…'
        else:
            starter_user = cc.get_user_public(starter) or {}
            name = f"{(starter_user.get('first_name') or '').strip()} {(starter_user.get('last_name') or '').strip()}".strip()
            thread_title = name or starter_user.get('username') or 'Member'
            thread_kicker = f'Writing {church}'
            other = starter_user
            if starter_user.get('username'):
                other_page_url = url_for('church.member_page', username=starter_user['username'])
            space = cc.get_member_space(starter) or {}
            pic_url = social_model.identity_url(space.get('photo_path'))
            compose_hint = f'Reply as {church}…'
    else:
        other_id = thread['user_high'] if int(thread['user_low']) == int(me) else thread['user_low']
        other = cc.get_user_public(other_id) or {}
        thread_title = (
            f"{(other.get('first_name') or '').strip()} {(other.get('last_name') or '').strip()}".strip()
            or other.get('username')
            or 'Member'
        )
        thread_kicker = 'Private note'
        if other.get('username'):
            other_page_url = url_for('church.member_page', username=other['username'])
        space = cc.get_member_space(other_id) or {}
        pic_url = social_model.identity_url(space.get('photo_path'))
        first = (other.get('first_name') or thread_title).strip()
        compose_hint = f'Write {first} a note…'
        people = []
    from app.utils.note_notify import vapid_public
    return render_template(
        'church/messages_thread.html',
        thread=thread,
        other=other,
        thread_title=thread_title,
        thread_kicker=thread_kicker,
        other_page_url=other_page_url,
        pic_url=pic_url,
        initials=social_model._initials(thread_title),
        compose_hint=compose_hint,
        church_name=church,
        church_thread=church_thread,
        room_thread=room_thread,
        members=members,
        mine=mine,
        people=people if room_thread else [],
        vapid_public=vapid_public(),
        messages=social_model.list_thread_messages(thread_id, me),
    )


def _ids_from_form():
    ids = []
    for raw in request.form.getlist('user_ids'):
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    return ids


@church_bp.route('/notes/new', methods=['POST'])
@login_required
def notes_new():
    uid = session['user_id']
    open_join = request.form.get('join') == 'open'
    tid, err = social_model.create_room(uid, request.form.get('title') or '', open_join, _ids_from_form())
    if not tid:
        flash(err or 'Could not start that note.', 'error')
        return redirect(url_for('church.messages'))
    log_change(uid, 'create_note_room', target_id=tid, change_details=request.form.get('title') or '')
    flash('Open note is live — anyone in this church can join.' if open_join else 'Group note started. Invited people have to accept.', 'success')
    return redirect(url_for('church.messages_thread', thread_id=tid))


@church_bp.route('/notes/<int:thread_id>/invite', methods=['POST'])
@login_required
def notes_invite(thread_id):
    ok, msg = False, 'Pick someone.'
    for uid in _ids_from_form():
        ok, msg = social_model.invite_to_room(thread_id, session['user_id'], uid)
    flash(msg, 'success' if ok else 'error')
    return redirect(url_for('church.messages_thread', thread_id=thread_id))


@church_bp.route('/notes/<int:thread_id>/accept', methods=['POST'])
@login_required
def notes_accept(thread_id):
    ok, msg = social_model.accept_invite(thread_id, session['user_id'])
    flash(msg, 'success' if ok else 'error')
    if ok:
        return redirect(url_for('church.messages_thread', thread_id=thread_id))
    return redirect(url_for('church.messages'))


@church_bp.route('/notes/<int:thread_id>/decline', methods=['POST'])
@login_required
def notes_decline(thread_id):
    ok, msg = social_model.decline_invite(thread_id, session['user_id'])
    flash(msg, 'success' if ok else 'info')
    return redirect(url_for('church.messages'))


@church_bp.route('/notes/<int:thread_id>/join', methods=['POST'])
@login_required
def notes_join(thread_id):
    ok, msg = social_model.join_open_room(thread_id, session['user_id'])
    flash(msg, 'success' if ok else 'error')
    if ok:
        return redirect(url_for('church.messages_thread', thread_id=thread_id))
    return redirect(url_for('church.messages'))


@church_bp.route('/notes/<int:thread_id>/leave', methods=['POST'])
@login_required
def notes_leave(thread_id):
    ok, msg = social_model.leave_room(thread_id, session['user_id'])
    flash(msg, 'success' if ok else 'error')
    return redirect(url_for('church.messages'))


@church_bp.route('/notes/<int:thread_id>/notify', methods=['POST'])
@login_required
def notes_notify(thread_id):
    social_model.set_room_notify(
        thread_id,
        session['user_id'],
        email=request.form.get('notify_email') == '1',
        push=request.form.get('notify_push') != '0',
    )
    flash('Notification preferences saved.', 'success')
    return redirect(url_for('church.messages_thread', thread_id=thread_id))


@church_bp.route('/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    from flask import jsonify
    from app.utils.note_notify import save_subscription
    data = request.get_json(silent=True) or {}
    keys = data.get('keys') or {}
    ok = save_subscription(
        session['user_id'],
        data.get('endpoint') or '',
        keys.get('p256dh') or '',
        keys.get('auth') or '',
    )
    return jsonify({'ok': bool(ok)}), 200 if ok else 400


@church_bp.route('/push/vapid-key')
@login_required
def push_vapid_key():
    from flask import jsonify
    from app.utils.note_notify import vapid_public
    return jsonify({'publicKey': vapid_public()})


@church_bp.route('/photos/<int:photo_id>')
def serve_photo(photo_id):
    from flask import current_app
    import os

    row = social_model.get_photo(photo_id)
    if not row:
        return _unknown()
    denied = cc.media_access(row.get('owner_type') or 'church', int(row.get('owner_id') or 0), session.get('user_id'))
    if denied == 'login':
        flash('That page is for church members.', 'info')
        return redirect(url_for('auth.login'))
    if denied:
        return _unknown()
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'page_photos')
    return send_from_directory(folder, secure_filename(row['filename']))


@church_bp.route('/u/<username>/photos', methods=['POST'])
@login_required
def member_photo_add(username):
    user = cc.get_user_by_username(username)
    if not user or int(user['id']) != int(session['user_id']):
        return _unknown()
    ok, msg = social_model.add_photo(
        'member', user['id'], request.files.get('photo'), request.form.get('caption') or '', session['user_id'],
    )
    flash(msg, 'success' if ok else 'error')
    return redirect(url_for('church.member_page', username=username))


@church_bp.route('/u/<username>/photos/<int:photo_id>/delete', methods=['POST'])
@login_required
def member_photo_delete(username):
    user = cc.get_user_by_username(username)
    if not user or int(user['id']) != int(session['user_id']):
        return _unknown()
    social_model.delete_photo(photo_id, 'member', user['id'])
    return redirect(url_for('church.member_page', username=username))


@church_bp.route('/photos', methods=['POST'])
@login_required
def church_photo_add():
    if not cc.can_edit_church_page():
        flash('Only pastors and admins can add church photos.', 'error')
        return redirect(url_for('church.church_home'))
    campus_id = 0 if cc.single_church_install() else int(request.form.get('campus_id') or 0)
    owner_type = 'campus' if campus_id else 'church'
    ok, msg = social_model.add_photo(
        owner_type, campus_id, request.files.get('photo'), request.form.get('caption') or '', session['user_id'],
    )
    flash(msg, 'success' if ok else 'error')
    if campus_id:
        return redirect(url_for('church.church_home', campus_id=campus_id))
    return redirect(url_for('church.church_home'))


@church_bp.route('/u/<username>/links', methods=['POST'])
@login_required
def member_link_add(username):
    user = cc.get_user_by_username(username)
    if not user or int(user['id']) != int(session['user_id']):
        return _unknown()
    title = request.form.get('title') or ''
    if contains_censored_word(title):
        flash('That title is not allowed.', 'error')
        return redirect(url_for('church.member_page', username=username))
    added = social_model.add_link(
        'member', user['id'],
        request.form.get('kind') or 'website',
        title,
        request.form.get('url') or '',
        request.form.get('note') or '',
        session['user_id'],
    )
    flash('Added to your page.' if added else 'Need a title (and a link for sermons/sites).', 'success' if added else 'error')
    return redirect(url_for('church.member_page', username=username))


@church_bp.route('/u/<username>/links/<int:link_id>/delete', methods=['POST'])
@login_required
def member_link_delete(username):
    user = cc.get_user_by_username(username)
    if not user or int(user['id']) != int(session['user_id']):
        return _unknown()
    social_model.delete_link(link_id, 'member', user['id'])
    return redirect(url_for('church.member_page', username=username))


@church_bp.route('/links', methods=['POST'])
@login_required
def church_link_add():
    if not cc.can_edit_church_page():
        flash('Only pastors and admins can add church links.', 'error')
        return redirect(url_for('church.church_home'))
    campus_id = 0 if cc.single_church_install() else int(request.form.get('campus_id') or 0)
    owner_type = 'campus' if campus_id else 'church'
    added = social_model.add_link(
        owner_type, campus_id,
        request.form.get('kind') or 'website',
        request.form.get('title') or '',
        request.form.get('url') or '',
        request.form.get('note') or '',
        session['user_id'],
    )
    flash('Added.' if added else 'Need a title.', 'success' if added else 'error')
    if campus_id:
        return redirect(url_for('church.church_home', campus_id=campus_id))
    return redirect(url_for('church.church_home'))
