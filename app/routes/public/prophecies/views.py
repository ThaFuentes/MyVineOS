# MYVINECHURCH.ONLINE/app/routes/public/prophecies/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/prophecies/views.py
# File name: views.py
# Brief, detailed purpose: Public Prophecies routes for unauthenticated guests only.
# • 100% rebuilt to match the working public/events/views.py gold standard exactly.
# • FIXED: prophecy['comments.html'] → prophecy['comments'] so the template can see the comments.
# • Listing shows only public prophecies with creator_name.
# • Detail page supports guest comments/replies (one-level).
# • Logged-in users are redirected to private prophecies.
# • All debug prints removed for production cleanliness.
# • Uses local queries.py, forms.py and utils.py for modularity.

from flask import render_template, abort, request, flash, redirect, url_for, session
import pymysql

from . import prophecies_bp
from .queries import get_public_prophecies, get_public_prophecy
from .forms import validate_guest_comment_form
from .utils import censor_public_content

from app.models.db import get_db
from app.utils.helpers import censor_text
from app.utils.comment_moderation import (
    public_comments_enabled, fetch_public_comments, insert_public_comment, map_comments_legacy,
)


# ----------------------------------------------------------------------
# Public Prophecies Listing (Guests Only)
# ----------------------------------------------------------------------
@prophecies_bp.route('/')
def public_prophecies():
    """Public prophecies listing – logged-in users are redirected to the private prophecies dashboard."""
    if 'user_id' in session:
        return redirect(url_for('prophecies.list_prophecies'))

    # Guest view only
    prophecies = get_public_prophecies()
    prophecies = censor_public_content(prophecies)

    # Prepare data for template – SAFE date formatting + creator_name fallback
    for p in prophecies:
        # Safe date formatting (handles both datetime objects and strings)
        posted = p.get('created_at')
        if posted:
            if hasattr(posted, 'strftime'):
                p['datetime'] = posted.strftime('%B %d, %Y')
            else:
                p['datetime'] = str(posted)[:10]
        else:
            p['datetime'] = 'Unknown'

        # Guarantee creator_name and posted_by for template compatibility
        p['creator_name'] = p.get('creator_name') or p.get('posted_by') or 'Anonymous'
        p['posted_by'] = p['creator_name']

    return render_template('public/prophecies/prophecies.html', prophecies=prophecies)


# ----------------------------------------------------------------------
# Public Single Prophecy Detail (Guests Only + Comments/Replies)
# ----------------------------------------------------------------------
@prophecies_bp.route('/<int:prophecy_id>', methods=['GET', 'POST'])
def public_prophecy_detail(prophecy_id):
    """Public single prophecy detail with guest comments/replies."""
    if 'user_id' in session and request.method == 'GET':
        return redirect(url_for('prophecies.view_prophecy', prophecy_id=prophecy_id))

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    prophecy = get_public_prophecy(prophecy_id)
    if not prophecy:
        abort(404)

    # Censor content for public view
    prophecy['title']       = censor_text(prophecy.get('title', ''))
    prophecy['description'] = censor_text(prophecy.get('description', ''))

    viewer_ip = request.remote_addr
    viewer_uid = session.get('user_id')
    comments_enabled = public_comments_enabled()
    prophecy['comments'] = map_comments_legacy(
        fetch_public_comments('prophecy', prophecy_id, viewer_ip, viewer_uid)
    )

    # Handle POST - guest comment or reply
    if request.method == 'POST':
        action = request.form.get('action')

        if action in ('comment', 'reply'):
            if not comments_enabled:
                flash('Comments are temporarily disabled.', 'error')
            else:
                clean = validate_guest_comment_form(request.form)
                if clean and insert_public_comment(
                    'prophecy', prophecy_id, clean['name'], clean['comment'], clean.get('parent_id'),
                    ip=viewer_ip, user_id=viewer_uid,
                ):
                    flash('Comment posted successfully!', 'success')
                elif clean:
                    flash('Failed to post comment.', 'error')

        # Always redirect using the CORRECT nested blueprint endpoint
        return redirect(url_for('public.public_prophecies.public_prophecy_detail', prophecy_id=prophecy_id))

    return render_template('public/prophecies/view_prophecy.html',
                           prophecy=prophecy, comments_enabled=comments_enabled)


# print("✅ MYVINECHURCH.ONLINE public/prophecies/views.py loaded successfully (comments key fixed + Events gold standard applied)")