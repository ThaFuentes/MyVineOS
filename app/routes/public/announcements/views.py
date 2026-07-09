# MYVINECHURCH.ONLINE/app/routes/public/announcements/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/announcements/views.py
# File name: views.py
# Brief, detailed purpose: Public Announcements routes for unauthenticated guests only.
# - 100% rebuilt to match the working public/events/views.py gold standard exactly.
# - FIXED: announcement['comments.html'] -> announcement['comments'] so the template can see the comments.
# - Listing shows only public + active announcements with creator_name.
# - Detail page supports guest comments/replies (one-level).
# - Logged-in users are redirected to private announcements.
# - All debug prints removed for production cleanliness.
# - Uses local queries.py, forms.py and utils.py for modularity.

from flask import render_template, abort, request, flash, redirect, url_for, session
import pymysql

from . import announcements_bp
from .queries import get_public_announcements, get_public_announcement
from .forms import validate_guest_comment_form
from .utils import censor_public_content

from app.models.db import get_db
from app.utils.helpers import censor_text
from app.utils.comment_moderation import (
    public_comments_enabled, fetch_public_comments, insert_public_comment, map_comments_legacy,
)


# ----------------------------------------------------------------------
# Public Announcements Listing (Guests Only)
# ----------------------------------------------------------------------
@announcements_bp.route('/')
def public_announcements():
    """Public announcements listing - logged-in users are redirected to the private announcements dashboard."""
    if 'user_id' in session:
        return redirect(url_for('announcements.announcements'))

    # Guest view only
    announcements = get_public_announcements()
    announcements = censor_public_content(announcements)

    # Prepare data for template - SAFE date formatting + creator_name fallback
    for a in announcements:
        # Safe date formatting (handles both datetime objects and strings)
        posted = a.get('created_at')
        if posted:
            if hasattr(posted, 'strftime'):
                a['datetime'] = posted.strftime('%B %d, %Y')
            else:
                a['datetime'] = str(posted)[:10]
        else:
            a['datetime'] = 'Unknown'

        # Guarantee creator_name and posted_by
        a['creator_name'] = a.get('creator_name') or a.get('posted_by') or 'Anonymous'
        a['posted_by'] = a['creator_name']

    return render_template('public/announcements/announcements.html', announcements=announcements)


# ----------------------------------------------------------------------
# Public Single Announcement Detail (Guests Only + Comments/Replies)
# ----------------------------------------------------------------------
@announcements_bp.route('/<int:ann_id>', methods=['GET', 'POST'])
def public_announcement_detail(ann_id):
    """Public single announcement detail with guest comments/replies."""
    if 'user_id' in session and request.method == 'GET':
        return redirect(url_for('announcements.view_announcement', ann_id=ann_id))

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    announcement = get_public_announcement(ann_id)
    if not announcement:
        abort(404)

    # Censor content for public view
    announcement['title']   = censor_text(announcement.get('title', ''))
    announcement['content'] = censor_text(announcement.get('content', ''))

    viewer_ip = request.remote_addr
    viewer_uid = session.get('user_id')
    comments_enabled = public_comments_enabled()
    announcement['comments'] = map_comments_legacy(
        fetch_public_comments('announcement', ann_id, viewer_ip, viewer_uid)
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
                    'announcement', ann_id, clean['name'], clean['comment'], clean.get('parent_id'),
                    ip=viewer_ip, user_id=viewer_uid,
                ):
                    flash('Comment posted successfully!', 'success')
                elif clean:
                    flash('Failed to post comment.', 'error')

        # Always redirect using the CORRECT nested blueprint endpoint
        return redirect(url_for('public.public_announcements.public_announcement_detail', ann_id=ann_id))

    return render_template('public/announcements/view_announcement.html',
                           announcement=announcement, comments_enabled=comments_enabled)


# print(" MYVINECHURCH.ONLINE public/announcements/views.py loaded successfully (comments key fixed + Events gold standard applied)")