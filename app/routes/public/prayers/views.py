# MYVINECHURCH.ONLINE/app/routes/public/prayers/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/prayers/views.py
# File name: views.py
# Brief, detailed purpose: Public Prayers routes for unauthenticated guests only.
# - Listing shows only public prayers (with creator_name).
# - Detail page supports guest responses/replies (one-level) + potluck-style censorship.
# - Logged-in users are redirected to private prayers.
# - Uses local queries.py, forms.py and utils.py for modularity.
# - 100% rebuilt clean version - identical structure and style to the working public/events/views.py gold standard.
# - FIXED: Correct nested blueprint endpoints, response aliasing for new template, creator_name handling, and clean production code (debug prints removed).

from flask import render_template, abort, request, flash, redirect, url_for, session
import pymysql

from . import prayers_bp
from .queries import get_public_prayers, get_public_prayer, create_guest_prayer_request
from .forms import validate_guest_comment_form, validate_guest_prayer_request_form
from .utils import censor_public_content

from app.models.db import get_db
from app.utils.helpers import censor_text, contains_censored_word
from app.utils.comment_moderation import (
    public_comments_enabled, fetch_public_comments, insert_public_comment,
)


# ----------------------------------------------------------------------
# Public Prayers Listing (Guests Only)
# ----------------------------------------------------------------------
@prayers_bp.route('/', methods=['GET', 'POST'])
def public_prayers():
    """Public prayers listing — approved requests plus guest submission form."""
    if 'user_id' in session and request.method == 'GET':
        return redirect(url_for('prayers.prayers'))

    if request.method == 'POST' and request.form.get('action') == 'submit_request':
        clean = validate_guest_prayer_request_form(request.form)
        if clean:
            try:
                create_guest_prayer_request(
                    clean['title'],
                    clean['description'],
                    clean['contributor_name'],
                    request.remote_addr,
                )
                flash(
                    'Thank you — your prayer request was received and will appear after a brief review.',
                    'success',
                )
            except Exception:
                flash('Failed to submit your prayer request. Please try again.', 'error')
        return redirect(url_for('public.public_prayers.public_prayers'))

    prayers = get_public_prayers()

    # Censorship first
    prayers = censor_public_content(prayers)

    # Prepare data for template
    for p in prayers:
        p['formatted_date'] = p.get('date_posted').strftime('%B %d, %Y') if p.get('date_posted') else 'Unknown'
        p['posted_by'] = p.get('creator_name', 'Anonymous')

    return render_template('public/prayers/prayers.html', prayers=prayers)


# ----------------------------------------------------------------------
# Public Single Prayer Detail (Guests Only + Responses/Replies)
# ----------------------------------------------------------------------
@prayers_bp.route('/<int:prayer_id>', methods=['GET', 'POST'])
def public_prayer_detail(prayer_id):
    """Public single prayer detail with guest responses/replies."""
    if 'user_id' in session and request.method == 'GET':
        return redirect(url_for('prayers.view_prayer', prayer_id=prayer_id))

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    prayer = get_public_prayer(prayer_id)
    if not prayer:
        abort(404)

    # Censor content for public view
    prayer['title']       = censor_text(prayer.get('title', ''))
    prayer['description'] = censor_text(prayer.get('description', ''))

    viewer_ip = request.remote_addr
    viewer_uid = session.get('user_id')
    comments_enabled = public_comments_enabled()
    responses = fetch_public_comments('prayer', prayer_id, viewer_ip, viewer_uid)

    # Handle POST - guest response or reply
    if request.method == 'POST':
        action = request.form.get('action')

        if action in ('comment', 'reply'):
            if not comments_enabled:
                flash('Comments are temporarily disabled.', 'error')
            else:
                clean = validate_guest_comment_form(request.form)
                if not clean:
                    return redirect(url_for('public.public_prayers.public_prayer_detail', prayer_id=prayer_id))
                if insert_public_comment(
                    'prayer', prayer_id, clean['name'], clean['comment'], clean.get('parent_id'),
                    ip=viewer_ip, user_id=viewer_uid,
                ):
                    flash('Response posted successfully!', 'success')
                else:
                    flash('Failed to post response.', 'error')

        # Always redirect using the CORRECT nested blueprint endpoint
        return redirect(url_for('public.public_prayers.public_prayer_detail', prayer_id=prayer_id))

    return render_template('public/prayers/view_prayer.html',
                           prayer=prayer,
                           responses=responses,
                           comments_enabled=comments_enabled)


