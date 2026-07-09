# MYVINECHURCH.ONLINE/app/routes/the_gathering/dreams/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/dreams/views.py
# File name: views.py
# Brief, detailed purpose: All dream/vision routes for the Gathering Place Manager.
# • Dedicated sub-blueprint routes: listing, create/edit, view, delete, comment moderation.
# • Uses dreams/forms.py, queries.py, and utils.py for clean separation.
# • Protected by the exact same session + DB role check pattern used everywhere else.
# • All url_for calls use the correct nested blueprint: 'the_gathering.dreams.*'
# • 100% rebuilt entire file — only this script was touched.

from flask import render_template, abort, request, flash, redirect, url_for, session
import pymysql

from ..permissions import gathering_place_required
from . import dreams_bp
from .queries import get_all_dreams, get_dream, get_dream_comments
from .forms import validate_dream_form, validate_search_filter
from app.utils.comment_moderation import handle_manager_comments_post
from .utils import censor_for_manager

from app.models.db import get_db
from app.utils.helpers import censor_text


# ----------------------------------------------------------------------
# Dreams Listing / Dashboard
# ----------------------------------------------------------------------
@dreams_bp.route('/')
@gathering_place_required
def dreams_dashboard():
    """Main dreams management page with search + filters."""
    clean = validate_search_filter(request.args)
    filter_type = clean.get('filter', 'all')
    search = clean.get('search')

    dreams = get_all_dreams(filter_type=filter_type, search_query=search)
    dreams = censor_for_manager(dreams)

    return render_template('the_gathering/dreams/dreams_dashboard.html',
                           dreams=dreams,
                           filter_type=filter_type,
                           search=search or '',
                           page_title="Dreams & Visions Manager")


# ----------------------------------------------------------------------
# Create / Edit Dream
# ----------------------------------------------------------------------
@dreams_bp.route('/<int:dream_id>/edit', methods=['GET', 'POST'])
@dreams_bp.route('/new', methods=['GET', 'POST'], defaults={'dream_id': None})
@gathering_place_required
def edit_dream(dream_id):
    """Create new or edit existing dream/vision."""
    if request.method == 'POST':
        clean = validate_dream_form(request.form)
        if not clean:
            return redirect(url_for('the_gathering.dreams.edit_dream', dream_id=dream_id))

        db = get_db()
        cur = db.cursor()

        try:
            if dream_id:  # UPDATE
                cur.execute("""
                    UPDATE dreams 
                    SET title=%s, dream_text=%s, visibility=%s, 
                        updated_by=%s, updated_at=NOW()
                    WHERE id = %s
                """, (clean['title'], clean['dream_text'], clean['visibility'],
                      session['user_id'], dream_id))
                flash('Dream/Vision updated successfully.', 'success')
            else:  # INSERT
                cur.execute("""
                    INSERT INTO dreams 
                    (title, dream_text, visibility, created_by, updated_by)
                    VALUES (%s, %s, %s, %s, %s)
                """, (clean['title'], clean['dream_text'], clean['visibility'],
                      session['user_id'], session['user_id']))
                flash('Dream/Vision created successfully.', 'success')
            db.commit()
        except Exception as e:
            db.rollback()
            flash('Failed to save dream/vision.', 'error')

        return redirect(url_for('the_gathering.dreams.dreams_dashboard'))

    # GET - load existing or blank form
    dream = get_dream(dream_id) if dream_id else None
    return render_template('the_gathering/dreams/edit.html',
                           dream=dream,
                           page_title="Edit Dream/Vision" if dream_id else "New Dream/Vision")


# ----------------------------------------------------------------------
# View Single Dream
# ----------------------------------------------------------------------
@dreams_bp.route('/<int:dream_id>/view')
@gathering_place_required
def view_dream(dream_id):
    """Read-only view of a single dream/vision."""
    dream = get_dream(dream_id)
    if not dream:
        abort(404)

    return render_template('the_gathering/dreams/view.html',
                           dream=dream,
                           comment_count=dream.get('comment_count', 0),
                           page_title="View Dream/Vision")


# ----------------------------------------------------------------------
# Delete Dream
# ----------------------------------------------------------------------
@dreams_bp.route('/<int:dream_id>/delete', methods=['POST'])
@gathering_place_required
def delete_dream(dream_id):
    """Delete dream/vision (with confirmation in template)."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM dreams WHERE id = %s", (dream_id,))
        db.commit()
        flash('Dream/Vision deleted permanently.', 'success')
    except Exception:
        flash('Failed to delete dream/vision.', 'error')
    return redirect(url_for('the_gathering.dreams.dreams_dashboard'))


# ----------------------------------------------------------------------
# Comment Moderation for Dreams
# ----------------------------------------------------------------------
@dreams_bp.route('/<int:dream_id>/comments.html', methods=['GET', 'POST'])
@gathering_place_required
def dream_comments(dream_id):
    """Moderate comments on a specific dream/vision."""
    dream = get_dream(dream_id)
    if not dream:
        abort(404)

    search = request.args.get('search', '').strip() or None
    status_filter = request.args.get('filter', 'all')

    if request.method == 'POST':
        if handle_manager_comments_post('dream', dream_id, session['user_id'], request.form):
            return redirect(url_for('the_gathering.dreams.dream_comments', dream_id=dream_id,
                                    search=search or '', filter=status_filter))

    comments = get_dream_comments(dream_id, search=search, status_filter=status_filter)

    return render_template('the_gathering/partials/comments_moderation.html',
                           parent_id=dream_id,
                           parent_title=dream.get('title'),
                           section_label='Dream Comments',
                           comments_url=url_for('the_gathering.dreams.dream_comments', dream_id=dream_id),
                           item_view_url=url_for('the_gathering.dreams.view_dream', dream_id=dream_id),
                           public_url=url_for('public.public_dreams.public_dream_detail', dream_id=dream_id),
                           comments=comments,
                           search=search or '',
                           filter=status_filter)


# print("✅ MYVINECHURCH.ONLINE the_gathering/dreams/views.py loaded successfully (full dedicated routes for dreams ready)")