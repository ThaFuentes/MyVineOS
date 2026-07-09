# app/routes/pastoral/podium.py
# Full path: WebChurchMan/app/routes/pastoral/podium.py
# File name: podium.py
# Brief, detailed purpose:
#   Blueprint for Podium / Teleprompter mode within the Pastoral Area.
#   Provides:
#     - /podium/ → sermon selection list (today's linked sermon highlighted at top)
#     - /podium/view/<sermon_id> → full-screen teleprompter for selected sermon
#   Features:
#     - Large readable text with user-saved font size (localStorage)
#     - Teleprompter controls: play/pause, speed, timer, reset, fullscreen
#     - Toggle preacher notes
#     - All sections displayed (title, scripture, content, notes)
#     - Audit log access to podium mode
#   All routes require @pastoral_required()
#   Delegates DB work to sermons and service_plans models
#   FIXED: render_template with 'pastoral/' prefix to match blueprint template_folder

from flask import Blueprint, render_template, session, abort
from datetime import datetime
from app.models.db import get_db
from app.models.pastoral.sermons import get_sermon_by_id, get_sermon_sections
from app.models.pastoral.service_plans import get_service_plan_by_date
from app.models.log import log_change
import pymysql  # For DictCursor

from . import pastoral_required

podium_bp = Blueprint('podium', __name__, url_prefix='/podium', template_folder='templates/pastoral')


@podium_bp.route('/')
@pastoral_required()
def index():
    """Sermon selection list for Podium Mode – today's linked sermon highlighted at top."""
    user_id = session['user_id']
    today_str = datetime.today().strftime('%A, %B %d, %Y')
    today_date_str = datetime.today().strftime('%Y-%m-%d')

    plan = get_service_plan_by_date(today_date_str)
    today_sermon = None
    today_plan = None
    if plan and plan.get('pastoral_sermon_id'):
        today_sermon = get_sermon_by_id(plan['pastoral_sermon_id'], user_id)
        today_plan = plan

    # Get all sermons (newest first)
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT ps.*, sp.service_date AS associated_date, sp.title AS plan_title
        FROM pastoral_sermons ps
        LEFT JOIN service_plans sp ON ps.service_date = sp.service_date
        ORDER BY ps.created_at DESC
    """)
    sermons = cur.fetchall()

    log_change(user_id, 'podium_access', None, 'Sermon Selection List', 'Accessed podium sermon list')

    return render_template(
        'pastoral/podium_list.html',  # FIXED: Added 'pastoral/' prefix
        sermons=sermons,
        today_sermon=today_sermon,
        today_plan=today_plan,
        today_str=today_str
    )


@podium_bp.route('/view/<int:sermon_id>')
@pastoral_required()
def view(sermon_id: int):
    """Full-screen podium mode for selected sermon."""
    user_id = session['user_id']

    sermon = get_sermon_by_id(sermon_id, user_id)
    if not sermon:
        abort(404)

    sections = get_sermon_sections(sermon_id)

    log_change(user_id, 'podium_access', sermon_id, sermon['title'], 'Accessed podium mode for sermon')

    return render_template(
        'pastoral/podium_view.html',  # FIXED: Added 'pastoral/' prefix
        sermon=sermon,
        sections=sections
    )