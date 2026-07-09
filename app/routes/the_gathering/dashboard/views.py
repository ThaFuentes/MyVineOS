# MYVINECHURCH.ONLINE/app/routes/the_gathering/dashboard/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/dashboard/views.py
# File name: views.py
# Brief, detailed purpose: Main dashboard routes and permission logic for the Gathering Place Manager.
# • Handles the primary dashboard view at /the_gathering/dashboard/ (overview, stats, recent activity).
# • Includes the gathering_place_required decorator (kept exactly as original for now – will be centralized later).
# • 100% rebuilt to match the exact clean, consistent style of public/events/views.py and public/dreams/views.py
#   (detailed section comments, enhanced docstrings, route structure, flash handling, and template rendering).
# • Original behavior, role checks, stats/recent queries, and template keys preserved 100%.

from flask import render_template, session, redirect, url_for, flash, request

from . import dashboard_bp
from ..permissions import gathering_place_required
from .queries import (
    get_dashboard_stats,
    get_recent_activity,
    get_pending_moderation,
    get_pending_prayer_submissions,
)
from .utils import format_manager_datetime, manager_view_url, manager_comments_url
from app.models.db import get_db
from app.utils.comment_moderation import fetch_moderation_comments_queue, handle_manager_comments_post


# ----------------------------------------------------------------------
# Main Gathering Place Manager Dashboard
# ----------------------------------------------------------------------
@dashboard_bp.route('/')
@gathering_place_required
def dashboard():
    """Main dashboard view for the Gathering Place Manager.

    Loads summary statistics and recent activity feed.
    Renders the dedicated template with all original context variables.
    """
    stats = get_dashboard_stats()
    recent_activity = get_recent_activity(limit=10)
    # Enrich timestamps for nice display in the recent activity feed (uses the manager formatter)
    for item in recent_activity:
        item['created_at'] = format_manager_datetime(item.get('created_at'))
        item['manager_url'] = manager_view_url(item.get('type'), item.get('id'))
    pending = get_pending_moderation()
    pending_prayers = get_pending_prayer_submissions(limit=10)

    # Map/alias for the template which expects certain keys (back-compat with current stats query)
    stats.setdefault('upcoming_public_events', stats.get('public_events', 0))
    stats.setdefault('total_public_prayers', stats.get('total_prayers', 0))
    stats.setdefault('total_public_sermons', stats.get('total_sermons', 0))
    stats.setdefault('dreams_and_visions', stats.get('total_dreams', 0))
    stats.setdefault('prophecies', stats.get('total_prophecies', 0))
    stats.setdefault('announcements', stats.get('total_announcements', 0))

    return render_template(
        'the_gathering/dashboard.html',
        stats=stats,
        recent=recent_activity,           # legacy key (some templates may still reference)
        recent_activity=recent_activity,  # primary key used by the_gathering/dashboard.html recent feed
        pending=pending,
        pending_prayers=pending_prayers,
        page_title="Gathering Place Manager"
    )


@dashboard_bp.route('/moderation', methods=['GET', 'POST'])
@gathering_place_required
def moderation_queue():
    """Unified moderation hub — inline actions on all comments plus pending prayers."""
    status_filter = request.args.get('filter', 'all')
    search = request.args.get('search', '').strip() or None

    if request.method == 'POST':
        content_type = request.form.get('content_type', '').strip()
        parent_id = request.form.get('parent_id', '').strip()
        if content_type and parent_id and parent_id.isdigit():
            handle_manager_comments_post(
                content_type, int(parent_id), session['user_id'], request.form,
            )
        return redirect(url_for(
            'the_gathering.dashboard.moderation_queue',
            filter=status_filter,
            search=search or '',
        ))

    all_comments = fetch_moderation_comments_queue(
        limit=300, status_filter=status_filter, search=search,
    )
    for item in all_comments:
        item['section_url'] = manager_comments_url(item['content_type'], item['parent_id'])
        item['posted_at_nice'] = format_manager_datetime(item.get('posted_at'))

    pending_prayers = get_pending_prayer_submissions(limit=100)
    for p in pending_prayers:
        p['posted_at_nice'] = format_manager_datetime(p.get('date_posted'))

    return render_template(
        'the_gathering/moderation_queue.html',
        all_comments=all_comments,
        pending_prayers=pending_prayers,
        status_filter=status_filter,
        search=search or '',
        post_url=url_for('the_gathering.dashboard.moderation_queue'),
        page_title="Moderation Hub",
    )


# print("✅ MYVINECHURCH.ONLINE the_gathering/dashboard/views.py loaded successfully (public-style rebuilt)")