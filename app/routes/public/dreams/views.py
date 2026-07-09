# MYVINECHURCH.ONLINE/app/routes/public/dreams/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/dreams/views.py
# File name: views.py
# Brief, detailed purpose: Public Dreams & Visions routes for unauthenticated guests only.
# • 100% rebuilt to match the working public/events/views.py gold standard exactly.
# • FIXED: dream['comments.html'] → dream['comments'] so the template can see the comments.
# • Listing shows only public + approved dreams with creator_name.
# • Detail page supports guest comments/replies (one-level).
# • Logged-in users are redirected to private dreams.
# • All debug prints removed for production cleanliness.
# • Uses local queries.py, forms.py and utils.py for modularity.

from flask import render_template, abort, request, flash, redirect, url_for, session
import pymysql

from . import dreams_bp
from .queries import get_public_dreams, get_public_dream
from .forms import validate_guest_comment_form
from .utils import censor_public_content

from app.models.db import get_db
from app.utils.helpers import censor_text
from app.utils.comment_moderation import (
    public_comments_enabled, fetch_public_comments, insert_public_comment, map_comments_legacy,
)


# ----------------------------------------------------------------------
# Public Dreams Listing (Guests Only)
# ----------------------------------------------------------------------
@dreams_bp.route('/')
def public_dreams():
    """Public dreams listing – logged-in users are redirected to the private dreams dashboard."""
    if 'user_id' in session:
        return redirect(url_for('dreams.dreams'))

    # Guest view only
    dreams = get_public_dreams()
    dreams = censor_public_content(dreams)

    # Prepare data for template – SAFE date formatting + creator_name fallback
    for d in dreams:
        # Safe date formatting (handles both datetime objects and strings)
        posted = d.get('date_posted')
        if posted:
            if hasattr(posted, 'strftime'):
                d['datetime'] = posted.strftime('%B %d, %Y')
            else:
                d['datetime'] = str(posted)[:10]
        else:
            d['datetime'] = 'Unknown'

        # Guarantee both creator_name and poster_name (template uses either)
        d['creator_name'] = d.get('creator_name') or d.get('contributor_name') or 'Anonymous'
        d['posted_by'] = d['creator_name']
        d['poster_name'] = d['creator_name']

    return render_template('public/dreams/dreams.html', dreams=dreams)


# ----------------------------------------------------------------------
# Public Single Dream Detail (Guests Only + Comments/Replies)
# ----------------------------------------------------------------------
@dreams_bp.route('/<int:dream_id>', methods=['GET', 'POST'])
def public_dream_detail(dream_id):
    """Public single dream detail with guest comments/replies."""
    if 'user_id' in session and request.method == 'GET':
        return redirect(url_for('dreams.view_dream', dream_id=dream_id))

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    dream = get_public_dream(dream_id)
    if not dream:
        abort(404)

    # Censor content for public view
    dream['title']       = censor_text(dream.get('title', ''))
    dream['description'] = censor_text(dream.get('description', ''))
    dream['notes']       = censor_text(dream.get('notes', ''))

    viewer_ip = request.remote_addr
    viewer_uid = session.get('user_id')
    comments_enabled = public_comments_enabled()
    dream['comments'] = map_comments_legacy(
        fetch_public_comments('dream', dream_id, viewer_ip, viewer_uid)
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
                    'dream', dream_id, clean['name'], clean['comment'], clean.get('parent_id'),
                    ip=viewer_ip, user_id=viewer_uid,
                ):
                    flash('Comment posted successfully!', 'success')
                elif clean:
                    flash('Failed to post comment.', 'error')

        # Always redirect using the CORRECT nested blueprint endpoint
        return redirect(url_for('public.public_dreams.public_dream_detail', dream_id=dream_id))

    return render_template('public/dreams/view_dream.html',
                           dream=dream, comments_enabled=comments_enabled)


# print("✅ MYVINECHURCH.ONLINE public/dreams/views.py loaded successfully (comments key fixed + Events gold standard applied)")