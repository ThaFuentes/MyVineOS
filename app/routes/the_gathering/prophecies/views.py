# MYVINECHURCH.ONLINE/app/routes/the_gathering/prophecies/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/prophecies/views.py
# File name: views.py
# Brief, detailed purpose: All prophecy routes for the Gathering Place Manager.
# • Dedicated sub-blueprint routes: listing, create/edit, view, delete, comment moderation.
# • Uses prophecies/forms.py, queries.py, and utils.py for clean separation.
# • Protected by the exact same session + DB role check pattern used everywhere else.
# • All url_for calls use the correct nested blueprint: 'the_gathering.prophecies.*'
# • 100% rebuilt entire file — only this script was touched.

from flask import render_template, abort, request, flash, redirect, url_for, session
import pymysql

from ..permissions import gathering_place_required
from . import prophecies_bp
from .queries import get_all_prophecies, get_prophecy, get_prophecy_comments
from .forms import validate_prophecy_form, validate_search_filter
from app.utils.comment_moderation import handle_manager_comments_post
from .utils import censor_for_manager

from app.models.db import get_db
from app.utils.helpers import censor_text


# ----------------------------------------------------------------------
# Prophecies Listing / Dashboard
# ----------------------------------------------------------------------
@prophecies_bp.route('/')
@gathering_place_required
def prophecies_dashboard():
    """Main prophecies management page with search + filters."""
    clean = validate_search_filter(request.args)
    filter_type = clean.get('filter', 'all')
    search = clean.get('search')

    prophecies = get_all_prophecies(filter_type=filter_type, search_query=search)
    prophecies = censor_for_manager(prophecies)

    return render_template('the_gathering/prophecies/prophecies_dashboard.html',
                           prophecies=prophecies,
                           filter_type=filter_type,
                           search=search or '',
                           page_title="Prophecies Manager")


# ----------------------------------------------------------------------
# Create / Edit Prophecy
# ----------------------------------------------------------------------
@prophecies_bp.route('/new', methods=['GET', 'POST'])
@prophecies_bp.route('/<int:prophecy_id>/edit', methods=['GET', 'POST'])
@gathering_place_required
def edit_prophecy(prophecy_id=None):
    """Create new or edit existing prophecy."""
    if request.method == 'POST':
        clean = validate_prophecy_form(request.form)
        if not clean:
            return redirect(url_for('the_gathering.prophecies.edit_prophecy', prophecy_id=prophecy_id))

        db = get_db()
        cur = db.cursor()

        try:
            if prophecy_id:  # UPDATE
                cur.execute("""
                    UPDATE prophecies 
                    SET title=%s, prophecy_text=%s, visibility=%s, 
                        updated_by=%s, updated_at=NOW()
                    WHERE id = %s
                """, (clean['title'], clean['prophecy_text'], clean['visibility'],
                      session['user_id'], prophecy_id))
                flash('Prophecy updated successfully.', 'success')
            else:  # INSERT
                cur.execute("""
                    INSERT INTO prophecies 
                    (title, prophecy_text, visibility, created_by, updated_by)
                    VALUES (%s, %s, %s, %s, %s)
                """, (clean['title'], clean['prophecy_text'], clean['visibility'],
                      session['user_id'], session['user_id']))
                flash('Prophecy created successfully.', 'success')
            db.commit()
        except Exception:
            db.rollback()
            flash('Failed to save prophecy.', 'error')

        return redirect(url_for('the_gathering.prophecies.prophecies_dashboard'))

    # GET - load existing or blank form
    prophecy = get_prophecy(prophecy_id) if prophecy_id else None
    return render_template('the_gathering/prophecies/edit.html',
                           prophecy=prophecy,
                           page_title="Edit Prophecy" if prophecy_id else "Create New Prophecy")


# ----------------------------------------------------------------------
# View Single Prophecy
# ----------------------------------------------------------------------
@prophecies_bp.route('/<int:prophecy_id>/view')
@gathering_place_required
def view_prophecy(prophecy_id):
    """Read-only view of a single prophecy."""
    prophecy = get_prophecy(prophecy_id)
    if not prophecy:
        abort(404)

    return render_template('the_gathering/prophecies/view.html',
                           prophecy=prophecy,
                           comment_count=prophecy.get('comment_count', 0),
                           page_title="View Prophecy")


# ----------------------------------------------------------------------
# Delete Prophecy
# ----------------------------------------------------------------------
@prophecies_bp.route('/<int:prophecy_id>/delete', methods=['POST'])
@gathering_place_required
def delete_prophecy(prophecy_id):
    """Delete prophecy (with confirmation in template)."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM prophecies WHERE id = %s", (prophecy_id,))
        db.commit()
        flash('Prophecy deleted permanently.', 'success')
    except Exception:
        flash('Failed to delete prophecy.', 'error')
    return redirect(url_for('the_gathering.prophecies.prophecies_dashboard'))


# ----------------------------------------------------------------------
# Comment Moderation for a Prophecy
# ----------------------------------------------------------------------
@prophecies_bp.route('/<int:prophecy_id>/comments.html', methods=['GET', 'POST'])
@gathering_place_required
def prophecy_comments(prophecy_id):
    """Moderate comments on a specific prophecy."""
    prophecy = get_prophecy(prophecy_id)
    if not prophecy:
        abort(404)

    search = request.args.get('search', '').strip() or None
    status_filter = request.args.get('filter', 'all')

    if request.method == 'POST':
        if handle_manager_comments_post('prophecy', prophecy_id, session['user_id'], request.form):
            return redirect(url_for('the_gathering.prophecies.prophecy_comments', prophecy_id=prophecy_id,
                                    search=search or '', filter=status_filter))

    comments = get_prophecy_comments(prophecy_id, search=search, status_filter=status_filter)

    return render_template('the_gathering/partials/comments_moderation.html',
                           parent_id=prophecy_id,
                           parent_title=prophecy.get('title'),
                           section_label='Prophecy Comments',
                           comments_url=url_for('the_gathering.prophecies.prophecy_comments', prophecy_id=prophecy_id),
                           item_view_url=url_for('the_gathering.prophecies.view_prophecy', prophecy_id=prophecy_id),
                           public_url=url_for('public.public_prophecies.public_prophecy_detail', prophecy_id=prophecy_id),
                           comments=comments,
                           search=search or '',
                           filter=status_filter)


# print("✅ MYVINECHURCH.ONLINE the_gathering/prophecies/views.py loaded successfully (full dedicated routes for prophecies ready)")