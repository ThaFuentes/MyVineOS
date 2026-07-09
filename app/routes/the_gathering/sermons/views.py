# MYVINECHURCH.ONLINE/app/routes/the_gathering/sermons/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/sermons/views.py
# File name: views.py
# Brief, detailed purpose: All sermon routes for the Gathering Place Manager.
# - Dedicated sub-blueprint routes: listing, create/edit, view, delete, comment moderation.
# - Uses sermons/forms.py, queries.py, and utils.py for clean separation.
# - Protected by the exact same session + DB role check pattern used everywhere else.
# - All url_for calls use the correct nested blueprint: 'the_gathering.sermons.*'
# - 100% rebuilt entire file — only this script was touched.

from flask import render_template, abort, request, flash, redirect, url_for, session
import pymysql

from ..permissions import gathering_place_required
from . import sermons_bp
from .queries import get_all_sermons, get_sermon, get_sermon_comments
from .forms import validate_sermon_form, validate_search_filter
from app.utils.comment_moderation import handle_manager_comments_post
from .utils import censor_for_manager

from app.models.db import get_db
from app.utils.helpers import censor_text


# ----------------------------------------------------------------------
# Sermons Listing / Dashboard
# ----------------------------------------------------------------------
@sermons_bp.route('/')
@gathering_place_required
def sermons_dashboard():
    """Main sermons management page with search + filters."""
    clean = validate_search_filter(request.args)
    filter_type = clean.get('filter', 'all')
    search = clean.get('search')

    sermons = get_all_sermons(filter_type=filter_type, search_query=search)
    sermons = censor_for_manager(sermons)

    return render_template('the_gathering/sermons/sermons_dashboard.html',
                           sermons=sermons,
                           filter_type=filter_type,
                           search=search or '',
                           page_title="Sermons Manager")


# ----------------------------------------------------------------------
# Create / Edit Sermon
# ----------------------------------------------------------------------
@sermons_bp.route('/new', methods=['GET', 'POST'])
@sermons_bp.route('/<int:sermon_id>/edit', methods=['GET', 'POST'])
@gathering_place_required
def edit_sermon(sermon_id=None):
    """Create new or edit existing sermon."""
    if request.method == 'POST':
        clean = validate_sermon_form(request.form)
        if not clean:
            return redirect(url_for('the_gathering.sermons.edit_sermon', sermon_id=sermon_id))

        db = get_db()
        cur = db.cursor()

        try:
            if sermon_id:  # UPDATE
                cur.execute("""
                    UPDATE sermons 
                    SET title=%s, scripture=%s, notes=%s, sermon_text=%s, visibility=%s, 
                        updated_by=%s, updated_at=NOW()
                    WHERE id = %s
                """, (clean['title'], clean['scripture'], clean['notes'],
                      clean['sermon_text'], clean['visibility'],
                      session['user_id'], sermon_id))
                flash('Sermon updated successfully.', 'success')
            else:  # INSERT
                cur.execute("""
                    INSERT INTO sermons 
                    (title, scripture, notes, sermon_text, visibility, created_by, updated_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (clean['title'], clean['scripture'], clean['notes'],
                      clean['sermon_text'], clean['visibility'],
                      session['user_id'], session['user_id']))
                flash('Sermon created successfully.', 'success')
            db.commit()
        except Exception:
            db.rollback()
            flash('Failed to save sermon.', 'error')

        return redirect(url_for('the_gathering.sermons.sermons_dashboard'))

    # GET - load existing or blank form
    sermon = get_sermon(sermon_id) if sermon_id else None
    return render_template('the_gathering/sermons/edit.html',
                           sermon=sermon,
                           page_title="Edit Sermon" if sermon_id else "Create New Sermon")


# ----------------------------------------------------------------------
# View Single Sermon
# ----------------------------------------------------------------------
@sermons_bp.route('/<int:sermon_id>/view')
@gathering_place_required
def view_sermon(sermon_id):
    """Read-only view of a single sermon."""
    sermon = get_sermon(sermon_id)
    if not sermon:
        abort(404)

    return render_template('the_gathering/sermons/view.html',
                           sermon=sermon,
                           comment_count=sermon.get('comment_count', 0),
                           page_title="View Sermon")


# ----------------------------------------------------------------------
# Delete Sermon
# ----------------------------------------------------------------------
@sermons_bp.route('/<int:sermon_id>/delete', methods=['POST'])
@gathering_place_required
def delete_sermon(sermon_id):
    """Delete sermon (with confirmation in template)."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM sermons WHERE id = %s", (sermon_id,))
        db.commit()
        flash('Sermon deleted permanently.', 'success')
    except Exception:
        flash('Failed to delete sermon.', 'error')
    return redirect(url_for('the_gathering.sermons.sermons_dashboard'))


# ----------------------------------------------------------------------
# Comment Moderation for a Sermon
# ----------------------------------------------------------------------
@sermons_bp.route('/<int:sermon_id>/comments.html', methods=['GET', 'POST'])
@gathering_place_required
def sermon_comments(sermon_id):
    """Moderate comments on a specific sermon."""
    sermon = get_sermon(sermon_id)
    if not sermon:
        abort(404)

    search = request.args.get('search', '').strip() or None
    status_filter = request.args.get('filter', 'all')

    if request.method == 'POST':
        if handle_manager_comments_post('sermon', sermon_id, session['user_id'], request.form):
            return redirect(url_for('the_gathering.sermons.sermon_comments', sermon_id=sermon_id,
                                    search=search or '', filter=status_filter))

    comments = get_sermon_comments(sermon_id, search=search, status_filter=status_filter)

    return render_template('the_gathering/partials/comments_moderation.html',
                           parent_id=sermon_id,
                           parent_title=sermon.get('title'),
                           section_label='Sermon Comments',
                           comments_url=url_for('the_gathering.sermons.sermon_comments', sermon_id=sermon_id),
                           item_view_url=url_for('the_gathering.sermons.view_sermon', sermon_id=sermon_id),
                           public_url=url_for('public.public_sermons.public_sermon_detail', sermon_id=sermon_id),
                           comments=comments,
                           search=search or '',
                           filter=status_filter)


# print(" MYVINECHURCH.ONLINE the_gathering/sermons/views.py loaded successfully (full dedicated routes for sermons ready)")