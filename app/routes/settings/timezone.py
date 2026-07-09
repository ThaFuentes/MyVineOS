# app/routes/settings/timezone.py
# Full path: WebChurchMan/app/routes/settings/timezone.py
# File name: timezone.py
# Brief, detailed purpose: Dedicated route for configuring the church's timezone.
# Displays current timezone, allows selection from common IANA zones or free-text entry,
# shows real-time server vs church time preview for debugging offsets.
# Validation: tries ZoneInfo directly (graceful error if invalid or tzdata missing).
# Saves to settings.timezone column (TEXT).
# Protected by admin/owner + granular permission check.
# All changes audit-logged.
# Default: 'America/Chicago' (Central Time - matches church location in Odessa, TX).

from flask import render_template, request, redirect, url_for, flash, session
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import datetime
from app.models.db import get_db
from app.models.log import log_change
from . import settings_bp, has_section_permission, load_settings
from app.utils.time_utils import now_church  # For consistent preview with fallback
import pymysql

# Curated list of common timezones - US-heavy + major global (America/Chicago first after UTC)
COMMON_TIMEZONES = sorted([
    'UTC',
    'America/Chicago',              # Central Time - default for Odessa, TX
    'America/New_York',
    'America/Denver',
    'America/Phoenix',
    'America/Los_Angeles',
    'America/Anchorage',
    'Pacific/Honolulu',
    'America/Toronto',
    'America/Vancouver',
    'Europe/London',
    'Europe/Paris',
    'Europe/Berlin',
    'Asia/Jerusalem',
    'Asia/Tokyo',
    'Australia/Sydney',
    'Africa/Johannesburg',
])

@settings_bp.route('/timezone', methods=['GET', 'POST'])
def timezone():
    if not has_section_permission('timezone'):
        flash('You do not have permission to edit timezone settings.', 'error')
        return redirect(url_for('settings.general'))

    db = get_db()
    user_id = session['user_id']
    cur = db.cursor(pymysql.cursors.DictCursor)

    settings = load_settings()
    current_tz_name = settings.get('timezone') or 'America/Chicago'  # Default Central Time

    # Server time preview
    server_now = datetime.now()
    server_tz_name = str(datetime.now().astimezone().tzinfo) or 'System Local'

    # Church time preview - uses time_utils fallback if zoneinfo/tzdata unavailable
    church_now = now_church()
    church_time_str = church_now.strftime('%Y-%m-%d %H:%M:%S %Z')

    if request.method == 'POST':
        new_tz = request.form.get('timezone', '').strip() or 'America/Chicago'

        # Relaxed validation: try to instantiate ZoneInfo, catch invalid names
        try:
            ZoneInfo(new_tz)
        except ZoneInfoNotFoundError:
            flash(f"'{new_tz}' is not a valid IANA timezone name.", 'error')
            return redirect(url_for('settings.timezone'))

        if new_tz == current_tz_name:
            flash('No change - timezone already set to this value.', 'info')
            return redirect(url_for('settings.timezone'))

        # Save to DB
        cur.execute("UPDATE settings SET timezone = %s WHERE id = 1", (new_tz,))
        db.commit()

        log_change(user_id, 'update', None, None, f"Changed church timezone from '{current_tz_name}' to '{new_tz}'")
        flash(f"Church timezone successfully updated to '{new_tz}'.", 'success')

        # Update for immediate preview
        current_tz_name = new_tz
        church_time_str = now_church().strftime('%Y-%m-%d %H:%M:%S %Z')

    return render_template(
        'settings/timezone.html',
        settings=settings,
        current_tz_name=current_tz_name,
        common_timezones=COMMON_TIMEZONES,
        server_now=server_now.strftime('%Y-%m-%d %H:%M:%S'),
        server_tz_name=server_tz_name,
        church_time_str=church_time_str,
    )