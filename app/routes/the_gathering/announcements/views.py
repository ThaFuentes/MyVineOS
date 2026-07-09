# MYVINECHURCH.ONLINE/app/routes/the_gathering/announcements/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/announcements/views.py
# File name: views.py
# Brief, detailed purpose: All announcement routes for the Gathering Place Manager.
# • Dedicated sub-blueprint routes: listing, create/edit, view, delete, comment moderation.
# • Uses announcements/forms.py, queries.py, and utils.py for clean separation.
# • Protected by the exact same session + DB role check pattern used everywhere else.
# • All url_for calls use the correct nested blueprint: 'the_gathering.announcements.*'
# • 100% rebuilt entire file — only this script was touched.

from flask import render_template, abort, request, flash, redirect, url_for, session
import pymysql

from ..permissions import gathering_place_required
from . import announcements_bp
from .queries import get_all_announcements, get_announcement, get_announcement_comments
from .forms import validate_announcement_form, validate_search_filter
from app.utils.comment_moderation import handle_manager_comments_post
from .utils import censor_for_manager, prepare_audit_log

from app.models.db import get_db
from app.utils.helpers import censor_text


# ----------------------------------------------------------------------
# Announcements Listing / Dashboard
# ----------------------------------------------------------------------
@announcements_bp.route('/')
@gathering_place_required
def announcements_dashboard():
    """Main announcements management page with search + filters."""
    clean = validate_search_filter(request.args)
    filter_type = clean.get('filter', 'all')
    search = clean.get('search')

    announcements = get_all_announcements(filter_type=filter_type, search_query=search)
    announcements = censor_for_manager(announcements)

    return render_template('the_gathering/announcements/announcements_dashboard.html',
                           announcements=announcements,
                           filter_type=filter_type,
                           search=search or '',
                           page_title="Announcements Manager")


# ----------------------------------------------------------------------
# Create / Edit Announcement
# ----------------------------------------------------------------------
@announcements_bp.route('/<int:announcement_id>/edit', methods=['GET', 'POST'])
@announcements_bp.route('/new', methods=['GET', 'POST'], defaults={'announcement_id': None})
@gathering_place_required
def edit_announcement(announcement_id):
    """Create new or edit existing announcement."""
    if request.method == 'POST':
        clean = validate_announcement_form(request.form)
        if not clean:
            return redirect(url_for('the_gathering.announcements.edit_announcement', announcement_id=announcement_id))

        db = get_db()
        cur = db.cursor()

        try:
            if announcement_id:  # UPDATE
                cur.execute("""
                    UPDATE announcements 
                    SET title=%s, content=%s, visibility=%s, is_pinned=%s, 
                        expiration_date=%s, is_active=1, is_archived=0, updated_by=%s, updated_at=NOW()
                    WHERE id = %s
                """, (clean['title'], clean['content'], clean['visibility'],
                      int(clean['is_pinned']), clean['expiration_date'],
                      session['user_id'], announcement_id))
                flash('Announcement updated successfully.', 'success')
            else:  # INSERT
                cur.execute("""
                    INSERT INTO announcements 
                    (title, content, visibility, is_pinned, expiration_date, is_active, is_archived, created_by, updated_by)
                    VALUES (%s, %s, %s, %s, %s, 1, 0, %s, %s)
                """, (clean['title'], clean['content'], clean['visibility'],
                      int(clean['is_pinned']), clean['expiration_date'],
                      session['user_id'], session['user_id']))
                flash('Announcement created successfully.', 'success')
            db.commit()
        except Exception as e:
            db.rollback()
            flash('Failed to save announcement.', 'error')

        return redirect(url_for('the_gathering.announcements.announcements_dashboard'))

    # GET - load existing or blank form
    announcement = get_announcement(announcement_id) if announcement_id else None
    return render_template('the_gathering/announcements/edit.html',
                           announcement=announcement,
                           page_title="Edit Announcement" if announcement_id else "New Announcement")


# ----------------------------------------------------------------------
# View Single Announcement
# ----------------------------------------------------------------------
@announcements_bp.route('/<int:announcement_id>/view')
@gathering_place_required
def view_announcement(announcement_id):
    """Read-only view of a single announcement."""
    announcement = get_announcement(announcement_id)
    if not announcement:
        abort(404)

    return render_template('the_gathering/announcements/view.html',
                           announcement=announcement,
                           comment_count=announcement.get('comment_count', 0),
                           page_title="View Announcement")


# ----------------------------------------------------------------------
# Delete Announcement
# ----------------------------------------------------------------------
@announcements_bp.route('/<int:announcement_id>/delete', methods=['POST'])
@gathering_place_required
def delete_announcement(announcement_id):
    """Delete announcement (with confirmation in template)."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM announcements WHERE id = %s", (announcement_id,))
        db.commit()
        flash('Announcement deleted permanently.', 'success')
    except Exception:
        flash('Failed to delete announcement.', 'error')
    return redirect(url_for('the_gathering.announcements.announcements_dashboard'))


# ----------------------------------------------------------------------
# Comment Moderation for Announcements
# ----------------------------------------------------------------------
@announcements_bp.route('/<int:announcement_id>/comments.html', methods=['GET', 'POST'])
@gathering_place_required
def announcement_comments(announcement_id):
    """Moderate comments on a specific announcement."""
    announcement = get_announcement(announcement_id)
    if not announcement:
        abort(404)

    search = request.args.get('search', '').strip() or None
    status_filter = request.args.get('filter', 'all')

    if request.method == 'POST':
        if handle_manager_comments_post('announcement', announcement_id, session['user_id'], request.form):
            return redirect(url_for('the_gathering.announcements.announcement_comments',
                                    announcement_id=announcement_id,
                                    search=search or '', filter=status_filter))

    comments = get_announcement_comments(announcement_id, search=search, status_filter=status_filter)

    return render_template('the_gathering/partials/comments_moderation.html',
                           parent_id=announcement_id,
                           parent_title=announcement.get('title'),
                           section_label='Announcement Comments',
                           comments_url=url_for('the_gathering.announcements.announcement_comments',
                                              announcement_id=announcement_id),
                           item_view_url=url_for('the_gathering.announcements.view_announcement', announcement_id=announcement_id),
                           public_url=url_for('public.public_announcements.public_announcement_detail',
                                              ann_id=announcement_id),
                           comments=comments,
                           search=search or '',
                           filter=status_filter)


print("✅ MYVINECHURCH.ONLINE the_gathering/announcements/views.py loaded successfully (full dedicated routes for announcements ready)")