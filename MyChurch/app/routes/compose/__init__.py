# Quick-compose posts from Home / Community Feed.

from flask import Blueprint, request, redirect, url_for, render_template, session

from app.utils.decorators import login_required
from app.utils.compose import create_from_compose, available_compose_types

compose_bp = Blueprint('compose', __name__, url_prefix='/compose')


@compose_bp.route('/', methods=['GET'])
@login_required
def compose_form():
    types = available_compose_types()
    preset = (request.args.get('type') or '').strip()
    nxt = (request.args.get('next') or request.referrer or '/public/community').strip()
    if nxt and not nxt.startswith('/'):
        nxt = '/public/community'
    return render_template(
        'compose/compose.html',
        compose_types=types,
        preset=preset,
        next_url=nxt,
    )


@compose_bp.route('/link-preview')
@login_required
def compose_link_preview():
    from flask import jsonify
    from app.utils.link_preview import fetch_link_preview, first_url_in

    raw = (request.args.get('url') or '').strip()
    href = first_url_in(raw) or raw
    data = fetch_link_preview(href)
    if not data:
        return jsonify({'ok': False})
    return jsonify({'ok': True, **data})


@compose_bp.route('/', methods=['POST'])
@login_required
def compose_create():
    _ok, dest = create_from_compose(request.form, request.files)
    if dest and str(dest).startswith('/') and not str(dest).startswith('//'):
        return redirect(dest)
    nxt = (request.form.get('next') or '').strip()
    if nxt.startswith('/') and not nxt.startswith('//'):
        return redirect(nxt)
    return redirect(url_for('church.church_home'))


@compose_bp.route('/reply', methods=['POST'])
def compose_reply():
    """Inline reply. Guests: community/church only. Not on member pages."""
    from flask import flash, session
    from app.utils.comment_moderation import insert_public_comment, COMMENT_TYPES
    from app.utils.helpers import contains_censored_word
    from app.utils.html_sanitize import sanitize_plain_text
    from app.utils.visitor_permissions import visitor_can_comment

    nxt = (request.form.get('next') or request.referrer or '/').strip()
    if not nxt.startswith('/') or nxt.startswith('//'):
        nxt = '/'
    surface = (request.form.get('surface') or 'community').strip()
    kind = (request.form.get('content_type') or '').strip()
    parent_id = request.form.get('parent_id') or ''
    text = sanitize_plain_text(request.form.get('body') or request.form.get('comment') or '')
    uid = session.get('user_id')

    if kind not in COMMENT_TYPES:
        flash('Cannot comment on that.', 'error')
        return redirect(nxt)
    if not parent_id.isdigit():
        flash('Missing post.', 'error')
        return redirect(nxt)
    if not text:
        flash('Write a reply.', 'error')
        return redirect(nxt)
    if contains_censored_word(text) or contains_censored_word(request.form.get('name') or ''):
        flash('That reply has a prohibited word.', 'error')
        return redirect(nxt)
    if surface == 'member' and not uid:
        flash('Sign in to reply on a member page. Guests can reply in Community.', 'info')
        return redirect(url_for('auth.login', next=nxt))
    if not uid:
        area = {
            'prayer': 'prayers', 'announcement': 'announcements', 'event': 'events',
            'sermon': 'sermons', 'dream': 'dreams', 'prophecy': 'prophecies',
            'photo': 'announcements',
            'post': 'announcements', 'quote': 'announcements', 'verse': 'announcements',
            'image': 'announcements', 'book': 'announcements', 'blog': 'announcements',
            'share': 'announcements',
        }.get(kind, '')
        if surface == 'member' or not visitor_can_comment(area):
            flash('Sign in to reply, or use Community.', 'info')
            return redirect(url_for('auth.login', next=nxt))
        name = sanitize_plain_text(request.form.get('name') or '') or 'Guest'
    else:
        name = session.get('username') or 'Member'

    if insert_public_comment(kind, int(parent_id), name, text, ip=request.remote_addr, user_id=uid):
        flash('Reply posted.', 'success')
    else:
        flash('Could not post that reply.', 'error')
    return redirect(nxt)
