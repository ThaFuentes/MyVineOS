# MYVINECHURCH.ONLINE/app/routes/the_gathering/prayers/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/prayers/views.py
# File name: views.py
# Brief, detailed purpose: All prayer routes for the Gathering Place Manager.
# • Dedicated sub-blueprint routes: listing, create/edit, view, delete, comment moderation.
# • Uses prayers/forms.py, queries.py, and utils.py for clean separation.
# • Protected by the exact same session + DB role check pattern used everywhere else.
# • All url_for calls use the correct nested blueprint: 'the_gathering.prayers.*'
# • 100% rebuilt entire file — only this script was touched.

from flask import render_template, abort, request, flash, redirect, url_for, session
import pymysql

from ..permissions import gathering_place_required
from . import prayers_bp
from .queries import get_all_prayers, get_prayer, get_prayer_comments, update_prayer_status
from app.models.log import log_change
from .forms import validate_prayer_form, validate_search_filter
from app.utils.comment_moderation import handle_manager_comments_post
from .utils import censor_for_manager

from app.models.db import get_db
from app.utils.helpers import censor_text


# ----------------------------------------------------------------------
# Prayers Listing / Dashboard
# ----------------------------------------------------------------------
@prayers_bp.route('/')
@gathering_place_required
def prayers_dashboard():
    """Main prayers management page with search + filters."""
    clean = validate_search_filter(request.args)
    filter_type = clean.get('filter', 'all')
    search = clean.get('search')

    prayers = get_all_prayers(filter_type=filter_type, search_query=search)
    prayers = censor_for_manager(prayers)

    return render_template('the_gathering/prayers/prayers_dashboard.html',
                           prayers=prayers,
                           filter_type=filter_type,
                           search=search or '',
                           page_title="Prayers Manager")


# ----------------------------------------------------------------------
# Create / Edit Prayer
# ----------------------------------------------------------------------
@prayers_bp.route('/new', methods=['GET', 'POST'])
@prayers_bp.route('/<int:prayer_id>/edit', methods=['GET', 'POST'])
@gathering_place_required
def edit_prayer(prayer_id=None):
    """Create new or edit existing prayer."""
    if request.method == 'POST':
        clean = validate_prayer_form(request.form)
        if not clean:
            return redirect(url_for('the_gathering.prayers.edit_prayer', prayer_id=prayer_id))

        db = get_db()
        cur = db.cursor()

        try:
            if prayer_id:  # UPDATE
                cur.execute("""
                    UPDATE prayers 
                    SET title=%s, description=%s, visibility=%s, updated_by=%s
                    WHERE id = %s
                """, (clean['title'], clean['prayer_text'], clean['visibility'],
                      session['user_id'], prayer_id))
                flash('Prayer updated successfully.', 'success')
            else:  # INSERT
                cur.execute("""
                    INSERT INTO prayers 
                    (title, description, visibility, user_id, created_by, status)
                    VALUES (%s, %s, %s, %s, %s, 'approved')
                """, (clean['title'], clean['prayer_text'], clean['visibility'],
                      session['user_id'], session['user_id']))
                flash('Prayer created successfully.', 'success')
            db.commit()
        except Exception:
            db.rollback()
            flash('Failed to save prayer.', 'error')

        return redirect(url_for('the_gathering.prayers.prayers_dashboard'))

    # GET - load existing or blank form
    prayer = get_prayer(prayer_id) if prayer_id else None
    return render_template('the_gathering/prayers/edit.html',
                           prayer=prayer,
                           page_title="Edit Prayer" if prayer_id else "Create New Prayer")


# ----------------------------------------------------------------------
# View Single Prayer
# ----------------------------------------------------------------------
@prayers_bp.route('/<int:prayer_id>/view')
@gathering_place_required
def view_prayer(prayer_id):
    """Read-only view of a single prayer."""
    prayer = get_prayer(prayer_id)
    if not prayer:
        abort(404)

    return render_template('the_gathering/prayers/view.html',
                           prayer=prayer,
                           comment_count=prayer.get('comment_count', 0),
                           page_title="View Prayer")


# ----------------------------------------------------------------------
# Delete Prayer
# ----------------------------------------------------------------------
@prayers_bp.route('/<int:prayer_id>/delete', methods=['POST'])
@gathering_place_required
def delete_prayer(prayer_id):
    """Delete prayer (with confirmation in template)."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM prayers WHERE id = %s", (prayer_id,))
        db.commit()
        flash('Prayer deleted permanently.', 'success')
    except Exception:
        flash('Failed to delete prayer.', 'error')
    return redirect(url_for('the_gathering.prayers.prayers_dashboard'))


# ----------------------------------------------------------------------
# Comment Moderation for a Prayer
# ----------------------------------------------------------------------
@prayers_bp.route('/<int:prayer_id>/comments.html', methods=['GET', 'POST'])
@gathering_place_required
def prayer_comments(prayer_id):
    """Moderate responses on a specific prayer."""
    prayer = get_prayer(prayer_id)
    if not prayer:
        abort(404)

    search = request.args.get('search', '').strip() or None
    status_filter = request.args.get('filter', 'all')

    if request.method == 'POST':
        if handle_manager_comments_post('prayer', prayer_id, session['user_id'], request.form):
            return redirect(url_for('the_gathering.prayers.prayer_comments', prayer_id=prayer_id,
                                    search=search or '', filter=status_filter))

    comments = get_prayer_comments(prayer_id, search=search, status_filter=status_filter)

    return render_template('the_gathering/partials/comments_moderation.html',
                           parent_id=prayer_id,
                           parent_title=prayer.get('title'),
                           section_label='Prayer Responses',
                           comments_url=url_for('the_gathering.prayers.prayer_comments', prayer_id=prayer_id),
                           item_view_url=url_for('the_gathering.prayers.view_prayer', prayer_id=prayer_id),
                           public_url=url_for('public.public_prayers.public_prayer_detail', prayer_id=prayer_id),
                           comments=comments,
                           search=search or '',
                           filter=status_filter)


@prayers_bp.route('/<int:prayer_id>/approve', methods=['POST'])
@gathering_place_required
def approve_prayer(prayer_id):
    """Approve a visitor-submitted prayer so it appears publicly."""
    try:
        update_prayer_status(prayer_id, 'approved')
        log_change(session['user_id'], 'approve_prayer', target_id=prayer_id,
                   change_details='Approved prayer via Gathering Place Manager')
        flash('Prayer approved and is now visible.', 'success')
    except Exception:
        flash('Failed to approve prayer.', 'error')
    return redirect(request.referrer or url_for('the_gathering.prayers.prayers_dashboard'))


@prayers_bp.route('/<int:prayer_id>/reject', methods=['POST'])
@gathering_place_required
def reject_prayer(prayer_id):
    """Reject a visitor-submitted prayer."""
    try:
        update_prayer_status(prayer_id, 'rejected')
        log_change(session['user_id'], 'reject_prayer', target_id=prayer_id,
                   change_details='Rejected prayer via Gathering Place Manager')
        flash('Prayer rejected.', 'success')
    except Exception:
        flash('Failed to reject prayer.', 'error')
    return redirect(request.referrer or url_for('the_gathering.prayers.prayers_dashboard'))


print("✅ MYVINECHURCH.ONLINE the_gathering/prayers/views.py loaded successfully (full dedicated routes for prayers ready)")