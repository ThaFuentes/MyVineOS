# app/routes/events/events_dashboard.py
# Full path: MyVineChurch/app/routes/events/events_dashboard.py
# File name: events_dashboard.py
# Brief, detailed purpose: Private Events Dashboard (/events) - login required.
# Shows ALL events (public + private) for logged-in users only.
# Full summary cards, filters, Add Event button (for authorized roles).
# Renders events/events_dashboard.html with private context.
# Public users are redirected to login (we'll add separate public route next).

from flask import render_template, session, redirect, url_for
from app.utils.decorators import login_required
from app.models.db import get_db
from app.utils.time_utils import now_church
from datetime import datetime
import pymysql

def register_dashboard_routes(bp):
    @bp.route('/')
    @login_required  # Private dashboard - forces login
    def events():
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        # Always show ALL events for logged-in users
        cur.execute("""
            SELECT * FROM events
            ORDER BY event_date DESC, event_time DESC
        """)
        events_list = cur.fetchall()
        cur.close()

        today_local = now_church().date()

        total_count = len(events_list)
        upcoming_count = 0
        potluck_count = 0

        for e in events_list:
            # Safe date formatting (MariaDB may return date objects or strings)
            e['nice_date'] = e['event_date'] or 'No date'
            raw_d = e.get('event_date')
            if raw_d:
                try:
                    if hasattr(raw_d, 'strftime') and not isinstance(raw_d, str):
                        date_obj = raw_d if hasattr(raw_d, 'year') and not hasattr(raw_d, 'hour') else raw_d.date() if hasattr(raw_d, 'date') else raw_d
                        # normalize datetime -> date
                        from datetime import date as date_cls
                        if isinstance(raw_d, datetime):
                            date_obj = raw_d.date()
                        elif isinstance(raw_d, date_cls):
                            date_obj = raw_d
                        else:
                            date_obj = datetime.strptime(str(raw_d)[:10], '%Y-%m-%d').date()
                    else:
                        date_obj = datetime.strptime(str(raw_d)[:10], '%Y-%m-%d').date()
                    e['event_date_obj'] = date_obj
                    e['nice_date'] = date_obj.strftime('%A, %B %d, %Y')
                    if date_obj >= today_local:
                        upcoming_count += 1
                except (ValueError, TypeError, AttributeError):
                    e['nice_date'] = str(raw_d)

            if e.get('potluck_enabled'):
                potluck_count += 1

        return render_template(
            'events/events_dashboard.html',
            events=events_list,
            total_count=total_count,
            upcoming_count=upcoming_count,
            potluck_count=potluck_count,
            is_logged_in=True  # Force private view message
        )