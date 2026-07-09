# app/utils/welcome_page.py
# Shared guest welcome page renderer used by /public/ and /index.

from datetime import date, datetime

from flask import render_template

from app.routes.auth.queries import get_welcome_overview
from app.utils.time_utils import format_church


def _coerce_event_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], '%Y-%m-%d')
        except ValueError:
            return None
    return None


def render_welcome_page():
    """Render the guest welcome overview with church info, events, and schedule."""
    overview = get_welcome_overview()
    for event in overview['upcoming_events']:
        dt = _coerce_event_date(event.get('event_date'))
        if dt:
            event['formatted_date'] = format_church(dt, '%B %d, %Y')
            if event.get('event_time'):
                event['formatted_time'] = str(event['event_time'])[:5]
            else:
                event['formatted_time'] = ''
        else:
            event['formatted_date'] = 'Date TBD'
            event['formatted_time'] = ''
    return render_template(
        'auth/index.html',
        upcoming_events=overview['upcoming_events'],
        upcoming_services=overview['upcoming_services'],
    )