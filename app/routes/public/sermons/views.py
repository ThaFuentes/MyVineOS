# MYVINECHURCH.ONLINE/app/routes/public/sermons/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/sermons/views.py
# File name: views.py
# Brief, detailed purpose: Public Sermons routes for unauthenticated guests only.
# - 100% rebuilt to match the working public/events/views.py gold standard exactly.
# - FIXED: sermon['comments.html'] → sermon['comments'] so the template can see the comments.
# - Listing safely formats uploaded_at and sets posted_by/creator_name.
# - Detail page now correctly loads and passes comments (guest comments + replies + admin delete).
# - All url_for calls use correct nested blueprint endpoint 'public.public_sermons.public_sermon_detail'.
# - Production-clean (no debug prints).

from flask import render_template, abort, request, flash, redirect, url_for, session
import pymysql

from . import sermons_bp
from .queries import get_public_sermons, get_public_sermon
from .forms import validate_guest_comment_form
from .utils import censor_public_content

from app.models.db import get_db
from app.utils.helpers import censor_text
from app.utils.comment_moderation import (
    public_comments_enabled, fetch_public_comments, insert_public_comment, map_comments_legacy,
)


# ----------------------------------------------------------------------
# Public Sermons Listing (Guests Only)
# ----------------------------------------------------------------------
@sermons_bp.route('/')
def public_sermons():
    """Public sermons listing – logged-in users are redirected to private dashboard."""
    if 'user_id' in session:
        return redirect(url_for('sermons.sermons'))

    # Guest view only
    sermons = get_public_sermons()
    sermons = censor_public_content(sermons)

    # Prepare data for template – SAFE date formatting + creator_name fallback
    for s in sermons:
        # Safe date formatting (handles both datetime objects and strings)
        uploaded_at = s.get('uploaded_at')
        if uploaded_at:
            if hasattr(uploaded_at, 'strftime'):
                s['datetime'] = uploaded_at.strftime('%B %d, %Y')
            else:
                # It's a string (common with pymysql)
                s['datetime'] = str(uploaded_at)[:10]  # take YYYY-MM-DD part
        else:
            s['datetime'] = 'Unknown'

        # Creator name – use creator_name first, then fallback
        s['posted_by'] = s.get('creator_name') or 'Anonymous'

    return render_template('public/sermons/sermons.html', sermons=sermons)


# ----------------------------------------------------------------------
# Public Single Sermon Detail (Guests Only + Comments/Replies + Admin Delete)
# ----------------------------------------------------------------------
@sermons_bp.route('/<int:sermon_id>', methods=['GET', 'POST'])
def public_sermon_detail(sermon_id):
    """Public single sermon detail with guest comments/replies and admin delete capability."""
    if 'user_id' in session and request.method == 'GET':
        return redirect(url_for('sermons.view_sermon', sermon_id=sermon_id))

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    sermon = get_public_sermon(sermon_id)
    if not sermon:
        abort(404)

    # Censor content for public view
    sermon['title']   = censor_text(sermon.get('title', ''))
    sermon['details'] = censor_text(sermon.get('details', ''))
    sermon['notes']   = censor_text(sermon.get('notes', ''))

    viewer_ip = request.remote_addr
    viewer_uid = session.get('user_id')
    comments_enabled = public_comments_enabled()
    sermon['comments'] = map_comments_legacy(
        fetch_public_comments('sermon', sermon_id, viewer_ip, viewer_uid)
    )

    # Handle POST
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'delete' and session.get('role') in ['Owner', 'Admin']:
            comment_id = request.form.get('comment_id')
            try:
                cur.execute("DELETE FROM sermon_comments WHERE id = %s", (comment_id,))
                db.commit()
                flash('Comment deleted.', 'success')
            except Exception:
                flash('Failed to delete comment.', 'error')

        elif action in ('comment', 'reply'):
            if not comments_enabled:
                flash('Comments are temporarily disabled.', 'error')
            else:
                clean = validate_guest_comment_form(request.form)
                if clean and insert_public_comment(
                    'sermon', sermon_id, clean['name'], clean['comment'], clean.get('parent_id'),
                    ip=viewer_ip, user_id=viewer_uid,
                ):
                    flash('Comment posted successfully!', 'success')
                elif clean:
                    flash('Failed to post comment.', 'error')

        # Always redirect using the CORRECT nested blueprint endpoint
        return redirect(url_for('public.public_sermons.public_sermon_detail', sermon_id=sermon_id))

    return render_template('public/sermons/view_sermon.html',
                           sermon=sermon, comments_enabled=comments_enabled)


# print(" MYVINECHURCH.ONLINE public/sermons/views.py loaded successfully (comments key fixed + Events gold standard applied)")